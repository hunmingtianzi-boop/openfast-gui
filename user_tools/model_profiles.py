# -*- coding: utf-8 -*-
"""Model and OpenFAST runtime profile loading for the local GUI."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_profiles.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "local_model_profiles.json"


def _expand_path(value: str | os.PathLike | None) -> pathlib.Path | None:
    if value is None:
        return None
    text = str(value)
    text = text.replace("${ROOT}", str(ROOT))
    text = text.replace("${OPENFAST_ROOT}", str(ROOT))
    text = os.path.expandvars(text)
    return pathlib.Path(text)


def _read_config(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {"models": [], "runtimes": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _merge_configs() -> dict[str, list[dict[str, Any]]]:
    merged = _read_config(CONFIG_PATH)
    local = _read_config(LOCAL_CONFIG_PATH)
    for key in ("models", "runtimes"):
        rows = {str(item.get("id")): dict(item) for item in merged.get(key, [])}
        for item in local.get(key, []):
            rows[str(item.get("id"))] = dict(item)
        merged[key] = list(rows.values())
    return merged


def _materialize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    row = dict(profile)
    path = _expand_path(row.get("path"))
    row["path"] = str(path) if path else ""
    row["exists"] = bool(path and path.is_dir())
    fst = row.get("fst") or ""
    row["fstPath"] = str(path / fst) if path and fst else ""
    row["fstExists"] = bool(path and fst and (path / fst).is_file())
    hydro = row.get("hydroFile") or ""
    row["hydroPath"] = str(path / hydro) if path and hydro else ""
    row["hydroExists"] = bool(path and hydro and (path / hydro).is_file())
    return row


def _materialize_runtime(runtime: dict[str, Any], include_version: bool = False) -> dict[str, Any]:
    row = dict(runtime)
    path = _expand_path(row.get("path"))
    row["path"] = str(path) if path else ""
    row["exists"] = bool(path and path.is_file())
    if include_version:
        row["version"] = openfast_version(path) if path and path.is_file() else ""
    return row


def model_profiles() -> list[dict[str, Any]]:
    return [_materialize_profile(item) for item in _merge_configs().get("models", [])]


def runtime_profiles(include_version: bool = False) -> list[dict[str, Any]]:
    return [_materialize_runtime(item, include_version=include_version) for item in _merge_configs().get("runtimes", [])]


def select_model(model_id: str | None = None) -> dict[str, Any]:
    rows = model_profiles()
    if model_id:
        for row in rows:
            if row.get("id") == model_id:
                return row
    for row in rows:
        if row.get("exists") and row.get("fstExists"):
            return row
    if rows:
        return rows[0]
    raise ValueError("No model profiles configured.")


def select_runtime(runtime_id: str | None = None, model: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = runtime_profiles(include_version=True)
    preferred = runtime_id or (model or {}).get("preferredRuntime")
    if preferred:
        for row in rows:
            if row.get("id") == preferred:
                return row
    for row in rows:
        if row.get("exists"):
            return row
    if rows:
        return rows[0]
    raise ValueError("No OpenFAST runtime profiles configured.")


def openfast_version(exe: pathlib.Path) -> str:
    try:
        proc = subprocess.run(
            [str(exe), "-v"],
            cwd=str(exe.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return f"version check failed: {exc}"
    for line in proc.stdout.splitlines():
        if line.startswith("OpenFAST-"):
            return line.strip()
    return ""


def quoted_value(line: str) -> str | None:
    match = re.match(r'^\s*"([^"]*)"\s+([A-Za-z][A-Za-z0-9_()]+)\b', line)
    if not match:
        return None
    value = match.group(1)
    if value.lower() in {"", "unused", "none"}:
        return None
    return value


def input_files_for_model(model: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for name in [model.get("fst"), *(model.get("inputFiles") or [])]:
        if name and name not in files:
            files.append(str(name))
    model_path = pathlib.Path(model["path"])
    fst_name = model.get("fst")
    fst_path = model_path / str(fst_name or "")
    if fst_path.is_file():
        for line in fst_path.read_text(encoding="utf-8", errors="replace").splitlines():
            value = quoted_value(line)
            if value and value not in files and (model_path / value).is_file():
                files.append(value)
    return files
