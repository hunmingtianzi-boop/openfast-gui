# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_tools"))

import model_profiles  # noqa: E402


class LocalProfileOverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.config = self.root / "model_profiles.json"
        self.local = self.root / "local_model_profiles.json"
        self.model_root = self.root / "model"
        self.model_root.mkdir()
        (self.model_root / "main.fst").write_text("0 CompHydro\n", encoding="utf-8")
        (self.model_root / "HydroDyn.dat").write_text("HydroDyn\n", encoding="utf-8")
        self.runtime = self.root / "openfast.exe"
        self.runtime.write_bytes(b"placeholder")
        self.original_config = model_profiles.CONFIG_PATH
        self.original_local = model_profiles.LOCAL_CONFIG_PATH
        model_profiles.CONFIG_PATH = self.config
        model_profiles.LOCAL_CONFIG_PATH = self.local
        self.config.write_text(
            json.dumps(
                {
                    "models": [{"id": "test_model", "name": "Test model", "path": "D:/stale", "fst": "main.fst", "hydroFile": "HydroDyn.dat"}],
                    "runtimes": [{"id": "test_runtime", "name": "Test runtime", "path": "D:/stale/openfast.exe"}],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        model_profiles.CONFIG_PATH = self.original_config
        model_profiles.LOCAL_CONFIG_PATH = self.original_local
        self.temp.cleanup()

    def test_partial_local_override_keeps_shared_model_fields(self):
        self.local.write_text(
            json.dumps({"models": [{"id": "test_model", "path": str(self.model_root)}], "runtimes": []}),
            encoding="utf-8",
        )
        model = model_profiles.model_profiles()[0]
        self.assertEqual(model["name"], "Test model")
        self.assertEqual(model["fst"], "main.fst")
        self.assertEqual(model["hydroFile"], "HydroDyn.dat")
        self.assertTrue(model["fstExists"])

    def test_save_local_paths_writes_path_only_overrides(self):
        model, runtime = model_profiles.save_local_profile_paths(
            "test_model", self.model_root, "test_runtime", self.runtime
        )
        saved = json.loads(self.local.read_text(encoding="utf-8"))
        self.assertEqual(saved["models"], [{"id": "test_model", "path": str(self.model_root)}])
        self.assertEqual(saved["runtimes"], [{"id": "test_runtime", "path": str(self.runtime)}])
        self.assertTrue(model["fstExists"])
        self.assertTrue(runtime["exists"])


if __name__ == "__main__":
    unittest.main()
