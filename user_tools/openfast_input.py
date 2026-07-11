# -*- coding: utf-8 -*-
"""Generic, format-preserving helpers for OpenFAST text input files."""
from __future__ import annotations

from collections import deque
import pathlib
import re
from typing import Any, Iterable


FIELD_RE = re.compile(
    r"^\s*(?P<value>.+?)\s+(?P<key>[A-Za-z][A-Za-z0-9_()]+)\s*(?:-\s*(?P<description>.*))?$"
)
OUTLIST_HEADER_RE = re.compile(
    r"(?:^\s*(?:\d+\s+)?OutList\b)|(?:^-+\s*OUTPUT(?:\s+CHANNELS|S)\s*-+\s*$)",
    re.IGNORECASE,
)
OUTLIST_END_RE = re.compile(r'^\s*"?END\b', re.IGNORECASE)
QUOTED_RE = re.compile(r'"([^"]+)"')

REFERENCE_EXTENSIONS = {
    ".fst",
    ".dat",
    ".txt",
    ".inp",
    ".ipt",
    ".in",
    ".csv",
    ".yaml",
    ".yml",
    ".dll",
    ".so",
    ".dylib",
    ".bts",
    ".wnd",
    ".hh",
}
SCANNABLE_EXTENSIONS = {".fst", ".dat", ".txt", ".inp", ".ipt", ".in", ".yaml", ".yml"}
IGNORED_REFERENCE_VALUES = {"", "default", "unused", "none", "null", "true", "false"}


def read_text_lines(path: pathlib.Path) -> tuple[list[str], str, bool]:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.splitlines(), newline, raw.endswith(("\n", "\r"))


def parse_scalar_fields(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Parse ordinary ``value key - description`` rows without changing text."""
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#", "=", "---")):
            continue
        match = FIELD_RE.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        key = match.group("key")
        if key.upper() == "END" or key.startswith("-"):
            continue
        rows.append(
            {
                "line": line_number,
                "key": key,
                "value": value,
                "description": (match.group("description") or "").strip(),
            }
        )
    return rows


def _split_channels(text: str) -> list[str]:
    return [token for token in re.split(r"[,;\s]+", text.strip()) if token]


def parse_outlist_sections(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Return all OpenFAST OutList blocks and their channel order."""
    source = list(lines)
    sections: list[dict[str, Any]] = []
    for header_index, line in enumerate(source):
        if not OUTLIST_HEADER_RE.match(line):
            continue
        channels: list[str] = []
        saw_quoted_channel = False
        end_index = None
        for index in range(header_index + 1, len(source)):
            candidate = source[index]
            if OUTLIST_END_RE.match(candidate):
                end_index = index
                break
            quoted = QUOTED_RE.findall(candidate)
            saw_quoted_channel = saw_quoted_channel or bool(quoted)
            for value in quoted:
                channels.extend(_split_channels(value))
            if not quoted:
                stripped = candidate.strip()
                if stripped and not stripped.startswith(("!", "#", "-", "=")):
                    channel = re.split(r"\s+-\s+|\s+", stripped, maxsplit=1)[0]
                    if channel:
                        channels.append(channel.strip('"'))
        if end_index is None:
            continue
        sections.append(
            {
                "section": len(sections),
                "headerLine": header_index + 1,
                "endLine": end_index + 1,
                "header": line.strip(),
                "channels": channels,
                "quoted": saw_quoted_channel or not channels,
            }
        )
    return sections


def _normalized_channels(values: Iterable[Any]) -> list[str]:
    channels: list[str] = []
    seen: set[str] = set()
    for value in values:
        channel = str(value).strip().strip('"')
        if not channel or channel.upper() == "END" or channel in seen:
            continue
        if any(character.isspace() for character in channel):
            raise ValueError(f"Invalid OutList channel with whitespace: {channel!r}")
        channels.append(channel)
        seen.add(channel)
    return channels


def write_outlist_edits(path: pathlib.Path, edits: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace selected OutList blocks while preserving all surrounding text."""
    lines, newline, trailing_newline = read_text_lines(path)
    sections = parse_outlist_sections(lines)
    normalized: dict[int, list[str]] = {}
    for edit in edits:
        section_index = int(edit.get("section", 0))
        if section_index < 0 or section_index >= len(sections):
            raise IndexError(f"OutList section {section_index} not found in {path}")
        normalized[section_index] = _normalized_channels(edit.get("channels") or [])

    changes: list[dict[str, Any]] = []
    for section_index in sorted(normalized, reverse=True):
        section = sections[section_index]
        start = int(section["headerLine"])
        end = int(section["endLine"]) - 1
        indent = ""
        if start < len(lines):
            indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        quoted = bool(section.get("quoted", True))
        replacement = [f'{indent}"{channel}"' if quoted else f"{indent}{channel}" for channel in normalized[section_index]]
        before = list(section["channels"])
        lines[start:end] = replacement
        changes.append(
            {
                "file": str(path),
                "section": section_index,
                "before": before,
                "channels": normalized[section_index],
                "channelCount": len(normalized[section_index]),
            }
        )

    payload = newline.join(lines)
    if trailing_newline:
        payload += newline
    path.write_text(payload, encoding="utf-8", newline="")
    return list(reversed(changes))


def _strip_reference(value: str) -> str:
    value = value.split("!", 1)[0].strip()
    return value.strip('"').strip("'").strip()


def _reference_suffix(value: str) -> str:
    clean = value.replace("\\", "/").split("?", 1)[0]
    return pathlib.PurePosixPath(clean).suffix.lower()


def _looks_like_reference(value: str, key: str = "") -> bool:
    clean = _strip_reference(value)
    lower = clean.lower()
    if lower in IGNORED_REFERENCE_VALUES or pathlib.PurePath(clean).stem.lower() in IGNORED_REFERENCE_VALUES:
        return False
    suffix = _reference_suffix(clean)
    key_lower = key.lower()
    key_suggests_file = any(token in key_lower for token in ("file", "path", "dll"))
    numeric = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", clean)
    fallback_path = key_suggests_file and not numeric and not any(character.isspace() for character in clean) and bool(suffix)
    return suffix in REFERENCE_EXTENSIONS or bool(fallback_path)


def _reference_candidates(line: str, field: dict[str, Any] | None) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    field_value = str(field["value"]) if field else ""
    if field and len(QUOTED_RE.findall(field_value)) <= 1 and _looks_like_reference(field_value, str(field["key"])):
        candidates.append((_strip_reference(str(field["value"])), str(field["key"])))
    for quoted in QUOTED_RE.findall(line):
        if _looks_like_reference(quoted):
            candidates.append((_strip_reference(quoted), str(field["key"]) if field else ""))
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value, key in candidates:
        marker = value.lower()
        if marker not in seen:
            seen.add(marker)
            result.append((value, key))
    return result


def _is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _node_id(path: pathlib.Path, root: pathlib.Path) -> str:
    if _is_within(path, root):
        return path.relative_to(root).as_posix()
    return f"external:{path}"


def _node_kind(path: pathlib.Path, main_path: pathlib.Path) -> str:
    suffix = path.suffix.lower()
    if path == main_path or suffix == ".fst":
        return "main"
    if suffix in {".dll", ".so", ".dylib"}:
        return "library"
    if suffix in {".bts", ".wnd", ".hh"}:
        return "wind"
    if suffix in SCANNABLE_EXTENSIONS:
        return "input"
    return "asset"


def discover_model_dependencies(
    model_root: pathlib.Path,
    fst_name: str,
    configured_files: Iterable[str] | None = None,
    max_files: int = 600,
) -> dict[str, Any]:
    """Conservatively discover referenced OpenFAST files under a model root."""
    root = model_root.resolve()
    main_path = (root / fst_name).resolve()
    configured = [str(value) for value in (configured_files or []) if value]
    seeds = [fst_name, *configured]
    queue: deque[tuple[pathlib.Path, int, bool]] = deque()
    for seed in seeds:
        candidate = pathlib.Path(seed.replace("\\", "/"))
        if not candidate.is_absolute():
            candidate = root / candidate
        queue.append((candidate.resolve(), 0 if str(seed) == fst_name else 1, True))

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()
    scanned: set[str] = set()
    warnings: list[str] = []

    while queue and len(scanned) < max_files:
        path, depth, is_configured = queue.popleft()
        marker = str(path).lower()
        node_id = _node_id(path, root)
        exists = path.is_file()
        node = nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "path": str(path),
                "name": path.name,
                "extension": path.suffix.lower(),
                "kind": _node_kind(path, main_path),
                "exists": exists,
                "external": not _is_within(path, root),
                "depth": depth,
                "configured": False,
                "scalarCount": 0,
                "outListCount": 0,
            },
        )
        node["depth"] = min(int(node["depth"]), depth)
        node["configured"] = bool(node["configured"] or is_configured)
        node["exists"] = exists
        if marker in scanned or not exists or node["external"] or path.suffix.lower() not in SCANNABLE_EXTENSIONS:
            continue
        scanned.add(marker)
        try:
            lines, _, _ = read_text_lines(path)
        except OSError as exc:
            warnings.append(f"Could not read {node_id}: {exc}")
            continue
        fields = parse_scalar_fields(lines)
        field_by_line = {int(row["line"]): row for row in fields}
        node["scalarCount"] = len(fields)
        node["outListCount"] = len(parse_outlist_sections(lines))
        for line_number, line in enumerate(lines, start=1):
            field = field_by_line.get(line_number)
            for raw_reference, key in _reference_candidates(line, field):
                normalized = raw_reference.replace("\\", "/")
                target = pathlib.Path(normalized)
                if not target.is_absolute():
                    target = path.parent / target
                target = target.resolve()
                target_id = _node_id(target, root)
                edge_marker = (node_id, target_id, key)
                if edge_marker in edge_keys:
                    continue
                edge_keys.add(edge_marker)
                edges.append(
                    {
                        "source": node_id,
                        "target": target_id,
                        "key": key,
                        "reference": raw_reference,
                        "line": line_number,
                        "exists": target.is_file(),
                    }
                )
                if target_id not in nodes:
                    nodes[target_id] = {
                        "id": target_id,
                        "path": str(target),
                        "name": target.name,
                        "extension": target.suffix.lower(),
                        "kind": _node_kind(target, main_path),
                        "exists": target.is_file(),
                        "external": not _is_within(target, root),
                        "depth": depth + 1,
                        "configured": False,
                        "scalarCount": 0,
                        "outListCount": 0,
                    }
                if target.is_file() and _is_within(target, root):
                    queue.append((target, depth + 1, False))

    if queue:
        warnings.append(f"Dependency scan stopped at the {max_files}-file safety limit.")
    missing = sum(1 for node in nodes.values() if not node["exists"])
    external = sum(1 for node in nodes.values() if node["external"])
    return {
        "root": str(root),
        "main": _node_id(main_path, root),
        "nodes": sorted(nodes.values(), key=lambda row: (not row["exists"], row["depth"], row["id"].lower())),
        "edges": sorted(edges, key=lambda row: (row["source"].lower(), row["line"], row["target"].lower())),
        "warnings": warnings,
        "summary": {
            "files": len(nodes),
            "existing": len(nodes) - missing,
            "missing": missing,
            "external": external,
            "outListFiles": sum(1 for node in nodes.values() if node["outListCount"]),
        },
    }


def structure_file_ids(structure: dict[str, Any], existing_only: bool = True) -> list[str]:
    result = []
    for node in structure.get("nodes") or []:
        if node.get("external") or (existing_only and not node.get("exists")):
            continue
        result.append(str(node["id"]))
    return result


def outlists_for_structure(model_root: pathlib.Path, structure: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    root = model_root.resolve()
    for file_id in structure_file_ids(structure):
        path = (root / pathlib.PurePosixPath(file_id)).resolve()
        if not path.is_file() or path.suffix.lower() not in SCANNABLE_EXTENSIONS:
            continue
        lines, _, _ = read_text_lines(path)
        sections = parse_outlist_sections(lines)
        if sections:
            result[file_id] = sections
    return result


def _normalize_outlist_payload(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    if isinstance(payload, list):
        return [dict(row) for row in payload]
    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = []
        for file_name, edits in payload.items():
            if isinstance(edits, dict):
                edits = [edits]
            for edit in edits or []:
                rows.append({"file": file_name, **dict(edit)})
        return rows
    raise TypeError("outlist_edits must be a list or object")


def apply_outlist_edits(run_dir: pathlib.Path, payload: Any) -> list[dict[str, Any]]:
    """Apply scenario OutList edits to files inside a copied run directory."""
    root = run_dir.resolve()
    by_file: dict[str, list[dict[str, Any]]] = {}
    for row in _normalize_outlist_payload(payload):
        file_name = str(row.get("file") or "").replace("\\", "/").strip()
        if not file_name:
            raise ValueError("OutList edit is missing file")
        by_file.setdefault(file_name, []).append(row)

    changes: list[dict[str, Any]] = []
    for file_name, edits in by_file.items():
        path = (root / pathlib.PurePosixPath(file_name)).resolve()
        if not _is_within(path, root):
            raise ValueError(f"OutList target escapes run directory: {file_name}")
        if not path.is_file():
            raise FileNotFoundError(f"OutList input file not found: {path}")
        file_changes = write_outlist_edits(path, edits)
        for change in file_changes:
            change["file"] = file_name
        changes.extend(file_changes)
    return changes
