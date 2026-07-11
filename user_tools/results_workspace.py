# -*- coding: utf-8 -*-
"""Read and analyze OpenFAST result files for the local GUI."""
from __future__ import annotations

from array import array
import json
import math
import pathlib
import struct
from typing import Any, Iterable

import numpy as np
from scipy import signal


MAX_FILES = 6
MAX_CHANNELS = 8
MAX_RAW_VALUES = 20_000_000
MAX_CATALOG_FILES = 400
DEFAULT_MAX_POINTS = 5000
FILE_IDS = {1, 2, 3, 4}
_META_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}


def _clean_unit(value: str) -> str:
    return value.strip().strip("()[]").replace("sec", "s")


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_float_list(values: np.ndarray) -> list[float | None]:
    return [float(value) if np.isfinite(value) else None for value in values]


def _ascii_header(path: pathlib.Path) -> dict[str, Any]:
    description: list[str] = []
    names: list[str] = []
    units: list[str] = []
    header_line = -1
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index in range(160):
            line = handle.readline()
            if not line:
                break
            tokens = line.strip().split()
            if tokens and tokens[0].lower() in {"time", "alpha"}:
                names = tokens
                units = [_clean_unit(value) for value in handle.readline().strip().split()]
                header_line = index
                break
            description.append(line.rstrip())
    if header_line < 0 or not names:
        raise ValueError(f"Could not find Time/Alpha header in {path}")
    if len(units) < len(names):
        units.extend([""] * (len(names) - len(units)))
    return {
        "format": "ascii",
        "description": "\n".join(description).strip(),
        "names": names,
        "units": units[: len(names)],
        "headerLine": header_line + 1,
        "dataLine": header_line + 3,
    }


def _first_ascii_rows(path: pathlib.Path, data_line: int, count: int = 2) -> list[list[float]]:
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for _ in range(data_line - 1):
            handle.readline()
        for line in handle:
            tokens = line.strip().split()
            if not tokens:
                continue
            try:
                rows.append([float(token) for token in tokens])
            except ValueError:
                continue
            if len(rows) >= count:
                break
    return rows


def _last_ascii_row(path: pathlib.Path, minimum_columns: int) -> list[float] | None:
    size = path.stat().st_size
    read_size = min(size, 512 * 1024)
    with path.open("rb") as handle:
        handle.seek(max(0, size - read_size))
        tail = handle.read().decode("utf-8", errors="replace")
    for line in reversed(tail.splitlines()):
        tokens = line.strip().split()
        if len(tokens) < minimum_columns:
            continue
        try:
            return [float(token) for token in tokens]
        except ValueError:
            continue
    return None


def _read_binary_header(path: pathlib.Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        raw_id = handle.read(2)
        if len(raw_id) != 2:
            raise ValueError(f"Incomplete OpenFAST binary header: {path}")
        little_id = struct.unpack("<h", raw_id)[0]
        big_id = struct.unpack(">h", raw_id)[0]
        if little_id in FILE_IDS:
            endian = "<"
            file_id = little_id
        elif big_id in FILE_IDS:
            endian = ">"
            file_id = big_id
        else:
            raise ValueError(f"Unsupported OpenFAST binary FileID {little_id}: {path}")

        def read_one(code: str) -> int | float:
            size = struct.calcsize(code)
            raw = handle.read(size)
            if len(raw) != size:
                raise ValueError(f"Incomplete OpenFAST binary header: {path}")
            return struct.unpack(endian + code, raw)[0]

        name_length = int(read_one("h")) if file_id == 4 else 10
        channel_count = int(read_one("i"))
        sample_count = int(read_one("i"))
        if channel_count < 1 or sample_count < 1 or name_length < 1 or name_length > 4096:
            raise ValueError(f"Invalid OpenFAST binary dimensions in {path}")
        if file_id == 1:
            time_scale = float(read_one("d"))
            time_offset = float(read_one("d"))
            time_start = None
            time_step = None
        else:
            time_start = float(read_one("d"))
            time_step = float(read_one("d"))
            time_scale = None
            time_offset = None

        if file_id == 3:
            column_scale = np.ones(channel_count, dtype=np.float64)
            column_offset = np.zeros(channel_count, dtype=np.float64)
        else:
            dtype = np.dtype(endian + "f4")
            column_scale = np.frombuffer(handle.read(channel_count * 4), dtype=dtype).astype(np.float64)
            column_offset = np.frombuffer(handle.read(channel_count * 4), dtype=dtype).astype(np.float64)
            if len(column_scale) != channel_count or len(column_offset) != channel_count:
                raise ValueError(f"Incomplete OpenFAST binary scaling arrays: {path}")

        description_length = int(read_one("i"))
        if description_length < 0 or description_length > 10_000_000:
            raise ValueError(f"Invalid OpenFAST binary description length: {path}")
        description = handle.read(description_length).decode("utf-8", errors="replace").strip()

        def read_labels() -> list[str]:
            labels = []
            for _ in range(channel_count + 1):
                raw = handle.read(name_length)
                if len(raw) != name_length:
                    raise ValueError(f"Incomplete OpenFAST binary labels: {path}")
                labels.append(raw.decode("utf-8", errors="replace").replace("\x00", "").strip())
            return labels

        names = read_labels()
        units = [_clean_unit(value) for value in read_labels()]
        time_data_offset = handle.tell()
        if file_id == 1:
            data_offset = time_data_offset + sample_count * 4
            packed_time = np.memmap(
                path,
                mode="r",
                dtype=np.dtype(endian + "i4"),
                offset=time_data_offset,
                shape=(sample_count,),
            )
            if not time_scale:
                raise ValueError(f"OpenFAST binary time scale is zero: {path}")
            first_time = (float(packed_time[0]) - float(time_offset)) / float(time_scale)
            last_time = (float(packed_time[-1]) - float(time_offset)) / float(time_scale)
            inferred_step = (last_time - first_time) / max(1, sample_count - 1)
        else:
            data_offset = time_data_offset
            first_time = float(time_start)
            last_time = float(time_start) + float(time_step) * (sample_count - 1)
            inferred_step = float(time_step)

    expected_bytes = sample_count * channel_count * (8 if file_id == 3 else 2)
    if path.stat().st_size < data_offset + expected_bytes:
        raise ValueError(f"OpenFAST binary data is truncated: {path}")
    return {
        "format": "binary",
        "fileId": file_id,
        "endian": endian,
        "nameLength": name_length,
        "channelCount": channel_count + 1,
        "sampleCount": sample_count,
        "description": description,
        "names": names,
        "units": units,
        "timeStart": first_time,
        "timeEnd": last_time,
        "timeStep": inferred_step,
        "timeScale": time_scale,
        "timeOffset": time_offset,
        "timeDataOffset": time_data_offset,
        "dataOffset": data_offset,
        "columnScale": column_scale,
        "columnOffset": column_offset,
    }


def read_output_metadata(path: pathlib.Path, use_cache: bool = True) -> dict[str, Any]:
    path = path.resolve()
    stat = path.stat()
    cache_key = str(path).lower()
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _META_CACHE.get(cache_key)
    if use_cache and cached and cached[:2] == stamp:
        return dict(cached[2])

    if path.suffix.lower() == ".outb":
        internal = _read_binary_header(path)
    else:
        internal = _ascii_header(path)
        first_rows = _first_ascii_rows(path, int(internal["dataLine"]))
        last_row = _last_ascii_row(path, len(internal["names"]))
        first_time = first_rows[0][0] if first_rows else None
        time_step = first_rows[1][0] - first_rows[0][0] if len(first_rows) > 1 else None
        last_time = last_row[0] if last_row else first_time
        sample_count = None
        if first_time is not None and last_time is not None and time_step and time_step > 0:
            sample_count = max(1, int(round((last_time - first_time) / time_step)) + 1)
        internal.update(
            {
                "channelCount": len(internal["names"]),
                "sampleCount": sample_count,
                "timeStart": first_time,
                "timeEnd": last_time,
                "timeStep": time_step,
            }
        )

    public = {
        "format": internal["format"],
        "description": internal.get("description", ""),
        "channelCount": int(internal["channelCount"]),
        "sampleCount": internal.get("sampleCount"),
        "timeStart": _finite_number(internal.get("timeStart")),
        "timeEnd": _finite_number(internal.get("timeEnd")),
        "timeStep": _finite_number(internal.get("timeStep")),
        "independent": {
            "name": internal["names"][0],
            "unit": internal["units"][0] if internal["units"] else "",
        },
        "channels": [
            {"name": name, "unit": internal["units"][index] if index < len(internal["units"]) else "", "index": index}
            for index, name in enumerate(internal["names"])
        ],
    }
    _META_CACHE[cache_key] = (stamp[0], stamp[1], public)
    return dict(public)


def _time_slice_indices(times: np.ndarray, start: float | None, end: float | None) -> tuple[int, int]:
    low = 0 if start is None else int(np.searchsorted(times, start, side="left"))
    high = len(times) if end is None else int(np.searchsorted(times, end, side="right"))
    low = max(0, min(low, len(times)))
    high = max(low, min(high, len(times)))
    return low, high


def _read_binary_selected(
    path: pathlib.Path,
    selected: list[str],
    start: float | None,
    end: float | None,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, str], dict[str, Any]]:
    header = _read_binary_header(path)
    names = header["names"]
    units = header["units"]
    name_lookup = {name.lower(): index for index, name in enumerate(names)}
    selected_indices = [(name, name_lookup[name.lower()]) for name in selected if name.lower() in name_lookup and name_lookup[name.lower()] > 0]
    sample_count = int(header["sampleCount"])
    if header["fileId"] == 1:
        packed_time = np.memmap(
            path,
            mode="r",
            dtype=np.dtype(header["endian"] + "i4"),
            offset=int(header["timeDataOffset"]),
            shape=(sample_count,),
        )
        times_all = (packed_time.astype(np.float64) - float(header["timeOffset"])) / float(header["timeScale"])
    else:
        times_all = float(header["timeStart"]) + float(header["timeStep"]) * np.arange(sample_count, dtype=np.float64)
    low, high = _time_slice_indices(times_all, start, end)
    times = np.asarray(times_all[low:high], dtype=np.float64)
    if len(times) * max(1, len(selected_indices)) > MAX_RAW_VALUES:
        raise ValueError("Selected binary window is too large; narrow the time range or select fewer channels.")

    packed_dtype = np.dtype(header["endian"] + ("f8" if header["fileId"] == 3 else "i2"))
    packed = np.memmap(
        path,
        mode="r",
        dtype=packed_dtype,
        offset=int(header["dataOffset"]),
        shape=(sample_count, int(header["channelCount"]) - 1),
    )
    values: dict[str, np.ndarray] = {}
    unit_map: dict[str, str] = {}
    for requested_name, file_index in selected_indices:
        column_index = file_index - 1
        raw = np.asarray(packed[low:high, column_index], dtype=np.float64)
        if header["fileId"] == 3:
            values[requested_name] = raw
        else:
            scale = float(header["columnScale"][column_index])
            offset = float(header["columnOffset"][column_index])
            if scale == 0:
                values[requested_name] = np.full_like(raw, np.nan)
            else:
                values[requested_name] = (raw - offset) / scale
        unit_map[requested_name] = units[file_index] if file_index < len(units) else ""
    return times, values, unit_map, header


def _read_ascii_selected(
    path: pathlib.Path,
    selected: list[str],
    start: float | None,
    end: float | None,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, str], dict[str, Any]]:
    header = _ascii_header(path)
    names = header["names"]
    units = header["units"]
    name_lookup = {name.lower(): index for index, name in enumerate(names)}
    selected_indices = [(name, name_lookup[name.lower()]) for name in selected if name.lower() in name_lookup and name_lookup[name.lower()] > 0]

    meta = read_output_metadata(path)
    estimated = meta.get("sampleCount")
    time_step = meta.get("timeStep")
    if start is not None and end is not None and time_step and end >= start:
        estimated = int((end - start) / time_step) + 2
    if estimated and estimated * max(1, len(selected_indices)) > MAX_RAW_VALUES:
        raise ValueError("Selected ASCII window is too large; narrow the time range or select fewer channels.")

    buffers = [array("d") for _ in range(len(selected_indices) + 1)]
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for _ in range(int(header["dataLine"]) - 1):
            handle.readline()
        for line in handle:
            tokens = line.strip().split()
            if not tokens:
                continue
            try:
                independent = float(tokens[0])
            except ValueError:
                continue
            if start is not None and independent < start:
                continue
            if end is not None and independent > end:
                break
            try:
                row = [independent, *[float(tokens[index]) for _name, index in selected_indices]]
            except (ValueError, IndexError):
                continue
            for target, value in zip(buffers, row):
                target.append(value)
            if len(buffers[0]) * max(1, len(selected_indices)) > MAX_RAW_VALUES:
                raise ValueError("Selected ASCII data exceeded the analysis safety limit; narrow the time range.")

    times = np.asarray(buffers[0], dtype=np.float64)
    values = {name: np.asarray(buffers[index + 1], dtype=np.float64) for index, (name, _column) in enumerate(selected_indices)}
    unit_map = {name: units[column] if column < len(units) else "" for name, column in selected_indices}
    return times, values, unit_map, header


def _channel_statistics(values: np.ndarray) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": 0, "min": None, "max": None, "mean": None, "std": None, "rms": None, "absMax": None, "range": None}
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    return {
        "count": int(finite.size),
        "min": minimum,
        "max": maximum,
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "rms": float(np.sqrt(np.mean(np.square(finite)))),
        "absMax": float(np.max(np.abs(finite))),
        "range": maximum - minimum,
    }


def _sample_indices(length: int, max_points: int) -> np.ndarray:
    if length <= max_points:
        return np.arange(length, dtype=np.int64)
    return np.unique(np.linspace(0, length - 1, max_points, dtype=np.int64))


def _psd_series(times: np.ndarray, values: np.ndarray, max_points: int = 2000) -> tuple[np.ndarray, np.ndarray] | None:
    finite = np.isfinite(times) & np.isfinite(values)
    if np.count_nonzero(finite) < 32:
        return None
    time_values = times[finite]
    signal_values = values[finite]
    deltas = np.diff(time_values)
    positive = deltas[deltas > 0]
    if not positive.size:
        return None
    dt = float(np.median(positive))
    if dt <= 0:
        return None
    nperseg = min(4096, 2 ** int(math.floor(math.log2(len(signal_values)))))
    if nperseg < 32:
        return None
    frequency, density = signal.welch(
        signal_values,
        fs=1.0 / dt,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend="constant",
        scaling="density",
    )
    indices = _sample_indices(len(frequency), max_points)
    return frequency[indices], density[indices]


def analyze_output_file(
    path: pathlib.Path,
    channels: Iterable[str],
    start: float | None = None,
    end: float | None = None,
    max_points: int = DEFAULT_MAX_POINTS,
    include_psd: bool = True,
) -> dict[str, Any]:
    metadata = read_output_metadata(path)
    independent_name = metadata["independent"]["name"]
    selected = []
    for channel in channels:
        name = str(channel).strip()
        if name and name.lower() != independent_name.lower() and name not in selected:
            selected.append(name)
    if not selected:
        raise ValueError("Select at least one result channel.")
    if len(selected) > MAX_CHANNELS:
        raise ValueError(f"Select no more than {MAX_CHANNELS} channels at once.")
    if start is not None and end is not None and end < start:
        raise ValueError("End time must be greater than or equal to start time.")
    max_points = max(200, min(int(max_points), 8000))

    if metadata["format"] == "binary":
        times, values, unit_map, _internal = _read_binary_selected(path, selected, start, end)
    else:
        times, values, unit_map, _internal = _read_ascii_selected(path, selected, start, end)
    if times.size < 2:
        raise ValueError(f"No result samples in the selected time range: {path.name}")

    indices = _sample_indices(len(times), max_points)
    series = []
    statistics = []
    psd_rows = []
    for name in selected:
        if name not in values:
            continue
        unit = unit_map.get(name, "")
        series.append({"name": name, "unit": unit, "values": _safe_float_list(values[name][indices])})
        statistics.append({"name": name, "unit": unit, **_channel_statistics(values[name])})
        if include_psd:
            psd = _psd_series(times, values[name])
            if psd is not None:
                frequency, density = psd
                psd_rows.append(
                    {
                        "name": name,
                        "unit": f"{unit}^2/Hz" if unit else "1/Hz",
                        "frequency": _safe_float_list(frequency),
                        "values": _safe_float_list(density),
                    }
                )

    if not series:
        available = ", ".join(row["name"] for row in metadata["channels"][:20])
        raise ValueError(f"Selected channels are not present in {path.name}. Available: {available}")
    return {
        "metadata": metadata,
        "window": {"start": float(times[0]), "end": float(times[-1]), "samples": int(len(times)), "displayPoints": int(len(indices))},
        "independent": {**metadata["independent"], "values": _safe_float_list(times[indices])},
        "series": series,
        "statistics": statistics,
        "psd": psd_rows,
    }


def _read_summary(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_result_path(runs_root: pathlib.Path, file_id: str) -> pathlib.Path:
    root = runs_root.resolve()
    relative = pathlib.PurePosixPath(str(file_id).replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Invalid result file identifier.")
    path = root.joinpath(*relative.parts).resolve()
    if not _within(path, root):
        raise ValueError("Result file escapes the runs directory.")
    if not path.is_file() or path.suffix.lower() not in {".out", ".outb"}:
        raise FileNotFoundError(f"OpenFAST result file not found: {file_id}")
    return path


def discover_results(runs_root: pathlib.Path) -> dict[str, Any]:
    root = runs_root.resolve()
    rows: list[dict[str, Any]] = []
    scenario_names: set[str] = set()
    case_names: set[str] = set()
    if not root.is_dir():
        return {"summary": {"scenarios": 0, "cases": 0, "files": 0}, "files": []}

    scenario_dirs = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for scenario_dir in scenario_dirs:
        case_dirs = sorted((path for path in scenario_dir.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for case_dir in case_dirs:
            summary = _read_summary(case_dir / "scenario_summary.json")
            execution = summary.get("execution") if isinstance(summary.get("execution"), dict) else {}
            primary_raw = execution.get("out") or ""
            primary_path = pathlib.Path(primary_raw).resolve() if primary_raw else None
            output_files = sorted(
                {path.resolve() for pattern in ("*.out", "*.outb") for path in case_dir.glob(pattern) if path.is_file() and path.stat().st_size > 0},
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
            for output_path in output_files:
                try:
                    metadata = read_output_metadata(output_path)
                    parse_error = ""
                except Exception as exc:
                    metadata = {"format": "binary" if output_path.suffix.lower() == ".outb" else "ascii", "channels": [], "channelCount": 0}
                    parse_error = str(exc)
                file_id = output_path.relative_to(root).as_posix()
                primary = bool(primary_path and output_path == primary_path)
                if not primary and summary.get("fst"):
                    primary = output_path.stem == pathlib.Path(str(summary["fst"])).stem
                stat = output_path.stat()
                rows.append(
                    {
                        "id": file_id,
                        "scenario": scenario_dir.name,
                        "case": case_dir.name,
                        "file": output_path.name,
                        "label": f"{scenario_dir.name} / {case_dir.name} / {output_path.name}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "primary": primary,
                        "ok": bool(summary.get("ok", True)),
                        "format": metadata.get("format"),
                        "channelCount": metadata.get("channelCount", 0),
                        "sampleCount": metadata.get("sampleCount"),
                        "timeStart": metadata.get("timeStart"),
                        "timeEnd": metadata.get("timeEnd"),
                        "timeStep": metadata.get("timeStep"),
                        "independent": metadata.get("independent"),
                        "channels": metadata.get("channels", []),
                        "error": parse_error,
                    }
                )
                scenario_names.add(scenario_dir.name)
                case_names.add(f"{scenario_dir.name}/{case_dir.name}")
                if len(rows) >= MAX_CATALOG_FILES:
                    break
            if len(rows) >= MAX_CATALOG_FILES:
                break
        if len(rows) >= MAX_CATALOG_FILES:
            break

    rows.sort(key=lambda row: (row["modified"], row["primary"]), reverse=True)
    return {
        "summary": {"scenarios": len(scenario_names), "cases": len(case_names), "files": len(rows)},
        "files": rows,
    }


def analyze_results(
    runs_root: pathlib.Path,
    file_ids: Iterable[str],
    channels: Iterable[str],
    start: float | None = None,
    end: float | None = None,
    max_points: int = DEFAULT_MAX_POINTS,
    include_psd: bool = True,
) -> dict[str, Any]:
    selected_files = list(dict.fromkeys(str(value) for value in file_ids if str(value).strip()))
    selected_channels = list(dict.fromkeys(str(value) for value in channels if str(value).strip()))
    if not selected_files:
        raise ValueError("Select at least one result file.")
    if len(selected_files) > MAX_FILES:
        raise ValueError(f"Select no more than {MAX_FILES} result files at once.")
    if not selected_channels:
        raise ValueError("Select at least one result channel.")
    if len(selected_channels) > MAX_CHANNELS:
        raise ValueError(f"Select no more than {MAX_CHANNELS} channels at once.")

    cases = []
    warnings = []
    for file_id in selected_files:
        path = resolve_result_path(runs_root, file_id)
        metadata = read_output_metadata(path)
        available = {row["name"].lower() for row in metadata["channels"]}
        present = [name for name in selected_channels if name.lower() in available]
        missing = [name for name in selected_channels if name.lower() not in available]
        if missing:
            warnings.append(f"{file_id}: missing {', '.join(missing)}")
        if not present:
            continue
        result = analyze_output_file(path, present, start=start, end=end, max_points=max_points, include_psd=include_psd)
        result.update({"id": file_id, "label": file_id, "file": path.name})
        cases.append(result)
    if not cases:
        raise ValueError("None of the selected result files contain the requested channels.")
    return {
        "files": selected_files,
        "channels": selected_channels,
        "cases": cases,
        "warnings": warnings,
    }
