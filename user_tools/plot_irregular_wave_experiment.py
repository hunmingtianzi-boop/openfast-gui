# -*- coding: utf-8 -*-
"""Plot representative FOCAL C4 irregular-wave experiment records."""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import shutil
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = pathlib.Path(
    os.environ.get(
        "FOCAL_C4_IRREGULAR_DATA",
        r"D:\OpenFast\FOCAL_C4_PROJECT\01_data\raw_focal_c4_organized\04_irregular_wave",
    )
)
REPORT_DIR = ROOT / "reports" / "figures" / "irregular_wave"
WEB_DIR = ROOT / "webui" / "assets" / "irregular_wave"
CHANNELS = ["Time", "waveElev", "Surge", "Sway", "Heave", "Roll", "Pitch", "Yaw"]
COMPARISON_CHANNELS = ["waveElev", "Surge", "Sway", "Heave", "Roll", "Pitch", "Yaw"]
SIM_CHANNEL_ALIASES = {
    "waveElev": ["Wave1Elev", "WaveElev", "WaveElev1", "waveElev"],
    "Surge": ["PtfmSurge", "Surge"],
    "Sway": ["PtfmSway", "Sway"],
    "Heave": ["PtfmHeave", "Heave"],
    "Roll": ["PtfmRoll", "Roll"],
    "Pitch": ["PtfmPitch", "Pitch"],
    "Yaw": ["PtfmYaw", "Yaw"],
}
FOCAL_WAVE_GROUPS = {
    "E11_E15": {
        "id": "E11_E15",
        "label": "E11-E15 operational sea state",
        "folder": "E11_E15_operational_Hs3p1_Tp8p96",
        "seed_ids": list(range(11, 16)),
        "hs": 3.1,
        "tp": 8.96,
        "gamma": 1.80,
        "duration_s": 9294.4,
    },
    "E21_E25": {
        "id": "E21_E25",
        "label": "E21-E25 1-year extreme sea state",
        "folder": "E21_E25_extreme_Hs8p1_Tp12p8",
        "seed_ids": list(range(21, 26)),
        "hs": 8.1,
        "tp": 12.8,
        "gamma": 2.75,
        "duration_s": 9754.4,
    },
}
DEFAULT_MODE_FREQUENCIES = {
    "Surge": 1.0 / 80.79,
    "Pitch": 1.0 / 30.79,
    "Tower": 0.458,
}


def header_columns(path: pathlib.Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return next(csv.reader(handle))


def load_channels(path: pathlib.Path) -> dict[str, np.ndarray]:
    header = header_columns(path)
    indices = [header.index(name) for name in CHANNELS]
    data = np.loadtxt(path, delimiter=",", skiprows=2, usecols=indices)
    return {name: data[:, index] for index, name in enumerate(CHANNELS)}


def load_wave_calibration(path: pathlib.Path, channel: str = "waveStaff2") -> dict[str, np.ndarray]:
    """Load the report's calibration-probe element and remove repeated timestamps."""
    header = header_columns(path)
    selected = channel if channel in header else "waveElev"
    indices = [header.index("Time"), header.index(selected)]
    raw = np.loadtxt(path, delimiter=",", skiprows=2, usecols=indices)
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    finite = np.isfinite(raw).all(axis=1)
    raw = raw[finite]
    unique_time = np.r_[True, np.diff(raw[:, 0]) > 0]
    raw = raw[unique_time]
    return {"Time": raw[:, 0], "waveElev": raw[:, 1]}


def focal_seed_records(data_root: pathlib.Path, group_id: str) -> list[dict[str, Any]]:
    spec = FOCAL_WAVE_GROUPS[group_id]
    primary = data_root / spec["folder"]
    fallback = data_root.parent / "07_unknown_or_unclear"
    records: list[dict[str, Any]] = []
    for seed_id in spec["seed_ids"]:
        pattern = f"*E{seed_id}W00_R01_R01*.csv"
        matches = sorted(primary.glob(pattern))
        if not matches:
            matches = sorted(fallback.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"FOCAL E{seed_id} CSV not found below {data_root.parent}")
        records.append(
            {
                "id": f"E{seed_id}",
                "label": f"E{seed_id}",
                "source_label": matches[0].stem,
                "path": matches[0],
            }
        )
    return records


def wave_psd(
    data: dict[str, np.ndarray],
    start_s: float = 2000.0,
    end_s: float = 8000.0,
    segment_seconds: float = 768.0,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    time_values = data["Time"]
    wave = data["waveElev"]
    mask = (time_values >= start_s) & (time_values <= end_s)
    if np.count_nonzero(mask) < 16:
        raise ValueError(f"Not enough wave samples in PSD window {start_s:g}-{end_s:g} s")
    time_values = time_values[mask]
    wave = wave[mask]
    time_diffs = np.diff(time_values)
    positive = time_diffs[time_diffs > 0]
    if not positive.size:
        raise ValueError("Wave time series has no positive time step")
    sample_rate = 1.0 / float(np.median(positive))
    nperseg = min(len(wave), max(256, int(round(sample_rate * segment_seconds))))
    frequencies, density = welch(
        wave,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend="constant",
        scaling="density",
    )
    positive_frequency = frequencies > 0
    peak_index = int(np.argmax(density[positive_frequency]))
    peak_frequency = float(frequencies[positive_frequency][peak_index])
    hs_psd = float(4.0 * np.sqrt(np.trapezoid(density, frequencies)))
    return frequencies, density, {
        "sample_rate_hz": sample_rate,
        "nperseg": float(nperseg),
        "peak_frequency_hz": peak_frequency,
        "hs_psd_m": hs_psd,
    }


def plot_wave_calibration_group(
    records: list[dict[str, Any]],
    group_id: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path,
    mode_frequencies: dict[str, float] | None = None,
    psd_start_s: float = 2000.0,
    psd_end_s: float = 8000.0,
) -> dict[str, Any]:
    spec = FOCAL_WAVE_GROUPS[group_id]
    mode_frequencies = mode_frequencies or DEFAULT_MODE_FREQUENCIES
    colors = plt.get_cmap("tab10").colors
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.dpi": 130,
        }
    )
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(12.5, 7.5),
        gridspec_kw={"height_ratios": [1.15, 1]},
        constrained_layout=True,
    )
    seed_stats = []
    for index, record in enumerate(records):
        data = record["data"]
        plotted = downsample(data, max_points=12000)
        color = colors[index % len(colors)]
        axes[0].plot(plotted["Time"], plotted["waveElev"], lw=0.65, color=color, label=record["label"])
        frequency, density, psd_stats = wave_psd(data, start_s=psd_start_s, end_s=psd_end_s)
        visible = frequency <= 0.5
        axes[1].plot(frequency[visible], density[visible], lw=0.9, color=color, label=record["label"])
        seed_stats.append(
            {
                "id": record["id"],
                "source": str(record.get("path") or record.get("source") or ""),
                "duration_s": float(data["Time"][-1] - data["Time"][0]),
                "hs_4std_m": float(4.0 * np.std(data["waveElev"])),
                **psd_stats,
            }
        )

    axes[0].set_ylabel("Wave elevation (m)")
    axes[0].set_xlabel("Time (s)")
    axes[0].set_xlim(left=0)
    axes[0].grid(True, alpha=0.24)
    axes[0].legend(loc="upper right", ncol=min(5, len(records)))

    mode_colors = {"Surge": "#ef4444", "Pitch": "#1d4ed8", "Tower": "#d946ef"}
    label_y = 0.97
    for name, frequency in mode_frequencies.items():
        axes[1].axvline(frequency, color=mode_colors.get(name, "#64748b"), lw=0.9, alpha=0.8)
        axes[1].text(
            frequency,
            label_y,
            name,
            color=mode_colors.get(name, "#64748b"),
            rotation=90,
            va="top",
            ha="right",
            transform=axes[1].get_xaxis_transform(),
        )
    axes[1].set_xlim(0, 0.5)
    axes[1].set_ylim(bottom=0)
    axes[1].set_xlabel("Frequency (Hz)")
    axes[1].set_ylabel("Wave elevation PSD (m$^2$/Hz)")
    axes[1].grid(True, alpha=0.24)
    axes[1].legend(loc="upper right", ncol=min(5, len(records)))
    fig.suptitle(
        f"FOCAL Campaign 4 {spec['id'].replace('_', '-')} | "
        f"Hs={spec['hs']:g} m, Tp={spec['tp']:g} s, Gamma={spec['gamma']:.2f}",
        fontsize=13,
        fontweight="bold",
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    result = {
        "ok": True,
        "comparison_type": "focal_wave_calibration",
        "group": group_id,
        "label": f"FOCAL {spec['id'].replace('_', '-')} wave time histories and PSD",
        "png": str(out_png),
        "pdf": str(out_pdf),
        "psd_window_s": [psd_start_s, psd_end_s],
        "psd_method": "Welch, Hann window, 768 s segments, 50% overlap",
        "mode_frequencies_hz": mode_frequencies,
        "seeds": seed_stats,
    }
    out_png.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def create_focal_reference_figures(
    data_root: pathlib.Path = DEFAULT_DATA,
    report_dir: pathlib.Path = REPORT_DIR,
    web_dir: pathlib.Path = WEB_DIR,
) -> list[dict[str, Any]]:
    results = []
    for group_id in FOCAL_WAVE_GROUPS:
        records = focal_seed_records(data_root, group_id)
        for record in records:
            record["data"] = load_wave_calibration(record["path"])
        stem = f"focal_{group_id.lower()}_calibration"
        result = plot_wave_calibration_group(
            records,
            group_id=group_id,
            out_png=report_dir / f"{stem}.png",
            out_pdf=report_dir / f"{stem}.pdf",
        )
        web_dir.mkdir(parents=True, exist_ok=True)
        web_path = web_dir / f"{stem}.png"
        shutil.copyfile(result["png"], web_path)
        result["web_png"] = str(web_path)
        result["web_url"] = f"/assets/irregular_wave/{stem}.png"
        results.append(result)
    (report_dir / "focal_calibration_manifest.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return results


def create_focal_simulation_aggregate(
    case_summaries: list[dict[str, Any]],
    scenario_cases: list[dict[str, Any]],
    group_id: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path,
    mode_frequencies: dict[str, float] | None = None,
) -> dict[str, Any]:
    case_by_name = {str(case.get("name") or ""): case for case in scenario_cases}
    records = []
    for summary in case_summaries:
        case_name = str(summary.get("case") or "")
        original = case_by_name.get(case_name)
        metadata = summary.get("focal_wave") or (original or {}).get("focal_wave") or {}
        if metadata.get("group") != group_id or not summary.get("execution", {}).get("ok"):
            continue
        out_path = pathlib.Path(str(summary["execution"].get("out") or ""))
        if not out_path.is_file():
            continue
        data, _ = load_openfast_channels(out_path)
        if "waveElev" not in data:
            continue
        records.append(
            {
                "id": metadata.get("wave_id") or case_name,
                "label": metadata.get("wave_id") or case_name,
                "path": out_path,
                "data": {"Time": data["Time"], "waveElev": data["waveElev"]},
            }
        )
    expected = len(FOCAL_WAVE_GROUPS[group_id]["seed_ids"])
    if len(records) != expected:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"expected_{expected}_completed_cases_found_{len(records)}",
            "group": group_id,
        }
    records.sort(key=lambda record: record["label"])
    return plot_wave_calibration_group(
        records,
        group_id=group_id,
        out_png=out_png,
        out_pdf=out_pdf,
        mode_frequencies=mode_frequencies,
    )


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


def infer_experiment_id(case: dict[str, Any] | None, case_name: str = "") -> str | None:
    text = " ".join(
        str(part)
        for part in [
            case_name,
            (case or {}).get("name", ""),
            (case or {}).get("notes", ""),
        ]
    ).lower()
    if "operational" in text or "e11" in text or "hs3p1" in text or "hs3.1" in text:
        return "operational_E11"
    if "extreme" in text or "e21" in text or "hs8p1" in text or "hs8.1" in text:
        return "extreme_E21"
    return None


def experiment_record_for_case(case: dict[str, Any], data_root: pathlib.Path, case_name: str = "") -> dict[str, Any]:
    comparison = case.get("comparison") or {}
    csv_path = comparison.get("experiment_csv")
    if csv_path:
        path = pathlib.Path(csv_path)
        if not path.is_absolute():
            path = data_root / path
        return {
            "id": comparison.get("experiment_id") or path.stem,
            "label": comparison.get("label") or path.stem,
            "source_label": comparison.get("source_label") or path.stem,
            "path": path,
        }

    experiment_id = comparison.get("experiment_id") or case.get("experiment_id") or infer_experiment_id(case, case_name)
    records = representative_files(data_root)
    if experiment_id:
        for record in records:
            if record["id"] == experiment_id:
                return record
    known = ", ".join(record["id"] for record in records)
    raise ValueError(f"No experiment comparison record configured for case {case_name!r}. Known experiment ids: {known}")


def openfast_header(path: pathlib.Path) -> tuple[int, list[str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for lineno, line in enumerate(handle):
            tokens = line.strip().split()
            if tokens and tokens[0] == "Time":
                return lineno, tokens
    raise ValueError(f"Could not find OpenFAST output header in {path}")


def load_openfast_channels(path: pathlib.Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    header_line, header = openfast_header(path)
    indices = {"Time": header.index("Time")}
    selected_names = {"Time": "Time"}
    missing = []
    for target, aliases in SIM_CHANNEL_ALIASES.items():
        found = next((name for name in aliases if name in header), None)
        if found is None:
            missing.append(target)
            continue
        indices[target] = header.index(found)
        selected_names[target] = found

    usecols = list(indices.values())
    keys = list(indices.keys())
    try:
        raw = np.loadtxt(path, skiprows=header_line + 2, usecols=usecols)
    except ValueError:
        raw = np.genfromtxt(path, skip_header=header_line + 2, usecols=usecols, invalid_raise=False)
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    data = {key: raw[:, column] for column, key in enumerate(keys)}
    finite = np.isfinite(data["Time"])
    for key in list(data):
        data[key] = data[key][finite]
    meta = {"selected_names": selected_names, "missing": missing, "header_line": header_line}
    return data, meta


def downsample(data: dict[str, np.ndarray], max_points: int = 6000) -> dict[str, np.ndarray]:
    n = len(data["Time"])
    step = max(1, int(np.ceil(n / max_points)))
    return {key: value[::step] for key, value in data.items()}


def channel_rmse(reference: dict[str, np.ndarray], simulation: dict[str, np.ndarray], channel: str) -> float | None:
    t_ref = reference["Time"] - reference["Time"][0]
    t_sim = simulation["Time"] - simulation["Time"][0]
    overlap = min(float(t_ref[-1]), float(t_sim[-1]))
    if overlap <= 0:
        return None
    mask = (t_ref >= 0) & (t_ref <= overlap)
    if np.count_nonzero(mask) < 2:
        return None
    ref_time = t_ref[mask]
    ref_values = reference[channel][mask]
    if ref_time.size > 20000:
        step = int(np.ceil(ref_time.size / 20000))
        ref_time = ref_time[::step]
        ref_values = ref_values[::step]
    sim_values = np.interp(ref_time, t_sim, simulation[channel])
    return float(np.sqrt(np.mean((sim_values - ref_values) ** 2)))


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


def plot_comparison(
    experiment: dict[str, np.ndarray],
    simulation: dict[str, np.ndarray],
    experiment_label: str,
    simulation_label: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path,
) -> dict[str, Any]:
    available = [channel for channel in COMPARISON_CHANNELS if channel in experiment and channel in simulation]
    if not available:
        raise ValueError("No matching channels found between experiment data and OpenFAST output.")

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.dpi": 130,
        }
    )
    titles = {
        "waveElev": "Wave elevation (m)",
        "Surge": "Surge (m)",
        "Sway": "Sway (m)",
        "Heave": "Heave (m)",
        "Roll": "Roll (deg)",
        "Pitch": "Pitch (deg)",
        "Yaw": "Yaw (deg)",
    }
    rows = int(np.ceil(len(available) / 2))
    fig, axes = plt.subplots(rows, 2, figsize=(15, max(5.5, rows * 2.8)), constrained_layout=True)
    axes_arr = np.atleast_1d(axes).ravel()
    exp_plot = downsample(experiment)
    sim_plot = downsample(simulation)
    t_exp = (exp_plot["Time"] - exp_plot["Time"][0]) / 60.0
    t_sim = (sim_plot["Time"] - sim_plot["Time"][0]) / 60.0
    metrics: dict[str, dict[str, float | None]] = {}

    for ax, channel in zip(axes_arr, available):
        rmse = channel_rmse(experiment, simulation, channel)
        metrics[channel] = {"rmse": rmse}
        ax.plot(t_exp, exp_plot[channel], color="#0f766e", lw=0.9, label="Experiment")
        ax.plot(t_sim, sim_plot[channel], color="#b42318", lw=0.85, alpha=0.9, label="OpenFAST")
        suffix = f" | RMSE={rmse:.3g}" if rmse is not None else ""
        ax.set_title(f"{titles.get(channel, channel)}{suffix}")
        ax.set_xlabel("Time (min)")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right")

    for ax in axes_arr[len(available) :]:
        ax.axis("off")
    fig.suptitle(f"Experiment vs OpenFAST\n{experiment_label} | {simulation_label}", fontsize=14, fontweight="bold")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"channels": available, "metrics": metrics}


def create_case_comparison(
    openfast_out: pathlib.Path,
    case: dict[str, Any],
    scenario_name: str,
    case_name: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path | None = None,
    data_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    data_root = data_root or pathlib.Path((case.get("comparison") or {}).get("data_root") or DEFAULT_DATA)
    out_pdf = out_pdf or out_png.with_suffix(".pdf")
    record = experiment_record_for_case(case, data_root=data_root, case_name=case_name)
    experiment_data = load_channels(record["path"])
    simulation_data, sim_meta = load_openfast_channels(openfast_out)
    plot_meta = plot_comparison(
        experiment=experiment_data,
        simulation=simulation_data,
        experiment_label=record["label"],
        simulation_label=f"{scenario_name}/{case_name}",
        out_png=out_png,
        out_pdf=out_pdf,
    )
    warnings = [f"Missing OpenFAST channel for {name}" for name in sim_meta["missing"]]
    result = {
        "ok": True,
        "experiment_id": record["id"],
        "experiment_label": record["label"],
        "experiment_source": str(record["path"]),
        "openfast_out": str(openfast_out),
        "png": str(out_png),
        "pdf": str(out_pdf),
        "warnings": warnings,
        **plot_meta,
    }
    (out_png.parent / "comparison_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


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
    parser.add_argument("--calibration-figures", action="store_true")
    args = parser.parse_args(argv)
    data_root = pathlib.Path(args.data_root)
    if args.calibration_figures:
        results = create_focal_reference_figures(data_root=data_root)
        for result in results:
            print(f"PNG: {result['png']}")
            print(f"PDF: {result['pdf']}")
            print(f"WEB: {result['web_png']}")
        return 0
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
