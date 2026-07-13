# -*- coding: utf-8 -*-
"""Discover and parse OpenFAST VTK geometry for the browser viewer."""
from __future__ import annotations

import pathlib
import re
from typing import Any
import xml.etree.ElementTree as ET


VTK_SUFFIXES = {".vtk", ".vtp", ".pvd"}
MAX_POINTS = 250_000
MAX_PRIMITIVES = 500_000


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_visualization_path(runs_root: pathlib.Path, file_id: str) -> pathlib.Path:
    root = runs_root.resolve()
    path = (root / pathlib.PurePosixPath(str(file_id).replace("\\", "/"))).resolve()
    if not _within(path, root) or path.suffix.lower() not in VTK_SUFFIXES or not path.is_file():
        raise FileNotFoundError(f"VTK file not found: {file_id}")
    return path


def discover_visualizations(runs_root: pathlib.Path) -> dict[str, Any]:
    root = runs_root.resolve()
    files = []
    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VTK_SUFFIXES:
                continue
            try:
                relative = path.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            parts = pathlib.PurePosixPath(relative).parts
            files.append(
                {
                    "id": relative,
                    "name": path.name,
                    "format": path.suffix.lower().lstrip("."),
                    "scenario": parts[0] if len(parts) > 0 else "",
                    "case": parts[1] if len(parts) > 1 else "",
                    "size": path.stat().st_size,
                    "modified": path.stat().st_mtime,
                }
            )
    files.sort(key=lambda row: (row["scenario"], row["case"], row["name"]))
    return {"files": files, "count": len(files)}


def _bounds(points: list[list[float]]) -> dict[str, list[float]]:
    if not points:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "center": [0.0, 0.0, 0.0]}
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    center = [(minimum[axis] + maximum[axis]) / 2.0 for axis in range(3)]
    return {"min": minimum, "max": maximum, "center": center}


def _cells_to_segments(connectivity: list[int], offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    start = 0
    for end in offsets:
        cell = connectivity[start:end]
        result.extend([[cell[index], cell[index + 1]] for index in range(max(0, len(cell) - 1))])
        start = end
        if len(result) >= MAX_PRIMITIVES:
            break
    return result[:MAX_PRIMITIVES]


def _cells_to_triangles(connectivity: list[int], offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    start = 0
    for end in offsets:
        cell = connectivity[start:end]
        if len(cell) >= 3:
            result.extend([[cell[0], cell[index], cell[index + 1]] for index in range(1, len(cell) - 1)])
        start = end
        if len(result) >= MAX_PRIMITIVES:
            break
    return result[:MAX_PRIMITIVES]


def _numbers(text: str | None, cast=float) -> list[Any]:
    if not text:
        return []
    return [cast(token.replace("D", "E").replace("d", "e")) for token in text.split()]


def _find_data_array(parent: ET.Element | None, name: str | None = None) -> ET.Element | None:
    if parent is None:
        return None
    arrays = [element for element in parent.iter() if element.tag.rsplit("}", 1)[-1] == "DataArray"]
    if name is not None:
        for element in arrays:
            if element.attrib.get("Name", "").lower() == name.lower():
                return element
    return arrays[0] if arrays else None


def _require_ascii(array: ET.Element | None, label: str) -> ET.Element:
    if array is None:
        raise ValueError(f"VTP file is missing {label} DataArray")
    data_format = array.attrib.get("format", "ascii").lower()
    if data_format != "ascii":
        raise ValueError(f"Browser preview currently requires ASCII VTP DataArray; {label} uses {data_format}")
    return array


def parse_vtp(path: pathlib.Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    piece = next((element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "Piece"), None)
    if piece is None:
        raise ValueError("VTP file does not contain a Piece element")
    points_parent = next((element for element in piece if element.tag.rsplit("}", 1)[-1] == "Points"), None)
    point_values = _numbers(_require_ascii(_find_data_array(points_parent), "Points").text, float)
    points = [point_values[index : index + 3] for index in range(0, min(len(point_values), MAX_POINTS * 3), 3)]
    if points and len(points[-1]) != 3:
        points.pop()

    segments: list[list[int]] = []
    triangles: list[list[int]] = []
    for child in piece:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag not in {"Lines", "Polys", "Strips"}:
            continue
        connectivity = _numbers(_require_ascii(_find_data_array(child, "connectivity"), f"{tag} connectivity").text, int)
        offsets = _numbers(_require_ascii(_find_data_array(child, "offsets"), f"{tag} offsets").text, int)
        if tag == "Lines":
            segments.extend(_cells_to_segments(connectivity, offsets))
        else:
            triangles.extend(_cells_to_triangles(connectivity, offsets))

    return {
        "format": "vtp",
        "points": points,
        "segments": segments[:MAX_PRIMITIVES],
        "triangles": triangles[:MAX_PRIMITIVES],
        "bounds": _bounds(points),
        "truncated": len(point_values) > MAX_POINTS * 3 or len(segments) > MAX_PRIMITIVES or len(triangles) > MAX_PRIMITIVES,
    }


def parse_legacy_vtk(path: pathlib.Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if any("BINARY" in line.upper() for line in lines[:8]):
        raise ValueError("Browser preview currently requires ASCII legacy VTK")
    points: list[list[float]] = []
    segments: list[list[int]] = []
    triangles: list[list[int]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        point_match = re.match(r"POINTS\s+(\d+)\s+\w+", stripped, re.IGNORECASE)
        if point_match:
            expected = int(point_match.group(1))
            values: list[float] = []
            index += 1
            while index < len(lines) and len(values) < expected * 3:
                values.extend(_numbers(lines[index], float))
                index += 1
            points = [values[offset : offset + 3] for offset in range(0, min(len(values), MAX_POINTS * 3), 3)]
            continue
        cell_match = re.match(r"(LINES|POLYGONS|TRIANGLE_STRIPS)\s+(\d+)\s+(\d+)", stripped, re.IGNORECASE)
        if cell_match:
            kind = cell_match.group(1).upper()
            count = int(cell_match.group(2))
            index += 1
            cells: list[list[int]] = []
            for _ in range(count):
                if index >= len(lines):
                    break
                values = _numbers(lines[index], int)
                if values:
                    cells.append(values[1 : 1 + values[0]])
                index += 1
            if kind == "LINES":
                for cell in cells:
                    segments.extend([[cell[offset], cell[offset + 1]] for offset in range(max(0, len(cell) - 1))])
            else:
                for cell in cells:
                    triangles.extend([[cell[0], cell[offset], cell[offset + 1]] for offset in range(1, max(1, len(cell) - 1))])
            continue
        index += 1
    return {
        "format": "vtk",
        "points": points,
        "segments": segments[:MAX_PRIMITIVES],
        "triangles": triangles[:MAX_PRIMITIVES],
        "bounds": _bounds(points),
        "truncated": len(points) >= MAX_POINTS or len(segments) > MAX_PRIMITIVES or len(triangles) > MAX_PRIMITIVES,
    }


def parse_pvd(path: pathlib.Path, runs_root: pathlib.Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    datasets = []
    base = path.parent.resolve()
    run_root = runs_root.resolve()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "DataSet":
            continue
        raw = element.attrib.get("file", "")
        target = (base / pathlib.PurePosixPath(raw.replace("\\", "/"))).resolve()
        if not _within(target, run_root):
            continue
        datasets.append(
            {
                "time": float(element.attrib.get("timestep", len(datasets))),
                "file": target.relative_to(run_root).as_posix(),
                "exists": target.is_file(),
            }
        )
    return {"format": "pvd", "datasets": datasets, "count": len(datasets)}


def load_visualization_geometry(runs_root: pathlib.Path, file_id: str) -> dict[str, Any]:
    path = resolve_visualization_path(runs_root, file_id)
    suffix = path.suffix.lower()
    if suffix == ".vtp":
        payload = parse_vtp(path)
    elif suffix == ".vtk":
        payload = parse_legacy_vtk(path)
    else:
        payload = parse_pvd(path, runs_root)
    return {"id": file_id, "name": path.name, **payload}

