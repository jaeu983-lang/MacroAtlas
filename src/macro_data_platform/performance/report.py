"""Read-only summaries over privacy-safe runtime measurements."""
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import median

from macro_data_platform.performance.metrics import PHASES

MIN_P95_SAMPLES = 20
MAX_REPORT_SAMPLES = 100_000
_COLUMNS = (
    "execution_scope", "engine", "engine_version", "stage", "status", "duration_ns",
    "input_bytes", "input_rows", "input_columns", "output_bytes", "output_rows",
    "output_columns",
    "workload_tier", "sample_class", "cache_status", "phase_timings_json", "code_sha",
    "python_version", "platform", "architecture",
)


def _nearest_rank(values, percentile):
    values = sorted(values)
    if not values:
        return None
    return values[math.ceil(percentile * len(values)) - 1]


def _read_rows(database_path, limit):
    path = Path(database_path)
    if not path.is_file():
        return [], False
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='performance_samples'"
            ).fetchone()
            if table is None:
                return [], False
            columns = ",".join(_COLUMNS)
            rows = connection.execute(
                f"SELECT {columns} FROM performance_samples ORDER BY sample_id DESC LIMIT ?",
                (limit + 1,),
            ).fetchall()
            return rows[:limit], len(rows) > limit
        finally:
            connection.close()
    except sqlite3.Error:
        return [], False


def _valid_phases(value):
    try:
        phases = json.loads(value)
    except (TypeError, ValueError, RecursionError):
        return {}
    if not isinstance(phases, dict):
        return {}
    return {
        name: duration for name, duration in phases.items()
        if name in PHASES and type(duration) is int and duration >= 0
    }


def _summarize(group, rows):
    durations = [row[5] for row in rows if type(row[5]) is int and row[5] >= 0]
    count = len(durations)
    enough = count >= MIN_P95_SAMPLES
    status_counts = defaultdict(int)
    phase_values = defaultdict(list)
    rows_per_second = []
    bytes_per_second = []
    shapes = {
        "input_bytes": [], "input_rows": [], "input_columns": [],
        "output_bytes": [], "output_rows": [], "output_columns": [],
    }
    for row in rows:
        status_counts[row[4]] += 1
        duration = row[5]
        for name, index in zip(shapes, (6, 7, 8, 9, 10, 11), strict=True):
            if type(row[index]) is int and row[index] >= 0:
                shapes[name].append(row[index])
        for name, value in _valid_phases(row[15]).items():
            phase_values[name].append(value)
        if type(duration) is int and duration > 0:
            row_count = row[10] if type(row[10]) is int else row[7]
            byte_count = row[9] if type(row[9]) is int else row[6]
            if type(row_count) is int and row_count >= 0:
                rows_per_second.append(row_count * 1_000_000_000 / duration)
            if type(byte_count) is int and byte_count >= 0:
                bytes_per_second.append(byte_count * 1_000_000_000 / duration)

    phases = {}
    for name, values in sorted(phase_values.items()):
        phase_enough = len(values) >= MIN_P95_SAMPLES
        phases[name] = {
            "sample_count": len(values),
            "p50_ns": median(values),
            "p95_ns": _nearest_rank(values, 0.95) if phase_enough else None,
            "p95_status": "READY" if phase_enough else "INSUFFICIENT_SAMPLE",
        }
    summary = {
        "execution_scope": group[0], "engine": group[1], "engine_version": group[2],
        "stage": group[3], "workload_tier": group[4], "sample_class": group[5],
        "cache_status": group[6], "code_sha": group[7],
        "environment": {"python_version": group[8], "platform": group[9],
                        "architecture": group[10]},
        "sample_count": count,
        "status_counts": dict(sorted(status_counts.items())),
        "p50_ns": median(durations) if durations else None,
        "p95_ns": _nearest_rank(durations, 0.95) if enough else None,
        "p95_status": "READY" if enough else "INSUFFICIENT_SAMPLE",
        "median_input_bytes": median(shapes["input_bytes"])
        if shapes["input_bytes"] else None,
        "median_input_rows": median(shapes["input_rows"])
        if shapes["input_rows"] else None,
        "median_input_columns": median(shapes["input_columns"])
        if shapes["input_columns"] else None,
        "median_output_bytes": median(shapes["output_bytes"])
        if shapes["output_bytes"] else None,
        "median_output_rows": median(shapes["output_rows"])
        if shapes["output_rows"] else None,
        "median_output_columns": median(shapes["output_columns"])
        if shapes["output_columns"] else None,
        "rows_per_second_p50": median(rows_per_second) if rows_per_second else None,
        "rows_per_second_p95": _nearest_rank(rows_per_second, 0.95)
        if len(rows_per_second) >= MIN_P95_SAMPLES else None,
        "rows_per_second_p95_status": "READY"
        if len(rows_per_second) >= MIN_P95_SAMPLES else "INSUFFICIENT_SAMPLE",
        "bytes_per_second_p50": median(bytes_per_second) if bytes_per_second else None,
        "bytes_per_second_p95": _nearest_rank(bytes_per_second, 0.95)
        if len(bytes_per_second) >= MIN_P95_SAMPLES else None,
        "bytes_per_second_p95_status": "READY"
        if len(bytes_per_second) >= MIN_P95_SAMPLES else "INSUFFICIENT_SAMPLE",
        "phases": phases,
    }
    return summary


def build_performance_report(database_path, *, limit=10_000):
    """Aggregate only numeric sizes, fixed labels, environment, and timing fields."""
    if type(limit) is not int or not 1 <= limit <= MAX_REPORT_SAMPLES:
        raise ValueError(f"limit must be between 1 and {MAX_REPORT_SAMPLES}")
    rows, truncated = _read_rows(database_path, limit)
    groups = defaultdict(list)
    for row in rows:
        key = (row[0], row[1], row[2], row[3], row[12], row[13], row[14], row[16],
               row[17], row[18], row[19])
        groups[key].append(row)
    summaries = [_summarize(key, samples) for key, samples in groups.items()]
    summaries.sort(key=lambda item: (
        item["execution_scope"], item["engine"], item["engine_version"], item["stage"],
        item["workload_tier"], item["sample_class"], item["cache_status"],
    ))
    return {
        "schema_version": 1,
        "status": "READY" if summaries else "NO_DATA",
        "read_only": True,
        "sample_count": len(rows),
        "group_count": len(summaries),
        "p95_minimum_samples": MIN_P95_SAMPLES,
        "truncated": truncated,
        "groups": summaries,
    }
