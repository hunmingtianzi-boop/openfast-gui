# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from visualization_workspace import discover_visualizations, load_visualization_geometry


LEGACY_VTK = """# vtk DataFile Version 3.0
triangle
ASCII
DATASET POLYDATA
POINTS 3 float
0 0 0  1 0 0  0 1 0
POLYGONS 1 4
3 0 1 2
"""

VTP = """<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData><Piece NumberOfPoints="3" NumberOfPolys="1">
    <Points><DataArray type="Float32" NumberOfComponents="3" format="ascii">0 0 0 1 0 0 0 1 0</DataArray></Points>
    <Polys>
      <DataArray type="Int32" Name="connectivity" format="ascii">0 1 2</DataArray>
      <DataArray type="Int32" Name="offsets" format="ascii">3</DataArray>
    </Polys>
  </Piece></PolyData>
</VTKFile>
"""


class VisualizationWorkspaceTests(unittest.TestCase):
    def test_parses_legacy_and_xml_polydata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            case = root / "scenario" / "case"
            case.mkdir(parents=True)
            (case / "shape.vtk").write_text(LEGACY_VTK, encoding="utf-8")
            (case / "shape.vtp").write_text(VTP, encoding="utf-8")
            legacy = load_visualization_geometry(root, "scenario/case/shape.vtk")
            xml = load_visualization_geometry(root, "scenario/case/shape.vtp")
            self.assertEqual(len(legacy["points"]), 3)
            self.assertEqual(legacy["triangles"], [[0, 1, 2]])
            self.assertEqual(xml["triangles"], [[0, 1, 2]])
            self.assertEqual(discover_visualizations(root)["count"], 2)


if __name__ == "__main__":
    unittest.main()
