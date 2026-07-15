# -*- coding: utf-8 -*-
"""Generic, format-preserving helpers for OpenFAST text input files."""
from __future__ import annotations

from collections import deque
import hashlib
import pathlib
import re
import shlex
from typing import Any, Iterable

from module_plugins import classify_module, metadata_for_key


FIELD_RE = re.compile(
    r"^\s*(?P<value>.+?)\s+(?P<key>[A-Za-z][A-Za-z0-9_()%-]*)\s*(?:-\s*(?P<description>.*))?$"
)
OUTLIST_HEADER_RE = re.compile(
    r"(?:^\s*(?:\d+\s+)?OutList\b)|(?:^-+\s*OUTPUT(?:\s+CHANNELS|S)\s*-+\s*$)",
    re.IGNORECASE,
)
OUTLIST_END_RE = re.compile(r'^\s*"?END\b', re.IGNORECASE)
QUOTED_RE = re.compile(r'"([^"]+)"')

REFERENCE_EXTENSIONS = {
    ".fst",
    ".fstf",
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
SCANNABLE_EXTENSIONS = {".fst", ".fstf", ".dat", ".txt", ".inp", ".ipt", ".in", ".yaml", ".yml"}
IGNORED_REFERENCE_VALUES = {"", "default", "unused", "none", "null", "true", "false"}
YAML_FIELD_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*):(?P<spacing>\s*)(?P<value>.*?)(?P<comment>\s+#.*)?$"
)
SECTION_LINE_RE = re.compile(r"^\s*(?:[-=]{3,})\s*(.*?)\s*(?:[-=]{3,})?(?:\s*\[.*\])?\s*$")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?$")
MAX_EDITABLE_FILE_BYTES = 4 * 1024 * 1024


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


def parse_typed_value(raw: Any) -> tuple[Any, str]:
    text = str(raw).strip()
    unquoted = text[1:-1] if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"} else text
    lower = unquoted.lower()
    if lower in {"true", "false"}:
        return lower == "true", "boolean"
    normalized = unquoted.replace("D", "E").replace("d", "e")
    if NUMBER_RE.fullmatch(normalized):
        try:
            number = float(normalized)
            if re.fullmatch(r"[+-]?\d+", normalized):
                return int(number), "integer"
            return number, "number"
        except ValueError:
            pass
    if "," in unquoted:
        return unquoted, "list"
    return unquoted, "string"


def format_typed_value(value: Any, old_raw: str = "", value_type: str | None = None) -> str:
    if isinstance(value, bool) or value_type == "boolean":
        if isinstance(value, str):
            value = value.strip().lower() == "true"
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    text = str(value)
    old = old_raw.strip()
    if old.startswith('"') and old.endswith('"') and not (text.startswith('"') and text.endswith('"')):
        return f'"{text}"'
    if old.startswith("'") and old.endswith("'") and not (text.startswith("'") and text.endswith("'")):
        return f"'{text}'"
    return text


def section_title(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or not (stripped.startswith("---") or stripped.startswith("===")):
        return None
    core = stripped.strip("-= ")
    core = re.sub(r"\s*\[.*$", "", core).strip()
    if not core or set(core) <= {"-", "="}:
        return None
    return core


def parse_sections(lines: Iterable[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        title = section_title(line)
        if title:
            sections.append({"title": title, "line": line_number})
    if not sections:
        sections.append({"title": "Input", "line": 1})
    return sections


def _section_for_line(sections: list[dict[str, Any]], line_number: int) -> str:
    current = sections[0]["title"] if sections else "Input"
    for section in sections:
        if int(section["line"]) > line_number:
            break
        current = str(section["title"])
    return current


def _unit_from_description(description: str) -> str:
    matches = re.findall(r"\(([^()]*)\)", description)
    if not matches:
        return ""
    candidate = matches[-1].strip()
    if len(candidate) > 24 or any(token in candidate for token in ("=", ",", ";")):
        return ""
    return candidate


def _options_from_description(description: str) -> list[Any]:
    options: list[Any] = []
    for raw in re.findall(r"(?<![A-Za-z0-9_.])(-?\d+)\s*(?:=|:)", description):
        number = int(raw)
        if number not in options:
            options.append(number)
    return options[:16]


def parse_yaml_fields(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    section = "YAML"
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#- ").rstrip("- ").strip()
            if heading:
                section = heading
            continue
        match = YAML_FIELD_RE.match(line)
        if not match:
            continue
        indent = len(match.group("indent").replace("\t", "  "))
        key = match.group("key")
        value = match.group("value").strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not value:
            stack.append((indent, key))
            continue
        path = ".".join([item[1] for item in stack] + [key])
        parsed, inferred_type = parse_typed_value(value)
        comment = (match.group("comment") or "").lstrip(" #")
        rows.append(
            {
                "line": line_number,
                "key": key,
                "path": path,
                "value": value,
                "parsedValue": parsed,
                "type": inferred_type,
                "description": comment,
                "unit": _unit_from_description(comment),
                "section": section,
                "format": "yaml",
            }
        )
    return rows


def parse_document_fields(lines: Iterable[str], format_name: str = "openfast") -> list[dict[str, Any]]:
    source = list(lines)
    if format_name == "yaml":
        return parse_yaml_fields(source)
    sections = parse_sections(source)
    rows = []
    for field in parse_scalar_fields(source):
        raw = str(field["value"])
        parsed, inferred_type = parse_typed_value(raw)
        metadata = metadata_for_key(str(field["key"]))
        description = str(field.get("description") or "")
        options = metadata.get("options") or _options_from_description(description)
        rows.append(
            {
                **field,
                "parsedValue": parsed,
                "type": metadata.get("type") or inferred_type,
                "options": options,
                "unit": _unit_from_description(description),
                "section": _section_for_line(sections, int(field["line"])),
                "format": "openfast",
                "path": str(field["key"]),
            }
        )
    return rows


def _split_table_tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _looks_like_units(tokens: list[str]) -> bool:
    if len(tokens) < 2:
        return False
    unitish = sum(1 for token in tokens if token.startswith(("(", "[")) or token in {"-", "(-)"})
    return unitish >= max(2, len(tokens) // 2)


def _looks_like_numeric_row(tokens: list[str]) -> bool:
    if not tokens:
        return False
    numeric = sum(1 for token in tokens if NUMBER_RE.fullmatch(token.replace("D", "E").replace("d", "e")))
    return numeric >= max(1, len(tokens) // 2)


def parse_document_tables(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Detect source tables that have a column-name line followed by a units line."""
    source = list(lines)
    sections = parse_sections(source)
    fields_by_line = {int(row["line"]): row for row in parse_scalar_fields(source)}
    tables: list[dict[str, Any]] = []
    consumed: set[int] = set()
    for units_index, units_line in enumerate(source):
        units = _split_table_tokens(units_line.strip())
        if not _looks_like_units(units):
            continue
        header_index = units_index - 1
        while header_index >= 0 and not source[header_index].strip():
            header_index -= 1
        if header_index < 0 or section_title(source[header_index]):
            continue
        columns = _split_table_tokens(source[header_index].strip())
        if len(columns) < 2 or len(columns) > 80 or _looks_like_numeric_row(columns):
            continue
        row_index = units_index + 1
        rows: list[dict[str, Any]] = []
        while row_index < len(source):
            line_number = row_index + 1
            line = source[row_index]
            stripped = line.strip()
            scalar = fields_by_line.get(line_number)
            scalar_boundary = bool(
                scalar
                and (
                    re.search(r"\s+-\s+", line)
                    or len(_split_table_tokens(stripped)) <= 4
                )
            )
            if not stripped or section_title(line) or scalar_boundary:
                break
            tokens = _split_table_tokens(stripped)
            if len(tokens) < 2 or stripped.upper().startswith(("END", "OUTLIST")):
                break
            rows.append({"line": line_number, "tokens": tokens, "text": line})
            consumed.add(line_number)
            row_index += 1
        if not rows:
            continue
        tables.append(
            {
                "id": f"table-{header_index + 1}",
                "title": _section_for_line(sections, header_index + 1),
                "headerLine": header_index + 1,
                "unitsLine": units_index + 1,
                "columns": columns,
                "units": units,
                "rows": rows,
            }
        )
    return tables


def _numeric_prefix(line: str, count: int = 6) -> list[float] | None:
    values: list[float] = []
    for token in line.split():
        normalized = token.replace("D", "E").replace("d", "e")
        if not NUMBER_RE.fullmatch(normalized):
            break
        values.append(float(normalized))
        if len(values) == count:
            return values
    return None


def parse_document_matrices(lines: Iterable[str]) -> list[dict[str, Any]]:
    source = list(lines)
    sections = parse_sections(source)
    matrices: list[dict[str, Any]] = []
    index = 0
    while index + 5 < len(source):
        rows = [_numeric_prefix(source[index + offset]) for offset in range(6)]
        if not all(row is not None for row in rows):
            index += 1
            continue
        first_tokens = source[index].split()
        if len(first_tokens) > 8 and not any(key in source[index] for key in ("AddCLin", "AddBLin", "AddBQuad")):
            index += 1
            continue
        label = _section_for_line(sections, index + 1)
        for key in ("AddCLin", "AddBLin", "AddBQuad"):
            if key in source[index]:
                label = key
        matrices.append(
            {
                "id": f"matrix-{index + 1}",
                "title": label,
                "startLine": index + 1,
                "rows": [
                    {"line": index + offset + 1, "values": rows[offset], "text": source[index + offset]}
                    for offset in range(6)
                ],
            }
        )
        index += 6
    return matrices


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_editable_document(path: pathlib.Path, file_id: str | None = None) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_EDITABLE_FILE_BYTES:
        raise ValueError(f"Input file is too large for browser editing ({size} bytes): {path.name}")
    lines, newline, trailing_newline = read_text_lines(path)
    format_name = "yaml" if path.suffix.lower() in {".yaml", ".yml"} else "openfast"
    fields = parse_document_fields(lines, format_name=format_name)
    tables = parse_document_tables(lines) if format_name == "openfast" else []
    matrices = parse_document_matrices(lines) if format_name == "openfast" else []
    outlists = parse_outlist_sections(lines)
    excluded_lines: set[int] = set()
    for table in tables:
        excluded_lines.update({int(table["headerLine"]), int(table["unitsLine"])})
        excluded_lines.update(int(row["line"]) for row in table["rows"])
    for matrix in matrices:
        excluded_lines.update(int(row["line"]) for row in matrix["rows"])
    for section in outlists:
        excluded_lines.update(range(int(section["headerLine"]) + 1, int(section["endLine"])))
    fields = [field for field in fields if int(field["line"]) not in excluded_lines]
    heading = "\n".join(lines[:4])
    plugin = classify_module(file_id or path.name, heading=heading, keys=[row["key"] for row in fields])
    return {
        "file": file_id or path.name,
        "path": str(path),
        "plugin": plugin.public(),
        "format": format_name,
        "sha256": file_sha256(path),
        "size": size,
        "lineCount": len(lines),
        "newline": "crlf" if newline == "\r\n" else "lf",
        "trailingNewline": trailing_newline,
        "sections": parse_sections(lines),
        "fields": fields,
        "tables": tables,
        "matrices": matrices,
        "outLists": outlists,
        "content": newline.join(lines) + (newline if trailing_newline else ""),
    }


def module_catalog_for_structure(model_root: pathlib.Path, structure: dict[str, Any]) -> list[dict[str, Any]]:
    root = model_root.resolve()
    result: list[dict[str, Any]] = []
    for node in structure.get("nodes") or []:
        if node.get("external") or not node.get("exists"):
            continue
        file_id = str(node.get("id") or "")
        path = (root / pathlib.PurePosixPath(file_id)).resolve()
        if not _is_within(path, root) or not path.is_file() or path.suffix.lower() not in SCANNABLE_EXTENSIONS:
            continue
        try:
            lines, _, _ = read_text_lines(path)
            format_name = "yaml" if path.suffix.lower() in {".yaml", ".yml"} else "openfast"
            fields = parse_document_fields(lines, format_name=format_name)
            heading = "\n".join(lines[:4])
            plugin = classify_module(file_id, heading=heading, keys=[row["key"] for row in fields])
            result.append(
                {
                    "file": file_id,
                    "name": path.name,
                    "pluginId": plugin.id,
                    "pluginName": plugin.name,
                    "category": plugin.category,
                    "stage": plugin.stage,
                    "description": plugin.description,
                    "docs": plugin.docs,
                    "capabilities": list(plugin.capabilities),
                    "fields": len(fields),
                    "outLists": int(node.get("outListCount") or 0),
                    "size": path.stat().st_size,
                    "editable": path.stat().st_size <= MAX_EDITABLE_FILE_BYTES,
                }
            )
        except OSError:
            continue
    return sorted(result, key=lambda row: (int(row["stage"]), str(row["pluginName"]), str(row["file"])))


def _replace_openfast_value(line: str, key: str, value: Any, value_type: str | None = None) -> str:
    pattern = re.compile(rf"^(\s*)(.*?)(\s+)({re.escape(key)})(\s*(?:-.*)?)$")
    match = pattern.match(line)
    if not match:
        raise ValueError(f"Key {key!r} was not found on the selected source line")
    indent, old_value, separator, found_key, tail = match.groups()
    width = max(1, len(old_value))
    replacement = format_typed_value(value, old_value, value_type=value_type)
    return f"{indent}{replacement:<{width}}{separator}{found_key}{tail}"


def _replace_yaml_value(line: str, key: str, value: Any, value_type: str | None = None) -> str:
    match = YAML_FIELD_RE.match(line)
    if not match or match.group("key") != key:
        raise ValueError(f"YAML key {key!r} was not found on the selected source line")
    old_value = match.group("value").strip()
    replacement = format_typed_value(value, old_value, value_type=value_type)
    return (
        f"{match.group('indent')}{key}:{match.group('spacing') or ' '}"
        f"{replacement}{match.group('comment') or ''}"
    )


def _normalize_file_payload(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    if isinstance(payload, list):
        return [dict(row) for row in payload]
    if isinstance(payload, dict):
        return [{"file": file_name, **(dict(row) if isinstance(row, dict) else {"content": row})} for file_name, row in payload.items()]
    raise TypeError("input_file_overrides must be a list or object")


def apply_input_file_overrides(run_dir: pathlib.Path, payload: Any) -> list[dict[str, Any]]:
    root = run_dir.resolve()
    changes: list[dict[str, Any]] = []
    for row in _normalize_file_payload(payload):
        file_name = str(row.get("file") or "").replace("\\", "/").strip()
        content = row.get("content")
        if not file_name or not isinstance(content, str):
            raise ValueError("Input file override requires file and string content")
        if len(content.encode("utf-8")) > MAX_EDITABLE_FILE_BYTES:
            raise ValueError(f"Input file override exceeds {MAX_EDITABLE_FILE_BYTES} bytes: {file_name}")
        path = (root / pathlib.PurePosixPath(file_name)).resolve()
        if not _is_within(path, root):
            raise ValueError(f"Input file override escapes run directory: {file_name}")
        if not path.is_file():
            raise FileNotFoundError(f"Input file override target not found: {path}")
        expected = str(row.get("source_sha256") or "").strip()
        before_hash = file_sha256(path)
        if expected and expected != before_hash:
            raise ValueError(f"Input file changed since it was opened; reload before applying override: {file_name}")
        newline = "\r\n" if row.get("newline") == "crlf" else "\n"
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        if newline == "\r\n":
            normalized = normalized.replace("\n", "\r\n")
        path.write_text(normalized, encoding="utf-8", newline="")
        changes.append({"file": file_name, "mode": "full-file", "before_sha256": before_hash, "after_sha256": file_sha256(path)})
    return changes


def apply_input_edits(run_dir: pathlib.Path, payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []
    if not isinstance(payload, list):
        raise TypeError("input_edits must be a list")
    root = run_dir.resolve()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise TypeError("Each input edit must be an object")
        file_name = str(row.get("file") or "").replace("\\", "/").strip()
        if not file_name:
            raise ValueError("Input edit is missing file")
        grouped.setdefault(file_name, []).append(dict(row))
    changes: list[dict[str, Any]] = []
    for file_name, edits in grouped.items():
        path = (root / pathlib.PurePosixPath(file_name)).resolve()
        if not _is_within(path, root):
            raise ValueError(f"Input edit escapes run directory: {file_name}")
        if not path.is_file():
            raise FileNotFoundError(f"Input edit target not found: {path}")
        lines, newline, trailing_newline = read_text_lines(path)
        for edit in sorted(edits, key=lambda item: int(item.get("line") or 0)):
            line_number = int(edit.get("line") or 0)
            if line_number < 1 or line_number > len(lines):
                raise IndexError(f"Input edit line {line_number} is outside {file_name}")
            before = lines[line_number - 1]
            kind = str(edit.get("kind") or "value")
            if kind == "line":
                after = str(edit.get("text") or "")
            else:
                key = str(edit.get("key") or "")
                if not key:
                    raise ValueError(f"Value edit on line {line_number} is missing key")
                if edit.get("format") == "yaml":
                    after = _replace_yaml_value(before, key, edit.get("value"), edit.get("type"))
                else:
                    after = _replace_openfast_value(before, key, edit.get("value"), edit.get("type"))
            lines[line_number - 1] = after
            changes.append({"file": file_name, "line": line_number, "kind": kind, "key": edit.get("key"), "before": before, "after": after})
        output = newline.join(lines) + (newline if trailing_newline else "")
        path.write_text(output, encoding="utf-8", newline="")
    return changes


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
        format_name = "yaml" if path.suffix.lower() in {".yaml", ".yml"} else "openfast"
        fields = parse_document_fields(lines, format_name=format_name)
        field_by_line = {int(row["line"]): row for row in fields}
        field_values = {str(row["key"]).lower(): row.get("parsedValue", row.get("value")) for row in fields}
        comp_aa_value = field_values.get("compaa")
        aeroacoustics_disabled = str(comp_aa_value).strip().lower() in {"false", "0", "0.0"}
        node["scalarCount"] = len(fields)
        node["outListCount"] = len(parse_outlist_sections(lines))
        for line_number, line in enumerate(lines, start=1):
            field = field_by_line.get(line_number)
            for raw_reference, key in _reference_candidates(line, field):
                if aeroacoustics_disabled and key.lower() == "aa_inputfile":
                    continue
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
