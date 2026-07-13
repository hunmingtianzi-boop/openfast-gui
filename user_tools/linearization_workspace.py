# -*- coding: utf-8 -*-
"""Catalog and analyze OpenFAST ``.lin`` linearization files."""
from __future__ import annotations

import pathlib
import re
from typing import Any

import numpy as np


COUNT_PATTERNS = {
    "continuousStates": re.compile(r"Number of continuous states:\s*(\d+)", re.IGNORECASE),
    "discreteStates": re.compile(r"Number of discrete states:\s*(\d+)", re.IGNORECASE),
    "constraintStates": re.compile(r"Number of constraint states:\s*(\d+)", re.IGNORECASE),
    "inputs": re.compile(r"Number of inputs:\s*(\d+)", re.IGNORECASE),
    "outputs": re.compile(r"Number of outputs:\s*(\d+)", re.IGNORECASE),
}
TIME_RE = re.compile(r"Simulation time:\s*([+\-0-9.EeDd]+)", re.IGNORECASE)
MATRIX_RE = re.compile(r"^\s*([ABCD])\s*:\s*(?:(\d+)\s*[xX]\s*(\d+))?\s*$")
NUMBER_RE = re.compile(r"^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+\-]?\d+)?$")
MAX_MATRIX_DIMENSION = 2500


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_linearization_path(runs_root: pathlib.Path, file_id: str) -> pathlib.Path:
    root = runs_root.resolve()
    path = (root / pathlib.PurePosixPath(str(file_id).replace("\\", "/"))).resolve()
    if not _within(path, root) or path.suffix.lower() != ".lin" or not path.is_file():
        raise FileNotFoundError(f"Linearization file not found: {file_id}")
    return path


def _float_tokens(line: str) -> list[float] | None:
    tokens = line.split()
    if not tokens or not all(NUMBER_RE.fullmatch(token) for token in tokens):
        return None
    return [float(token.replace("D", "E").replace("d", "e")) for token in tokens]


def _matrix_dimensions(name: str, counts: dict[str, int]) -> tuple[int, int] | None:
    nx = counts.get("continuousStates", 0)
    nu = counts.get("inputs", 0)
    ny = counts.get("outputs", 0)
    return {
        "A": (nx, nx),
        "B": (nx, nu),
        "C": (ny, nx),
        "D": (ny, nu),
    }.get(name)


def _read_matrix(
    lines: list[str],
    marker_index: int,
    explicit_rows: int | None,
    explicit_cols: int | None,
    expected: tuple[int, int] | None,
) -> tuple[np.ndarray, int]:
    row_count = explicit_rows or (expected[0] if expected else 0)
    col_count = explicit_cols or (expected[1] if expected else 0)
    if row_count > MAX_MATRIX_DIMENSION or col_count > MAX_MATRIX_DIMENSION:
        raise ValueError(f"Linearization matrix exceeds {MAX_MATRIX_DIMENSION} rows or columns")
    rows: list[list[float]] = []
    index = marker_index + 1
    while index < len(lines):
        values = _float_tokens(lines[index])
        if values is None:
            if rows:
                break
            index += 1
            continue
        if col_count and len(values) != col_count:
            if rows:
                break
            index += 1
            continue
        if not col_count:
            col_count = len(values)
        rows.append(values)
        index += 1
        if row_count and len(rows) >= row_count:
            break
    if not rows:
        raise ValueError(f"No numeric rows found after matrix marker on line {marker_index + 1}")
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"Ragged linearization matrix after line {marker_index + 1}")
    return np.asarray(rows, dtype=float), index


def _state_descriptions(lines: list[str], header: str, expected: int) -> list[str]:
    start = next((index for index, line in enumerate(lines) if header.lower() in line.lower()), None)
    if start is None:
        return []
    rows: list[str] = []
    for line in lines[start + 1 :]:
        if MATRIX_RE.match(line) or line.lower().startswith("order of"):
            break
        match = re.match(r"^\s*(\d+)\s+(.*\S)\s*$", line)
        if not match:
            continue
        rows.append(match.group(2).strip())
        if expected and len(rows) >= expected:
            break
    return rows


def parse_linearization_file(path: pathlib.Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    counts = {name: 0 for name in COUNT_PATTERNS}
    simulation_time = None
    for line in lines[:160]:
        for name, pattern in COUNT_PATTERNS.items():
            match = pattern.search(line)
            if match:
                counts[name] = int(match.group(1))
        time_match = TIME_RE.search(line)
        if time_match:
            simulation_time = float(time_match.group(1).replace("D", "E").replace("d", "e"))

    matrices: dict[str, np.ndarray] = {}
    index = 0
    while index < len(lines):
        match = MATRIX_RE.match(lines[index])
        if not match:
            index += 1
            continue
        name = match.group(1).upper()
        matrix, next_index = _read_matrix(
            lines,
            index,
            int(match.group(2)) if match.group(2) else None,
            int(match.group(3)) if match.group(3) else None,
            _matrix_dimensions(name, counts),
        )
        matrices[name] = matrix
        index = next_index

    state_names = _state_descriptions(lines, "Order of continuous states", counts["continuousStates"])
    input_names = _state_descriptions(lines, "Order of inputs", counts["inputs"])
    output_names = _state_descriptions(lines, "Order of outputs", counts["outputs"])
    return {
        "path": str(path),
        "simulationTime": simulation_time,
        "counts": counts,
        "stateNames": state_names,
        "inputNames": input_names,
        "outputNames": output_names,
        "matrices": matrices,
    }


def modal_analysis(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    matrix = parsed.get("matrices", {}).get("A")
    if matrix is None:
        raise ValueError("The linearization file does not contain an A matrix")
    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"A matrix must be square, received {matrix.shape}")
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    names = list(parsed.get("stateNames") or [])
    modes: list[dict[str, Any]] = []
    for index, eigenvalue in enumerate(eigenvalues):
        if eigenvalue.imag < -1e-8:
            continue
        magnitude = abs(eigenvalue)
        vector = np.abs(eigenvectors[:, index])
        dominant_index = int(np.argmax(vector)) if vector.size else -1
        modes.append(
            {
                "real": float(eigenvalue.real),
                "imag": float(eigenvalue.imag),
                "frequencyHz": float(abs(eigenvalue.imag) / (2.0 * np.pi)),
                "naturalFrequencyHz": float(magnitude / (2.0 * np.pi)),
                "dampingRatio": float(-eigenvalue.real / magnitude) if magnitude else 0.0,
                "stable": bool(eigenvalue.real <= 1e-8),
                "dominantStateIndex": dominant_index + 1 if dominant_index >= 0 else None,
                "dominantState": names[dominant_index] if 0 <= dominant_index < len(names) else f"State {dominant_index + 1}",
            }
        )
    modes.sort(key=lambda row: (row["frequencyHz"], row["naturalFrequencyHz"], row["real"]))
    for number, mode in enumerate(modes, start=1):
        mode["mode"] = number
    return modes


def discover_linearizations(runs_root: pathlib.Path) -> dict[str, Any]:
    root = runs_root.resolve()
    files = []
    if root.is_dir():
        for path in root.rglob("*.lin"):
            try:
                relative = path.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            parts = pathlib.PurePosixPath(relative).parts
            files.append(
                {
                    "id": relative,
                    "name": path.name,
                    "scenario": parts[0] if len(parts) > 0 else "",
                    "case": parts[1] if len(parts) > 1 else "",
                    "size": path.stat().st_size,
                    "modified": path.stat().st_mtime,
                }
            )
    files.sort(key=lambda row: (row["scenario"], row["case"], row["name"]))
    return {"files": files, "count": len(files)}


def analyze_linearization(runs_root: pathlib.Path, file_id: str) -> dict[str, Any]:
    path = resolve_linearization_path(runs_root, file_id)
    parsed = parse_linearization_file(path)
    matrices = parsed.pop("matrices")
    return {
        "id": file_id,
        **parsed,
        "matrixShapes": {name: list(matrix.shape) for name, matrix in matrices.items()},
        "modes": modal_analysis({**parsed, "matrices": matrices}),
    }

