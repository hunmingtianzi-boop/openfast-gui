# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_tools"))
sys.path.insert(0, str(ROOT / "work_c4"))

from driver_c4 import _ensure_hydrodyn_v4  # noqa: E402
from hydrodyn_tables import (  # noqa: E402
    apply_hydrodyn_tables,
    parse_hydrodyn_tables,
    repair_hydrodyn_tables,
    validate_hydrodyn_tables,
)


def c4_hydrodyn_lines() -> list[str]:
    path = ROOT / "FOCAL_OpenFast_C4-main" / "FOCAL_OpenFast_C4-main" / "FOCAL_C4_HydroDyn.dat"
    if not path.is_file():
        raise unittest.SkipTest(f"C4 HydroDyn template not found: {path}")
    return _ensure_hydrodyn_v4(path.read_text(encoding="utf-8", errors="replace").splitlines())


def coeff_row(fields: list[str], member_id: int = 1) -> dict:
    row = {}
    for field in fields:
        if field == "MemberID":
            row[field] = member_id
        elif "Cb" in field:
            row[field] = 1
        else:
            row[field] = 1
    return row


def key_line(lines: list[str], key: str) -> int:
    for index, line in enumerate(lines):
        parts = line.split()
        if len(parts) >= 2 and parts[1] == key:
            return index
    raise AssertionError(f"Missing key {key}")


class HydroDynTableTests(unittest.TestCase):
    def test_parse_current_template_counts(self):
        meta = parse_hydrodyn_tables(c4_hydrodyn_lines())
        tables = meta["tables"]
        self.assertEqual(meta["format"], "legacy_v4")
        self.assertEqual(len(tables["axial"]), 0)
        self.assertEqual(len(tables["joints"]), 0)
        self.assertEqual(len(tables["prop_sets_cyl"]), 0)
        self.assertEqual(len(tables["member_coeffs_cyl"]), 0)
        self.assertEqual(len(tables["members"]), 0)
        self.assertIn("SimplCd", meta["schemas"]["simple_cyl"])
        self.assertIn("MemberCb1", meta["schemas"]["member_coeffs_cyl"])
        self.assertEqual(meta["schemas"]["members"], ["MemberID", "MJointID1", "MJointID2", "MPropSetID1", "MPropSetID2", "MDivSize", "MCoefMod", "MHstLMod", "PropPot"])

    def test_write_one_v4_morison_member_counts(self):
        lines = c4_hydrodyn_lines()
        meta = parse_hydrodyn_tables(lines)
        tables = meta["tables"]
        tables["axial"] = [{"AxCoefID": 1, "AxCd": 1, "AxCa": 1, "AxCp": 1, "AxFDMod": 0, "AxVnCOff": 0, "AxFDLoFSc": 1}]
        tables["joints"] = [
            {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": -20, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 10, "JointAxID": 1, "JointOvrlp": 0},
        ]
        tables["prop_sets_cyl"] = [{"PropSetID": 1, "PropD": 6, "PropThck": 0.06}]
        tables["member_coeffs_cyl"] = [coeff_row(meta["schemas"]["member_coeffs_cyl"], member_id=1)]
        tables["members"] = [
            {
                "MemberID": 1,
                "MJointID1": 1,
                "MJointID2": 2,
                "MPropSetID1": 1,
                "MPropSetID2": 1,
                "MDivSize": 0.5,
                "MCoefMod": 3,
                "PropPot": False,
            }
        ]
        updated, changes, warnings = apply_hydrodyn_tables(lines, {"tables": tables}, target_format="auto_v4_runtime")
        reparsed = parse_hydrodyn_tables(updated)
        self.assertFalse(warnings)
        self.assertTrue(any(change["countKey"] == "NMembers" and change["rows"] == 1 for change in changes))
        self.assertEqual(len(reparsed["tables"]["axial"]), 1)
        self.assertEqual(len(reparsed["tables"]["joints"]), 2)
        self.assertEqual(len(reparsed["tables"]["prop_sets_cyl"]), 1)
        self.assertEqual(len(reparsed["tables"]["member_coeffs_cyl"]), 1)
        self.assertEqual(len(reparsed["tables"]["members"]), 1)
        coef_idx = key_line(updated, "NCoefMembers")
        member_idx = key_line(updated, "NMembers")
        self.assertIn("MemberCb1", updated[coef_idx + 1])
        self.assertIn("MHstLMod", updated[member_idx + 1])
        self.assertEqual(len(updated[coef_idx + 3].split()), 29)
        self.assertEqual(len(updated[member_idx + 3].split()), 9)

    def test_repairs_missing_prop_set_and_member_coeff(self):
        lines = c4_hydrodyn_lines()
        meta = parse_hydrodyn_tables(lines)
        tables = meta["tables"]
        tables["axial"] = [{"AxCoefID": 1, "AxCd": 1, "AxCa": 1, "AxCp": 1, "AxFDMod": 0, "AxVnCOff": 0, "AxFDLoFSc": 1}]
        tables["joints"] = [
            {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": -20, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 10, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 3, "Jointxi": 5, "Jointyi": 0, "Jointzi": -20, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 4, "Jointxi": 5, "Jointyi": 0, "Jointzi": 10, "JointAxID": 1, "JointOvrlp": 0},
        ]
        tables["prop_sets_cyl"] = [{"PropSetID": 1, "PropD": 6, "PropThck": 0.06}]
        tables["member_coeffs_cyl"] = [coeff_row(meta["schemas"]["member_coeffs_cyl"], member_id=1)]
        tables["members"] = [
            {"MemberID": 1, "MJointID1": 1, "MJointID2": 2, "MPropSetID1": 1, "MPropSetID2": 1, "MCoefMod": 3},
            {"MemberID": 2, "MJointID1": 3, "MJointID2": 4, "MPropSetID1": 2, "MPropSetID2": 2, "MCoefMod": 3},
        ]
        updated, _changes, warnings = apply_hydrodyn_tables(lines, {"tables": tables}, target_format="auto_v4_runtime")
        reparsed = parse_hydrodyn_tables(updated)
        self.assertTrue(any("PropSetID 2" in warning for warning in warnings))
        self.assertTrue(any("Member 2" in warning for warning in warnings))
        self.assertEqual(len(reparsed["tables"]["prop_sets_cyl"]), 2)
        self.assertEqual(len(reparsed["tables"]["member_coeffs_cyl"]), 2)

    def test_v4_rejects_hydrostatic_endplate_at_waterplane(self):
        lines = c4_hydrodyn_lines()
        meta = parse_hydrodyn_tables(lines)
        tables = meta["tables"]
        tables["axial"] = [{"AxCoefID": 1, "AxCd": 1, "AxCa": 1, "AxCp": 1, "AxFDMod": 0, "AxVnCOff": 0, "AxFDLoFSc": 1}]
        tables["joints"] = [
            {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": 0, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 10, "JointAxID": 1, "JointOvrlp": 0},
        ]
        tables["prop_sets_cyl"] = [{"PropSetID": 1, "PropD": 6, "PropThck": 0.06}]
        tables["members"] = [
            {"MemberID": 1, "MJointID1": 1, "MJointID2": 2, "MPropSetID1": 1, "MPropSetID2": 1, "MCoefMod": 1, "MHstLMod": 1, "PropPot": False}
        ]
        with self.assertRaisesRegex(ValueError, "water plane"):
            apply_hydrodyn_tables(lines, {"tables": tables}, target_format="auto_v4_runtime")

    def test_parse_v5_sections(self):
        lines = """
False Echo
---------------------- AXIAL COEFFICIENTS --------------------------------------
            1   NAxCoef        - Number of axial coefficients (-)
AxCoefID  AxCd     AxCa     AxCp     AxFDMod     AxVnCOff      AxFDLoFSc
   (-)    (-)      (-)      (-)        (-)         (Hz)           (-)
1 1 1 1 0 0 1
---------------------- MEMBER JOINTS -------------------------------------------
            2   NJoints        - Number of joints (-)
JointID   Jointxi     Jointyi     Jointzi  JointAxID   JointOvrlp
   (-)     (m)         (m)         (m)        (-)       (switch)
1 0 0 -20 1 0
2 0 0 10 1 0
---------------- CYLINDRICAL MEMBER CROSS-SECTION PROPERTIES -------------------
            1   NPropSetsCyl      - Number of cylindrical member property sets (-)
PropSetID    PropD         PropThck
   (-)        (m)            (m)
1 6 0.06
---------------- RECTANGULAR MEMBER CROSS-SECTION PROPERTIES -------------------
            0   NPropSetsRec      - Number of rectangular member property sets (-)
MPropSetID    PropA    PropB    PropThck
   (-)        (m)      (m)      (m)
-------- SIMPLE CYLINDRICAL-MEMBER HYDRODYNAMIC COEFFICIENTS (model 1) ---------
SimplCd SimplCdMG SimplCa SimplCaMG SimplCp SimplCpMG SimplAxCd SimplAxCdMG SimplAxCa SimplAxCaMG SimplAxCp SimplAxCpMG SimplCb SimplCbMG
(-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
1 1 1 1 1 1 1 1 1 1 1 1 1 1
-------- SIMPLE RECTANGULAR-MEMBER HYDRODYNAMIC COEFFICIENTS (model 1) ---------
SimplCdA SimplCdAMG SimplCdB SimplCdBMG SimplCaA SimplCaAMG SimplCaB SimplCaBMG SimplCp SimplCpMG SimplAxCd SimplAxCdMG SimplAxCa SimplAxCaMG SimplAxCp SimplAxCpMG SimplCb SimplCbMG
(-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
------ DEPTH-BASED CYLINDRICAL-MEMBER HYDRODYNAMIC COEFFICIENTS (model 2) -------
            0   NCoefDpthCyl      - Number of depth-dependent cylindrical member coefficients (-)
Dpth DpthCd DpthCdMG DpthCa DpthCaMG DpthCp DpthCpMG DpthAxCd DpthAxCdMG DpthAxCa DpthAxCaMG DpthAxCp DpthAxCpMG DpthCb DpthCbMG
(m) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
------ DEPTH-BASED RECTANGULAR-MEMBER HYDRODYNAMIC COEFFICIENTS (model 2) -------
            0   NCoefDpthRec      - Number of depth-dependent rectangular member coefficients (-)
Dpth DpthCdA DpthCdAMG DpthCdB DpthCdBMG DpthCaA DpthCaAMG DpthCaB DpthCaBMG DpthCp DpthCpMG DpthAxCd DpthAxCdMG DpthAxCa DpthAxCaMG DpthAxCp DpthAxCpMG DpthCb DpthCbMG
(m) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
------ MEMBER-BASED CYLINDRICAL-MEMBER HYDRODYNAMIC COEFFICIENTS (model 3) ------
            1   NCoefMembersCyl      - Number of member-based cylindrical member coefficients (-)
MemberID MemberCd1 MemberCd2 MemberCdMG1 MemberCdMG2 MemberCa1 MemberCa2 MemberCaMG1 MemberCaMG2 MemberCp1 MemberCp2 MemberCpMG1 MemberCpMG2 MemberAxCd1 MemberAxCd2 MemberAxCdMG1 MemberAxCdMG2 MemberAxCa1 MemberAxCa2 MemberAxCaMG1 MemberAxCaMG2 MemberAxCp1 MemberAxCp2 MemberAxCpMG1 MemberAxCpMG2 MemberCb1 MemberCb2 MemberCbMG1 MemberCbMG2
(-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
------ MEMBER-BASED RECTANGULAR-MEMBER HYDRODYNAMIC COEFFICIENTS (model 3) ------
            0   NCoefMembersRec      - Number of member-based rectangular member coefficients (-)
MemberID MemberCdA1 MemberCdA2 MemberCdAMG1 MemberCdAMG2 MemberCdB1 MemberCdB2 MemberCdBMG1 MemberCdBMG2 MemberCaA1 MemberCaA2 MemberCaAMG1 MemberCaAMG2 MemberCaB1 MemberCaB2 MemberCaBMG1 MemberCaBMG2 MemberCp1 MemberCp2 MemberCpMG1 MemberCpMG2 MemberAxCd1 MemberAxCd2 MemberAxCdMG1 MemberAxCdMG2 MemberAxCa1 MemberAxCa2 MemberAxCaMG1 MemberAxCaMG2 MemberAxCp1 MemberAxCp2 MemberAxCpMG1 MemberAxCpMG2 MemberCb1 MemberCb2 MemberCbMG1 MemberCbMG2
(-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-) (-)
-------------------- MEMBERS -------------------------------------------------
            1   NMembers       - Number of members (-)
MemberID MJointID1 MJointID2 MPropSetID1 MPropSetID2 MSecGeom MSpinOrient MDivSize MCoefMod MHstLMod PropPot
(-) (-) (-) (-) (-) (switch) (deg) (m) (switch) (switch) (flag)
1 1 2 1 1 1 0 0.5 3 1 False
""".strip().splitlines()
        meta = parse_hydrodyn_tables(lines)
        self.assertEqual(meta["format"], "v5")
        self.assertEqual(len(meta["tables"]["prop_sets_cyl"]), 1)
        self.assertEqual(len(meta["tables"]["member_coeffs_cyl"]), 1)
        self.assertIn("MSecGeom", meta["schemas"]["members"])

        rect_count_idx = key_line(lines, "NPropSetsRec")
        lines[rect_count_idx + 1] = "PropSetID PropD PropThck"
        tables = meta["tables"]
        tables["prop_sets_rec"] = [{"MPropSetID": 2, "PropA": 12.5, "PropB": 7.0, "PropThck": 0.04}]
        tables["members"].append({
            "MemberID": 2,
            "MJointID1": 1,
            "MJointID2": 2,
            "MPropSetID1": 2,
            "MPropSetID2": 2,
            "MSecGeom": 2,
            "MSpinOrient": 0,
            "MDivSize": 1,
            "MCoefMod": 1,
            "MHstLMod": 0,
            "PropPot": True,
        })
        updated, _, warnings = apply_hydrodyn_tables(lines, {"tables": tables}, target_format="v5")
        rect_count_idx = key_line(updated, "NPropSetsRec")
        self.assertIn("MPropSetID", updated[rect_count_idx + 1])
        self.assertIn("PropA", updated[rect_count_idx + 1])
        self.assertEqual(updated[rect_count_idx + 3].split(), ["2", "12.5", "7", "0.04"])
        self.assertFalse(warnings)

    def test_v4_rejects_rectangular_member(self):
        lines = c4_hydrodyn_lines()
        meta = parse_hydrodyn_tables(lines)
        tables = meta["tables"]
        tables["joints"] = [
            {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": -20, "JointAxID": 1, "JointOvrlp": 0},
            {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 10, "JointAxID": 1, "JointOvrlp": 0},
        ]
        tables["prop_sets_rec"] = [{"MPropSetID": 1, "PropA": 6, "PropB": 4, "PropThck": 0.06}]
        tables["members"] = [{"MemberID": 1, "MJointID1": 1, "MJointID2": 2, "MPropSetID1": 1, "MPropSetID2": 1, "MSecGeom": 2, "MCoefMod": 1, "PropPot": False}]
        with self.assertRaises(ValueError):
            apply_hydrodyn_tables(lines, {"tables": tables}, target_format="auto_v4_runtime")

    def test_v5_repairs_complete_rectangular_member_bundle(self):
        tables = {
            "joints": [
                {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": -20, "JointAxID": 0, "JointOvrlp": 1},
                {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 10, "JointAxID": 0, "JointOvrlp": 2},
            ],
            "prop_sets_cyl": [{"PropSetID": 7, "PropD": 8, "PropThck": 0.08}],
            "member_coeffs_cyl": [{"MemberID": 4, "MemberCd1": 1, "MemberCd2": 1, "MemberCa1": 1, "MemberCa2": 1}],
            "members": [{
                "MemberID": 4,
                "MJointID1": 1,
                "MJointID2": 2,
                "MPropSetID1": 7,
                "MPropSetID2": 7,
                "MSecGeom": 2,
                "MSpinOrient": 0,
                "MDivSize": 0.5,
                "MCoefMod": 3,
                "MHstLMod": 0,
                "PropPot": False,
            }],
        }
        repaired, warnings = repair_hydrodyn_tables(tables, target_format="v5")
        self.assertTrue(warnings)
        self.assertEqual(repaired["joints"][0]["JointOvrlp"], 1, "v5 overlap data must not be rewritten as v4")
        self.assertEqual(repaired["prop_sets_rec"][0]["MPropSetID"], 7)
        self.assertEqual(repaired["prop_sets_rec"][0]["PropA"], 8)
        self.assertEqual(repaired["member_coeffs_rec"][0]["MemberID"], 4)
        self.assertEqual(repaired["member_coeffs_rec"][0]["MemberCdA1"], 1)
        self.assertFalse(repaired["member_coeffs_cyl"])
        self.assertFalse(validate_hydrodyn_tables(repaired, target_format="v5")["errors"])

    def test_member_without_endpoint_rows_is_rejected(self):
        tables = {
            "prop_sets_cyl": [{"PropSetID": 1, "PropD": 6, "PropThck": 0.06}],
            "members": [{
                "MemberID": 1,
                "MJointID1": 1,
                "MJointID2": 2,
                "MPropSetID1": 1,
                "MPropSetID2": 1,
                "MDivSize": 0.5,
                "MCoefMod": 1,
            }],
        }
        errors = validate_hydrodyn_tables(tables, target_format="v5")["errors"]
        self.assertTrue(any("MJointID1" in error for error in errors))
        self.assertTrue(any("MJointID2" in error for error in errors))

    def test_v5_rectangular_member_rejects_analytical_hydrostatics(self):
        tables = {
            "joints": [
                {"JointID": 1, "Jointxi": 0, "Jointyi": 0, "Jointzi": -20, "JointAxID": 1, "JointOvrlp": 0},
                {"JointID": 2, "Jointxi": 0, "Jointyi": 0, "Jointzi": 2, "JointAxID": 1, "JointOvrlp": 0},
            ],
            "prop_sets_rec": [{"MPropSetID": 1, "PropA": 6, "PropB": 6, "PropThck": 0.05}],
            "members": [{
                "MemberID": 1, "MJointID1": 1, "MJointID2": 2,
                "MPropSetID1": 1, "MPropSetID2": 1, "MSecGeom": 2,
                "MDivSize": 0.5, "MCoefMod": 1, "MHstLMod": 1,
            }],
        }
        errors = validate_hydrodyn_tables(tables, target_format="v5")["errors"]
        self.assertTrue(any("MHstLMod=1" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
