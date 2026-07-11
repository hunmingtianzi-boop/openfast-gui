from __future__ import annotations

import pathlib
import tempfile
import unittest

import numpy as np

from plot_irregular_wave_experiment import create_focal_simulation_aggregate


class FocalWavePlotTests(unittest.TestCase):
    def test_five_seed_openfast_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            times = np.arange(0.0, 9001.0, 1.0)
            summaries = []
            cases = []
            for seed_id in range(11, 16):
                case_name = f"focal_e{seed_id}_jonswap"
                out_path = root / f"{case_name}.out"
                wave = 0.75 * np.sin(2.0 * np.pi * times / 8.96 + seed_id)
                rows = ["Synthetic OpenFAST output", "Time Wave1Elev", "(s) (m)"]
                rows.extend(f"{time_value:g} {wave_value:.9g}" for time_value, wave_value in zip(times, wave))
                out_path.write_text("\n".join(rows), encoding="utf-8")
                cases.append(
                    {
                        "name": case_name,
                        "focal_wave": {"group": "E11_E15", "wave_id": f"E{seed_id}"},
                    }
                )
                summaries.append(
                    {
                        "case": case_name,
                        "execution": {"ok": True, "out": str(out_path)},
                        "focal_wave": {"group": "E11_E15", "wave_id": f"E{seed_id}"},
                    }
                )

            result = create_focal_simulation_aggregate(
                case_summaries=summaries,
                scenario_cases=cases,
                group_id="E11_E15",
                out_png=root / "aggregate.png",
                out_pdf=root / "aggregate.pdf",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(5, len(result["seeds"]))
            self.assertTrue((root / "aggregate.png").is_file())
            self.assertTrue((root / "aggregate.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
