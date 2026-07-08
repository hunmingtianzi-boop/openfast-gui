# -*- coding: utf-8 -*-
"""Run general OpenFAST scenarios from a copied FOCAL C4 model folder."""
from __future__ import annotations

import argparse
from collections import deque
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]


def configured_path(env_name: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(env_name)
    return pathlib.Path(raw) if raw else default


MODEL_TEMPLATE = configured_path("FOCAL_C4_MODEL_TEMPLATE", ROOT / "FOCAL_OpenFast_C4-main" / "FOCAL_OpenFast_C4-main")
OPENFAST_EXE = configured_path("OPENFAST_EXE", ROOT / "bin" / "openfast_x64.exe")
DEFAULT_RUNS = ROOT / "runs"
WORK_C4 = ROOT / "work_c4"
if str(WORK_C4) not in sys.path:
    sys.path.insert(0, str(WORK_C4))

from driver_c4 import (  # noqa: E402
    _ensure_hydrodyn_v4,
    _ensure_moordyn_v2,
    _ensure_platform_cross_inertia,
    _ensure_yaw_friction,
    apply_edits,
)
from hydrodyn_tables import TABLE_COUNT_KEYS, apply_hydrodyn_tables  # noqa: E402


def slug(text: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(text).strip())
    return text.strip("_") or "case"


def value_text(value: Any, old_value: str = "") -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    text = str(value)
    old = old_value.strip()
    if old.startswith('"') and old.endswith('"') and not (text.startswith('"') and text.endswith('"')):
        return f'"{text}"'
    return text


def replace_key_value(line: str, key: str, value: Any) -> tuple[str, bool]:
    pattern = re.compile(rf"^(\s*)(.*?)(\s+)({re.escape(key)})(\s*(?:-.*)?)$")
    match = pattern.match(line)
    if not match:
        return line, False
    indent, old_value, sep, found_key, tail = match.groups()
    width = max(13, len(old_value))
    new_value = value_text(value, old_value)
    return f"{indent}{new_value:<{width}}{sep}{found_key}{tail}", True


def set_openfast_key(path: pathlib.Path, key: str, value: Any) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    changed = False
    out = []
    for line in lines:
        new_line, did = replace_key_value(line, key, value)
        out.append(new_line)
        changed = changed or did
    if not changed:
        raise KeyError(f"Key {key!r} not found in {path}")
    path.write_text("\n".join(out), encoding="utf-8")


def parse_set(text: str) -> tuple[str, str, str]:
    if ":" not in text or "=" not in text:
        raise ValueError(f"Bad --set {text!r}; expected file:key=value")
    file_part, rest = text.split(":", 1)
    key, value = rest.split("=", 1)
    return file_part.strip(), key.strip(), value.strip()


def parse_matrix_edit(text: str) -> tuple[str, int, int, float]:
    parts = [part.strip() for part in text.split(",", 3)]
    if len(parts) != 4:
        raise ValueError(f"Bad matrix edit {text!r}; expected BLOCK,i,j,value")
    block, i, j, value = parts
    if block not in {"CLin", "BLin", "BQuad"}:
        raise ValueError("Matrix block must be CLin, BLin, or BQuad")
    return block, int(i) - 1, int(j) - 1, float(value)


def merge_case_sets(case: dict[str, Any], args) -> dict[str, dict[str, Any]]:
    sets: dict[str, dict[str, Any]] = {}
    for file_name, values in case.get("set", {}).items():
        sets[str(file_name)] = dict(values)

    def put(file_name: str, key: str, value: Any) -> None:
        sets.setdefault(file_name, {})[key] = value

    if args.tmax is not None:
        put("FOCAL_C4.fst", "TMax", args.tmax)
    if args.wind_speed is not None:
        put("FOCAL_C4.fst", "CompInflow", 1)
        put("FOCAL_C4_InflowFile.dat", "WindType", 1)
        put("FOCAL_C4_InflowFile.dat", "HWindSpeed", args.wind_speed)
    if args.wave_mod is not None:
        put("SeaState_DLC_1p6.dat", "WaveMod", args.wave_mod)
    if args.wave_hs is not None:
        put("SeaState_DLC_1p6.dat", "WaveHs", args.wave_hs)
    if args.wave_tp is not None:
        put("SeaState_DLC_1p6.dat", "WaveTp", args.wave_tp)
    for item in args.set or []:
        file_name, key, value = parse_set(item)
        put(file_name, key, value)
    return sets


def apply_sets(run_dir: pathlib.Path, sets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    changes = []
    for file_name, values in sets.items():
        path = run_dir / file_name
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found for set: {path}")
        for key, value in values.items():
            set_openfast_key(path, key, value)
            changes.append({"file": file_name, "key": key, "value": value})
    return changes


def apply_matrix_edits_to_file(run_dir: pathlib.Path, case: dict[str, Any], args) -> list[dict[str, Any]]:
    raw_edits = list(case.get("matrix_edits", []))
    raw_edits.extend(args.matrix_edit or [])
    if not raw_edits:
        return []

    edits = []
    for item in raw_edits:
        if isinstance(item, str):
            block, i, j, value = parse_matrix_edit(item)
        else:
            block = item["block"]
            i = int(item["i"]) - 1
            j = int(item["j"]) - 1
            value = float(item["value"])
        edits.append((block, i, j, value))

    hydro_file = case.get("hydro_file", "FOCAL_C4_HydroDyn.dat")
    path = run_dir / hydro_file
    if not path.is_file():
        raise FileNotFoundError(f"HydroDyn file not found: {path}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated = apply_edits(lines, edits)
    path.write_text("\n".join(updated), encoding="utf-8")
    return [
        {"file": hydro_file, "block": block, "i": i + 1, "j": j + 1, "value": value}
        for block, i, j, value in edits
    ]


def hydrodyn_table_key_conflicts(sets: dict[str, dict[str, Any]], hydro_file: str) -> list[str]:
    values = sets.get(hydro_file, {})
    return sorted(key for key in values if key in TABLE_COUNT_KEYS)


def apply_hydrodyn_tables_to_file(
    run_dir: pathlib.Path,
    case: dict[str, Any],
    sets: dict[str, dict[str, Any]],
    runtime_format: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    payload = case.get("hydrodyn_tables")
    if not isinstance(payload, dict):
        return [], []

    hydro_file = case.get("hydro_file", "FOCAL_C4_HydroDyn.dat")
    path = run_dir / hydro_file
    if not path.is_file():
        raise FileNotFoundError(f"HydroDyn file not found: {path}")

    warnings = []
    conflicts = hydrodyn_table_key_conflicts(sets, hydro_file)
    if conflicts:
        warnings.append(
            "HydroDyn table editor controls row-count keys; key-value overrides were superseded: "
            + ", ".join(conflicts)
        )

    target_format = str(payload.get("target_format") or "auto_v4_runtime")
    if target_format == "auto_v4_runtime" and runtime_format == "v5":
        target_format = "v5"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated, changes, table_warnings = apply_hydrodyn_tables(
        lines,
        payload,
        target_format=target_format,
        runtime_format=runtime_format,
    )
    path.write_text("\n".join(updated), encoding="utf-8")
    warnings.extend(table_warnings)
    return [{"file": hydro_file, **change} for change in changes], warnings


def _has_key(lines: list[str], key: str) -> bool:
    return any(len(line.split()) >= 2 and line.split()[1].lower() == key.lower() for line in lines)


def _replace_second_token_value(line: str, key: str, value: Any) -> str:
    match = re.match(rf"^(\s*)(\S+)(\s+)({re.escape(key)}\b.*)$", line)
    if not match:
        return line
    indent, old_value, _sep, rest = match.groups()
    return f"{indent}{value_text(value, old_value):<{max(13, len(old_value))}} {rest}"


def _ensure_inflowwind_v4(lines: list[str]) -> list[str]:
    """Add InflowWind fields required by the bundled OpenFAST v4 executable."""
    out = list(lines)
    if not _has_key(out, "VelInterpCubic"):
        for index, line in enumerate(out):
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "vflowang":
                out[index + 1:index + 1] = [
                    "False                  VelInterpCubic - Use cubic interpolation for velocity in time (false=linear, true=cubic) [Used with WindType=2,3,4,5,7]"
                ]
                break

    if not _has_key(out, "SensorType"):
        output_index = next(
            (
                i
                for i, line in enumerate(out)
                if "OUTPUT" in line.upper() and line.lstrip().startswith(("=", "-"))
            ),
            None,
        )
        if output_index is not None:
            out[output_index:output_index] = [
                "================== LIDAR Parameters ===========================================================================",
                "0                      SensorType  - Switch for lidar configuration (0=None, 1=Single Point Beam(s), 2=Continuous, 3=Pulsed)",
                "0                      NumPulseGate - Number of lidar measurement gates (used when SensorType = 3)",
                "30                     PulseSpacing - Distance between range gates (m) (used when SensorType = 3)",
                "0                      NumBeam     - Number of lidar measurement beams (0-5) (used when SensorType = 1)",
                "-200                   FocalDistanceX - Focal distance coordinate of the lidar beam in x direction relative to hub height (m)",
                "0                      FocalDistanceY - Focal distance coordinate of the lidar beam in y direction relative to hub height (m)",
                "0                      FocalDistanceZ - Focal distance coordinate of the lidar beam in z direction relative to hub height (m)",
                "0, 0, 0                RotorApexOffsetPos - Offset of the lidar from hub height (m)",
                "17                     URefLid     - Reference average wind speed for the lidar (m/s)",
                "0.25                   MeasurementInterval - Time between each measurement (s)",
                "False                  LidRadialVel - TRUE => return radial component, FALSE => return x direction estimate",
                "1                      ConsiderHubMotion - Flag whether to consider hub motion impact on lidar measurements",
            ]
    return out


def _ensure_aerodyn_v4(lines: list[str]) -> list[str]:
    """Add AeroDyn fields required by the bundled OpenFAST v4 executable."""
    out = list(lines)
    for index, line in enumerate(out):
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[1].lower()
        if key == "afaeromod":
            out[index] = _replace_second_token_value(line, parts[1], 1)
        elif key == "uamod":
            out[index] = _replace_second_token_value(line, parts[1], 0)
    if not _has_key(out, "Buoyancy"):
        for index, line in enumerate(out):
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "cavitcheck":
                out[index + 1:index + 1] = [
                    "False                  Buoyancy    - Include buoyancy effects? (flag)"
                ]
                break
    if not _has_key(out, "NacelleDrag"):
        for index, line in enumerate(out):
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "buoyancy":
                out[index + 1:index + 1] = [
                    "False                  NacelleDrag - Calculate nacelle drag loads? (flag)"
                ]
                break
    if not _has_key(out, "VolHub"):
        tower_index = next(
            (
                i
                for i, line in enumerate(out)
                if "TOWER INFLUENCE" in line.upper() and line.lstrip().startswith(("=", "-"))
            ),
            None,
        )
        if tower_index is not None:
            out[tower_index:tower_index] = [
                "======  Hub Properties ============================================================================== [used only when Buoyancy=True]",
                "0                      VolHub      - Hub volume (m^3)",
                "0                      HubCenBx    - Hub center of buoyancy x direction offset (m)",
                "======  Nacelle Properties ========================================================================== [used only when Buoyancy=True or NacelleDrag=True]",
                "0                      VolNac      - Nacelle volume (m^3)",
                "0, 0, 0                NacCenB     - Position of nacelle center of buoyancy from yaw bearing in nacelle coordinates (m)",
                "0, 0, 0                NacArea     - Projected nacelle areas in nacelle coordinates (m^2)",
                "0, 0, 0                NacCd       - Nacelle drag coefficients (-)",
                "0, 0, 0                NacDragAC   - Position of nacelle aerodynamic center from yaw bearing in nacelle coordinates (m)",
                "======  Tail fin AeroDynamics ========================================================================",
                "False                  TFinAero    - Calculate tail fin aerodynamics model (flag)",
                "\"unused\"               TFinFile    - Input file for tail fin aerodynamics [used only when TFinAero=True]",
            ]
    for index, line in enumerate(out):
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower() == "numtwrnds":
            try:
                node_count = int(float(parts[0]))
            except ValueError:
                break
            header_index = index + 1
            unit_index = index + 2
            row_start = index + 3
            if header_index < len(out) and "TwrCb" not in out[header_index]:
                out[header_index] = out[header_index].rstrip() + "       TwrCb"
                if unit_index < len(out):
                    out[unit_index] = out[unit_index].rstrip() + "         (-)"
                for row_index in range(row_start, min(row_start + node_count, len(out))):
                    row_parts = out[row_index].split()
                    if len(row_parts) == 4:
                        out[row_index] = out[row_index].rstrip() + "        0.0"
            break
    return out


def copy_model(run_dir: pathlib.Path, overwrite: bool, model_template: pathlib.Path) -> None:
    if run_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Run directory exists: {run_dir}. Use --overwrite or choose another name.")
        shutil.rmtree(run_dir)
    shutil.copytree(model_template, run_dir)


def prepare_openfast_inputs(run_dir: pathlib.Path, compatibility: str, runtime_format: str) -> list[dict[str, str]]:
    """Apply the same OpenFAST v4 compatibility fixes used by the free-decay workflow."""
    fixes: list[dict[str, str]] = []
    if compatibility != "focal_c4_v4" or runtime_format != "v4":
        return fixes

    ed_path = run_dir / "FOCAL_C4_ElastoDyn.dat"
    if ed_path.is_file():
        lines = ed_path.read_text(encoding="utf-8", errors="replace").splitlines()
        before = list(lines)
        _ensure_platform_cross_inertia(lines)
        _ensure_yaw_friction(lines)
        if lines != before:
            ed_path.write_text("\n".join(lines), encoding="utf-8")
            fixes.append({"file": ed_path.name, "fix": "OpenFAST v4 ElastoDyn inertia/yaw-friction fields"})

    hd_path = run_dir / "FOCAL_C4_HydroDyn.dat"
    if hd_path.is_file():
        lines = hd_path.read_text(encoding="utf-8", errors="replace").splitlines()
        updated = _ensure_hydrodyn_v4(lines)
        if updated != lines:
            hd_path.write_text("\n".join(updated), encoding="utf-8")
            fixes.append({"file": hd_path.name, "fix": "OpenFAST v4 HydroDyn layout"})

    ifw_path = run_dir / "FOCAL_C4_InflowFile.dat"
    if ifw_path.is_file():
        lines = ifw_path.read_text(encoding="utf-8", errors="replace").splitlines()
        updated = _ensure_inflowwind_v4(lines)
        if updated != lines:
            ifw_path.write_text("\n".join(updated), encoding="utf-8")
            fixes.append({"file": ifw_path.name, "fix": "OpenFAST v4 InflowWind VelInterpCubic/LIDAR fields"})

    for aero_name in ["FOCAL_C4_AeroDyn15_aboverated.dat", "FOCAL_C4_AeroDyn15_rated.dat"]:
        aero_path = run_dir / aero_name
        if aero_path.is_file():
            lines = aero_path.read_text(encoding="utf-8", errors="replace").splitlines()
            updated = _ensure_aerodyn_v4(lines)
            if updated != lines:
                aero_path.write_text("\n".join(updated), encoding="utf-8")
                fixes.append({"file": aero_path.name, "fix": "OpenFAST v4 AeroDyn fields/tower table/UA compatibility"})

    md_path = run_dir / "FOCAL_C4_MoorDyn.dat"
    if md_path.is_file():
        lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
        updated = _ensure_moordyn_v2(lines)
        if updated != lines:
            md_path.write_text("\n".join(updated), encoding="utf-8")
            fixes.append({"file": md_path.name, "fix": "MoorDyn v2 table layout"})

    return fixes


def run_openfast(run_dir: pathlib.Path, fst_name: str, timeout: float, openfast_exe: pathlib.Path) -> dict[str, Any]:
    t0 = time.time()
    proc = subprocess.Popen(
        [str(openfast_exe), fst_name],
        cwd=str(run_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    output_parts: list[str] = []
    tail = deque(maxlen=240)
    timed_out = False
    assert proc.stdout is not None
    for line in proc.stdout:
        output_parts.append(line)
        tail.append(line)
        print(line, end="", flush=True)
        if time.time() - t0 > timeout:
            timed_out = True
            proc.kill()
            break
    try:
        returncode = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = proc.wait()
        timed_out = True
    walltime = time.time() - t0
    if timed_out:
        message = f"\nOpenFAST timed out after {timeout:g} seconds.\n"
        output_parts.append(message)
        tail.append(message)
        print(message, end="", flush=True)
        if returncode == 0:
            returncode = -9
    stdout = "".join(output_parts)
    log_path = run_dir / "openfast_console.log"
    log_path.write_text(stdout + "\n\nSTDERR:\n", encoding="utf-8")
    out_path = run_dir / f"{pathlib.Path(fst_name).stem}.out"
    return {
        "returncode": returncode,
        "ok": returncode == 0 and out_path.is_file(),
        "walltime_s": walltime,
        "stdout_tail": "".join(tail)[-2000:],
        "stderr_tail": "",
        "log": str(log_path),
        "out": str(out_path),
    }


def run_case(case: dict[str, Any], scenario_name: str, out_root: pathlib.Path, args) -> dict[str, Any]:
    case_name = slug(case.get("name") or args.name or f"case_{dt.datetime.now():%Y%m%d_%H%M%S}")
    scenario_dir = out_root / slug(scenario_name)
    run_dir = scenario_dir / case_name
    fst_name = case.get("fst", args.fst)
    copy_model(run_dir, overwrite=args.overwrite, model_template=args.model_template)
    compatibility_fixes = prepare_openfast_inputs(run_dir, compatibility=args.compatibility, runtime_format=args.runtime_format)

    sets = merge_case_sets(case, args)
    changes = apply_sets(run_dir, sets)
    matrix_changes = apply_matrix_edits_to_file(run_dir, case, args)
    hydrodyn_table_changes, hydrodyn_table_warnings = apply_hydrodyn_tables_to_file(
        run_dir,
        case,
        sets,
        runtime_format=args.runtime_format,
    )

    timeout = float(case.get("timeout", args.timeout))
    execution = {"ok": True, "skipped": True, "reason": "generate_only"}
    if not args.generate_only:
        execution = run_openfast(run_dir, fst_name=fst_name, timeout=timeout, openfast_exe=args.openfast_exe)

    summary = {
        "scenario": scenario_name,
        "case": case_name,
        "run_dir": str(run_dir),
        "fst": str(run_dir / fst_name),
        "model_template": str(args.model_template),
        "openfast_exe": str(args.openfast_exe),
        "runtime_format": args.runtime_format,
        "compatibility": args.compatibility,
        "changes": changes,
        "matrix_changes": matrix_changes,
        "hydrodyn_table_changes": hydrodyn_table_changes,
        "hydrodyn_table_warnings": hydrodyn_table_warnings,
        "compatibility_fixes": compatibility_fixes,
        "execution": execution,
        "ok": bool(execution.get("ok")),
        "notes": case.get("notes", ""),
    }
    summary_path = run_dir / "scenario_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary"] = str(summary_path)
    return summary


def load_scenario(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def scenario_from_args(args) -> dict[str, Any]:
    name = args.scenario_name or "manual_general"
    case_name = args.name or f"manual_{dt.datetime.now():%Y%m%d_%H%M%S}"
    return {"name": name, "cases": [{"name": case_name, "fst": args.fst, "set": {}}]}


def list_scenarios() -> int:
    folder = ROOT / "scenarios"
    for path in sorted(folder.glob("*.json")):
        try:
            data = load_scenario(path)
            count = len(data.get("cases", []))
            print(f"{path.name:<28} cases={count:<3} {data.get('description', '')}")
        except Exception as exc:
            print(f"{path.name:<28} ERROR {exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None, help="Path to scenarios/*.json. If omitted, run one ad-hoc case.")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--scenario-name", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--fst", default="FOCAL_C4.fst")
    parser.add_argument("--model", default=None, help="Model template directory to copy for each case.")
    parser.add_argument("--openfast-exe", default=None, help="OpenFAST executable path.")
    parser.add_argument("--runtime-format", choices=["v4", "v5"], default="v4", help="HydroDyn table/runtime input format.")
    parser.add_argument("--compatibility", choices=["focal_c4_v4", "none"], default="focal_c4_v4", help="Input compatibility fixes to apply after copying the model.")
    parser.add_argument("--out-root", default=str(DEFAULT_RUNS))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--continue-on-fail", action="store_true")
    parser.add_argument("--timeout", type=float, default=7200.0)
    parser.add_argument("--tmax", type=float, default=None)
    parser.add_argument("--wind-speed", type=float, default=None)
    parser.add_argument("--wave-mod", type=int, default=None)
    parser.add_argument("--wave-hs", type=float, default=None)
    parser.add_argument("--wave-tp", type=float, default=None)
    parser.add_argument("--set", action="append", default=[], help="Override as file:key=value, e.g. FOCAL_C4.fst:TMax=60")
    parser.add_argument(
        "--matrix-edit",
        action="append",
        default=[],
        help="HydroDyn matrix edit as BLOCK,i,j,value with 1-based indices.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.model_template = pathlib.Path(args.model) if args.model else MODEL_TEMPLATE
    args.openfast_exe = pathlib.Path(args.openfast_exe) if args.openfast_exe else OPENFAST_EXE
    if not args.model_template.is_absolute():
        args.model_template = ROOT / args.model_template
    if not args.openfast_exe.is_absolute():
        args.openfast_exe = ROOT / args.openfast_exe
    if args.list_scenarios:
        return list_scenarios()
    if not args.model_template.is_dir():
        print(f"Model template not found: {args.model_template}", file=sys.stderr)
        return 1
    if not args.openfast_exe.is_file() and not args.generate_only:
        print(f"OpenFAST exe not found: {args.openfast_exe}", file=sys.stderr)
        return 1

    if args.scenario:
        scenario_path = pathlib.Path(args.scenario)
        if not scenario_path.is_absolute():
            scenario_path = ROOT / scenario_path
        scenario = load_scenario(scenario_path)
        scenario_name = args.scenario_name or scenario.get("name") or scenario_path.stem
    else:
        scenario = scenario_from_args(args)
        scenario_name = scenario["name"]

    out_root = pathlib.Path(args.out_root)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    scenario_dir = out_root / slug(scenario_name)
    scenario_dir.mkdir(parents=True, exist_ok=True)
    report = scenario_dir / "scenario_results.json"

    cases = list(scenario.get("cases", []))
    if not cases:
        report.write_text("[]", encoding="utf-8")
        print(f"No cases found in scenario {scenario_name!r}.", file=sys.stderr, flush=True)
        print(f"REPORT: {report}", flush=True)
        return 1

    summaries = []
    all_ok = True
    for index, case in enumerate(cases, start=1):
        try:
            print(f"[{index}/{len(cases)}] RUNNING {slug(case.get('name') or f'case_{index}')}", flush=True)
            summary = run_case(case, scenario_name=scenario_name, out_root=out_root, args=args)
            summaries.append(summary)
            report.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[{index}] {'OK' if summary['ok'] else 'FAILED'} {summary['case']} -> {summary['run_dir']}", flush=True)
            all_ok = all_ok and summary["ok"]
            if not summary["ok"] and not args.continue_on_fail:
                break
        except Exception as exc:
            summary = {
                "scenario": scenario_name,
                "case": slug(case.get("name") or f"case_{index}"),
                "ok": False,
                "error": str(exc),
            }
            summaries.append(summary)
            report.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
            all_ok = False
            print(f"[{index}] FAILED: {exc}", file=sys.stderr, flush=True)
            if not args.continue_on_fail:
                break

    report.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"REPORT: {report}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
