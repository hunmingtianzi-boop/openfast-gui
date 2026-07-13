# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from module_plugins import classify_module
from openfast_input import (
    apply_input_edits,
    apply_input_file_overrides,
    file_sha256,
    parse_editable_document,
)


class ModulePluginTests(unittest.TestCase):
    def test_classifies_all_planned_module_families(self):
        cases = {
            "Main.fst": "openfast",
            "InflowWind.dat": "inflowwind",
            "SeaState.dat": "seastate",
            "HydroDyn.dat": "hydrodyn",
            "MoorDyn.dat": "moordyn",
            "ElastoDyn.dat": "elastodyn",
            "AeroDyn15.dat": "aerodyn",
            "ServoDyn.dat": "servodyn",
            "DISCON.IN": "rosco",
            "BeamDyn.dat": "beamdyn",
            "SubDyn.dat": "subdyn",
            "ExtPtfm.dat": "extptfm",
            "Farm.fstf": "fastfarm",
            "Wind/TurbSim.in": "turbsim",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_module(name).id, expected)

    def test_parses_fields_tables_matrices_and_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "MoorDyn.dat"
            source.write_text(
                "---------------- LINE TYPES ----------------\n"
                "Name Diam EA\n"
                "(-) (m) (N)\n"
                "main 0.2 1e9\n"
                "---------------- OPTIONS ----------------\n"
                "False Echo - echo input\n"
                "1 0 0 0 0 0 AddCLin\n"
                "0 1 0 0 0 0\n"
                "0 0 1 0 0 0\n"
                "0 0 0 1 0 0\n"
                "0 0 0 0 1 0\n"
                "0 0 0 0 0 1\n",
                encoding="utf-8",
            )
            document = parse_editable_document(source, source.name)
            self.assertEqual(document["plugin"]["id"], "moordyn")
            self.assertIn("Echo", {field["key"] for field in document["fields"]})
            self.assertEqual(document["tables"][0]["rows"][0]["tokens"][0], "main")
            self.assertEqual(document["matrices"][0]["rows"][0]["values"][0], 1.0)

            yaml_file = root / "Controller_ROSCO.yaml"
            yaml_file.write_text("controller_params:\n  LoggingLevel: 1 # logging\n", encoding="utf-8")
            yaml_document = parse_editable_document(yaml_file, yaml_file.name)
            self.assertEqual(yaml_document["fields"][0]["path"], "controller_params.LoggingLevel")

    def test_applies_line_and_full_file_edits_inside_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "Input.dat"
            source.write_text("False Echo - echo\n1 Value - number\n", encoding="utf-8")
            changes = apply_input_edits(
                root,
                [{"file": "Input.dat", "line": 1, "key": "Echo", "format": "openfast", "type": "boolean", "value": True}],
            )
            self.assertEqual(len(changes), 1)
            self.assertTrue(source.read_text(encoding="utf-8").startswith("True"))

            before = file_sha256(source)
            override_changes = apply_input_file_overrides(
                root,
                [{"file": "Input.dat", "source_sha256": before, "content": "2 Value - number\n"}],
            )
            self.assertEqual(override_changes[0]["mode"], "full-file")
            self.assertEqual(source.read_text(encoding="utf-8"), "2 Value - number\n")
            with self.assertRaises(ValueError):
                apply_input_edits(root, [{"file": "../escape.dat", "line": 1, "kind": "line", "text": "bad"}])


if __name__ == "__main__":
    unittest.main()
