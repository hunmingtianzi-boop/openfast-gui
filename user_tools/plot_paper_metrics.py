# -*- coding: utf-8 -*-
"""Create paper-style metric checks from an OpenFAST .out file."""
from __future__ import annotations

import json
import pathlib
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_REFERENCE = "NREL/TP-5000-76773, Section 4 System Performance Assessment"
DEFAULT_LIMITS = {
    "platform_pitch_abs_max_deg": 6.0,
    "horizontal_offset_abs_max_m": 25.0,
    "rna_accel_abs_max_mps2": 1.5,
    "fairlead_tension_abs_max_kN": 22286.0,
}

METRIC_INFO = {
    "platform_pitch_abs_max_deg": {
        "label": "Platform pitch",
        "unit": "deg",
        "limit_label": "report check < 6 deg",
    },
    "horizontal_offset_abs_max_m": {
        "label": "Surge-sway offset",
        "unit": "m",
        "limit_label": "report check < 25 m",
    },
    "rna_accel_abs_max_mps2": {
        "label": "RNA acceleration",
        "unit": "m/s^2",
        "limit_label": "report check < 1.5 m/s^2",
    },
    "fairlead_tension_abs_max_kN": {
        "label": "Fairlead tension",
        "unit": "kN",
        "limit_label": "chain break = 22286 kN",
    },
}

ALIASES = {
    "Time": ["Time"],
    "PtfmPitch": ["PtfmPitch", "Pitch"],
    "PtfmSurge": ["PtfmSurge", "Surge"],
    "PtfmSway": ["PtfmSway", "Sway"],
    "NcIMUTAxs": ["NcIMUTAxs", "NcIMUTAx", "RNAAccelX"],
    "NcIMUTAys": ["NcIMUTAys", "NcIMUTAy", "RNAAccelY"],
    "NcIMUTAzs": ["NcIMUTAzs", "NcIMUTAz", "RNAAccelZ"],
}


def openfast_header(path: pathlib.Path) -> tuple[int, list[str], list[str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        tokens = line.strip().split()
        if tokens and tokens[0] == "Time":
            units = lines[index + 1].strip().split() if index + 1 < len(lines) else []
            return index, tokens, units
    raise ValueError(f"Could not find OpenFAST output header in {path}")


def find_first(header: list[str], names: list[str]) -> int | None:
    lowered = {name.lower(): idx for idx, name in enumerate(header)}
    for name in names:
        idx = lowered.get(name.lower())
        if idx is not None:
            return idx
    return None


def fairlead_indices(header: list[str]) -> list[int]:
    indices = []
    for idx, name in enumerate(header):
        upper = name.upper()
        if upper.startswith("FAIRTEN") or upper.startswith("FAIRHTEN"):
            indices.append(idx)
    return indices


def load_openfast_metrics_channels(path: pathlib.Path) -> tuple[dict[str, np.ndarray], dict[str, str], list[str]]:
    header_line, header, units = openfast_header(path)
    selections: list[tuple[str, int]] = []
    missing: list[str] = []

    for key, names in ALIASES.items():
        idx = find_first(header, names)
        if idx is None:
            missing.append(key)
        else:
            selections.append((key, idx))

    fairlead_cols = fairlead_indices(header)
    if not fairlead_cols:
        missing.append("FAIRTEN*")
    for idx in fairlead_cols:
        selections.append((header[idx], idx))

    if not any(key == "Time" for key, _idx in selections):
        raise ValueError(f"OpenFAST output has no Time channel: {path}")

    usecols = [idx for _key, idx in selections]
    raw = np.genfromtxt(path, skip_header=header_line + 2, usecols=usecols, invalid_raise=False)
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)

    data = {key: raw[:, col] for col, (key, _idx) in enumerate(selections)}
    finite = np.isfinite(data["Time"])
    for key in list(data):
        data[key] = data[key][finite]

    unit_map = {key: units[idx] if idx < len(units) else "" for key, idx in selections}
    return data, unit_map, missing


def slice_data(data: dict[str, np.ndarray], start_time: float | None) -> tuple[dict[str, np.ndarray], bool]:
    if start_time is None or "Time" not in data:
        return data, False
    mask = data["Time"] >= start_time
    if np.count_nonzero(mask) < 2:
        return data, True
    return {key: value[mask] for key, value in data.items()}, False


def abs_max(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")
    return float(np.max(np.abs(finite)))


def unit_scale_to_kn(unit: str) -> float:
    text = unit.strip().lower().replace("(", "").replace(")", "")
    if text == "kn":
        return 1.0
    if text == "n":
        return 0.001
    return 1.0


def compute_values(data: dict[str, np.ndarray], unit_map: dict[str, str]) -> tuple[dict[str, float], list[str]]:
    values: dict[str, float] = {}
    warnings: list[str] = []

    if "PtfmPitch" in data:
        values["platform_pitch_abs_max_deg"] = abs_max(data["PtfmPitch"])
    else:
        warnings.append("Missing PtfmPitch/Pitch for platform pitch metric.")

    if "PtfmSurge" in data and "PtfmSway" in data:
        offset = np.sqrt(data["PtfmSurge"] ** 2 + data["PtfmSway"] ** 2)
        values["horizontal_offset_abs_max_m"] = abs_max(offset)
    else:
        warnings.append("Missing PtfmSurge/PtfmSway for horizontal offset metric.")

    accel_keys = ["NcIMUTAxs", "NcIMUTAys", "NcIMUTAzs"]
    if all(key in data for key in accel_keys):
        accel = np.sqrt(sum(data[key] ** 2 for key in accel_keys))
        values["rna_accel_abs_max_mps2"] = abs_max(accel)
    else:
        warnings.append("Missing one or more NcIMUTA* channels for RNA acceleration metric.")

    fairlead_keys = [key for key in data if key.upper().startswith(("FAIRTEN", "FAIRHTEN"))]
    if fairlead_keys:
        fairlead = []
        for key in fairlead_keys:
            fairlead.append(np.abs(data[key]) * unit_scale_to_kn(unit_map.get(key, "")))
        values["fairlead_tension_abs_max_kN"] = float(np.nanmax(np.vstack(fairlead)))
    else:
        warnings.append("Missing FAIRTEN* channels for fairlead tension metric.")

    return values, warnings


def metric_summary(
    values: dict[str, float],
    all_time_values: dict[str, float],
    limits: dict[str, float],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for key, info in METRIC_INFO.items():
        value = values.get(key)
        limit = limits.get(key)
        ratio = value / limit if value is not None and limit else None
        summary[key] = {
            "label": info["label"],
            "value": value,
            "all_time_value": all_time_values.get(key),
            "limit": limit,
            "unit": info["unit"],
            "ratio": ratio,
            "ok": bool(ratio is not None and ratio <= 1.0),
            "limit_label": info["limit_label"],
        }
    return summary


def plot_metric_summary(
    metrics: dict[str, dict[str, Any]],
    title: str,
    subtitle: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path,
) -> None:
    rows = [metrics[key] for key in METRIC_INFO]
    labels = [row["label"] for row in rows]
    ratios = [float(row["ratio"]) if row.get("ratio") is not None else np.nan for row in rows]
    colors = ["#15803d" if np.isfinite(ratio) and ratio <= 1.0 else "#b42318" for ratio in ratios]
    y = np.arange(len(rows))

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.dpi": 130,
        }
    )
    fig, ax = plt.subplots(figsize=(12.5, 6.2), constrained_layout=True)
    ax.barh(y, ratios, color=colors, alpha=0.9)
    ax.axvline(1.0, color="#111827", lw=1.2, linestyle="--", label="reference limit")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Actual / reference limit")
    ax.set_xlim(0, max(1.15, np.nanmax(ratios) * 1.18 if np.any(np.isfinite(ratios)) else 1.15))
    ax.grid(axis="x", alpha=0.22)
    ax.legend(loc="lower right")
    ax.set_title(f"{title}\n{subtitle}")

    for row_index, row in enumerate(rows):
        value = row.get("value")
        limit = row.get("limit")
        unit = row.get("unit")
        all_time = row.get("all_time_value")
        if value is None or not np.isfinite(value):
            text = "missing"
            xpos = 0.02
        else:
            text = f"{value:.3g} {unit} / {limit:.3g} {unit}"
            if all_time is not None and np.isfinite(all_time) and abs(all_time - value) > max(1e-9, abs(value) * 0.02):
                text += f"   all-time {all_time:.3g}"
            if row.get("case"):
                text += f"   worst: {row['case']}"
            xpos = min(float(row.get("ratio") or 0) + 0.03, ax.get_xlim()[1] * 0.82)
        ax.text(xpos, row_index, text, va="center", ha="left", color="#111827")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def create_paper_metrics_comparison(
    openfast_out: pathlib.Path,
    case: dict[str, Any],
    scenario_name: str,
    case_name: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path | None = None,
) -> dict[str, Any]:
    comparison = case.get("comparison") or {}
    settings = comparison.get("paper_metrics") or comparison
    start_time = float(settings.get("start_time_s", settings.get("start_time", 100.0)))
    limits = {**DEFAULT_LIMITS, **(settings.get("limits") or {})}
    label = settings.get("label") or comparison.get("label") or f"{scenario_name}/{case_name}"
    reference = settings.get("reference") or comparison.get("reference") or DEFAULT_REFERENCE
    out_pdf = out_pdf or out_png.with_suffix(".pdf")

    data, unit_map, missing = load_openfast_metrics_channels(openfast_out)
    eval_data, start_fallback = slice_data(data, start_time)
    values, warnings = compute_values(eval_data, unit_map)
    all_time_values, all_time_warnings = compute_values(data, unit_map)
    summary = metric_summary(values, all_time_values, limits)
    warnings.extend(all_time_warnings)
    warnings.extend(f"Missing OpenFAST channel for {name}" for name in missing)
    if start_fallback:
        warnings.append(f"No usable samples after start_time={start_time:g}s; using all data.")

    plot_metric_summary(
        metrics=summary,
        title="IEA 15MW UMaineSemi paper metric check",
        subtitle=f"{label} | evaluation starts at {start_time:g}s",
        out_png=out_png,
        out_pdf=out_pdf,
    )

    result = {
        "ok": True,
        "comparison_type": "paper_metrics",
        "label": label,
        "reference": reference,
        "openfast_out": str(openfast_out),
        "png": str(out_png),
        "pdf": str(out_pdf),
        "start_time_s": start_time,
        "metrics": summary,
        "warnings": sorted(set(warnings)),
    }
    (out_png.parent / "paper_metrics_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def create_paper_metrics_aggregate(
    case_summaries: list[dict[str, Any]],
    scenario_name: str,
    out_png: pathlib.Path,
    out_pdf: pathlib.Path | None = None,
) -> dict[str, Any]:
    out_pdf = out_pdf or out_png.with_suffix(".pdf")
    by_metric: dict[str, list[dict[str, Any]]] = {key: [] for key in METRIC_INFO}
    warnings: list[str] = []
    case_names: set[str] = set()

    for summary in case_summaries:
        plot = summary.get("comparison_plot") or {}
        if plot.get("comparison_type") != "paper_metrics":
            continue
        case_names.add(str(summary.get("case", "")))
        for key, metric in (plot.get("metrics") or {}).items():
            if key not in by_metric or not isinstance(metric, dict):
                continue
            value = metric.get("value")
            limit = metric.get("limit")
            ratio = metric.get("ratio")
            if value is None or limit is None:
                continue
            if ratio is None and limit:
                ratio = value / limit
            by_metric[key].append(
                {
                    **metric,
                    "case": summary.get("case", ""),
                    "ratio": ratio,
                }
            )
        warnings.extend(plot.get("warnings") or [])

    worst_metrics: dict[str, dict[str, Any]] = {}
    for key, rows in by_metric.items():
        info = METRIC_INFO[key]
        if not rows:
            worst_metrics[key] = {
                "label": info["label"],
                "value": None,
                "all_time_value": None,
                "limit": DEFAULT_LIMITS.get(key),
                "unit": info["unit"],
                "ratio": None,
                "ok": False,
                "limit_label": info["limit_label"],
                "case": "",
            }
            continue
        worst = max(rows, key=lambda row: float(row.get("ratio") or 0.0))
        worst_metrics[key] = {
            "label": info["label"],
            "value": worst.get("value"),
            "all_time_value": worst.get("all_time_value"),
            "limit": worst.get("limit"),
            "unit": info["unit"],
            "ratio": worst.get("ratio"),
            "ok": bool((worst.get("ratio") or 0.0) <= 1.0),
            "limit_label": info["limit_label"],
            "case": worst.get("case", ""),
        }

    plot_metric_summary(
        metrics=worst_metrics,
        title="IEA 15MW UMaineSemi paper metric check - seed envelope",
        subtitle=f"{scenario_name} | worst case across completed seeds",
        out_png=out_png,
        out_pdf=out_pdf,
    )

    result = {
        "ok": True,
        "comparison_type": "paper_metrics_aggregate",
        "label": f"{scenario_name} seed envelope paper metric check",
        "reference": DEFAULT_REFERENCE,
        "png": str(out_png),
        "pdf": str(out_pdf),
        "metrics": worst_metrics,
        "case_count": len(case_names),
        "warnings": sorted(set(warnings)),
    }
    (out_png.parent / "paper_metrics_aggregate_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
