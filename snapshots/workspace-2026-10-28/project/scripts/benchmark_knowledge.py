"""Offline, reproducible benchmark for the bounded SQLite knowledge query."""
from __future__ import annotations

import argparse
import json
import math
import platform
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.mapping.concepts import ConceptLink, ConceptSearchPolicy
from macro_data_platform.storage.knowledge import KnowledgeStore, _digest

SIZES = (100, 1_000, 10_000)
REPETITIONS = 30
AS_OF = "2026-10-25T12:00:00+00:00"
MAX_COLD_P95_MS = 250.0
MAX_QUERY_PEAK_BYTES = 1_048_576


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def seed_records(store: KnowledgeStore, count: int) -> None:
    with store.history.transaction() as connection:
        for index in range(count):
            record_id = str(uuid4())
            institution = "worldbank" if index % 2 == 0 else "imf"
            document = {
                "record_id": record_id, "task_id": None, "feedback_id": None,
                "institution_id": institution, "dataset_id": "fixture-catalogue",
                "concept_id": f"BENCH_{index:05d}", "classification_axis": "benchmark_axis",
                "correction_type": "source_fact",
                "statement": f"Synthetic accepted evidence row {index} for local benchmark.",
                "provenance": "official_evidence", "validation_status": "verified",
                "source_version": "synthetic-v1", "effective_from": None,
                "effective_to": None, "evidence_refs": [f"fixture:benchmark:{index}"],
                "record_version": 1, "supersedes_id": None,
                "created_at": AS_OF, "schema_version": 1,
            }
            encoded = json.dumps(document, ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(",", ":"))
            connection.execute(
                "INSERT INTO knowledge_records(record_id, task_id, feedback_id, institution_id, "
                "dataset_id, concept_id, classification_axis, record_version, created_at, "
                "document, digest, idempotency_key) VALUES (?, NULL, NULL, ?, ?, ?, ?, 1, ?, ?, ?, NULL)",
                (record_id, institution, document["dataset_id"], document["concept_id"],
                 document["classification_axis"], AS_OF, encoded, _digest(document)),
            )
            review = {"event_id": str(uuid4()), "record_id": record_id, "action": "review",
                      "task_id": None, "at": AS_OF, "status": "accepted",
                      "reviewer": "benchmark-fixture", "note": None}
            connection.execute(
                "INSERT INTO knowledge_events(record_id, task_id, action, document) "
                "VALUES (?, NULL, 'review', ?)",
                (record_id, json.dumps(review, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"))),
            )
        for concept, statement, reference in (
            ("gdp_nominal", "Synthetic nominal GDP search candidate.",
             "fixture:benchmark:nominal"),
            ("gdp_real", "Synthetic real GDP search candidate.",
             "fixture:benchmark:real"),
        ):
            record_id = str(uuid4())
            document = {
                "record_id": record_id, "task_id": None, "feedback_id": None,
                "institution_id": "worldbank", "dataset_id": "concept-expansion",
                "concept_id": concept, "classification_axis": "price_basis",
                "correction_type": "source_fact",
                "statement": statement, "provenance": "official_evidence",
                "validation_status": "verified", "source_version": "synthetic-v1",
                "effective_from": None, "effective_to": None,
                "evidence_refs": [reference], "record_version": 1,
                "supersedes_id": None, "created_at": AS_OF, "schema_version": 1,
            }
            encoded = json.dumps(document, ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(",", ":"))
            connection.execute(
                "INSERT INTO knowledge_records(record_id, task_id, feedback_id, institution_id, "
                "dataset_id, concept_id, classification_axis, record_version, created_at, "
                "document, digest, idempotency_key) VALUES (?, NULL, NULL, ?, ?, ?, ?, 1, ?, ?, ?, NULL)",
                (record_id, "worldbank", "concept-expansion", concept, "price_basis", AS_OF,
                 encoded, _digest(document)),
            )
            review = {"event_id": str(uuid4()), "record_id": record_id, "action": "review",
                      "task_id": None, "at": AS_OF, "status": "accepted",
                      "reviewer": "benchmark-fixture", "note": None}
            connection.execute(
                "INSERT INTO knowledge_events(record_id, task_id, action, document) "
                "VALUES (?, NULL, 'review', ?)",
                (record_id, json.dumps(review, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"))),
            )


def naive_full_history_lookup(store: KnowledgeStore) -> tuple[str | None, int, int]:
    """Comparison baseline: load/decode every source record before applying the same scope."""
    with store._connect() as connection:
        rows = connection.execute("SELECT document FROM knowledge_records").fetchall()
    total_bytes = 0
    found = None
    for (encoded,) in rows:
        total_bytes += len(encoded.encode("utf-8"))
        document = json.loads(encoded)
        if (document.get("institution_id") == "worldbank"
                and document.get("dataset_id") == "fixture-catalogue"
                and document.get("concept_id") == "BENCH_00000"
                and document.get("classification_axis") == "benchmark_axis"):
            found = document["record_id"]
    return found, len(rows), total_bytes


def benchmark_size(root: Path, count: int) -> dict:
    workspace = root / "reports"
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"macroatlas-iter12-{count}-", dir=workspace) as temp:
        settings = Settings(Path(temp))
        store = KnowledgeStore(settings)
        seed_records(store, count)
        refresh_batches = 0
        refresh_rows = 0
        refresh = store.refresh_index(batch_size=500, restart=True)
        refresh_batches += 1
        refresh_rows += refresh["processed"]
        while refresh["refresh_pending"]:
            refresh = store.refresh_index(batch_size=500)
            refresh_batches += 1
            refresh_rows += refresh["processed"]

        plan = store.explain_query_plan(institution_id="worldbank")
        scope = {"institution_id": "worldbank", "dataset_id": "fixture-catalogue",
                 "concept_id": "BENCH_00000", "classification_axis": "benchmark_axis",
                 "as_of": AS_OF, "max_rows": 20, "max_bytes": 65_536, "max_time_ms": 250}
        cold_times = []
        warm_times = []
        baseline_times = []
        max_peak_bytes = 0
        baseline_peak_bytes = 0
        last_result = None
        baseline_record_id = None
        baseline_rows = 0
        baseline_bytes = 0
        tracemalloc.start()
        for _ in range(10):
            tracemalloc.reset_peak()
            started = time.perf_counter()
            baseline_record_id, baseline_rows, baseline_bytes = naive_full_history_lookup(store)
            baseline_times.append((time.perf_counter() - started) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            baseline_peak_bytes = max(baseline_peak_bytes, peak)
        for _ in range(REPETITIONS):
            store.clear_cache()
            tracemalloc.reset_peak()
            started = time.perf_counter()
            last_result = store.query(**scope)
            cold_times.append((time.perf_counter() - started) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            max_peak_bytes = max(max_peak_bytes, peak)
        store.clear_cache()
        store.query(**scope)
        for _ in range(REPETITIONS):
            tracemalloc.reset_peak()
            started = time.perf_counter()
            warm = store.query(**scope)
            warm_times.append((time.perf_counter() - started) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            max_peak_bytes = max(max_peak_bytes, peak)
        tracemalloc.stop()
        cache = store.cache_info()
        broad = store.query(institution_id="worldbank", as_of=AS_OF, max_rows=20,
                            max_bytes=65_536, max_time_ms=250)
        concept_policy = ConceptSearchPolicy("benchmark-gdp-v1", (
            ConceptLink("GDP", "gdp_nominal", "subtype", "fixture:benchmark:nominal"),
            ConceptLink("GDP", "gdp_real", "subtype", "fixture:benchmark:real"),
        ))
        expansion = store.query(
            institution_id="worldbank", dataset_id="concept-expansion", concept_id="GDP",
            source_version="synthetic-v1", as_of=AS_OF, max_rows=20,
            max_depth=1, concept_policy=concept_policy,
        )
        assert last_result is not None
        assert last_result["status"] == "complete"
        assert len(last_result["records"]) == 1
        assert last_result["records"][0]["concept_id"] == "BENCH_00000"
        assert last_result["records"][0]["institution_id"] == "worldbank"
        assert last_result["records"][0]["reusable"] is True
        assert last_result["records"][0]["record_id"] == baseline_record_id
        assert baseline_rows == count + 2
        assert broad["status"] == "partial"  # A broad 20-row query reports omitted matches.
        assert len(broad["records"]) == 20
        assert all(item["institution_id"] == "worldbank" for item in broad["records"])
        assert all(item["reusable"] is False for item in broad["records"])
        assert "knowledge_current_scope" in " ".join(plan)
        assert {item["concept_id"] for item in expansion["records"]} == {
            "gdp_nominal", "gdp_real",
        }
        assert expansion["metrics"]["expansion_depth"] == 1
        assert all(item["search_concept_match"] == "search_subtype"
                   and not item["reusable"] for item in expansion["records"])
        assert warm["metrics"]["cache_hit"] is True
        assert warm["metrics"]["evidence_bytes_read"] == 0
        assert cache["entries"] <= cache["max_entries"]
        assert cache["bytes"] <= cache["max_bytes"]
        cold_p95 = percentile(cold_times, 0.95)
        assert cold_p95 <= MAX_COLD_P95_MS, f"{count} records p95={cold_p95:.3f}ms"
        assert max_peak_bytes <= MAX_QUERY_PEAK_BYTES, (
            f"{count} records Python allocation peak={max_peak_bytes} bytes"
        )
        return {
            "records_total": count + 2, "institution_matches": (count + 1) // 2 + 2,
            "refresh_batches": refresh_batches, "refresh_rows": refresh_rows,
            "query_limit": 20, "cold_ms": {
                "p50": round(percentile(cold_times, 0.50), 3),
                "p95": round(cold_p95, 3), "max": round(max(cold_times), 3),
            },
            "warm_ms": {
                "p50": round(percentile(warm_times, 0.50), 3),
                "p95": round(percentile(warm_times, 0.95), 3),
                "max": round(max(warm_times), 3),
            },
            "python_tracemalloc_peak_bytes": max_peak_bytes,
            "naive_full_history_baseline": {
                "p50_ms": round(percentile(baseline_times, 0.50), 3),
                "p95_ms": round(percentile(baseline_times, 0.95), 3),
                "rows_decoded_per_lookup": baseline_rows,
                "bytes_decoded_per_lookup": baseline_bytes,
                "python_tracemalloc_peak_bytes": baseline_peak_bytes,
                "indexed_cold_p95_speedup_ratio": round(
                    percentile(baseline_times, 0.95) / cold_p95, 2),
            },
            "cold_index_rows_read_max": last_result["metrics"]["index_rows_read"],
            "cold_evidence_bytes_read": last_result["metrics"]["evidence_bytes_read"],
            "warm_index_rows_read": warm["metrics"]["index_rows_read"],
            "warm_evidence_bytes_read": warm["metrics"]["evidence_bytes_read"],
            "broad_query": {"status": broad["status"],
                            "index_rows_read": broad["metrics"]["index_rows_read"],
                            "records_returned": broad["metrics"]["records_returned"],
                            "uncertainties": broad["uncertainties"]},
            "query_plan": list(plan), "cache": cache,
            "concept_expansion": {
                "query_concept": "GDP", "policy_version": concept_policy.version,
                "returned_concepts": sorted(item["concept_id"] for item in expansion["records"]),
                "expansion_depth": expansion["metrics"]["expansion_depth"],
                "candidates": expansion["metrics"]["expansion_candidates"],
                "read_rows": expansion["metrics"]["index_rows_read"],
                "evidence_bytes_read": expansion["metrics"]["evidence_bytes_read"],
                "all_candidates_non_reusable": all(
                    not item["reusable"] for item in expansion["records"]),
                "search_correct": True,
            },
            "search_correct": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "reports" /
                        "iteration_12_benchmark.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    results = [benchmark_size(root, size) for size in SIZES]
    report = {
        "mode": "synthetic_local_sqlite_only", "network_used": False,
        "environment": {
            "platform": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "processor": platform.processor() or "unknown",
        },
        "repetitions_per_temperature_and_size": REPETITIONS,
        "limits": {"rows": 20, "evidence_bytes": 65_536, "time_ms": 250,
                   "cache_entries": 128, "cache_bytes": 1_048_576,
                   "cold_p95_ms": MAX_COLD_P95_MS,
                   "python_allocation_peak_bytes": MAX_QUERY_PEAK_BYTES},
        "memory_measurement": "Python tracemalloc peak during one query; excludes native SQLite and process RSS",
        "results": results,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
