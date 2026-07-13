# -*- coding: utf-8 -*-
"""Configuration and validation for optional OpenFAST companion tools."""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tool_profiles.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "local_tool_profiles.json"
ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
KNOWN_EXECUTABLES = {
    "openfast": ("openfast_x64.exe", "OpenFAST_x64.exe", "openfast.exe", "OpenFAST.exe", "openfast"),
    "turbsim": ("TurbSim_x64.exe", "TurbSim.exe", "turbsim"),
    "fastfarm": ("FAST.Farm_x64.exe", "FAST.Farm.exe", "FAST.Farm"),
    "aerodyn_driver": ("AeroDyn_Driver_x64.exe", "AeroDyn_Driver.exe"),
    "hydrodyn_driver": ("HydroDyn_Driver_x64.exe", "HydroDyn_Driver.exe"),
    "beamdyn_driver": ("BeamDyn_Driver_x64.exe", "BeamDyn_Driver.exe"),
    "subdyn_driver": ("SubDyn_Driver_x64.exe", "SubDyn_Driver.exe"),
}


def _read(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"tools": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _expanded(value: Any) -> str:
    text = str(value or "")
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        value = os.environ.get(match.group(1))
        if value is None:
            missing = True
            return ""
        return value

    text = ENV_RE.sub(replace, text)
    return "" if missing and not text.strip() else os.path.expandvars(text)


def _merged() -> list[dict[str, Any]]:
    rows = {str(row.get("id")): dict(row) for row in _read(CONFIG_PATH).get("tools", [])}
    for row in _read(LOCAL_CONFIG_PATH).get("tools", []):
        tool_id = str(row.get("id"))
        rows[tool_id] = {**rows.get(tool_id, {}), **dict(row)}
    return list(rows.values())


def _discover_executable(tool_id: str) -> str:
    for name in KNOWN_EXECUTABLES.get(tool_id, ()):
        found = shutil.which(name)
        if found:
            return found
        for directory in (ROOT / "bin", ROOT.parent / "bin"):
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)
    return ""


def tool_profiles() -> list[dict[str, Any]]:
    result = []
    for raw in _merged():
        row = dict(raw)
        path = _expanded(row.get("path"))
        if not path and row.get("kind") == "process":
            path = _discover_executable(str(row.get("id")))
        path_obj = pathlib.Path(path) if path else None
        row["path"] = str(path_obj) if path_obj else ""
        row["exists"] = bool(path_obj and path_obj.is_file())
        row["runnable"] = bool(row["exists"] and row.get("kind") == "process")
        row["status"] = "ready" if row["exists"] else "not-installed"
        result.append(row)
    return result


def select_tool(tool_id: str) -> dict[str, Any]:
    for row in tool_profiles():
        if row.get("id") == tool_id:
            return row
    raise KeyError(f"Unknown external tool profile: {tool_id}")


def update_local_tool(tool_id: str, path: str) -> dict[str, Any]:
    known_ids = {str(row.get("id")) for row in _merged()}
    if tool_id not in known_ids:
        raise KeyError(f"Unknown external tool profile: {tool_id}")
    current = _read(LOCAL_CONFIG_PATH)
    rows = {str(row.get("id")): dict(row) for row in current.get("tools", [])}
    rows[tool_id] = {"id": tool_id, "path": str(path).strip()}
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG_PATH.write_text(
        json.dumps({"tools": list(rows.values())}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return select_tool(tool_id)


def build_tool_command(tool: dict[str, Any], input_file: pathlib.Path) -> list[str]:
    if not tool.get("runnable"):
        raise FileNotFoundError(f"{tool.get('name', tool.get('id'))} executable is not configured")
    suffixes = {str(value).lower() for value in tool.get("accepts") or []}
    if suffixes and input_file.suffix.lower() not in suffixes:
        raise ValueError(f"{tool.get('name')} does not accept {input_file.suffix or 'files without an extension'}")
    if not input_file.is_file():
        raise FileNotFoundError(f"External-tool input file not found: {input_file}")
    return [str(tool["path"]), input_file.name]


def run_tool(tool: dict[str, Any], input_file: pathlib.Path, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    command = build_tool_command(tool, input_file)
    return subprocess.run(
        command,
        cwd=str(input_file.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
