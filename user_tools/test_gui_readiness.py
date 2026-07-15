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
    def test_scenario_revision_blocks_stale_writes_and_preserves_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "scenario.json"
            first_revision = ui_server.write_scenario_if_current(path, {"name": "first"}, None)
            self.assertEqual(first_revision, ui_server.scenario_revision(path))

            with self.assertRaises(ui_server.ScenarioRevisionConflict):
                ui_server.write_scenario_if_current(path, {"name": "stale"}, None)
            self.assertEqual(ui_server.read_json(path), {"name": "first"})

            second_revision = ui_server.write_scenario_if_current(path, {"name": "second"}, first_revision)
            self.assertNotEqual(first_revision, second_revision)
            self.assertEqual(ui_server.read_json(path), {"name": "second"})

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

    def test_case_override_resolves_a_missing_dependency_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "main.fst").write_text('"missing.so" DLL_FileName\n', encoding="utf-8")
            (root / "local.dll").write_bytes(b"controller")
            model = {
                "id": "m", "path": str(root), "exists": True,
                "fst": "main.fst", "fstExists": True,
            }
            runtime = {"id": "r", "path": sys.executable, "exists": True}
            structure = {
                "nodes": [
                    {"id": "main.fst", "exists": True, "external": False},
                    {"id": "missing.so", "exists": False, "external": False},
                ],
                "edges": [
                    {"source": "main.fst", "target": "missing.so", "key": "DLL_FileName"},
                ],
                "summary": {"missing": 1},
            }
            scenario = {
                "model_id": "m",
                "cases": [{"set": {"main.fst": {"DLL_FileName": "local.dll"}}}],
            }

            issues = ui_server.readiness_issues(
                model, runtime, scenario=scenario, structure=structure,
            )
            self.assertNotIn("dependency_missing", {issue["code"] for issue in issues})

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
