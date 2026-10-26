import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageStatus, TaskStatus
from macro_data_platform.ingestion.large_file_production import (
    BIS_FLAT_URL,
    create_production_handoff,
    make_large_file_production_orchestrator,
)
from macro_data_platform.ingestion.large_file_trial import _trial_root, worker_slot
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, decision
from macro_data_platform.orchestration import Orchestrator, StageInput
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.tabular_archives import begin_tabular_package


def _zip_csv(rows):
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("WS_GLI_csv_flat.csv", "period,value\n" + rows)
    return body.getvalue()


def setup_handoff(tmp_path, rows="2026Q1,0\n2026Q2,\n"):
    settings = Settings(tmp_path)
    store = HistoryStore(settings)
    source = tmp_path / "data/inbox/source.zip"
    source.parent.mkdir(parents=True)
    raw = _zip_csv(rows)
    source.write_bytes(raw)
    package = begin_tabular_package(settings, raw, "zip", {
        "source_url": BIS_FLAT_URL,
        "source_agency": "Bank for International Settlements",
    })
    origin_task = Orchestrator(store, {}).create("BIS local re-audit")
    record = DeferredNonAPIStore(settings).register(
        {"relative_path": source.relative_to(tmp_path).as_posix(), "format": "zip",
         "source_url": BIS_FLAT_URL,
         "source_agency": "Bank for International Settlements"},
        origin_task.task_id, "inspect", decision("cells", 500010, 500000),
    )
    with store.transaction() as connection:
        origin = store.load(connection, origin_task.task_id)
        origin["status"] = TaskStatus.NEEDS_REVIEW
        origin["stages"] = [{"stage_id": "inspect", "status": StageStatus.NEEDS_REVIEW,
                              "result": {"payload": {"non_api_deferral": record}}}]
        store.save(connection, origin)
    with store.transaction() as connection:
        event_seq = connection.execute(
            "SELECT seq FROM deferred_non_api_events WHERE id=? ORDER BY seq DESC LIMIT 1",
            (record["id"],),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO tasks(task_id,idempotency_key,document) VALUES ('trial-fixture',NULL,?)",
            (json.dumps({
                "task_id": "trial-fixture", "parent_task_id": origin_task.task_id,
                "deferral_event_seq": event_seq, "trial_only": True, "status": "COMPLETED",
                "stages": [{"status": "SUCCEEDED", "result": {"payload": {
                    "execution_state": "TRIAL_PASSED",
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                }}}],
            }),),
        )
    return settings, store, record, event_seq, package, raw


def test_production_requires_explicit_approval_and_matching_qualification(tmp_path):
    settings, store, record, event_seq, *_ = setup_handoff(tmp_path)
    with pytest.raises(ValueError, match="explicit_production_approval_required"):
        create_production_handoff(store, settings, record["id"], event_seq=event_seq)
    with store.transaction() as connection:
        connection.execute("DELETE FROM tasks WHERE task_id='trial-fixture'")
    with pytest.raises(ValueError, match="matching_qualification_required"):
        create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )


@pytest.mark.skipif(sys.platform != "linux", reason="production integrity guard runs inside Linux worker path")
def test_handoff_is_idempotent_and_source_change_after_binding_stops(tmp_path):
    settings, store, record, event_seq, package, raw = setup_handoff(tmp_path)
    with patch("macro_data_platform.ingestion.large_file_production._qualification_passed",
               return_value=True):
        task_id = create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )
        assert create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        ) == task_id
    assert store.get(task_id)["parent_task_id"] == record["task_id"]
    latest = DeferredNonAPIStore(settings, read_only=True).events(record["id"])[0]
    assert latest["status"] == "handed_off"
    Path(settings.project_root / package["raw_path"]).write_bytes(raw + b"changed")
    doc = make_large_file_production_orchestrator(store, settings).run(task_id)
    result = doc["stages"][-1]["result"]["payload"]
    assert result["execution_state"] == "NOT_EXECUTED"
    assert result["reason"] == "source_changed_since_binding"
    assert not (tmp_path / doc["plan"][0]["input_data"]["artifact_root"]
                / "output_manifest.json").exists()


def test_unsupported_platform_never_falls_back_to_unbounded_processing(tmp_path):
    settings, store, record, event_seq, *_ = setup_handoff(tmp_path)
    with patch("macro_data_platform.ingestion.large_file_production._qualification_passed",
               return_value=True):
        task_id = create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )
    with patch("macro_data_platform.ingestion.large_file_production.sys.platform", "win32"):
        doc = make_large_file_production_orchestrator(store, settings).run(task_id)
    payload = doc["stages"][-1]["result"]["payload"]
    assert payload["reason"] == "resource_isolation_unavailable"
    assert not (tmp_path / doc["plan"][0]["input_data"]["artifact_root"]
                / "output_manifest.json").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited production worker is Linux only")
def test_production_streams_string_rows_and_publishes_verifiable_manifest(tmp_path):
    settings, store, record, event_seq, package, raw = setup_handoff(tmp_path)
    with patch("macro_data_platform.ingestion.large_file_production._qualification_passed",
               return_value=True):
        task_id = create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )
    doc = make_large_file_production_orchestrator(store, settings).run(task_id)
    assert doc["status"] == "COMPLETED"
    payload = doc["stages"][-1]["result"]["payload"]
    assert (payload["rows"], payload["columns"], payload["empty_fields"],
            payload["zero_fields"]) == (2, 2, 1, 1)
    assert payload["quality_scope"].startswith("rectangular CSV structure only")
    assert payload["production_execution"] == "COMPLETED"
    assert hashlib.sha256((tmp_path / package["raw_path"]).read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest()
    manifest_path = tmp_path / payload["output_manifest_path"]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["representation"].startswith("UTF-8 JSON Lines")
    assert manifest["source"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / payload["artifact_root"] / manifest["chunks"][0]["path"]).read_text() == (
        '["2026Q1","0"]\n["2026Q2",""]\n'
    )
    events = DeferredNonAPIStore(settings, read_only=True).events(record["id"])
    assert [event["status"] for event in reversed(events)] == ["deferred", "handed_off", "resolved"]
    assert events[0]["output_manifest_sha256"] == payload["output_manifest_sha256"]


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited production worker is Linux only")
def test_complete_output_can_be_revalidated_after_task_result_loss(tmp_path):
    settings, store, record, event_seq, _package, _raw = setup_handoff(tmp_path)
    with patch("macro_data_platform.ingestion.large_file_production._qualification_passed",
               return_value=True):
        task_id = create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )
    runner = make_large_file_production_orchestrator(store, settings)
    task = store.get(task_id)
    inputs = task["plan"][0]["input_data"]
    artifact_root = tmp_path / inputs["artifact_root"]
    artifact_root.mkdir(parents=True, exist_ok=True)
    # The engine's second invocation validates and reuses the completed output manifest.
    first = runner.run(task_id)
    assert first["status"] == "COMPLETED"
    manifest_hash = hashlib.sha256((artifact_root / "output_manifest.json").read_bytes()).hexdigest()
    with worker_slot(_trial_root(settings)) as descriptor:
        runner.production_engine.worker_lock_fd = descriptor
        try:
            result = runner.production_engine.run(
                StageInput(task_id, task["request"], "materialize", inputs, None, ())
            )
        finally:
            runner.production_engine.worker_lock_fd = None
    assert result.status == StageStatus.SUCCEEDED
    assert result.payload["output_manifest_sha256"] == manifest_hash
    with (artifact_root / "output_manifest.json").open("rb") as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == manifest_hash


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited production worker is Linux only")
def test_checkpoint_resumes_after_all_chunks_but_before_manifest_commit(tmp_path):
    settings, store, record, event_seq, _package, _raw = setup_handoff(
        tmp_path, "".join(f"2026Q{i % 4 + 1},{i}\n" for i in range(10001)),
    )
    with patch("macro_data_platform.ingestion.large_file_production._qualification_passed",
               return_value=True):
        task_id = create_production_handoff(
            store, settings, record["id"], event_seq=event_seq, approved=True,
        )
    runner = make_large_file_production_orchestrator(store, settings)
    task = store.get(task_id)
    inputs = task["plan"][0]["input_data"]
    _trial_root(settings).mkdir(parents=True, exist_ok=True)
    with worker_slot(_trial_root(settings)) as descriptor:
        runner.production_engine.worker_lock_fd = descriptor
        try:
            first = runner.production_engine.run(
                StageInput(task_id, task["request"], "materialize", inputs, None, ())
            )
        finally:
            runner.production_engine.worker_lock_fd = None
    assert first.status == StageStatus.SUCCEEDED
    artifact_root = tmp_path / inputs["artifact_root"]
    (artifact_root / "output_manifest.json").unlink()
    with worker_slot(_trial_root(settings)) as descriptor:
        runner.production_engine.worker_lock_fd = descriptor
        try:
            resumed = runner.production_engine.run(
                StageInput(task_id, task["request"], "materialize", inputs, None, ())
            )
        finally:
            runner.production_engine.worker_lock_fd = None
    assert resumed.status == StageStatus.SUCCEEDED
    manifest = json.loads((artifact_root / "output_manifest.json").read_text())
    assert manifest["rows"] == 10001
    assert [chunk["rows"] for chunk in manifest["chunks"]] == [10000, 1]
