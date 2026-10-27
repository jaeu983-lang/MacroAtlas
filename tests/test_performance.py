"""Performance telemetry is monotonic, aggregated, and separate from task content."""
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.performance.cli import main as perf_main
from macro_data_platform.performance.report import build_performance_report
from macro_data_platform.performance.storage import prepare_sample
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore


def _sample(duration_ns, **overrides):
    values = {
        "observed_at": datetime(2026, 10, 27, tzinfo=UTC).isoformat(),
        "execution_scope": "orchestrator_stage",
        "engine": "fixture_engine",
        "engine_version": "1",
        "stage": "collect",
        "status": "SUCCEEDED",
        "duration_ns": duration_ns,
        "input_bytes": 512,
        "input_rows": 10,
        "input_columns": 3,
        "output_bytes": 256,
        "output_rows": 8,
        "workload_tier": "bytes_le_64k",
        "sample_class": "fixture",
        "cache_status": "not_applicable",
        "phase_timings_ns": {"parse": duration_ns // 2},
        "code_sha": "a" * 40,
        "environment": {
            "python_version": "3.11.8", "platform": "linux",
            "architecture": "x86_64",
        },
    }
    values.update(overrides)
    return values


def test_p95_requires_twenty_samples_and_report_is_grouped_by_evidence(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for duration in range(1, 20):
        history.record_performance(_sample(duration))

    report = build_performance_report(history.settings.performance_database_path)
    group = report["groups"][0]
    assert report["status"] == "READY"
    assert group["sample_count"] == 19
    assert group["p95_ns"] is None
    assert group["p95_status"] == "INSUFFICIENT_SAMPLE"
    assert group["phases"]["parse"]["p95_status"] == "INSUFFICIENT_SAMPLE"

    history.record_performance(_sample(20))
    report = build_performance_report(history.settings.performance_database_path)
    group = report["groups"][0]
    assert group["sample_count"] == 20
    assert group["p95_ns"] == 19
    assert group["p95_status"] == "READY"
    assert group["rows_per_second_p50"] is not None


def test_sample_writer_discards_unapproved_text_fields(tmp_path):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    catalog_before = settings.database_path.read_bytes()
    sample = _sample(
        10,
        request="private question containing a token sk-test-secret",
        source_url="https://example.org/api?key=credential",
        original_value="private source observation",
    )
    history.record_performance(sample)

    with sqlite3.connect(settings.performance_database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(performance_samples)")}
        row = connection.execute("SELECT * FROM performance_samples").fetchone()
    assert not {"request", "source_url", "original_value", "task_id"} & columns
    stored = repr(row)
    assert "private question" not in stored
    assert "sk-test-secret" not in stored
    assert "credential" not in stored
    assert "private source observation" not in stored
    assert "performance.sqlite" in str(settings.performance_database_path)
    assert settings.database_path.read_bytes() == catalog_before


def test_report_does_not_create_a_database_when_no_samples_exist(tmp_path):
    path = tmp_path / "missing.sqlite"
    report = build_performance_report(path)
    assert report["status"] == "NO_DATA"
    assert report["read_only"] is True
    assert not path.exists()


def test_performance_cli_reads_only_its_separate_store(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MACROATLAS_DATA_DIR", raising=False)
    assert perf_main(["report", "--project-root", str(tmp_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "NO_DATA"
    assert output["read_only"] is True
    assert not (tmp_path / "data" / "performance.sqlite").exists()
    assert not (tmp_path / "data" / "catalog.sqlite").exists()


def test_performance_samples_reject_non_utc_time_and_unknown_phase():
    with pytest.raises(ValueError, match="UTC"):
        prepare_sample(_sample(1, observed_at="2026-10-27T00:00:00+09:00"))
    with pytest.raises(ValueError, match="phases"):
        prepare_sample(_sample(1, phase_timings_ns={"request_text": 10}))


def test_knowledge_query_returns_latency_and_records_cache_hit_without_query_content(tmp_path):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    feedback = FeedbackStore(history)
    knowledge = KnowledgeStore(
        history, feedback=feedback,
        clock=lambda: datetime(2026, 10, 27, tzinfo=UTC),
    )
    private_query = "do not persist this natural language request"

    miss = knowledge.query(institution_id=private_query)
    hit = knowledge.query(institution_id=private_query)

    assert miss["latency_ns"] > 0
    assert hit["latency_ns"] > 0
    assert miss["cache"] == "miss"
    assert hit["cache"] == "hit"
    with sqlite3.connect(settings.performance_database_path) as connection:
        rows = connection.execute(
            "SELECT execution_scope, engine, stage, cache_status, duration_ns, "
            "phase_timings_json FROM performance_samples ORDER BY sample_id",
        ).fetchall()
    assert [row[3] for row in rows] == ["miss", "hit"]
    assert all(row[0:3] == ("knowledge_lookup", "knowledge", "query") for row in rows)
    assert all(row[4] > 0 and "sqlite" in json.loads(row[5]) for row in rows)
    assert private_query not in repr(rows)
