# -*- coding: utf-8 -*-
"""Create a multi-seed PSD figure from completed OpenFAST outputs."""
from __future__ import annotations

import json
import pathlib
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from results_workspace import analyze_output_file, read_output_metadata


CHANNEL_SPECS = {
    "Wave1Elev": {
        "label": "Wave elevation",
        "aliases": ["Wave1Elev", "WaveElev", "WaveElev1"],
    },
    "PtfmSurge": {
        "label": "Platform surge",
        "aliases": ["PtfmSurge", "Surge"],
    },
    "PtfmHeave": {
        "label": "Platform heave",
        "aliases": ["PtfmHeave", "Heave"],
    },
    "PtfmPitch": {
        "label": "Platform pitch",
        "aliases": ["PtfmPitch", "Pitch"],
    },
    "RotSpeed": {
        "label": "Rotor speed",
        "aliases": ["RotSpeed", "GenSpeed"],
    },
    "GenPwr": {
        "label": "Generator power",
        "aliases": ["GenPwr"],
    },
    "FairTen1": {
        "label": "Fairlead tension 1",
        "aliases": ["FairTen1", "FAIRTEN1", "FairHTen1"],
    },
}
DEFAULT_CHANNELS = ["Wave1Elev", "PtfmSurge", "PtfmHeave", "PtfmPitch"]
DEFAULT_MODE_FREQUENCIES = {
    "Surge": 1.0 / 80.79,
    "Pitch": 1.0 / 30.79,
    "Tower": 0.458,
}


def _requested_spec(name: str) -> dict[str, Any]:
    configured = CHANNEL_SPECS.get(name)
    if configured:
        return {"name": name, **configured}
    return {"name": name, "label": name, "aliases": [name]}


def _resolve_channel(metadata: dict[str, Any], aliases: list[str]) -> str | None:
    available = {
        str(row.get("name") or "").lower(): str(row.get("name") or "")
        for row in metadata.get("channels") or []
        if row.get("name")
    }
    for alias in aliases:
        actual = available.get(str(alias).lower())
        if actual:
            return actual
    return None


def _peak(frequency: np.ndarray, density: np.ndarray) -> tuple[float | None, float | None]:
    valid = (frequency > 0) & np.isfinite(frequency) & np.isfinite(density)
    if not np.any(valid):
        return None, None
    valid_indices = np.flatnonzero(valid)
    index = int(valid_indices[int(np.argmax(density[valid]))])
    return float(frequency[index]), float(density[index])


def create_response_psd_aggregate(
    case_summaries: list[dict[str, Any]],
    scenario_name: str,
    spec: dict[str, Any],
    out_png: pathlib.Path,
    out_pdf: pathlib.Path | None = None,
) -> dict[str, Any]:
    requested = [str(value) for value in (spec.get("channels") or DEFAULT_CHANNELS) if str(value).strip()]
    if not requested:
        raise ValueError("response_psd.channels must contain at least one channel")
    if len(requested) > 8:
        raise ValueError("response_psd supports at most eight channels")

    start_time = float(spec.get("start_time_s", 100.0))
    end_raw = spec.get("end_time_s")
    end_time = float(end_raw) if end_raw not in {None, ""} else None
    max_frequency = float(spec.get("max_frequency_hz", 0.5))
    mode_frequencies = {
        str(name): float(value)
        for name, value in (spec.get("mode_frequencies_hz") or DEFAULT_MODE_FREQUENCIES).items()
    }
    channel_specs = [_requested_spec(name) for name in requested]
    records: dict[str, list[dict[str, Any]]] = {row["name"]: [] for row in channel_specs}
    warnings: list[str] = []

    completed = [
        row for row in case_summaries
        if isinstance(row, dict) and row.get("execution", {}).get("ok")
        and not row.get("execution", {}).get("skipped")
    ]
    for summary in completed:
        case_name = str(summary.get("case") or "case")
        output = pathlib.Path(str(summary.get("execution", {}).get("out") or ""))
        if not output.is_file():
            warnings.append(f"{case_name}: OpenFAST output missing")
            continue
        metadata = read_output_metadata(output)
        resolved = {
            row["name"]: _resolve_channel(metadata, list(row["aliases"]))
            for row in channel_specs
        }
        present = list(dict.fromkeys(value for value in resolved.values() if value))
        if not present:
            warnings.append(f"{case_name}: none of the requested PSD channels are available")
            continue
        analysis = analyze_output_file(
            output,
            present,
            start=start_time,
            end=end_time,
            max_points=4000,
            include_psd=True,
        )
        psd_by_name = {str(row["name"]).lower(): row for row in analysis.get("psd") or []}
        for row in channel_specs:
            actual = resolved[row["name"]]
            psd = psd_by_name.get(str(actual).lower()) if actual else None
            if not psd:
                warnings.append(f"{case_name}: {row['name']} is unavailable for PSD")
                continue
            frequency = np.asarray(psd["frequency"], dtype=float)
            density = np.asarray(psd["values"], dtype=float)
            peak_frequency, peak_density = _peak(frequency, density)
            records[row["name"]].append(
                {
                    "case": case_name,
                    "source": str(output),
                    "actual_channel": actual,
                    "unit": str(psd.get("unit") or "1/Hz"),
                    "frequency": frequency,
                    "density": density,
                    "peak_frequency_hz": peak_frequency,
                    "peak_density": peak_density,
                }
            )

    plottable = [row for row in channel_specs if records[row["name"]]]
    if not plottable:
        return {"ok": False, "skipped": True, "reason": "no_completed_psd_channels", "warnings": warnings}

    columns = 2 if len(plottable) > 1 else 1
    rows_count = int(np.ceil(len(plottable) / columns))
    with plt.rc_context(
        {
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "legend.fontsize": 7.5,
            "figure.dpi": 130,
        }
    ):
        fig, axes = plt.subplots(
            rows_count,
            columns,
            figsize=(13.2, 4.2 * rows_count),
            constrained_layout=True,
            squeeze=False,
        )
        colors = plt.get_cmap("tab10").colors
        channel_results = []
        for plot_index, row in enumerate(plottable):
            ax = axes.flat[plot_index]
            channel_records = records[row["name"]]
            common_frequency = channel_records[0]["frequency"]
            interpolated = []
            for case_index, record in enumerate(channel_records):
                frequency = record["frequency"]
                density = record["density"]
                visible = (frequency > 0) & (frequency <= max_frequency) & np.isfinite(density) & (density > 0)
                ax.semilogy(
                    frequency[visible],
                    density[visible],
                    color=colors[case_index % len(colors)],
                    lw=0.8,
                    alpha=0.65,
                    label=record["case"].rsplit("_", 1)[-1],
                )
                interpolated.append(np.interp(common_frequency, frequency, density, left=np.nan, right=np.nan))
            ensemble_density = np.nanmean(np.vstack(interpolated), axis=0)
            ensemble_visible = (
                (common_frequency > 0) & (common_frequency <= max_frequency)
                & np.isfinite(ensemble_density) & (ensemble_density > 0)
            )
            ax.semilogy(
                common_frequency[ensemble_visible],
                ensemble_density[ensemble_visible],
                color="#111827",
                lw=1.8,
                label="seed mean",
            )
            for mode_name, frequency in mode_frequencies.items():
                if 0 < frequency <= max_frequency:
                    ax.axvline(frequency, color="#64748b", lw=0.75, linestyle="--", alpha=0.75)
                    ax.text(
                        frequency,
                        0.97,
                        mode_name,
                        rotation=90,
                        va="top",
                        ha="right",
                        color="#475569",
                        transform=ax.get_xaxis_transform(),
                    )
            ax.set_xlim(0, max_frequency)
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel(f"PSD ({channel_records[0]['unit']})")
            ax.set_title(f"{row['label']} · {len(channel_records)} seeds")
            ax.grid(True, which="both", alpha=0.2)
            if plot_index == 0:
                ax.legend(loc="upper right", ncol=min(3, len(channel_records) + 1))
            ensemble_peak_frequency, ensemble_peak_density = _peak(common_frequency, ensemble_density)
            channel_results.append(
                {
                    "name": row["name"],
                    "label": row["label"],
                    "unit": channel_records[0]["unit"],
                    "case_count": len(channel_records),
                    "ensemble_peak_frequency_hz": ensemble_peak_frequency,
                    "ensemble_peak_density": ensemble_peak_density,
                    "cases": [
                        {
                            key: record[key]
                            for key in ("case", "source", "actual_channel", "peak_frequency_hz", "peak_density")
                        }
                        for record in channel_records
                    ],
                }
            )
        for unused_index in range(len(plottable), rows_count * columns):
            fig.delaxes(axes.flat[unused_index])
        end_label = f"{end_time:g}" if end_time is not None else "end"
        fig.suptitle(
            f"IEA 15 MW UMaineSemi multi-seed response PSD | {start_time:g}-{end_label} s | Welch/Hann",
            fontsize=13,
            fontweight="bold",
        )
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_pdf = out_pdf or out_png.with_suffix(".pdf")
        fig.savefig(out_png, dpi=180, bbox_inches="tight", facecolor="white")
        fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    result = {
        "ok": True,
        "comparison_type": "response_psd_aggregate",
        "label": "五随机种子响应 PSD / Five-seed response PSD",
        "scenario": scenario_name,
        "png": str(out_png),
        "pdf": str(out_pdf),
        "window_s": [start_time, end_time],
        "max_frequency_hz": max_frequency,
        "method": "Welch PSD, Hann window, half-record segments, 50% overlap, constant detrend",
        "mode_frequencies_hz": mode_frequencies,
        "channels": channel_results,
        "warnings": sorted(set(warnings)),
    }
    out_png.with_suffix(".json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
