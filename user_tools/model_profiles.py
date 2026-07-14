# -*- coding: utf-8 -*-
"""Model and OpenFAST runtime profile loading for the local GUI."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
from typing import Any

from openfast_input import discover_model_dependencies, structure_file_ids


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_profiles.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "local_model_profiles.json"


def _expand_path(value: str | os.PathLike | None) -> pathlib.Path | None:
    if value is None or not str(value).strip():
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


def _write_config(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _merge_configs() -> dict[str, list[dict[str, Any]]]:
    merged = _read_config(CONFIG_PATH)
    local = _read_config(LOCAL_CONFIG_PATH)
    for key in ("models", "runtimes"):
        rows = {str(item.get("id")): dict(item) for item in merged.get(key, [])}
        for item in local.get(key, []):
            item_id = str(item.get("id"))
            rows[item_id] = {**rows.get(item_id, {}), **dict(item)}
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


def materialize_model_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return a model profile with absolute paths and filesystem availability."""
    return _materialize_profile(profile)


def materialize_runtime_profile(runtime: dict[str, Any], include_version: bool = False) -> dict[str, Any]:
    """Return a runtime profile with absolute paths and filesystem availability."""
    return _materialize_runtime(runtime, include_version=include_version)


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


def _require_profile(profile_id: str, rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for row in rows:
        if row.get("id") == profile_id:
            return row
    raise ValueError(f"Unknown {kind} profile: {profile_id}")


def preview_profile_paths(
    model_id: str,
    model_path: str | os.PathLike | None,
    runtime_id: str,
    runtime_path: str | os.PathLike | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize an unsaved model/runtime path pair for validation."""
    model = dict(_require_profile(model_id, model_profiles(), "model"))
    runtime = dict(_require_profile(runtime_id, runtime_profiles(), "runtime"))
    if model_path is not None:
        model["path"] = str(model_path).strip()
    if runtime_path is not None:
        runtime["path"] = str(runtime_path).strip()
    return materialize_model_profile(model), materialize_runtime_profile(runtime, include_version=True)


def save_local_profile_paths(
    model_id: str,
    model_path: str | os.PathLike,
    runtime_id: str,
    runtime_path: str | os.PathLike,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist local path-only overrides without changing the shared profile file."""
    model_text = str(model_path).strip()
    runtime_text = str(runtime_path).strip()
    if not model_text or not runtime_text:
        raise ValueError("Model root and OpenFAST executable paths are both required")

    model, runtime = preview_profile_paths(model_id, model_text, runtime_id, runtime_text)
    if not model.get("exists"):
        raise FileNotFoundError(f"Model root does not exist: {model.get('path')}")
    if not model.get("fstExists"):
        raise FileNotFoundError(f"Main .fst input does not exist: {model.get('fstPath')}")
    if not runtime.get("exists"):
        raise FileNotFoundError(f"OpenFAST executable does not exist: {runtime.get('path')}")

    local = _read_config(LOCAL_CONFIG_PATH)
    local.setdefault("models", [])
    local.setdefault("runtimes", [])

    def set_path(rows: list[dict[str, Any]], profile_id: str, value: str) -> list[dict[str, Any]]:
        updated = [dict(row) for row in rows]
        for row in updated:
            if row.get("id") == profile_id:
                row["path"] = value
                break
        else:
            updated.append({"id": profile_id, "path": value})
        return updated

    local["models"] = set_path(local["models"], model_id, model_text)
    local["runtimes"] = set_path(local["runtimes"], runtime_id, runtime_text)
    _write_config(LOCAL_CONFIG_PATH, local)
    return preview_profile_paths(model_id, model_text, runtime_id, runtime_text)


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


def dependency_structure_for_model(model: dict[str, Any]) -> dict[str, Any]:
    model_path = pathlib.Path(model["path"])
    return discover_model_dependencies(
        model_path,
        str(model.get("fst") or ""),
        configured_files=model.get("inputFiles") or [],
    )


def input_files_for_model(model: dict[str, Any], structure: dict[str, Any] | None = None) -> list[str]:
    structure = structure or dependency_structure_for_model(model)
    return structure_file_ids(structure)
