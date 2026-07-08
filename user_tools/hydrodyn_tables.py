# -*- coding: utf-8 -*-
"""Parse, validate, and rewrite HydroDyn strip-theory tables.

The editor only changes tables whose row count is controlled by an input key.
Everything outside those managed table row ranges is left unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_FORMAT = "v4"

TABLE_COUNT_KEYS = {
    "NAxCoef",
    "NJoints",
    "NPropSets",
    "NPropSetsCyl",
    "NPropSetsRec",
    "NCoefDpth",
    "NCoefDpthCyl",
    "NCoefDpthRec",
    "NCoefMembers",
    "NCoefMembersCyl",
    "NCoefMembersRec",
    "NMembers",
}

V4_COUNT_TABLES = {
    "axial": "NAxCoef",
    "joints": "NJoints",
    "prop_sets_cyl": "NPropSets",
    "depth_cyl": "NCoefDpth",
    "member_coeffs_cyl": "NCoefMembers",
    "members": "NMembers",
}

V5_COUNT_TABLES = {
    "axial": "NAxCoef",
    "joints": "NJoints",
    "prop_sets_cyl": "NPropSetsCyl",
    "prop_sets_rec": "NPropSetsRec",
    "depth_cyl": "NCoefDpthCyl",
    "depth_rec": "NCoefDpthRec",
    "member_coeffs_cyl": "NCoefMembersCyl",
    "member_coeffs_rec": "NCoefMembersRec",
    "members": "NMembers",
}

SIMPLE_HEADERS = {
    "simple_cyl": {"SimplCd", "SimplCdMG"},
    "simple_rec": {"SimplCdA", "SimplCdAMG", "SimplCdB", "SimplCdBMG"},
}

DEFAULT_TABLES: dict[str, Any] = {
    "axial": [],
    "joints": [],
    "prop_sets_cyl": [],
    "prop_sets_rec": [],
    "simple_cyl": {},
    "simple_rec": {},
    "depth_cyl": [],
    "depth_rec": [],
    "member_coeffs_cyl": [],
    "member_coeffs_rec": [],
    "members": [],
}

DEFAULT_SCHEMAS: dict[str, list[str]] = {
    "axial": ["AxCoefID", "AxCd", "AxCa", "AxCp", "AxFDMod", "AxVnCOff", "AxFDLoFSc"],
    "joints": ["JointID", "Jointxi", "Jointyi", "Jointzi", "JointAxID", "JointOvrlp"],
    "prop_sets_cyl": ["PropSetID", "PropD", "PropThck"],
    "prop_sets_rec": ["MPropSetID", "PropA", "PropB", "PropThck"],
    "simple_cyl": [
        "SimplCd",
        "SimplCdMG",
        "SimplCa",
        "SimplCaMG",
        "SimplCp",
        "SimplCpMG",
        "SimplAxCd",
        "SimplAxCdMG",
        "SimplAxCa",
        "SimplAxCaMG",
        "SimplAxCp",
        "SimplAxCpMG",
        "SimplCb",
        "SimplCbMG",
    ],
    "simple_rec": [
        "SimplCdA",
        "SimplCdAMG",
        "SimplCdB",
        "SimplCdBMG",
        "SimplCaA",
        "SimplCaAMG",
        "SimplCaB",
        "SimplCaBMG",
        "SimplCp",
        "SimplCpMG",
        "SimplAxCd",
        "SimplAxCdMG",
        "SimplAxCa",
        "SimplAxCaMG",
        "SimplAxCp",
        "SimplAxCpMG",
        "SimplCb",
        "SimplCbMG",
    ],
    "depth_cyl": [
        "Dpth",
        "DpthCd",
        "DpthCdMG",
        "DpthCa",
        "DpthCaMG",
        "DpthCp",
        "DpthCpMG",
        "DpthAxCd",
        "DpthAxCdMG",
        "DpthAxCa",
        "DpthAxCaMG",
        "DpthAxCp",
        "DpthAxCpMG",
        "DpthCb",
        "DpthCbMG",
    ],
    "depth_rec": [
        "Dpth",
        "DpthCdA",
        "DpthCdAMG",
        "DpthCdB",
        "DpthCdBMG",
        "DpthCaA",
        "DpthCaAMG",
        "DpthCaB",
        "DpthCaBMG",
        "DpthCp",
        "DpthCpMG",
        "DpthAxCd",
        "DpthAxCdMG",
        "DpthAxCa",
        "DpthAxCaMG",
        "DpthAxCp",
        "DpthAxCpMG",
        "DpthCb",
        "DpthCbMG",
    ],
    "member_coeffs_cyl": [
        "MemberID",
        "MemberCd1",
        "MemberCd2",
        "MemberCdMG1",
        "MemberCdMG2",
        "MemberCa1",
        "MemberCa2",
        "MemberCaMG1",
        "MemberCaMG2",
        "MemberCp1",
        "MemberCp2",
        "MemberCpMG1",
        "MemberCpMG2",
        "MemberAxCd1",
        "MemberAxCd2",
        "MemberAxCdMG1",
        "MemberAxCdMG2",
        "MemberAxCa1",
        "MemberAxCa2",
        "MemberAxCaMG1",
        "MemberAxCaMG2",
        "MemberAxCp1",
        "MemberAxCp2",
        "MemberAxCpMG1",
        "MemberAxCpMG2",
        "MemberCb1",
        "MemberCb2",
        "MemberCbMG1",
        "MemberCbMG2",
    ],
    "member_coeffs_rec": [
        "MemberID",
        "MemberCdA1",
        "MemberCdA2",
        "MemberCdAMG1",
        "MemberCdAMG2",
        "MemberCdB1",
        "MemberCdB2",
        "MemberCdBMG1",
        "MemberCdBMG2",
        "MemberCaA1",
        "MemberCaA2",
        "MemberCaAMG1",
        "MemberCaAMG2",
        "MemberCaB1",
        "MemberCaB2",
        "MemberCaBMG1",
        "MemberCaBMG2",
        "MemberCp1",
        "MemberCp2",
        "MemberCpMG1",
        "MemberCpMG2",
        "MemberAxCd1",
        "MemberAxCd2",
        "MemberAxCdMG1",
        "MemberAxCdMG2",
        "MemberAxCa1",
        "MemberAxCa2",
        "MemberAxCaMG1",
        "MemberAxCaMG2",
        "MemberAxCp1",
        "MemberAxCp2",
        "MemberAxCpMG1",
        "MemberAxCpMG2",
        "MemberCb1",
        "MemberCb2",
        "MemberCbMG1",
        "MemberCbMG2",
    ],
    "members": [
        "MemberID",
        "MJointID1",
        "MJointID2",
        "MPropSetID1",
        "MPropSetID2",
        "MSecGeom",
        "MSpinOrient",
        "MDivSize",
        "MCoefMod",
        "MHstLMod",
        "PropPot",
    ],
}

V4_MEMBER_COEFF_FIELDS = [
    "MemberID",
    "MemberCd1",
    "MemberCd2",
    "MemberCdMG1",
    "MemberCdMG2",
    "MemberCa1",
    "MemberCa2",
    "MemberCaMG1",
    "MemberCaMG2",
    "MemberCp1",
    "MemberCp2",
    "MemberCpMG1",
    "MemberCpMG2",
    "MemberAxCd1",
    "MemberAxCd2",
    "MemberAxCdMG1",
    "MemberAxCdMG2",
    "MemberAxCa1",
    "MemberAxCa2",
    "MemberAxCaMG1",
    "MemberAxCaMG2",
    "MemberAxCp1",
    "MemberAxCp2",
    "MemberAxCpMG1",
    "MemberAxCpMG2",
    "MemberCb1",
    "MemberCb2",
    "MemberCbMG1",
    "MemberCbMG2",
]

V4_MEMBER_FIELDS = [
    "MemberID",
    "MJointID1",
    "MJointID2",
    "MPropSetID1",
    "MPropSetID2",
    "MDivSize",
    "MCoefMod",
    "MHstLMod",
    "PropPot",
]

BOOL_FIELDS = {"PropPot"}


def clone_default_tables() -> dict[str, Any]:
    return deepcopy(DEFAULT_TABLES)


def _tokens_before_comment(line: str) -> list[str]:
    out = []
    for token in line.split():
        if token.startswith("!") or token.startswith("["):
            break
        out.append(token)
    return out


def _fields_from_header(line: str) -> list[str]:
    fields = []
    for token in line.split():
        if token.startswith("!") or token.startswith("["):
            break
        if token.startswith("(") or set(token) == {"-"}:
            continue
        fields.append(token)
    return fields


def _coerce(token: str) -> Any:
    raw = token.strip().rstrip(",")
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        if any(ch in raw.lower() for ch in [".", "e"]):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _format_value(value: Any, field: str = "") -> str:
    if isinstance(value, bool) or field in BOOL_FIELDS and str(value).lower() in {"true", "false"}:
        return "True" if str(value).lower() == "true" else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    text = str(value)
    return text if text else "0"


def _row_from_tokens(fields: list[str], tokens: list[str]) -> dict[str, Any]:
    return {field: _coerce(tokens[index]) for index, field in enumerate(fields) if index < len(tokens)}


def _format_row(fields: list[str], row: dict[str, Any]) -> str:
    values = [_format_value(row.get(field, _default_for_field(field)), field) for field in fields]
    return " ".join(f"{value:>12}" for value in values).rstrip()


def _format_header(fields: list[str]) -> str:
    return " ".join(f"{field:>12}" for field in fields).rstrip()


def _unit_for_field(field: str) -> str:
    if field in {"Jointxi", "Jointyi", "Jointzi", "PropD", "PropThck", "MDivSize", "Dpth", "PropA", "PropB"}:
        return "(m)"
    if field.endswith("Orient"):
        return "(deg)"
    return "(-)"


def _format_units(fields: list[str]) -> str:
    return " ".join(f"{_unit_for_field(field):>12}" for field in fields).rstrip()


def _default_for_field(field: str) -> Any:
    if field in BOOL_FIELDS:
        return False
    if field == "MDivSize":
        return 0.5
    if field == "MCoefMod":
        return 1
    if field == "MHstLMod":
        return 0
    if field.endswith("Cb") or field.endswith("Cb1") or field.endswith("Cb2") or field.endswith("CbMG") or field.endswith("CbMG1") or field.endswith("CbMG2"):
        return 1
    return 0


def _line_key(line: str) -> str | None:
    parts = line.split()
    return parts[1] if len(parts) >= 2 else None


def _find_key_line(lines: list[str], key: str) -> int | None:
    for index, line in enumerate(lines):
        if _line_key(line) == key:
            return index
    return None


def _read_count(line: str, key: str) -> int:
    parts = line.split()
    if len(parts) < 2 or parts[1] != key:
        raise ValueError(f"Expected count key {key}")
    return int(float(parts[0]))


def _replace_count(line: str, key: str, count: int) -> str:
    parts = line.split(None, 2)
    if len(parts) < 2 or parts[1] != key:
        raise ValueError(f"Expected count key {key}")
    tail = f" {parts[2]}" if len(parts) > 2 else ""
    return f"{count:>13}   {key}{tail}"


def _parse_count_table(lines: list[str], count_key: str) -> tuple[list[str], list[dict[str, Any]]]:
    idx = _find_key_line(lines, count_key)
    if idx is None:
        return [], []
    count = _read_count(lines[idx], count_key)
    header_idx = idx + 1
    fields = _fields_from_header(lines[header_idx]) if header_idx < len(lines) else []
    row_start = idx + 3
    rows = []
    for line in lines[row_start : row_start + count]:
        rows.append(_row_from_tokens(fields, _tokens_before_comment(line)))
    return fields, rows


def _find_simple_header(lines: list[str], required: set[str]) -> int | None:
    for index, line in enumerate(lines):
        fields = set(_fields_from_header(line))
        if required.issubset(fields):
            return index
    return None


def _parse_simple_table(lines: list[str], required: set[str]) -> tuple[list[str], dict[str, Any]]:
    idx = _find_simple_header(lines, required)
    if idx is None:
        return [], {}
    fields = _fields_from_header(lines[idx])
    value_idx = idx + 2
    if value_idx >= len(lines):
        return fields, {}
    return fields, _row_from_tokens(fields, _tokens_before_comment(lines[value_idx]))


def detect_hydrodyn_table_format(lines: list[str]) -> str:
    if _find_key_line(lines, "NPropSetsCyl") is not None or _find_key_line(lines, "NCoefMembersCyl") is not None:
        return "v5"
    return "legacy_v4"


def parse_hydrodyn_tables(lines: list[str], runtime_format: str = RUNTIME_FORMAT) -> dict[str, Any]:
    fmt = detect_hydrodyn_table_format(lines)
    count_specs = V5_COUNT_TABLES if fmt == "v5" else V4_COUNT_TABLES
    tables = clone_default_tables()
    schemas = deepcopy(DEFAULT_SCHEMAS)
    warnings: list[str] = []

    for name, key in count_specs.items():
        fields, rows = _parse_count_table(lines, key)
        if fields:
            schemas[name] = fields
        tables[name] = rows

    if fmt == "legacy_v4":
        tables["prop_sets_rec"] = []
        tables["depth_rec"] = []
        tables["member_coeffs_rec"] = []
        schemas["member_coeffs_cyl"] = list(V4_MEMBER_COEFF_FIELDS)
        schemas["members"] = list(V4_MEMBER_FIELDS)

    for name, required in SIMPLE_HEADERS.items():
        fields, values = _parse_simple_table(lines, required)
        if fields:
            schemas[name] = fields
        if values:
            tables[name] = values

    validation = validate_hydrodyn_tables(tables, target_format="v4" if runtime_format == "v4" else fmt)
    warnings.extend(validation["warnings"])

    return {
        "format": fmt,
        "runtimeFormat": runtime_format,
        "tables": tables,
        "schemas": schemas,
        "warnings": warnings,
    }


def _table_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "tables" in payload and isinstance(payload["tables"], dict):
        return payload["tables"]
    return payload


def _has_rows(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_v4_target(target_format: str) -> bool:
    return target_format in {"v4", "legacy_v4", "auto_v4_runtime"}


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "t", "1", ".true."}


def _ids(rows: list[dict[str, Any]], key: str) -> set[int]:
    return {_as_int(row.get(key)) for row in rows if row.get(key) is not None}


def _default_member_coeff(member_id: int, fields: list[str] | None = None) -> dict[str, Any]:
    fields = fields or DEFAULT_SCHEMAS["member_coeffs_cyl"]
    row: dict[str, Any] = {}
    for field in fields:
        if field == "MemberID":
            row[field] = member_id
        elif field.endswith(("Cd1", "Cd2", "CdMG1", "CdMG2", "Ca1", "Ca2", "CaMG1", "CaMG2", "Cp1", "Cp2", "CpMG1", "CpMG2")):
            row[field] = 1
        else:
            row[field] = _default_for_field(field)
    return row


def repair_hydrodyn_tables(tables: dict[str, Any], target_format: str = "v4") -> tuple[dict[str, Any], list[str]]:
    """Repair table references that the UI owns and can safely default."""
    repaired = clone_default_tables()
    repaired.update(deepcopy(tables or {}))
    warnings: list[str] = []

    for name in ["joints", "prop_sets_cyl", "member_coeffs_cyl", "members"]:
        if not isinstance(repaired.get(name), list):
            repaired[name] = []

    if _is_v4_target(target_format):
        fixed_joints = []
        for joint in repaired["joints"]:
            if _as_int(joint.get("JointOvrlp")) != 0:
                joint["JointOvrlp"] = 0
                fixed_joints.append(str(joint.get("JointID")))
        if fixed_joints:
            warnings.append(
                "Set JointOvrlp=0 for OpenFAST v4 runtime joints: " + ", ".join(fixed_joints) + "."
            )

    prop_ids = _ids(repaired["prop_sets_cyl"], "PropSetID")
    coeff_ids = _ids(repaired["member_coeffs_cyl"], "MemberID")

    for member in repaired["members"]:
        member_id = _as_int(member.get("MemberID"))
        member.setdefault("MDivSize", 0.5)
        member.setdefault("MCoefMod", 1)
        member.setdefault("MHstLMod", 0)
        member.setdefault("PropPot", False)
        shape = _as_int(member.get("MSecGeom"), 1)
        if shape != 2:
            for field in ["MPropSetID1", "MPropSetID2"]:
                prop_id = _as_int(member.get(field))
                if prop_id and prop_id not in prop_ids:
                    repaired["prop_sets_cyl"].append({"PropSetID": prop_id, "PropD": 6, "PropThck": 0.06})
                    prop_ids.add(prop_id)
                    warnings.append(
                        f"Auto-added missing cylindrical PropSetID {prop_id} referenced by Member {member_id}."
                    )
        if _as_int(member.get("MCoefMod"), 1) == 3 and member_id and member_id not in coeff_ids:
            repaired["member_coeffs_cyl"].append(_default_member_coeff(member_id))
            coeff_ids.add(member_id)
            warnings.append(f"Auto-added missing member coefficient row for Member {member_id}.")

    repaired["prop_sets_cyl"].sort(key=lambda row: _as_int(row.get("PropSetID")))
    repaired["member_coeffs_cyl"].sort(key=lambda row: _as_int(row.get("MemberID")))
    return repaired, warnings


def _duplicate_ids(rows: list[dict[str, Any]], key: str) -> list[int]:
    seen: set[int] = set()
    dupes: set[int] = set()
    for row in rows:
        value = _as_int(row.get(key))
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return sorted(dupes)


def validate_hydrodyn_tables(tables: dict[str, Any], target_format: str = "v4") -> dict[str, list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    table = clone_default_tables()
    table.update(tables or {})
    v4_target = _is_v4_target(target_format)

    if _has_rows(table["joints"]) and len(table["joints"]) < 2:
        errors.append("NJoints must be exactly 0 or at least 2.")

    for rows_name, key in [
        ("axial", "AxCoefID"),
        ("joints", "JointID"),
        ("prop_sets_cyl", "PropSetID"),
        ("prop_sets_rec", "MPropSetID"),
        ("member_coeffs_cyl", "MemberID"),
        ("member_coeffs_rec", "MemberID"),
        ("members", "MemberID"),
    ]:
        dupes = _duplicate_ids(table.get(rows_name, []), key)
        if dupes:
            errors.append(f"Duplicate {key} values in {rows_name}: {dupes}")

    axial_ids = _ids(table["axial"], "AxCoefID")
    joint_ids = _ids(table["joints"], "JointID")
    prop_cyl_ids = _ids(table["prop_sets_cyl"], "PropSetID")
    prop_rec_ids = _ids(table["prop_sets_rec"], "MPropSetID")
    coeff_cyl_ids = _ids(table["member_coeffs_cyl"], "MemberID")
    coeff_rec_ids = _ids(table["member_coeffs_rec"], "MemberID")

    for joint in table["joints"]:
        ax_id = _as_int(joint.get("JointAxID"))
        if ax_id and axial_ids and ax_id not in axial_ids:
            errors.append(f"Joint {joint.get('JointID')} references missing AxCoefID {ax_id}.")
        if v4_target and _as_int(joint.get("JointOvrlp")) != 0:
            errors.append(f"Joint {joint.get('JointID')} has JointOvrlp={joint.get('JointOvrlp')}; OpenFAST v4 requires 0.")

    if v4_target:
        if _has_rows(table["prop_sets_rec"]) or _has_rows(table["depth_rec"]) or _has_rows(table["member_coeffs_rec"]):
            errors.append("Rectangular HydroDyn tables are v5-only and cannot run with the current v4 runtime.")

    joint_by_id = {_as_int(row.get("JointID")): row for row in table["joints"]}
    prop_cyl_by_id = {_as_int(row.get("PropSetID")): row for row in table["prop_sets_cyl"]}

    for member in table["members"]:
        member_id = _as_int(member.get("MemberID"))
        j1 = _as_int(member.get("MJointID1"))
        j2 = _as_int(member.get("MJointID2"))
        if joint_ids and j1 not in joint_ids:
            errors.append(f"Member {member_id} references missing MJointID1 {j1}.")
        if joint_ids and j2 not in joint_ids:
            errors.append(f"Member {member_id} references missing MJointID2 {j2}.")

        shape = _as_int(member.get("MSecGeom"), 1)
        if v4_target and shape == 2:
            errors.append(f"Member {member_id} is rectangular (MSecGeom=2), unsupported by current v4 runtime.")

        p1 = _as_int(member.get("MPropSetID1"))
        p2 = _as_int(member.get("MPropSetID2"))
        props = prop_rec_ids if shape == 2 else prop_cyl_ids
        if p1 and p1 not in props:
            errors.append(f"Member {member_id} references missing MPropSetID1 {p1}.")
        if p2 and p2 not in props:
            errors.append(f"Member {member_id} references missing MPropSetID2 {p2}.")

        coef_mod = _as_int(member.get("MCoefMod"), 1)
        if coef_mod == 3:
            coeffs = coeff_rec_ids if shape == 2 else coeff_cyl_ids
            if member_id not in coeffs:
                errors.append(f"Member {member_id} uses MCoefMod=3 but has no member coefficient row.")

        if v4_target and shape != 2 and _as_int(member.get("MHstLMod"), 0) == 1 and not _is_truthy(member.get("PropPot")):
            j1_row = joint_by_id.get(j1)
            j2_row = joint_by_id.get(j2)
            p1_row = prop_cyl_by_id.get(p1)
            p2_row = prop_cyl_by_id.get(p2)
            if j1_row and p1_row and abs(_as_float(j1_row.get("Jointzi"))) < abs(_as_float(p1_row.get("PropD"))) / 2:
                errors.append(
                    f"Member {member_id} has MHstLMod=1 and endpoint MJointID1={j1} too close to the water plane."
                )
            if j2_row and p2_row and abs(_as_float(j2_row.get("Jointzi"))) < abs(_as_float(p2_row.get("PropD"))) / 2:
                errors.append(
                    f"Member {member_id} has MHstLMod=1 and endpoint MJointID2={j2} too close to the water plane."
                )

    member_ids = _ids(table["members"], "MemberID")
    for coeff in table["member_coeffs_cyl"]:
        member_id = _as_int(coeff.get("MemberID"))
        if member_ids and member_id not in member_ids:
            warnings.append(f"Member coefficient row {member_id} is not referenced by an active member.")
    for coeff in table["member_coeffs_rec"]:
        member_id = _as_int(coeff.get("MemberID"))
        if member_ids and member_id not in member_ids:
            warnings.append(f"Rectangular member coefficient row {member_id} is not referenced by an active member.")

    return {"warnings": warnings, "errors": errors}


def _write_count_table(lines: list[str], count_key: str, fields: list[str], rows: list[dict[str, Any]]) -> int:
    idx = _find_key_line(lines, count_key)
    if idx is None:
        return 0
    old_count = _read_count(lines[idx], count_key)
    lines[idx] = _replace_count(lines[idx], count_key, len(rows))
    if idx + 1 < len(lines):
        lines[idx + 1] = _format_header(fields)
    if idx + 2 < len(lines):
        lines[idx + 2] = _format_units(fields)
    row_start = idx + 3
    lines[row_start : row_start + old_count] = [_format_row(fields, row) for row in rows]
    return len(rows)


def _write_simple_table(lines: list[str], required: set[str], fields: list[str], values: dict[str, Any]) -> int:
    idx = _find_simple_header(lines, required)
    if idx is None:
        return 0
    value_idx = idx + 2
    if value_idx >= len(lines):
        return 0
    lines[idx] = _format_header(fields)
    if idx + 1 < len(lines):
        lines[idx + 1] = _format_units(fields)
    lines[value_idx] = _format_row(fields, values)
    return 1


def _counts_for_format(fmt: str) -> dict[str, str]:
    return V5_COUNT_TABLES if fmt == "v5" else V4_COUNT_TABLES


def apply_hydrodyn_tables(
    lines: list[str],
    payload: dict[str, Any],
    target_format: str = "auto_v4_runtime",
    runtime_format: str = RUNTIME_FORMAT,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    current = parse_hydrodyn_tables(lines, runtime_format=runtime_format)
    source_format = current["format"]
    write_format = source_format
    if target_format in {"v4", "legacy_v4", "auto_v4_runtime"}:
        write_format = "legacy_v4"
    elif target_format == "v5":
        write_format = "v5"

    tables = clone_default_tables()
    tables.update(_table_payload(payload))
    validation_target = "v4" if _is_v4_target(target_format) else write_format
    tables, repair_warnings = repair_hydrodyn_tables(tables, target_format=validation_target)
    schemas = deepcopy(DEFAULT_SCHEMAS)
    schemas.update(current.get("schemas") or {})

    validation = validate_hydrodyn_tables(tables, target_format=validation_target)
    if validation["errors"]:
        raise ValueError("; ".join(validation["errors"]))

    if write_format == "legacy_v4" and source_format == "v5":
        raise ValueError("Cannot write a v5 HydroDyn file as v4 without a v4 HydroDyn template.")
    if write_format == "v5" and source_format != "v5":
        raise ValueError("Cannot write v5 HydroDyn tables into a legacy/v4 HydroDyn file.")

    updated = list(lines)
    changes: list[dict[str, Any]] = []
    for table_name, count_key in _counts_for_format(write_format).items():
        if table_name not in tables:
            continue
        rows = tables.get(table_name) or []
        fields = schemas.get(table_name) or DEFAULT_SCHEMAS[table_name]
        if write_format == "legacy_v4" and table_name == "member_coeffs_cyl":
            fields = V4_MEMBER_COEFF_FIELDS
        elif write_format == "legacy_v4" and table_name == "members":
            fields = V4_MEMBER_FIELDS
        written = _write_count_table(updated, count_key, fields, rows)
        changes.append({"table": table_name, "countKey": count_key, "rows": written})

    for table_name, required in SIMPLE_HEADERS.items():
        if table_name == "simple_rec" and write_format != "v5":
            continue
        values = tables.get(table_name) or {}
        fields = schemas.get(table_name) or DEFAULT_SCHEMAS[table_name]
        if values:
            written = _write_simple_table(updated, required, fields, values)
            if written:
                changes.append({"table": table_name, "rows": written})

    return updated, changes, repair_warnings + validation["warnings"]
