# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from linearization_workspace import analyze_linearization, discover_linearizations, parse_linearization_file


LIN_TEXT = """OpenFAST linearization output
Simulation time: 60.0
Number of continuous states: 2
Number of discrete states: 0
Number of constraint states: 0
Number of inputs: 1
Number of outputs: 1
Order of continuous states:
1 State one
2 State two
A:
-0.10 -2.00
 2.00 -0.10
B:
1.0
0.0
C:
1.0 0.0
D:
0.0
"""


class LinearizationWorkspaceTests(unittest.TestCase):
    def test_parses_and_analyzes_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "scenario" / "case" / "model.1.lin"
            path.parent.mkdir(parents=True)
            path.write_text(LIN_TEXT, encoding="utf-8")
            parsed = parse_linearization_file(path)
            self.assertEqual(parsed["matrices"]["A"].shape, (2, 2))
            result = analyze_linearization(root, "scenario/case/model.1.lin")
            self.assertEqual(len(result["modes"]), 1)
            self.assertAlmostEqual(result["modes"][0]["frequencyHz"], 2 / (2 * 3.141592653589793), places=6)
            self.assertTrue(result["modes"][0]["stable"])
            self.assertEqual(discover_linearizations(root)["count"], 1)


if __name__ == "__main__":
    unittest.main()
