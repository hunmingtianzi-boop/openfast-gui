# -*- coding: utf-8 -*-
"""Local web UI server for editing and running OpenFAST scenarios."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "webui"
SCENARIOS = ROOT / "scenarios"
RUNS = ROOT / "runs"
RUN_SCENARIO = ROOT / "user_tools" / "run_scenario.py"
PYTHON = sys.executable
WORK_C4 = ROOT / "work_c4"
USER_TOOLS = ROOT / "user_tools"
for import_path in [WORK_C4, USER_TOOLS]:
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from driver_c4 import _ensure_hydrodyn_v4  # noqa: E402
from hydrodyn_tables import detect_hydrodyn_table_format, parse_hydrodyn_tables  # noqa: E402
from linearization_workspace import analyze_linearization, discover_linearizations  # noqa: E402
from module_plugins import capability_matrix, plugin_definitions  # noqa: E402
from openfast_input import (  # noqa: E402
    module_catalog_for_structure,
    outlists_for_structure,
    parse_editable_document,
    parse_scalar_fields,
    read_text_lines,
)
from results_workspace import analyze_results, discover_results, read_output_metadata, resolve_result_path  # noqa: E402
from tool_profiles import run_tool, select_tool, tool_profiles, update_local_tool  # noqa: E402
from tool_inputs import TOOL_INPUTS, generate_tool_input, safe_tool_input_path, save_tool_input, tool_input_catalog  # noqa: E402
from visualization_workspace import discover_visualizations, load_visualization_geometry  # noqa: E402
from model_profiles import (  # noqa: E402
    dependency_structure_for_model,
    input_files_for_model,
    model_profiles,
    preview_profile_paths,
    runtime_profiles,
    save_local_profile_paths,
    select_model,
    select_runtime,
)

INPUT_FILES = [
    "FOCAL_C4.fst",
    "FOCAL_C4_ElastoDyn.dat",
    "FOCAL_C4_InflowFile.dat",
    "FOCAL_C4_AeroDyn15_aboverated.dat",
    "FOCAL_C4_AeroDyn15_rated.dat",
    "FOCAL_C4_ServoDyn_aboverated_controller.dat",
    "FOCAL_C4_ServoDyn_rated_controller.dat",
    "SeaState_DLC_1p6.dat",
    "FOCAL_C4_HydroDyn.dat",
    "FOCAL_C4_MoorDyn.dat",
]

KEY_LINE_RE = re.compile(r"^\s*(?P<value>\S+(?:\s*,\s*\S+)*)\s+(?P<key>[A-Za-z][A-Za-z0-9_()]+)\s*(?:-|$)")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.json$")

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


MODULE_PRESETS = [
    {
        "id": "parked_still",
        "name": "停机静水",
        "description": "无风、无气动、无控制；保留 SeaState/HydroDyn/MoorDyn，WaveMod=0。",
        "set": {
            "FOCAL_C4.fst": {"CompInflow": 0, "CompAero": 0, "CompServo": 0, "CompSeaState": 1, "CompHydro": 1, "CompMooring": 3},
            "SeaState_DLC_1p6.dat": {"WaveMod": 0},
        },
    },
    {
        "id": "steady_wind",
        "name": "稳态风",
        "description": "开启 InflowWind + AeroDyn + ServoDyn 的运行工况，默认稳态风。",
        "set": {
            "FOCAL_C4.fst": {"CompInflow": 1, "CompAero": 2, "CompServo": 1, "CompSeaState": 1, "CompHydro": 1, "CompMooring": 3},
            "FOCAL_C4_InflowFile.dat": {"WindType": 1, "HWindSpeed": 12.8},
            "SeaState_DLC_1p6.dat": {"WaveMod": 0},
        },
    },
    {
        "id": "regular_wave_parked",
        "name": "停机规则波",
        "description": "无风/无气动/无控制，观察规则波下的水动力响应。",
        "set": {
            "FOCAL_C4.fst": {"CompInflow": 0, "CompAero": 0, "CompServo": 0, "CompSeaState": 1, "CompHydro": 1, "CompMooring": 3},
            "SeaState_DLC_1p6.dat": {"WaveMod": 1, "WaveHs": 2.0, "WaveTp": 10.0, "WaveDir": 0},
        },
    },
    {
        "id": "wind_wave",
        "name": "风 + 规则波",
        "description": "运行状态下同时施加稳态风和规则波。",
        "set": {
            "FOCAL_C4.fst": {"CompInflow": 1, "CompAero": 2, "CompServo": 1, "CompSeaState": 1, "CompHydro": 1, "CompMooring": 3},
            "FOCAL_C4_InflowFile.dat": {"WindType": 1, "HWindSpeed": 12.8},
            "SeaState_DLC_1p6.dat": {"WaveMod": 1, "WaveHs": 2.0, "WaveTp": 10.0, "WaveDir": 0},
        },
    },
    {
        "id": "linearization",
        "name": "线性化设置",
        "description": "在复制出的 case 中打开 OpenFAST 线性化相关字段。",
        "set": {
            "FOCAL_C4.fst": {"Linearize": True, "CalcSteady": False, "NLinTimes": 2, "LinTimes": "30.0, 60.0", "LinInputs": 1, "LinOutputs": 1},
        },
    },
    {
        "id": "vtk_output",
        "name": "VTK 可视化输出",
        "description": "打开 VTK 输出，用于快速检查几何和运动。",
        "set": {
            "FOCAL_C4.fst": {"WrVTK": 2, "VTK_type": 2, "VTK_fields": False, "VTK_fps": 15.0},
        },
    },
]

INTERFACE_MODES = [
    {"name": "OpenFAST 耦合 .fst", "status": "supported", "entry": "openfast_x64.exe FOCAL_C4.fst", "scope": "气动/水动/控制/结构耦合主流程"},
    {"name": "自由衰减助手", "status": "supported", "entry": "user_tools/run_case.py", "scope": "平台初始位移、自由衰减和实验评分"},
    {"name": "JSON 场景批量", "status": "supported", "entry": "user_tools/run_scenario.py", "scope": "复制完整模型后按参数覆盖运行一个或多个 case"},
    {"name": "线性化", "status": "template-supported", "entry": "FOCAL_C4.fst Linearize=True", "scope": "受所选模块限制的 OpenFAST 全系统线性化"},
    {"name": "VTK 可视化", "status": "template-supported", "entry": "FOCAL_C4.fst WrVTK", "scope": "OpenFAST 几何/运动可视化输出"},
    {"name": "模块独立 driver", "status": "documented-only", "entry": "AeroDyn / HydroDyn / SeaState / BeamDyn drivers", "scope": "官方有文档，但此工作区未打包对应 driver 可执行文件"},
    {"name": "FAST.Farm", "status": "documented-only", "entry": "FAST.Farm primary input", "scope": "风场级仿真接口，此工作区未打包"},
]

DOC_LINKS = [
    {"label": "OpenFAST 总览", "url": "https://openfast.readthedocs.io/en/main/"},
    {"label": "运行 OpenFAST", "url": "https://openfast.readthedocs.io/en/main/source/working.html"},
    {"label": "OpenFAST API 变化", "url": "https://openfast.readthedocs.io/en/main/source/user/api_change.html"},
    {"label": "ElastoDyn 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/elastodyn/input.html"},
    {"label": "InflowWind 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/inflowwind/input.html"},
    {"label": "SeaState 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/seastate/input_files.html"},
    {"label": "HydroDyn 输入", "url": "https://openfast.readthedocs.io/en/main/source/user/hydrodyn/input_files.html"},
    {"label": "MoorDyn 输入", "url": "https://moordyn.readthedocs.io/en/latest/inputs.html"},
    {"label": "FOCAL Campaign 4 数据", "url": "https://wdh.energy.gov/ds/focal/focal.campaign4"},
    {"label": "FOCAL OpenFAST 验证论文", "url": "https://doi.org/10.3390/machines11090865"},
]


def json_safe(value):
    if isinstance(value, pathlib.Path):
        return str(value)
    return value


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def job_snapshot(job: dict) -> dict:
    row = dict(job)
    started = row.get("startedAt")
    finished = row.get("finishedAt")
    if started:
        row["elapsed_s"] = max(0.0, float((finished or time.time()) - started))
    return row


def report_path_from_output(output: str) -> pathlib.Path | None:
    for line in reversed(output.splitlines()):
        if line.startswith("REPORT:"):
            raw = line.split(":", 1)[1].strip()
            if raw:
                return pathlib.Path(raw)
    return None


def job_results_from_output(output: str) -> tuple[str | None, list]:
    report = report_path_from_output(output)
    if not report or not report.is_file():
        return (str(report) if report else None), []
    try:
        data = read_json(report)
        return str(report), data if isinstance(data, list) else []
    except Exception:
        return str(report), []


def comparison_figures_from_results(results: list) -> list[dict]:
    figures = []
    for row in results:
        if not isinstance(row, dict):
            continue
        plot = row.get("comparison_plot") or {}
        if not isinstance(plot, dict) or not plot.get("web_url"):
            continue
        figures.append(
            {
                "label": f"{row.get('case', 'case')} 实验/仿真对比",
                "url": plot["web_url"],
                "source": plot.get("png") or plot.get("openfast_out") or "",
                "warnings": plot.get("warnings") or [],
            }
        )
        if plot.get("comparison_type") == "paper_metrics":
            figures[-1]["label"] = plot.get("label") or f"{row.get('case', 'case')} paper metric check"
        elif plot.get("label"):
            figures[-1]["label"] = plot["label"]
    return figures


def scenario_path(name: str) -> pathlib.Path:
    name = pathlib.Path(name).name
    if not SAFE_NAME_RE.match(name):
        raise ValueError("Scenario filename must end with .json and contain only letters, numbers, dot, dash, underscore.")
    return SCENARIOS / name


def model_path(model: dict) -> pathlib.Path:
    return pathlib.Path(model["path"])


def model_input_path(model: dict, file_id: str) -> pathlib.Path:
    root = model_path(model).resolve()
    normalized = pathlib.PurePosixPath(str(file_id).replace("\\", "/"))
    path = (root / normalized).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Model file escapes selected model: {file_id}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Model input file not found: {file_id}")
    return path


def active_context(qs: dict[str, list[str]] | None = None, options: dict | None = None) -> tuple[dict, dict]:
    qs = qs or {}
    options = options or {}
    model_id = options.get("modelId") or (qs.get("model") or [None])[0]
    runtime_id = options.get("runtimeId") or (qs.get("runtime") or [None])[0]
    model = select_model(model_id)
    runtime = select_runtime(runtime_id, model=model)
    return model, runtime


def readiness_issue(code: str, severity: str, scopes: list[str], **details) -> dict:
    return {
        "code": code,
        "severity": severity,
        "scopes": scopes,
        **{key: value for key, value in details.items() if value is not None and value != ""},
    }


def runtime_major(runtime: dict) -> int | None:
    """Return the reported OpenFAST major version when the executable identifies it."""
    match = re.search(r"OpenFAST-v(\d+)", str(runtime.get("version") or ""), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def hydrodyn_format_for_model(model: dict) -> str:
    path = pathlib.Path(str(model.get("hydroPath") or ""))
    if not path.is_file():
        return "missing"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return detect_hydrodyn_table_format(lines)


def case_file_targets(case: dict) -> set[str]:
    """Collect model-relative files a case attempts to edit without trusting their paths."""
    targets = {str(name) for name in (case.get("set") or {}) if str(name).strip()}
    if case.get("fst"):
        targets.add(str(case["fst"]))
    for field in ("input_edits", "input_file_overrides", "outlist_edits"):
        rows = case.get(field) or []
        if isinstance(rows, dict):
            targets.update(str(name) for name in rows if str(name).strip())
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("file"):
                targets.add(str(row["file"]))
    return targets


def readiness_issues(
    model: dict,
    runtime: dict,
    scenario: dict | None = None,
    structure: dict | None = None,
    require_runtime: bool = True,
) -> list[dict]:
    """Return stable, structured blockers/warnings for a selected GUI context."""
    issues: list[dict] = []
    if not model.get("exists"):
        issues.append(readiness_issue(
            "model_root_missing", "error", ["global", "context", "compose", "advanced", "modules", "hydro", "model"],
            path=model.get("path"), modelId=model.get("id"),
        ))
    elif not model.get("fstExists"):
        issues.append(readiness_issue(
            "main_input_missing", "error", ["global", "context", "compose", "advanced", "modules", "hydro", "model"],
            path=model.get("fstPath"), file=model.get("fst"), modelId=model.get("id"),
        ))

    if require_runtime and not runtime.get("exists"):
        issues.append(readiness_issue(
            "runtime_missing", "error", ["global", "context", "compose", "tools"],
            path=runtime.get("path"), runtimeId=runtime.get("id"),
        ))

    runtime_format = str(runtime.get("runtimeFormat") or "").lower()
    supported_formats = [str(value).lower() for value in (model.get("supportedRuntimeFormats") or [])]
    if runtime.get("exists") and supported_formats and runtime_format not in supported_formats:
        issues.append(readiness_issue(
            "runtime_format_incompatible", "error", ["global", "context", "compose", "hydro", "tools"],
            runtimeFormat=runtime_format, supportedRuntimeFormats=supported_formats,
            modelId=model.get("id"), runtimeId=runtime.get("id"),
        ))
    reported_major = runtime_major(runtime)
    if runtime.get("exists") and runtime_format == "v5" and reported_major is not None and reported_major < 5:
        issues.append(readiness_issue(
            "runtime_version_incompatible", "error", ["global", "context", "compose", "hydro", "tools"],
            version=runtime.get("version"), runtimeId=runtime.get("id"),
        ))

    structure = structure or dependency_structure_for_model(model)
    summary = structure.get("summary") or {}
    if model.get("exists") and model.get("fstExists") and summary.get("missing"):
        issues.append(readiness_issue(
            "dependency_missing", "warning", ["global", "context", "model"],
            count=int(summary.get("missing") or 0),
        ))
    hydro_format = hydrodyn_format_for_model(model) if model.get("hydroExists") else "missing"
    if model.get("hydroFile") and not model.get("hydroExists"):
        issues.append(readiness_issue(
            "hydrodyn_input_missing", "warning", ["global", "compose", "hydro", "model"],
            path=model.get("hydroPath"), file=model.get("hydroFile"),
        ))
    elif model.get("hydroFile") and runtime_format == "v5" and hydro_format != "v5":
        issues.append(readiness_issue(
            "hydrodyn_format_incompatible", "warning", ["global", "context", "hydro"],
            path=model.get("hydroPath"), hydroFormat=hydro_format, runtimeFormat=runtime_format,
        ))

    if not isinstance(scenario, dict):
        return issues

    scenario_model = scenario.get("model_id")
    if scenario_model and scenario_model != model.get("id"):
        issues.append(readiness_issue(
            "scenario_model_mismatch", "error", ["global", "context", "compose", "advanced"],
            scenarioModelId=scenario_model, modelId=model.get("id"),
        ))
    scenario_runtime = scenario.get("runtime_id")
    if scenario_runtime and scenario_runtime != runtime.get("id"):
        issues.append(readiness_issue(
            "scenario_runtime_mismatch", "error", ["global", "context", "compose", "advanced"],
            scenarioRuntimeId=scenario_runtime, runtimeId=runtime.get("id"),
        ))

    if not (model.get("exists") and model.get("fstExists")):
        return issues

    known_files = set(input_files_for_model(model, structure=structure))
    known_files.add(str(model.get("fst") or ""))
    missing_targets: set[str] = set()
    unknown_targets: set[str] = set()
    hydro_required = False
    for case in scenario.get("cases") or []:
        if not isinstance(case, dict):
            continue
        main_values = (case.get("set") or {}).get(model.get("fst") or "", {})
        try:
            hydro_required = hydro_required or float((main_values or {}).get("CompHydro", 0)) > 0
        except (TypeError, ValueError):
            pass
        for target in case_file_targets(case):
            if target not in known_files:
                unknown_targets.add(target)
            elif not (model_path(model) / pathlib.PurePosixPath(target.replace("\\", "/"))).is_file():
                missing_targets.add(target)

    if hydro_required and not model.get("hydroExists"):
        issues.append(readiness_issue(
            "hydrodyn_required_missing", "error", ["global", "compose", "hydro"],
            path=model.get("hydroPath"), file=model.get("hydroFile"),
        ))
    elif hydro_required and runtime_format == "v5" and hydro_format != "v5":
        issues.append(readiness_issue(
            "hydrodyn_format_required", "error", ["global", "compose", "hydro"],
            path=model.get("hydroPath"), hydroFormat=hydro_format, runtimeFormat=runtime_format,
        ))
    for target in sorted(unknown_targets):
        issues.append(readiness_issue(
            "override_target_unknown", "error", ["global", "advanced", "modules"], file=target,
        ))
    for target in sorted(missing_targets):
        issues.append(readiness_issue(
            "override_target_missing", "error", ["global", "advanced", "modules"], file=target,
        ))
    return issues


def module_presets_for(model: dict) -> list[dict]:
    fst = model.get("fst") or "FOCAL_C4.fst"
    inflow = model.get("inflowFile") or "FOCAL_C4_InflowFile.dat"
    sea = model.get("seaStateFile") or "SeaState_DLC_1p6.dat"
    sea_key = model.get("seaStateCompKey") or "CompSeaState"
    mooring = int(model.get("defaultMooring", 0))
    return [
        {
            "id": "parked_still",
            "name": "停机静水",
            "description": "无风、无气动、无控制；保留 SeaState/HydroDyn/Mooring，WaveMod=0。",
            "set": {
                fst: {"CompInflow": 0, "CompAero": 0, "CompServo": 0, sea_key: 1, "CompHydro": 1, "CompMooring": mooring},
                sea: {"WaveMod": 0},
            },
        },
        {
            "id": "steady_wind",
            "name": "稳态风",
            "description": "开启 InflowWind + AeroDyn + ServoDyn；默认静水。",
            "set": {
                fst: {"CompInflow": 1, "CompAero": 2, "CompServo": 1, sea_key: 1, "CompHydro": 1, "CompMooring": mooring},
                inflow: {"WindType": 1, "HWindSpeed": 12.8},
                sea: {"WaveMod": 0},
            },
        },
        {
            "id": "regular_wave_parked",
            "name": "停机规则波",
            "description": "无风/无气动/无控制，规则波水动力工况。",
            "set": {
                fst: {"CompInflow": 0, "CompAero": 0, "CompServo": 0, sea_key: 1, "CompHydro": 1, "CompMooring": mooring},
                sea: {"WaveMod": 1, "WaveHs": 2.0, "WaveTp": 10.0, "WaveDir": 0},
            },
        },
        {
            "id": "wind_wave",
            "name": "风 + 规则波",
            "description": "运行状态下同时施加稳态风和规则波。",
            "set": {
                fst: {"CompInflow": 1, "CompAero": 2, "CompServo": 1, sea_key: 1, "CompHydro": 1, "CompMooring": mooring},
                inflow: {"WindType": 1, "HWindSpeed": 12.8},
                sea: {"WaveMod": 1, "WaveHs": 2.0, "WaveTp": 10.0, "WaveDir": 0},
            },
        },
        {
            "id": "linearization",
            "name": "线性化设置",
            "description": "在复制出的 case 中打开 OpenFAST 线性化相关字段。",
            "set": {
                fst: {"Linearize": True, "CalcSteady": False, "NLinTimes": 2, "LinTimes": "30.0, 60.0", "LinInputs": 1, "LinOutputs": 1},
            },
        },
        {
            "id": "vtk_output",
            "name": "VTK 可视化输出",
            "description": "打开 VTK 输出，用于快速检查几何和运动。",
            "set": {
                fst: {"WrVTK": 2, "VTK_type": 2, "VTK_fields": False, "VTK_fps": 15.0},
            },
        },
    ]


def interface_modes_for(model: dict, runtime: dict) -> list[dict]:
    fst = model.get("fst") or "Input.fst"
    exe = pathlib.Path(runtime.get("path") or "openfast").name
    tools = {str(row.get("id")): row for row in tool_profiles()}

    def tool_mode(tool_id: str, scope: str) -> dict:
        tool = tools.get(tool_id) or {"id": tool_id, "name": tool_id, "status": "not-installed"}
        return {
            "name": tool.get("name", tool_id),
            "status": "ready" if tool.get("runnable") else "configurable",
            "entry": tool.get("path") or "在工具接口页配置可执行文件",
            "scope": scope,
        }

    return [
        {"name": "OpenFAST 主运行 / Primary runtime", "status": "ready" if runtime.get("exists") else "configurable", "entry": f"{exe} {fst}", "scope": "在运行上下文配置 executable；按当前模型 profile 复制模板并运行"},
        {"name": "JSON 场景批量", "status": "supported", "entry": "user_tools/run_scenario.py", "scope": "复制完整模型后按参数覆盖运行一个或多个 case"},
        {"name": "线性化", "status": "supported", "entry": f"{fst} Linearize=True", "scope": "配置线性化并解析 .lin 模态、频率和阻尼"},
        {"name": "VTK 可视化", "status": "supported", "entry": f"{fst} WrVTK", "scope": "发现并在浏览器三维查看 ASCII VTK/VTP/PVD"},
        tool_mode("turbsim", "生成全场湍流风并校验 InflowWind .bts 引用"),
        tool_mode("fastfarm", "编辑和运行 FAST.Farm 风场级仿真"),
        tool_mode("aerodyn_driver", "AeroDyn 独立 driver"),
        tool_mode("hydrodyn_driver", "HydroDyn / SeaState 独立 driver"),
        tool_mode("beamdyn_driver", "BeamDyn 独立 driver"),
        tool_mode("subdyn_driver", "SubDyn 独立 driver"),
        {
            "name": "OpenFAST Library / Simulink",
            "status": "ready" if (tools.get("openfast_library", {}).get("exists") or tools.get("simulink", {}).get("exists")) else "configurable",
            "entry": tools.get("openfast_library", {}).get("path") or tools.get("simulink", {}).get("path") or "在工具接口页配置库文件",
            "scope": "外部 C/C++/Fortran glue code、CFD 或 MATLAB/Simulink 接口",
        },
    ]


def parse_template_keys(model: dict, structure: dict | None = None) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    base = model_path(model)
    for file_name in input_files_for_model(model, structure=structure):
        path = base / file_name
        if not path.is_file():
            continue
        rows = []
        lines, _, _ = read_text_lines(path)
        for field in parse_scalar_fields(lines):
            key = field["key"]
            if key.upper() in {"END", "OUTLIST"} or key.startswith("-"):
                continue
            if key in {"OUTPUT", "LINEARIZATION", "VISUALIZATION", "BLADE", "ROTOR", "DRIVETRAIN", "FURLING", "TOWER", "WAVES", "CURRENT", "MACCAMY", "MEMBER", "MEMBERS", "DEPTH", "HIGH", "NACELLE", "THEVENIN", "OLAF", "Beddoes"}:
                continue
            rows.append(field)
        result[file_name] = rows
    return result


def parse_model_outlists(model: dict, structure: dict | None = None) -> dict[str, list[dict]]:
    structure = structure or dependency_structure_for_model(model)
    return outlists_for_structure(model_path(model), structure)


def parse_hydrodyn_matrices(model: dict) -> dict[str, list[list[float]]]:
    path = model_path(model) / (model.get("hydroFile") or "")
    matrices: dict[str, list[list[float]]] = {}
    if not path.is_file():
        return matrices
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for block, tag in {"CLin": "AddCLin", "BLin": "AddBLin", "BQuad": "AddBQuad"}.items():
        start = None
        for index, line in enumerate(lines):
            if tag in line:
                start = index
                break
        if start is None:
            continue
        rows = []
        for offset in range(6):
            nums = []
            for token in lines[start + offset].split():
                try:
                    nums.append(float(token))
                except ValueError:
                    break
                if len(nums) == 6:
                    break
            rows.append((nums + [0.0] * 6)[:6])
        matrices[block] = rows
    return matrices


def parse_hydrodyn_tables_meta(model: dict, runtime: dict) -> dict:
    hydro_file = model.get("hydroFile") or "HydroDyn.dat"
    path = model_path(model) / hydro_file
    runtime_format = runtime.get("runtimeFormat") or "v4"
    if not path.is_file():
        return {"format": "missing", "runtimeFormat": runtime_format, "tables": {}, "schemas": {}, "warnings": [f"{hydro_file} not found"]}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if model.get("compatibility") == "focal_c4_v4" and runtime_format == "v4":
        lines = _ensure_hydrodyn_v4(lines)
    return parse_hydrodyn_tables(lines, runtime_format=runtime_format)


def meta_payload(model: dict, runtime: dict) -> dict:
    """Build the complete GUI context from one model/runtime selection."""
    structure = dependency_structure_for_model(model)
    module_catalog = module_catalog_for_structure(model_path(model), structure)
    return {
        "root": str(ROOT),
        "model": model["path"],
        "modelProfile": model,
        "modelProfiles": model_profiles(),
        "selectedModelId": model.get("id"),
        "openfastExe": runtime["path"],
        "runtimeProfile": runtime,
        "runtimeProfiles": runtime_profiles(include_version=True),
        "selectedRuntimeId": runtime.get("id"),
        "openfastExists": bool(runtime.get("exists")),
        "runScenario": str(RUN_SCENARIO),
        "modelStructure": structure,
        "dependencySummary": structure.get("summary") or {},
        "hydroFormat": hydrodyn_format_for_model(model),
        "readiness": readiness_issues(model, runtime, structure=structure),
        "modulePlugins": plugin_definitions(),
        "moduleCatalog": module_catalog,
        "capabilityMatrix": capability_matrix(module_catalog),
        "templateKeys": parse_template_keys(model, structure=structure),
        "outLists": parse_model_outlists(model, structure=structure),
        "hydroMatrices": parse_hydrodyn_matrices(model),
        "hydroTables": parse_hydrodyn_tables_meta(model, runtime),
        "modulePresets": module_presets_for(model),
        "interfaceModes": interface_modes_for(model, runtime),
        "externalTools": tool_profiles(),
        "docLinks": DOC_LINKS,
    }


def readiness_text(issue: dict) -> str:
    detail = issue.get("path") or issue.get("file") or issue.get("scenarioModelId") or ""
    return f"{issue.get('code', 'readiness_error')}{f': {detail}' if detail else ''}"


def scenario_list() -> list[dict]:
    SCENARIOS.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(SCENARIOS.glob("*.json")):
        try:
            data = read_json(path)
            rows.append({"file": path.name, "name": data.get("name", path.stem), "cases": len(data.get("cases", [])), "description": data.get("description", "")})
        except Exception as exc:
            rows.append({"file": path.name, "name": path.stem, "cases": 0, "description": f"ERROR: {exc}"})
    return rows


def run_job(job_id: str, scenario_file: pathlib.Path, options: dict) -> None:
    model, runtime = active_context(options=options)
    scenario = read_json(scenario_file)
    structure = dependency_structure_for_model(model)
    readiness = readiness_issues(
        model,
        runtime,
        scenario=scenario,
        structure=structure,
        require_runtime=not bool(options.get("generateOnly")),
    )
    blockers = [issue for issue in readiness if issue.get("severity") == "error"]
    if blockers:
        with JOBS_LOCK:
            JOBS[job_id].update(
                {
                    "status": "failed",
                    "finishedAt": time.time(),
                    "output": "运行前检查未通过 / Readiness check failed\n" + "\n".join(readiness_text(issue) for issue in blockers),
                    "readiness": readiness,
                }
            )
        return
    workers = max(1, min(int(options.get("workers") or 1), 8))
    command = [
        PYTHON,
        str(RUN_SCENARIO),
        "--scenario",
        str(scenario_file),
        "--model",
        model["path"],
        "--openfast-exe",
        runtime["path"],
        "--runtime-format",
        runtime.get("runtimeFormat") or "v4",
        "--compatibility",
        model.get("compatibility") or "none",
        "--fst",
        model.get("fst") or "FOCAL_C4.fst",
        "--hydro-file",
        model.get("hydroFile") or "HydroDyn.dat",
        "--inflow-file",
        model.get("inflowFile") or "InflowWind.dat",
        "--sea-state-file",
        model.get("seaStateFile") or "SeaState.dat",
        "--workers",
        str(workers),
    ]
    if options.get("generateOnly"):
        command.append("--generate-only")
    if options.get("overwrite"):
        command.append("--overwrite")
    if options.get("continueOnFail"):
        command.append("--continue-on-fail")
    if options.get("resume"):
        command.append("--resume")
    if options.get("plotComparison"):
        command.append("--plot-comparison")

    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": "running",
                "command": command,
                "modelId": model.get("id"),
                "runtimeId": runtime.get("id"),
                "workers": workers,
                "startedAt": time.time(),
            }
        )

    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    output: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        output.append(line)
        if len(output) > 800:
            output = output[-800:]
        with JOBS_LOCK:
            JOBS[job_id]["output"] = "".join(output)
    returncode = proc.wait()
    output_text = "".join(output)
    result_report, results = job_results_from_output(output_text)
    comparison_figures = comparison_figures_from_results(results)
    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": "done" if returncode == 0 else "failed",
                "returncode": returncode,
                "finishedAt": time.time(),
                "output": output_text,
                "resultReport": result_report,
                "results": results,
                "comparisonFigures": comparison_figures,
            }
        )


def resolve_tool_input(model: dict, file_id: str, source: str = "model") -> pathlib.Path:
    if source == "model":
        return model_input_path(model, file_id)
    if source == "workspace":
        path = safe_tool_input_path(file_id)
        if not path.is_file():
            raise FileNotFoundError(f"Workspace tool input not found: {file_id}")
        return path
    if source != "runs":
        raise ValueError("External tool input source must be model, workspace or runs")
    root = RUNS.resolve()
    path = (root / pathlib.PurePosixPath(str(file_id).replace("\\", "/"))).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"External tool input escapes runs directory: {file_id}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"External tool input file not found: {file_id}")
    return path


def run_external_tool_job(job_id: str, tool_id: str, input_path: pathlib.Path) -> None:
    tool = select_tool(tool_id)
    command = [str(tool.get("path") or ""), input_path.name]
    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": "running",
                "command": command,
                "toolId": tool_id,
                "input": str(input_path),
                "startedAt": time.time(),
            }
        )
    try:
        completed = run_tool(tool, input_path)
        output = (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else "")
        with JOBS_LOCK:
            JOBS[job_id].update(
                {
                    "status": "done" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                    "finishedAt": time.time(),
                    "output": output[-200_000:],
                }
            )
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(
                {
                    "status": "failed",
                    "returncode": None,
                    "finishedAt": time.time(),
                    "output": str(exc),
                }
            )


def stage_external_tool_input(model: dict, input_path: pathlib.Path, source: str, tool_id: str) -> pathlib.Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", input_path.stem).strip("_") or "input"
    run_dir = RUNS / "external_tools" / f"{stamp}_{tool_id}_{safe_stem}"
    suffix = 1
    while run_dir.exists():
        run_dir = RUNS / "external_tools" / f"{stamp}_{tool_id}_{safe_stem}_{suffix}"
        suffix += 1
    if source == "model":
        model_root = model_path(model).resolve()
        relative = input_path.resolve().relative_to(model_root)
        shutil.copytree(model_root, run_dir)
        return run_dir / relative
    run_dir.mkdir(parents=True, exist_ok=False)
    if source == "workspace":
        target = run_dir / input_path.name
        shutil.copy2(input_path, target)
        if tool_id == "fastfarm":
            model_root = model_path(model).resolve()
            shutil.copytree(model_root, run_dir / "model")
            text = target.read_text(encoding="utf-8", errors="replace")
            source_root = str(model_root).replace("\\", "/")
            target.write_text(text.replace(source_root, "model"), encoding="utf-8")
        return target
    source_root = input_path.parent.resolve()
    staged_root = run_dir / "input"
    shutil.copytree(source_root, staged_root)
    return staged_root / input_path.name


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenFASTUI/1.0"

    def log_message(self, fmt, *args):
        return

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def send_json(self, value, status=200):
        payload = json.dumps(value, ensure_ascii=False, default=json_safe).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message, status=400, issues: list[dict] | None = None):
        payload = {"ok": False, "error": str(message)}
        if issues:
            payload["issues"] = issues
        self.send_json(payload, status=status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/api/meta":
                model, runtime = active_context(qs=qs)
                return self.send_json(meta_payload(model, runtime))
            if path == "/api/module":
                model, _runtime = active_context(qs=qs)
                file_id = qs.get("file", [""])[0]
                if not file_id:
                    raise ValueError("Missing module file")
                return self.send_json(parse_editable_document(model_input_path(model, file_id), file_id=file_id))
            if path == "/api/scenarios":
                return self.send_json({"scenarios": scenario_list()})
            if path == "/api/scenario":
                name = qs.get("file", [""])[0]
                path_obj = scenario_path(name)
                return self.send_json({"file": path_obj.name, "data": read_json(path_obj)})
            if path == "/api/results":
                return self.send_json(discover_results(RUNS))
            if path == "/api/results/meta":
                file_id = qs.get("file", [""])[0]
                result_path = resolve_result_path(RUNS, file_id)
                return self.send_json({"id": file_id, "metadata": read_output_metadata(result_path)})
            if path == "/api/linearizations":
                return self.send_json(discover_linearizations(RUNS))
            if path == "/api/visualizations":
                return self.send_json(discover_visualizations(RUNS))
            if path == "/api/visualizations/geometry":
                file_id = qs.get("file", [""])[0]
                return self.send_json(load_visualization_geometry(RUNS, file_id))
            if path == "/api/tools":
                return self.send_json({"tools": tool_profiles()})
            if path == "/api/tool-inputs":
                return self.send_json({"root": str(TOOL_INPUTS), "files": tool_input_catalog()})
            if path == "/api/tool-input":
                file_id = qs.get("file", [""])[0]
                return self.send_json(parse_editable_document(safe_tool_input_path(file_id), file_id=file_id))
            if path == "/api/jobs":
                with JOBS_LOCK:
                    jobs = [job_snapshot(job) for job in JOBS.values()]
                jobs.sort(key=lambda item: item.get("createdAt", 0), reverse=True)
                return self.send_json({"jobs": jobs})
            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if not job:
                        return self.send_error_json("Job not found", status=404)
                    return self.send_json(job_snapshot(job))
            return self.serve_static(path)
        except Exception as exc:
            return self.send_error_json(exc, status=500)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self.read_body()
            if parsed.path == "/api/profiles/validate":
                model, runtime = preview_profile_paths(
                    str(body.get("modelId") or ""),
                    body.get("modelPath"),
                    str(body.get("runtimeId") or ""),
                    body.get("runtimePath"),
                )
                structure = dependency_structure_for_model(model)
                return self.send_json(
                    {
                        "ok": True,
                        "modelProfile": model,
                        "runtimeProfile": runtime,
                        "dependencySummary": structure.get("summary") or {},
                        "readiness": readiness_issues(model, runtime, structure=structure),
                    }
                )
            if parsed.path == "/api/profiles/local":
                model_id = str(body.get("modelId") or "")
                runtime_id = str(body.get("runtimeId") or "")
                save_local_profile_paths(model_id, body.get("modelPath"), runtime_id, body.get("runtimePath"))
                model, runtime = active_context(options={"modelId": model_id, "runtimeId": runtime_id})
                return self.send_json(meta_payload(model, runtime))
            if parsed.path == "/api/readiness":
                scenario = body.get("scenario")
                if not isinstance(scenario, dict):
                    raise ValueError("Missing scenario for readiness check")
                options = body.get("options") or {}
                model, runtime = active_context(options=options)
                structure = dependency_structure_for_model(model)
                readiness = readiness_issues(
                    model,
                    runtime,
                    scenario=scenario,
                    structure=structure,
                    require_runtime=not bool(options.get("generateOnly")),
                )
                return self.send_json({"ok": True, "readiness": readiness, "dependencySummary": structure.get("summary") or {}})
            if parsed.path == "/api/scenario":
                filename = body.get("file") or f"{body.get('data', {}).get('name', 'ui_scenario')}.json"
                filename = pathlib.Path(str(filename)).name
                if not filename.endswith(".json"):
                    filename += ".json"
                path_obj = scenario_path(filename)
                data = body.get("data")
                if not isinstance(data, dict):
                    raise ValueError("Missing scenario data")
                write_json(path_obj, data)
                return self.send_json({"ok": True, "file": path_obj.name, "path": str(path_obj)})
            if parsed.path == "/api/jobs":
                data = body.get("scenario")
                if not isinstance(data, dict):
                    raise ValueError("Missing scenario")
                cases = data.get("cases")
                if not isinstance(cases, list) or not cases:
                    raise ValueError("Scenario has no cases. Add at least one case before running.")
                options = body.get("options") or {}
                model, runtime = active_context(options=options)
                structure = dependency_structure_for_model(model)
                readiness = readiness_issues(
                    model,
                    runtime,
                    scenario=data,
                    structure=structure,
                    require_runtime=not bool(options.get("generateOnly")),
                )
                blockers = [issue for issue in readiness if issue.get("severity") == "error"]
                if blockers:
                    return self.send_error_json("运行前检查未通过 / Readiness check failed", status=422, issues=blockers)
                filename = body.get("file") or f"_ui_{int(time.time())}.json"
                filename = pathlib.Path(str(filename)).name
                if not filename.endswith(".json"):
                    filename += ".json"
                path_obj = scenario_path(filename)
                write_json(path_obj, data)
                job_id = uuid.uuid4().hex[:12]
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "id": job_id,
                        "status": "queued",
                        "scenarioFile": path_obj.name,
                        "scenarioPath": str(path_obj),
                        "output": "",
                        "createdAt": time.time(),
                    }
                thread = threading.Thread(target=run_job, args=(job_id, path_obj, options), daemon=True)
                thread.start()
                return self.send_json({"ok": True, "jobId": job_id})
            if parsed.path == "/api/results/analyze":
                start = body.get("start")
                end = body.get("end")
                result = analyze_results(
                    RUNS,
                    file_ids=body.get("files") or [],
                    channels=body.get("channels") or [],
                    start=float(start) if start not in {None, ""} else None,
                    end=float(end) if end not in {None, ""} else None,
                    max_points=int(body.get("maxPoints") or 5000),
                    include_psd=bool(body.get("includePsd", True)),
                )
                return self.send_json(result)
            if parsed.path == "/api/linearizations/analyze":
                file_id = str(body.get("file") or "")
                if not file_id:
                    raise ValueError("Missing linearization file")
                return self.send_json(analyze_linearization(RUNS, file_id))
            if parsed.path == "/api/tools":
                tool_id = str(body.get("id") or "")
                return self.send_json({"ok": True, "tool": update_local_tool(tool_id, str(body.get("path") or ""))})
            if parsed.path == "/api/tool-jobs":
                tool_id = str(body.get("toolId") or "")
                tool = select_tool(tool_id)
                if not tool.get("runnable"):
                    raise FileNotFoundError(f"{tool.get('name', tool_id)} executable is not configured")
                model, _runtime = active_context(options={"modelId": body.get("modelId")})
                source = str(body.get("source") or "model")
                input_path = resolve_tool_input(model, str(body.get("inputFile") or ""), source)
                staged_input = stage_external_tool_input(model, input_path, source, tool_id)
                job_id = uuid.uuid4().hex[:12]
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "id": job_id,
                        "status": "queued",
                        "kind": "external-tool",
                        "toolId": tool_id,
                        "input": str(staged_input),
                        "sourceInput": str(input_path),
                        "output": "",
                        "createdAt": time.time(),
                    }
                thread = threading.Thread(target=run_external_tool_job, args=(job_id, tool_id, staged_input), daemon=True)
                thread.start()
                return self.send_json({"ok": True, "jobId": job_id})
            if parsed.path == "/api/tool-inputs/generate":
                kind = str(body.get("kind") or "")
                spec = dict(body.get("spec") or {})
                model, _runtime = active_context(options={"modelId": body.get("modelId")})
                if kind == "fastfarm":
                    spec.setdefault("fst_file", model.get("fst") or "OpenFAST.fst")
                    spec.setdefault("inflow_file", model.get("inflowFile") or "InflowWind.dat")
                    if body.get("absoluteModelPaths", True):
                        spec["fst_file"] = str(model_input_path(model, str(spec["fst_file"])))
                        spec["inflow_file"] = str(model_input_path(model, str(spec["inflow_file"])))
                result = generate_tool_input(kind, str(body.get("file") or kind), spec)
                return self.send_json({"ok": True, "result": result, "files": tool_input_catalog()})
            if parsed.path == "/api/tool-input":
                result = save_tool_input(
                    str(body.get("file") or ""),
                    str(body.get("content") or ""),
                    str(body.get("source_sha256") or ""),
                )
                return self.send_json({"ok": True, "result": result, "files": tool_input_catalog()})
            return self.send_error_json("Unknown endpoint", status=404)
        except Exception as exc:
            return self.send_error_json(exc, status=500)

    def serve_static(self, request_path: str):
        if request_path in {"/", ""}:
            request_path = "/index.html"
        rel = pathlib.Path(unquote(request_path.lstrip("/")))
        target = (WEB_ROOT / rel).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenFAST UI running at http://{args.host}:{args.port}")
    print(f"Workspace: {ROOT}")
    httpd.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
