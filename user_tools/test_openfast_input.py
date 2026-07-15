# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from openfast_input import (
    apply_outlist_edits,
    discover_model_dependencies,
    parse_outlist_sections,
    parse_scalar_fields,
    read_text_lines,
    write_outlist_edits,
)


class OpenFastInputTests(unittest.TestCase):
    def test_discovers_recursive_dependencies_and_missing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "Airfoils").mkdir()
            (root / "Main.fst").write_text(
                '"Module.dat"    EDFile - structural module\n'
                '"Missing.dat"   ServoFile - missing module\n'
                'OutList - output channels\n"Time"\nEND\n',
                encoding="utf-8",
            )
            (root / "Module.dat").write_text(
                '0.01 DT - time step\n'
                '"Airfoils/AF.dat" AFNames - airfoil table\n'
                'OutList - output channels\n"RotSpeed, GenPwr"\nEND\n',
                encoding="utf-8",
            )
            (root / "Airfoils" / "AF.dat").write_text("1 NumTabs - tabs\n", encoding="utf-8")

            structure = discover_model_dependencies(root, "Main.fst")
            node_ids = {row["id"] for row in structure["nodes"]}
            self.assertIn("Main.fst", node_ids)
            self.assertIn("Module.dat", node_ids)
            self.assertIn("Airfoils/AF.dat", node_ids)
            self.assertIn("Missing.dat", node_ids)
            self.assertEqual(structure["summary"]["missing"], 1)
            self.assertEqual(structure["summary"]["outListFiles"], 2)
            self.assertTrue(any(edge["key"] == "AFNames" for edge in structure["edges"]))

    def test_yaml_dependency_scan_ignores_comment_file_words(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "Main.fst").write_text(
                '"Controller.yaml" ControllerFile - controller settings\n',
                encoding="utf-8",
            )
            (root / "Controller.yaml").write_text(
                "path_params:\n"
                "  FAST_InputFile: 'Main.fst'  # Name of *.fst file\n"
                "  FAST_directory: '.'  # Main directory, where the *.fst lives\n"
                "  rotor_performance_filename: Cp_Ct_Cq.txt\n",
                encoding="utf-8",
            )
            (root / "Cp_Ct_Cq.txt").write_text("data\n", encoding="utf-8")

            structure = discover_model_dependencies(root, "Main.fst")
            node_ids = {row["id"] for row in structure["nodes"]}
            self.assertIn("Controller.yaml", node_ids)
            self.assertIn("Cp_Ct_Cq.txt", node_ids)
            self.assertNotIn("FAST_directory: '.'  # Main directory, where the *.fst lives", node_ids)
            self.assertEqual(structure["summary"]["missing"], 0)

    def test_dependency_scan_ignores_disabled_aeroacoustics_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "Main.fst").write_text(
                '"AeroDyn.dat" AeroFile - AeroDyn input\n',
                encoding="utf-8",
            )
            (root / "AeroDyn.dat").write_text(
                "False CompAA - aerodynamic acoustics disabled\n"
                '"MissingAcoustics.dat" AA_InputFile - unused input\n',
                encoding="utf-8",
            )

            structure = discover_model_dependencies(root, "Main.fst")
            node_ids = {row["id"] for row in structure["nodes"]}
            self.assertNotIn("MissingAcoustics.dat", node_ids)
            self.assertEqual(structure["summary"]["missing"], 0)

    def test_scalar_and_outlist_parsing(self):
        lines = [
            '"A path/file.dat" EDFile - module file',
            "30.0, 60.0 LinTimes - times",
            "OutList - channels",
            '  "RotSpeed, GenPwr"',
            '  "PtfmPitch"',
            "END",
        ]
        fields = parse_scalar_fields(lines)
        self.assertEqual(fields[0]["key"], "EDFile")
        self.assertEqual(fields[1]["value"], "30.0, 60.0")
        sections = parse_outlist_sections(lines)
        self.assertEqual(sections[0]["channels"], ["RotSpeed", "GenPwr", "PtfmPitch"])

    def test_writes_selected_outlist_and_preserves_surrounding_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "Module.dat"
            path.write_text(
                "1 Echo - echo\r\nOutList - channels\r\n  \"OldA, OldB\"\r\nEND\r\n2 SomeKey - keep\r\n",
                encoding="utf-8",
                newline="",
            )
            changes = write_outlist_edits(path, [{"section": 0, "channels": ["NewA", "NewB", "NewA"]}])
            lines, newline, trailing = read_text_lines(path)
            self.assertEqual(newline, "\r\n")
            self.assertTrue(trailing)
            self.assertIn('  "NewA"', lines)
            self.assertIn('  "NewB"', lines)
            self.assertIn("2 SomeKey - keep", lines)
            self.assertEqual(changes[0]["before"], ["OldA", "OldB"])
            self.assertEqual(changes[0]["channelCount"], 2)

    def test_apply_outlist_edits_is_confined_to_run_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = pathlib.Path(temp) / "run"
            run_dir.mkdir()
            module = run_dir / "Module.dat"
            module.write_text("OutList - channels\n\"Old\"\nEND\n", encoding="utf-8")
            changes = apply_outlist_edits(
                run_dir,
                [{"file": "Module.dat", "section": 0, "channels": ["Time", "Pitch"]}],
            )
            self.assertEqual(changes[0]["file"], "Module.dat")
            self.assertIn('"Pitch"', module.read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                apply_outlist_edits(
                    run_dir,
                    [{"file": "../outside.dat", "section": 0, "channels": ["Time"]}],
                )


if __name__ == "__main__":
    unittest.main()
