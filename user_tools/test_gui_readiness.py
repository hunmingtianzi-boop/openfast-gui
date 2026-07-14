# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_tools"))

import ui_server  # noqa: E402


class GuiReadinessTests(unittest.TestCase):
    def test_scenario_mismatch_unknown_override_and_required_hydrodyn_are_blockers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "main.fst").write_text("1 CompHydro\n", encoding="utf-8")
            model = {
                "id": "selected_model",
                "path": str(root),
                "exists": True,
                "fst": "main.fst",
                "fstExists": True,
                "hydroFile": "HydroDyn.dat",
                "hydroPath": str(root / "HydroDyn.dat"),
                "hydroExists": False,
            }
            runtime = {"id": "runtime", "path": sys.executable, "exists": True}
            structure = {"nodes": [{"id": "main.fst", "exists": True, "external": False}], "summary": {"missing": 0}}
            scenario = {
                "model_id": "another_model",
                "cases": [{"set": {"main.fst": {"CompHydro": 1}, "outside.dat": {"TMax": 10}}}],
            }
            issues = ui_server.readiness_issues(model, runtime, scenario=scenario, structure=structure)
            codes = {issue["code"] for issue in issues if issue["severity"] == "error"}
            self.assertTrue({"scenario_model_mismatch", "override_target_unknown", "hydrodyn_required_missing"}.issubset(codes))

    def test_generate_only_does_not_require_the_runtime(self):
        model = {"id": "m", "path": "D:/missing", "exists": False, "fst": "main.fst", "fstPath": "D:/missing/main.fst", "fstExists": False}
        runtime = {"id": "r", "path": "D:/missing/openfast.exe", "exists": False}
        issues = ui_server.readiness_issues(model, runtime, structure={"summary": {}}, require_runtime=False)
        self.assertNotIn("runtime_missing", {issue["code"] for issue in issues})

    def test_v5_model_rejects_v4_runtime_and_stale_scenario_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "main.fst").write_text("1 CompHydro\n", encoding="utf-8")
            (root / "HydroDyn.dat").write_text("0 NPropSetsCyl\n", encoding="utf-8")
            model = {
                "id": "v5_model", "path": str(root), "exists": True,
                "fst": "main.fst", "fstExists": True,
                "hydroFile": "HydroDyn.dat", "hydroPath": str(root / "HydroDyn.dat"), "hydroExists": True,
                "supportedRuntimeFormats": ["v5"],
            }
            runtime = {
                "id": "v4_runtime", "path": sys.executable, "exists": True,
                "runtimeFormat": "v4", "version": "OpenFAST-v4.0.0",
            }
            scenario = {"model_id": "v5_model", "runtime_id": "v5_runtime", "cases": []}
            issues = ui_server.readiness_issues(
                model, runtime, scenario=scenario,
                structure={"nodes": [{"id": "main.fst", "exists": True}], "summary": {"missing": 0}},
            )
            codes = {issue["code"] for issue in issues if issue["severity"] == "error"}
            self.assertIn("runtime_format_incompatible", codes)
            self.assertIn("scenario_runtime_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
