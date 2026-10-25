"""Offline end-to-end benchmark for the supported World Bank fixture workflow."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from test_worldbank import FixtureTransport, fixture_download
from test_worldbank_request import child, supplied

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import GDPQuery
from macro_data_platform.ingestion.worldbank_request import (
    WorldBankRequestDispatcher,
)
from macro_data_platform.orchestration.workflow import WorkflowService
from macro_data_platform.storage.history import HistoryStore

REPETITIONS = 30


def code_fingerprint() -> str:
    """Fingerprint the exact local source/test/fixture input for this measurement."""
    paths = [*ROOT.joinpath("src").rglob("*.py"),
             *ROOT.joinpath("tests").rglob("*.py"),
             *ROOT.joinpath("tests", "fixtures").rglob("*"),
             ROOT / "pyproject.toml", Path(__file__).resolve()]
    digest = hashlib.sha256()
    for path in sorted((item for item in paths if item.is_file()),
                       key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_head() -> str | None:
    """Return the checkout base commit when Git is available, without failing the run."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True,
            text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(percentile(values, 0.50), 4),
        "p95": round(percentile(values, 0.95), 4),
        "max": round(max(values), 4),
    }


def one_run() -> dict:
    with TemporaryDirectory(prefix="macroatlas-e2e-", dir=ROOT) as temporary:
        root = Path(temporary)
        settings = Settings(root, network_enabled=False)
        store = HistoryStore(settings)
        service = WorkflowService(store, clock=lambda: datetime.now(UTC))
        started = time.perf_counter_ns()
        workflow = supplied(service, "file")
        task = child(service, workflow)
        prepared_ms = (time.perf_counter_ns() - started) / 1_000_000

        download = fixture_download()
        transport = FixtureTransport(download)
        dispatcher = WorldBankRequestDispatcher(
            settings, store, clock=lambda: datetime.now(UTC), transport=transport, gate_a=True,
        )
        before_cpu = time.process_time_ns()
        run_started = time.perf_counter_ns()
        result = dispatcher.run(task["task_id"])
        dispatch_ms = (time.perf_counter_ns() - run_started) / 1_000_000
        cpu_ms = (time.process_time_ns() - before_cpu) / 1_000_000

        read_started = time.perf_counter_ns()
        assert result["status"] == "COMPLETED"
        assert len(transport.calls) == 1
        validation = next(
            stage["result"]["payload"] for stage in reversed(result["stages"])
            if stage["stage_id"] == "validate"
        )
        observations = dispatcher.audit.observations(validation["validation_id"])
        artifact = dispatcher.audit.get(validation["artifact_id"], kind="artifact")
        raw = (settings.project_root / artifact["raw_path"]).read_bytes()
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        assert raw_sha256 == artifact["raw_sha256"]
        assert [row["value"] for row in observations] == [123.5, None, 0]
        assert [row["value_status"] for row in observations] == [
            "reported", "missing", "reported",
        ]
        readback_ms = (time.perf_counter_ns() - read_started) / 1_000_000

        stage_ms = {}
        for stage in result["stages"]:
            begin = datetime.fromisoformat(stage["started_at"])
            finish = datetime.fromisoformat(stage["finished_at"])
            stage_ms[stage["stage_id"]] = max(0.0, (finish - begin).total_seconds() * 1000)

        query_bytes = len(urlsplit(GDPQuery().url).query.encode("ascii"))
        return {
            "preparation_ms": round(prepared_ms, 4),
            "dispatch_ms": round(dispatch_ms, 4),
            "readback_ms": round(readback_ms, 4),
            "dispatch_cpu_ms": round(cpu_ms, 4),
            "stage_duration_ms": {key: round(value, 4) for key, value in stage_ms.items()},
            "api_calls": len(transport.calls),
            "mock_query_bytes": query_bytes,
            "mock_response_body_bytes": len(download.body),
            "raw_response_bytes": len(raw),
            "raw_sha256": raw_sha256,
            "observation_count": len(observations),
            "observation_value_status": [
                {"value": row["value"], "status": row["value_status"]}
                for row in observations
            ],
            "raw_sha256_verified": True,
            "status": result["status"],
            "evidence_mode": artifact["mode"],
        }


def main() -> int:
    samples = [{"sample_no": index, **one_run()}
               for index in range(1, REPETITIONS + 1)]
    expected_values = [
        {"value": 123.5, "status": "reported"},
        {"value": None, "status": "missing"},
        {"value": 0, "status": "reported"},
    ]
    fingerprint = code_fingerprint()
    result = {
        "schema_version": 2,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "mode": "offline_e2e_fixture_workflow",
        "network_used": False,
        "git_head": git_head(),
        "code_fingerprint_sha256": fingerprint,
        "repetitions": REPETITIONS,
        "scenario": "structured request -> confirmation -> mock World Bank collect -> validate -> SQLite read-back",
        "environment": {
            "python": sys.version,
            "platform": sys.platform,
            "platform_release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "logical_cpu_count": os.cpu_count(),
        },
        "summary": {
            "preparation_ms": summarize([row["preparation_ms"] for row in samples]),
            "dispatch_ms": summarize([row["dispatch_ms"] for row in samples]),
            "readback_ms": summarize([row["readback_ms"] for row in samples]),
            "dispatch_cpu_ms": summarize([row["dispatch_cpu_ms"] for row in samples]),
            "stage_duration_ms": {
                stage_id: summarize([row["stage_duration_ms"][stage_id] for row in samples])
                for stage_id in samples[0]["stage_duration_ms"]
            },
        },
        "invariants": {
            "all_completed": all(row["status"] == "COMPLETED" for row in samples),
            "all_fixture_mode": all(row["evidence_mode"] == "fixture" for row in samples),
            "all_raw_hashes_verified": all(row["raw_sha256_verified"] for row in samples),
            "all_raw_hashes_match": len({row["raw_sha256"] for row in samples}) == 1,
            "all_observation_values_preserve_missing_and_zero": all(
                row["observation_count"] == 3
                and row["observation_value_status"] == expected_values
                for row in samples
            ),
            "all_samples_used_one_mock_api_call": all(row["api_calls"] == 1 for row in samples),
            "fingerprint_recorded": len(fingerprint) == 64,
            "live_http_requests": 0,
        },
        "samples": samples,
        "limits": [
            "The request enters as a structured DataRequest; no natural-language agent is measured.",
            "Only the fixed World Bank fixture route is exercised; other institutions are not covered.",
            "Mock query/body bytes are not live wire bytes; native SQLite memory is not measured.",
            "tracemalloc is intentionally off in this timing run to avoid measurement overhead.",
            "Stage durations use persisted UTC timestamps; dispatch_ms uses a monotonic timer.",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    checks = [value for key, value in result["invariants"].items()
              if key != "live_http_requests"]
    return 0 if all(value is True for value in checks) and result["invariants"][
        "live_http_requests"
    ] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
