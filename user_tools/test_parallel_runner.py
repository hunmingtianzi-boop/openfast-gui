# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_tools"))

import run_scenario  # noqa: E402


def runner_args(workers: int, continue_on_fail: bool = True, resume: bool = False) -> SimpleNamespace:
    return SimpleNamespace(workers=workers, name=None, continue_on_fail=continue_on_fail, resume=resume)


class ParallelRunnerTests(unittest.TestCase):
    def test_parallel_cases_are_bounded_and_reported_in_scenario_order(self):
        cases = [{"name": f"case_{index}"} for index in range(1, 5)]
        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_run(case, scenario_name, out_root, args, **kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04 if case["name"] in {"case_1", "case_3"} else 0.01)
            with lock:
                active -= 1
            return {
                "scenario": scenario_name,
                "case": case["name"],
                "run_dir": str(out_root / case["name"]),
                "ok": True,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            report = root / "scenario_results.json"
            with mock.patch.object(run_scenario, "run_case", side_effect=fake_run):
                summaries, all_ok = run_scenario.execute_cases(cases, "parallel_test", root, runner_args(2), report)

            self.assertTrue(all_ok)
            self.assertEqual(max_active, 2)
            self.assertEqual([row["case"] for row in summaries], [f"case_{index}" for index in range(1, 5)])
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual([row["case"] for row in saved], [f"case_{index}" for index in range(1, 5)])

    def test_failure_stops_new_submissions_but_finishes_active_workers(self):
        cases = [{"name": f"case_{index}"} for index in range(1, 5)]
        started = []
        lock = threading.Lock()

        def fake_run(case, scenario_name, out_root, args, **kwargs):
            with lock:
                started.append(case["name"])
            if case["name"] == "case_1":
                return {"scenario": scenario_name, "case": case["name"], "ok": False, "error": "expected failure"}
            time.sleep(0.04)
            return {
                "scenario": scenario_name,
                "case": case["name"],
                "run_dir": str(out_root / case["name"]),
                "ok": True,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            report = root / "scenario_results.json"
            with mock.patch.object(run_scenario, "run_case", side_effect=fake_run):
                summaries, all_ok = run_scenario.execute_cases(
                    cases,
                    "stop_test",
                    root,
                    runner_args(2, continue_on_fail=False),
                    report,
                )

            self.assertFalse(all_ok)
            self.assertEqual(set(started), {"case_1", "case_2"})
            self.assertEqual([row["case"] for row in summaries], ["case_1", "case_2"])

    def test_duplicate_case_names_are_rejected(self):
        cases = [{"name": "duplicate"}, {"name": "duplicate"}]
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            with self.assertRaisesRegex(ValueError, "must be unique"):
                run_scenario.execute_cases(cases, "duplicate_test", root, runner_args(2), root / "report.json")

    def test_resume_reuses_successful_output_and_runs_only_missing_cases(self):
        cases = [{"name": "case_1"}, {"name": "case_2"}, {"name": "case_3"}]
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            scenario_dir = root / "resume_test"
            completed_dir = scenario_dir / "case_1"
            completed_dir.mkdir(parents=True)
            completed_out = completed_dir / "model.out"
            completed_out.write_text("existing output", encoding="utf-8")
            completed_summary = {
                "scenario": "resume_test",
                "case": "case_1",
                "run_dir": str(completed_dir),
                "ok": True,
                "execution": {"ok": True, "out": str(completed_out)},
            }
            (completed_dir / "scenario_summary.json").write_text(json.dumps(completed_summary), encoding="utf-8")
            started = []

            def fake_run(case, scenario_name, out_root, args, **kwargs):
                started.append(case["name"])
                return {
                    "scenario": scenario_name,
                    "case": case["name"],
                    "run_dir": str(out_root / scenario_name / case["name"]),
                    "ok": True,
                    "execution": {"ok": True},
                }

            report = scenario_dir / "scenario_results.json"
            with mock.patch.object(run_scenario, "run_case", side_effect=fake_run):
                summaries, all_ok = run_scenario.execute_cases(
                    cases,
                    "resume_test",
                    root,
                    runner_args(2, resume=True),
                    report,
                )

            self.assertTrue(all_ok)
            self.assertEqual(set(started), {"case_2", "case_3"})
            self.assertTrue(summaries[0]["resumed"])
            self.assertEqual([row["case"] for row in summaries], ["case_1", "case_2", "case_3"])


if __name__ == "__main__":
    unittest.main()
