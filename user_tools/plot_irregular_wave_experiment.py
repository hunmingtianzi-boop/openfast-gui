# -*- coding: utf-8 -*-
"""Plot representative FOCAL C4 irregular-wave experiment records."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import shutil

import matplotlib.pyplot as plt
import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = pathlib.Path(
    r"D:\OpenFast\FOCAL_C4_workflow_hub\00_shared_assets\raw_data\focal_c4_organized\04_irregular_wave"
)
REPORT_DIR = ROOT / "reports" / "figures" / "irregular_wave"
WEB_DIR = ROOT / "webui" / "assets" / "irregular_wave"
CHANNELS = ["Time", "waveElev", "Surge", "Sway", "Heave", "Roll", "Pitch", "Yaw"]


def header_columns(path: pathlib.Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return next(csv.reader(handle))


def load_channels(path: pathlib.Path) -> dict[str, np.ndarray]:
    header = header_columns(path)
    indices = [header.index(name) for name in CHANNELS]
    data = np.loadtxt(path, delimiter=",", skiprows=2, usecols=indices)
    return {name: data[:, index] for index, name in enumerate(CHANNELS)}


def representative_files(data_root: pathlib.Path) -> list[dict]:
    specs = [
        {
            "id": "operational_E11",
            "label": "Operational E11-E15, Hs=3.1 m, Tp=8.96 s",
            "source_label": "E11W00 R01",
            "folder": "E11_E15_operational_Hs3p1_Tp8p96",
            "pattern": "*E11W00_R01*.csv",
        },
        {
            "id": "extreme_E21",
            "label": "Extreme E21-E25, Hs=8.1 m, Tp=12.8 s",
            "source_label": "E21W00 R01",
            "folder": "E21_E25_extreme_Hs8p1_Tp12p8",
            "pattern": "*E21W00_R01*.csv",
        },
    ]
    rows = []
    for spec in specs:
        folder = data_root / spec["folder"]
        matches = sorted(folder.glob(spec["pattern"]))
        if not matches:
            matches = sorted(folder.glob("*.csv"))
        if not matches:
            raise FileNotFoundError(f"No CSV files found in {folder}")
        rows.append({**spec, "path": matches[0]})
    return rows


def downsample(data: dict[str, np.ndarray], max_points: int = 6000) -> dict[str, np.ndarray]:
    n = len(data["Time"])
    step = max(1, int(np.ceil(n / max_points)))
    return {key: value[::step] for key, value in data.items()}


def stats(data: dict[str, np.ndarray]) -> dict[str, float]:
    wave = data["waveElev"]
    time_diffs = np.diff(data["Time"])
    positive_time_diffs = time_diffs[time_diffs > 0]
    return {
        "duration_s": float(data["Time"][-1] - data["Time"][0]),
        "dt_s": float(np.median(positive_time_diffs)) if positive_time_diffs.size else 0.0,
        "wave_mean_m": float(np.mean(wave)),
        "wave_std_m": float(np.std(wave)),
        "wave_hs_est_4std_m": float(4.0 * np.std(wave)),
        "surge_range_m": float(np.ptp(data["Surge"])),
        "heave_range_m": float(np.ptp(data["Heave"])),
        "pitch_range_deg": float(np.ptp(data["Pitch"])),
    }


def plot_overview(records: list[dict], out_png: pathlib.Path, out_pdf: pathlib.Path) -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.dpi": 130,
        }
    )
    fig, axes = plt.subplots(3, 2, figsize=(15, 9.5), sharex="col", constrained_layout=True)
    colors = {
        "waveElev": "#0f766e",
        "Surge": "#1f77b4",
        "Sway": "#9467bd",
        "Heave": "#2ca02c",
        "Roll": "#d62728",
        "Pitch": "#ff7f0e",
        "Yaw": "#4b5563",
    }
    for col, record in enumerate(records):
        data = downsample(record["data"])
        t_min = data["Time"] / 60.0
        summary = record["stats"]
        axes[0, col].plot(t_min, data["waveElev"], color=colors["waveElev"], lw=0.9)
        axes[0, col].set_title(
            f"{record['label']}\n"
            f"source: {record['source_label']} | "
            f"Hs_est=4*std={summary['wave_hs_est_4std_m']:.2f} m | "
            f"duration={summary['duration_s']/60:.1f} min"
        )
        axes[0, col].set_ylabel("Wave elev. (m)")
        for channel in ["Surge", "Sway", "Heave"]:
            axes[1, col].plot(t_min, data[channel], lw=0.9, label=channel, color=colors[channel])
        axes[1, col].set_ylabel("Translation (m)")
        axes[1, col].legend(ncol=3, loc="upper right")
        for channel in ["Roll", "Pitch", "Yaw"]:
            axes[2, col].plot(t_min, data[channel], lw=0.9, label=channel, color=colors[channel])
        axes[2, col].set_ylabel("Rotation (deg)")
        axes[2, col].set_xlabel("Time (min)")
        axes[2, col].legend(ncol=3, loc="upper right")
        for row in range(3):
            axes[row, col].grid(True, alpha=0.25)
    fig.suptitle("FOCAL C4 Irregular-Wave Experiment Reference", fontsize=14, fontweight="bold")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_summary(records: list[dict], out_csv: pathlib.Path, out_json: pathlib.Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "label", "source_label", "source", "duration_s", "dt_s", "wave_mean_m", "wave_std_m", "wave_hs_est_4std_m", "surge_range_m", "heave_range_m", "pitch_range_deg"]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({"id": record["id"], "label": record["label"], "source_label": record["source_label"], "source": str(record["path"]), **record["stats"]})
    manifest = {
        "figure": str(out_csv.parent / "experiment_overview.png"),
        "webFigure": "/assets/irregular_wave/experiment_overview.png",
        "records": [
            {
                "id": record["id"],
                "label": record["label"],
                "sourceLabel": record["source_label"],
                "source": str(record["path"]),
                "stats": record["stats"],
            }
            for record in records
        ],
    }
    out_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=str(DEFAULT_DATA))
    args = parser.parse_args(argv)
    data_root = pathlib.Path(args.data_root)
    records = representative_files(data_root)
    for record in records:
        record["data"] = load_channels(record["path"])
        record["stats"] = stats(record["data"])

    out_png = REPORT_DIR / "experiment_overview.png"
    out_pdf = REPORT_DIR / "experiment_overview.pdf"
    plot_overview(records, out_png=out_png, out_pdf=out_pdf)
    write_summary(records, REPORT_DIR / "experiment_summary.csv", REPORT_DIR / "experiment_manifest.json")

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_png, WEB_DIR / "experiment_overview.png")
    print(f"PNG: {out_png}")
    print(f"PDF: {out_pdf}")
    print(f"WEB: {WEB_DIR / 'experiment_overview.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
