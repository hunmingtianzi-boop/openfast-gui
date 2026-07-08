# -*- coding: utf-8 -*-
"""Local web UI server for editing and running OpenFAST scenarios."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import re
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


def configured_path(env_name: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(env_name)
    return pathlib.Path(raw) if raw else default


MODEL = configured_path("FOCAL_C4_MODEL_TEMPLATE", ROOT / "FOCAL_OpenFast_C4-main" / "FOCAL_OpenFast_C4-main")
OPENFAST_EXE = configured_path("OPENFAST_EXE", ROOT / "bin" / "openfast_x64.exe")
RUN_SCENARIO = ROOT / "user_tools" / "run_scenario.py"
PYTHON = sys.executable
WORK_C4 = ROOT / "work_c4"
if str(WORK_C4) not in sys.path:
    sys.path.insert(0, str(WORK_C4))

from driver_c4 import _ensure_hydrodyn_v4  # noqa: E402
from hydrodyn_tables import parse_hydrodyn_tables  # noqa: E402

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
    {"label": "运行 OpenFAST", "url": "https://openfast.readthedocs.io/en/v4.0.5/source/working.html"},
    {"label": "v4 API 变化", "url": "https://openfast.readthedocs.io/en/main/source/user/api_change.html"},
    {"label": "ElastoDyn 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/elastodyn/input.html"},
    {"label": "InflowWind 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/inflowwind/input.html"},
    {"label": "SeaState 输入", "url": "https://openfast.readthedocs.io/en/dev/source/user/seastate/input_files.html"},
    {"label": "HydroDyn 输入", "url": "https://openfast.readthedocs.io/en/main/source/user/hydrodyn/input_files.html"},
    {"label": "MoorDyn 输入", "url": "https://moordyn.readthedocs.io/en/latest/inputs.html"},
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


def scenario_path(name: str) -> pathlib.Path:
    name = pathlib.Path(name).name
    if not SAFE_NAME_RE.match(name):
        raise ValueError("Scenario filename must end with .json and contain only letters, numbers, dot, dash, underscore.")
    return SCENARIOS / name


def parse_template_keys() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for file_name in INPUT_FILES:
        path = MODEL / file_name
        if not path.is_file():
            continue
        rows = []
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            match = KEY_LINE_RE.match(line)
            if not match:
                continue
            key = match.group("key")
            if key.upper() in {"END", "OUTLIST"} or key.startswith("-"):
                continue
            value = match.group("value")
            if key in {"OUTPUT", "LINEARIZATION", "VISUALIZATION", "BLADE", "ROTOR", "DRIVETRAIN", "FURLING", "TOWER", "WAVES", "CURRENT", "MACCAMY", "MEMBER", "MEMBERS", "DEPTH", "HIGH", "NACELLE", "THEVENIN", "OLAF", "Beddoes"}:
                continue
            rows.append({"line": number, "key": key, "value": value})
        result[file_name] = rows
    return result


def parse_hydrodyn_matrices() -> dict[str, list[list[float]]]:
    path = MODEL / "FOCAL_C4_HydroDyn.dat"
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


def parse_hydrodyn_tables_meta() -> dict:
    path = MODEL / "FOCAL_C4_HydroDyn.dat"
    if not path.is_file():
        return {"format": "missing", "runtimeFormat": "v4", "tables": {}, "schemas": {}, "warnings": ["FOCAL_C4_HydroDyn.dat not found"]}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = _ensure_hydrodyn_v4(lines)
    return parse_hydrodyn_tables(lines, runtime_format="v4")


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
    command = [PYTHON, str(RUN_SCENARIO), "--scenario", str(scenario_file)]
    if options.get("generateOnly"):
        command.append("--generate-only")
    if options.get("overwrite"):
        command.append("--overwrite")
    if options.get("continueOnFail"):
        command.append("--continue-on-fail")

    with JOBS_LOCK:
        JOBS[job_id].update({"status": "running", "command": command, "startedAt": time.time()})

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
    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": "done" if returncode == 0 else "failed",
                "returncode": returncode,
                "finishedAt": time.time(),
                "output": "".join(output),
            }
        )


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

    def send_error_json(self, message, status=400):
        self.send_json({"ok": False, "error": str(message)}, status=status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/api/meta":
                return self.send_json(
                    {
                        "root": str(ROOT),
                        "model": str(MODEL),
                        "openfastExe": str(OPENFAST_EXE),
                        "openfastExists": OPENFAST_EXE.is_file(),
                        "runScenario": str(RUN_SCENARIO),
                        "templateKeys": parse_template_keys(),
                        "hydroMatrices": parse_hydrodyn_matrices(),
                        "hydroTables": parse_hydrodyn_tables_meta(),
                        "modulePresets": MODULE_PRESETS,
                        "interfaceModes": INTERFACE_MODES,
                        "docLinks": DOC_LINKS,
                    }
                )
            if path == "/api/scenarios":
                return self.send_json({"scenarios": scenario_list()})
            if path == "/api/scenario":
                name = qs.get("file", [""])[0]
                path_obj = scenario_path(name)
                return self.send_json({"file": path_obj.name, "data": read_json(path_obj)})
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
                thread = threading.Thread(target=run_job, args=(job_id, path_obj, body.get("options") or {}), daemon=True)
                thread.start()
                return self.send_json({"ok": True, "jobId": job_id})
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
