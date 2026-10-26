"""Synthetic, offline benchmark for the bounded iteration 13 analyzer."""
import argparse
import json
import math
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

from macro_data_platform.analysis.patterns import PatternAnalyzer
from macro_data_platform.config import Settings
from macro_data_platform.storage.history import HistoryStore

AT = datetime(2026, 10, 26, tzinfo=UTC).isoformat()
RECORDS_PER_TASK = 10


def _insert_fixture(history, record_count):
    task_count = record_count // RECORDS_PER_TASK
    with history.transaction() as connection:
        for task_index in range(task_count):
            task_id = f"benchmark-task-{task_index:04d}"
            document = history.document("synthetic benchmark task", AT)
            document.update(task_id=task_id, status="FAILED")
            document["plan"] = [{
                "stage_id": "collect", "engine": "benchmark_fixture", "engine_version": "1",
                "input_data": {"institution_id": "benchmark_agency",
                               "dataset_id": "benchmark_dataset", "concept": "benchmark_series"},
            }]
            document["stages"] = [{
                "stage_run_id": f"benchmark-stage-{task_index:04d}-{attempt:02d}",
                "stage_id": "collect", "engine": "benchmark_fixture", "engine_version": "1",
                "task_attempt_no": attempt + 1, "attempt_no": attempt + 1,
                "status": "FAILED_RETRYABLE", "started_at": AT, "finished_at": AT,
                "result": {"status": "FAILED_RETRYABLE", "error_code": "TRANSIENT",
                           "payload": {"opaque_fixture": "x" * 256}},
            } for attempt in range(RECORDS_PER_TASK)]
            history.insert(connection, document)


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _measure(root: Path, record_count: int, repeats: int):
    history = HistoryStore(Settings(root))
    _insert_fixture(history, record_count)
    analyzer = PatternAnalyzer(history)

    latencies_ms = []
    last_report = None
    for _ in range(repeats):
        started = time.perf_counter_ns()
        last_report = analyzer.analyze()
        latencies_ms.append((time.perf_counter_ns() - started) / 1_000_000)

    allocations = []
    for _ in range(max(3, repeats // 6)):
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        analyzer.analyze()
        _current, peak = tracemalloc.get_traced_memory()
        allocations.append(max(0, peak - baseline))
        tracemalloc.stop()

    metrics = last_report["metrics"]
    candidates = last_report["proposals"]
    relevant = sum(
        bool(item["scope"].get("institution_id")
             and (item["scope"].get("dataset_id") or item["scope"].get("concept")))
        for item in candidates
    )
    return {
        "input_stage_records": record_count,
        "status": last_report["status"],
        "tasks_scanned": metrics["tasks_scanned"],
        "records_scanned": metrics["records_scanned"],
        "logical_bytes_read": metrics["logical_bytes_read"],
        "candidate_count": metrics["candidate_count"],
        "scope_relevant_candidate_count": relevant,
        "scope_relevance_ratio": (relevant / len(candidates)) if candidates else None,
        "latency_p50_ms": round(statistics.median(latencies_ms), 3),
        "latency_p95_ms": round(_percentile(latencies_ms, 0.95), 3),
        "max_python_allocation_bytes": max(allocations, default=0),
        "truncation": last_report["truncation"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args(argv)
    if type(args.repeats) is not int or not 5 <= args.repeats <= 100:
        parser.error("--repeats must be between 5 and 100")

    results = []
    with tempfile.TemporaryDirectory(prefix="macro-patterns-bench-") as temp:
        root = Path(temp)
        for record_count in (100, 1_000, 5_000):
            size_root = root / str(record_count)
            size_root.mkdir()
            results.append(_measure(size_root, record_count, args.repeats))
    print(json.dumps({
        "benchmark": "iteration_13_synthetic_offline",
        "environment": {"platform": platform.platform(), "python": sys.version.split()[0],
                        "sqlite": sqlite3.sqlite_version},
        "repeats": args.repeats,
        "method": "warm local SQLite reads; latency and tracemalloc runs measured separately; "
                  "logical bytes count selected metadata fields, not physical disk I/O",
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
