"""Measure the local pytest suite without subprocess RSS estimates or tracemalloc overhead."""
from __future__ import annotations

import json
import math
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Some desktop Python installations add a different MacroAtlas checkout via .pth.
# Put this script's checkout first so tests cannot silently import another worktree.
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


class TestDurationPlugin:
    def __init__(self):
        self.collected = 0
        self.durations: dict[str, list[float]] = defaultdict(list)
        self.outcomes: dict[str, str] = {}

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)

    def pytest_runtest_logreport(self, report):
        module = report.nodeid.split("::", 1)[0]
        if report.when == "call":
            self.durations[module].append(float(report.duration))
            self.outcomes[report.nodeid] = report.outcome
        elif report.failed:
            self.outcomes[report.nodeid] = "failed"
        elif report.skipped and report.nodeid not in self.outcomes:
            self.outcomes[report.nodeid] = "skipped"


def main() -> int:
    import pytest

    plugin = TestDurationPlugin()
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    result = pytest.main(["-p", "no:cacheprovider", "-q"], plugins=[plugin])
    wall_seconds = time.perf_counter() - started_wall
    cpu_seconds = time.process_time() - started_cpu
    outcomes = {status: sum(value == status for value in plugin.outcomes.values())
                for status in ("passed", "failed", "skipped")}
    modules = []
    all_calls = []
    for module, durations in plugin.durations.items():
        all_calls.extend(durations)
        modules.append({
            "module": module,
            "calls": len(durations),
            "call_seconds_total": round(sum(durations), 6),
            "call_seconds_p50": round(percentile(durations, 0.50), 6),
            "call_seconds_p95": round(percentile(durations, 0.95), 6),
            "call_seconds_max": round(max(durations), 6),
        })
    modules.sort(key=lambda row: row["call_seconds_total"], reverse=True)
    result_data = {
        "schema_version": 1,
        "mode": "local_fixture_mock_test_suite",
        "network_used": False,
        "python": sys.version,
        "platform": platform.platform(),
        "exit_code": int(result),
        "collected_cases": plugin.collected,
        "outcomes": outcomes,
        "wall_seconds": round(wall_seconds, 4),
        "process_cpu_seconds": round(cpu_seconds, 4),
        "test_call_seconds_p50": round(percentile(all_calls, 0.50), 6),
        "test_call_seconds_p95": round(percentile(all_calls, 0.95), 6),
        "memory_measurement": None,
        "memory_note": "Full-suite RSS could not be measured reliably by the sandbox process API; Python tracemalloc is reserved for smaller microbenchmarks.",
        "durations_by_module": modules,
    }
    print("MACROATLAS_PERFORMANCE_TEST_RESULT_BEGIN")
    print(json.dumps(result_data, indent=2))
    print("MACROATLAS_PERFORMANCE_TEST_RESULT_END")
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
