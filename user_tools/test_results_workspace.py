# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pathlib
import struct
import sys
import tempfile
import unittest

import numpy as np


USER_TOOLS = pathlib.Path(__file__).resolve().parent
if str(USER_TOOLS) not in sys.path:
    sys.path.insert(0, str(USER_TOOLS))

from results_workspace import analyze_output_file, discover_results, read_output_metadata, resolve_result_path


def write_ascii(path: pathlib.Path, samples: int = 1024) -> None:
    rows = ["Synthetic OpenFAST output", "Time A B", "(s) (m) (deg)"]
    for index in range(samples):
        time = index * 0.1
        rows.append(f"{time:.3f} {np.sin(time):.8f} {2.0 * np.cos(time):.8f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _fixed(value: str, length: int) -> bytes:
    return value.encode("ascii")[:length].ljust(length, b" ")


def write_binary(path: pathlib.Path, file_id: int, samples: int = 1024) -> None:
    name_length = 16 if file_id == 4 else 10
    time = np.arange(samples, dtype=np.float64) * 0.1
    values = np.column_stack((np.sin(time), 2.0 * np.cos(time)))
    scales = np.array([1000.0, 1000.0], dtype="<f4")
    offsets = np.array([0.0, 0.0], dtype="<f4")
    description = b"Synthetic OpenFAST binary"
    with path.open("wb") as handle:
        handle.write(struct.pack("<h", file_id))
        if file_id == 4:
            handle.write(struct.pack("<h", name_length))
        handle.write(struct.pack("<i", 2))
        handle.write(struct.pack("<i", samples))
        if file_id == 1:
            handle.write(struct.pack("<d", 1000.0))
            handle.write(struct.pack("<d", 0.0))
        else:
            handle.write(struct.pack("<d", 0.0))
            handle.write(struct.pack("<d", 0.1))
        if file_id != 3:
            handle.write(scales.tobytes())
            handle.write(offsets.tobytes())
        handle.write(struct.pack("<i", len(description)))
        handle.write(description)
        for label in ["Time", "A", "B"]:
            handle.write(_fixed(label, name_length))
        for unit in ["(s)", "(m)", "(deg)"]:
            handle.write(_fixed(unit, name_length))
        if file_id == 1:
            handle.write(np.rint(time * 1000.0).astype("<i4").tobytes())
        if file_id == 3:
            handle.write(values.astype("<f8").tobytes())
        else:
            packed = np.rint(values * scales).astype("<i2")
            handle.write(packed.tobytes())


class ResultsWorkspaceTests(unittest.TestCase):
    def test_reads_ascii_metadata_analysis_statistics_and_psd(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "case.out"
            write_ascii(path)
            meta = read_output_metadata(path, use_cache=False)
            self.assertEqual(meta["format"], "ascii")
            self.assertEqual(meta["channelCount"], 3)
            self.assertAlmostEqual(meta["timeStep"], 0.1)
            result = analyze_output_file(path, ["A", "B"], start=10, end=50, max_points=300)
            self.assertLessEqual(result["window"]["displayPoints"], 300)
            self.assertEqual([row["name"] for row in result["statistics"]], ["A", "B"])
            self.assertAlmostEqual(result["statistics"][0]["absMax"], 1.0, places=4)
            self.assertEqual(len(result["psd"]), 2)

    def test_reads_all_supported_binary_file_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            for file_id in [1, 2, 3, 4]:
                path = root / f"case_{file_id}.outb"
                write_binary(path, file_id)
                meta = read_output_metadata(path, use_cache=False)
                self.assertEqual(meta["format"], "binary")
                self.assertEqual(meta["sampleCount"], 1024)
                self.assertAlmostEqual(meta["timeEnd"], 102.3, places=5)
                result = analyze_output_file(path, ["A"], start=5, end=15, max_points=250)
                self.assertEqual(result["series"][0]["name"], "A")
                self.assertGreater(result["statistics"][0]["count"], 90)
                self.assertAlmostEqual(result["statistics"][0]["absMax"], 1.0, places=2)

    def test_discovers_results_and_confines_result_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            runs = pathlib.Path(temp) / "runs"
            case = runs / "scenario_a" / "case_01"
            case.mkdir(parents=True)
            output = case / "Main.out"
            write_ascii(output, samples=64)
            (case / "scenario_summary.json").write_text(
                json.dumps({"ok": True, "fst": str(case / "Main.fst"), "execution": {"out": str(output)}}),
                encoding="utf-8",
            )
            catalog = discover_results(runs)
            self.assertEqual(catalog["summary"], {"scenarios": 1, "cases": 1, "files": 1})
            self.assertTrue(catalog["files"][0]["primary"])
            self.assertEqual(resolve_result_path(runs, catalog["files"][0]["id"]), output.resolve())
            with self.assertRaises(ValueError):
                resolve_result_path(runs, "../outside.out")


if __name__ == "__main__":
    unittest.main()
