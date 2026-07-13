# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from openfast_input import parse_editable_document
from tool_inputs import fastfarm_input_text, turbsim_input_text


class ToolInputTests(unittest.TestCase):
    def test_turbsim_template_contains_dlc_controls(self):
        text = turbsim_input_text({"seed": 42, "wind_speed": 11.5, "analysis_time": 800})
        self.assertIn("42        RandSeed1", text)
        self.assertIn("11.5 URef", text)
        self.assertIn("800 AnalysisTime", text)

    def test_fastfarm_template_is_editable_and_has_turbine_table(self):
        text = fastfarm_input_text(
            {
                "tmax": 900,
                "turbines": 2,
                "spacing": 1500,
                "fst_file": "model/Turbine.fst",
                "inflow_file": "model/InflowWind.dat",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "Farm.fstf"
            path.write_text(text, encoding="utf-8")
            document = parse_editable_document(path, path.name)
        self.assertEqual(document["plugin"]["id"], "fastfarm")
        self.assertEqual(next(field for field in document["fields"] if field["key"] == "NumTurbines")["parsedValue"], 2)
        self.assertEqual(document["tables"][0]["rows"].__len__(), 2)
        self.assertEqual(document["outLists"][0]["channels"][0], "RtAxsXT1")


if __name__ == "__main__":
    unittest.main()

