"""Gate A offline evidence: real SQLite/files, fixture HTTP and deliberate failures."""
import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest
import requests
from test_orchestration import Clock
from test_worldbank import FIXTURE, FixtureTransport, fixture_download
from test_worldbank_request import child, supplied

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.worldbank_quality import WorldBankValidation, verified_download
from macro_data_platform.ingestion.worldbank_request import WorldBankRequestDispatcher
from macro_data_platform.orchestration import WorkflowService
from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Gate A fixture tests must never use real HTTP")
    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture
def setup(tmp_path):
    settings = Settings(tmp_path)
    store = HistoryStore(settings)
    clock = Clock()
    service = WorkflowService(store, clock=clock)
    return settings, store, clock, service


def handler(setup, transport=None):
    settings, store, clock, _ = setup
    return WorldBankRequestDispatcher(settings, store, clock=clock, transport=transport, gate_a=True)


def payload(result):
    return next(row["result"]["payload"] for row in reversed(result["stages"])
                if row["stage_id"] == "validate")


def modified(change):
    data = json.loads(FIXTURE.read_bytes())
    change(data)
    return fixture_download(body=json.dumps(data).encode())


@pytest.mark.parametrize("mode", ["file", "both"])
def test_request_to_quality_observations_and_feedback_survives_restart(setup, mode):
    settings, store, clock, service = setup
    task = child(service, supplied(service, mode))
    transport = FixtureTransport(fixture_download())
    dispatch = handler(setup, transport)
    result = dispatch.run(task["task_id"])
    assert result["status"] == "COMPLETED" and len(transport.calls) == 1
    assert [s["stage_id"] for s in result["plan"]] == (
        ["collect", "validate", "deliver"] if mode == "both" else ["collect", "validate"])
    data = payload(result)
    audit = dispatch.audit
    artifact = audit.get(data["artifact_id"])
    assert artifact["raw_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert artifact["manifest_sha256"] == hashlib.sha256(
        (settings.project_root / artifact["manifest_path"]).read_bytes()).hexdigest()
    assert artifact["mode"] == "fixture"
    assert artifact["confirmation_fingerprint"] == task["workflow_context"]["confirmation"]["fingerprint"]
    rows = audit.observations(data["validation_id"])
    assert [row["original_row"] for row in rows] == json.loads(FIXTURE.read_bytes())[1]
    assert [row["value"] for row in rows] == [123.5, None, 0]
    assert [row["value_status"] for row in rows] == ["reported", "missing", "reported"]
    assert all(row["unit"] is None and row["frequency"] is None for row in rows)
    assert rows[0]["source_unit"] == "" and rows[0]["observation_status"] == "F"
    assert rows[0]["source_version"] is None and rows[0]["source_last_updated"] == "2026-01-01"
    assert data["quality"]["status"] == "passed" and data["quality"]["missing_value_count"] == 1
    feedback = audit.add_feedback(task["task_id"], text="Check source status flag before analysis.",
                                  category="problem", record_id=data["validation_id"],
                                  idempotency_key="feedback-1")
    assert feedback["status"] == "recorded_unreviewed" and feedback["origin"] == "user"
    reopened = AuditStore(HistoryStore(settings), clock=clock)
    assert reopened.observations(data["validation_id"]) == rows
    assert reopened.get(feedback["record_id"]) == feedback
    assert reopened.add_feedback(task["task_id"], text=feedback["text"], category="problem",
                                 record_id=data["validation_id"], idempotency_key="feedback-1") == feedback
    assert dispatch.run(task["task_id"]) == result
    assert len(transport.calls) == 1
    assert len(audit.for_task(task["task_id"], kind="artifact")) == 1
    assert len(audit.for_task(task["task_id"], kind="validation")) == 1
    assert len(audit.for_task(task["task_id"], kind="feedback")) == 1
    assert store.events(task["task_id"])[-1]["kind"] == "AUDIT_FEEDBACK"


@pytest.mark.parametrize("issue,change", [
    ("duplicate_periods", lambda d: d[1][1].update(date="2022")),
    ("missing_periods", lambda d: (d[1].pop(), d[0].update(total=2))),
    ("inconsistent_source_units", lambda d: (d[1][0].update(unit="USD"), d[1][1].update(unit="EUR"))),
    ("invalid_source_unit", lambda d: d[1][0].update(unit=123)),
])
def test_bad_quality_is_recorded_without_normalized_publication(setup, issue, change):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    download = modified(change)
    dispatch = handler(setup, FixtureTransport(download))
    result = dispatch.run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert result["stages"][-1]["result"]["error_code"] == "QUALITY_FAILURE"
    data = payload(result)
    assert issue in data["quality"]["issues"] and data["normalized_ref"] is None
    assert dispatch.audit.observations(data["validation_id"]) == []
    assert (settings.project_root / data["raw_path"]).read_bytes() == download.body
    incidents = dispatch.audit.for_task(task["task_id"], kind="incident")
    assert len(incidents) == 1 and incidents[0]["error_code"] == "QUALITY_FAILURE"


def test_explicit_source_unit_and_unknown_metadata_remain_distinct(setup):
    _, _, _, service = setup
    task = child(service, supplied(service))
    download = modified(lambda d: [row.update(unit="USD") for row in d[1]])
    dispatch = handler(setup, FixtureTransport(download))
    result = dispatch.run(task["task_id"])
    assert result["status"] == "COMPLETED"
    assert all(row["unit"] == "USD" and row["source_unit"] == "USD"
               for row in dispatch.audit.observations(payload(result)["validation_id"]))


@pytest.mark.parametrize("status,expected,error", [
    (503, "FAILED", "TRANSIENT"), (403, "NEEDS_REVIEW", "AUTH_ACCESS"),
    (404, "FAILED", "SITE_CHANGED"),
])
def test_http_failures_preserve_raw_hash_and_existing_error_contract(setup, status, expected, error):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download(status=status)))
    result = dispatch.run(task["task_id"])
    assert result["status"] == expected
    assert result["stages"][0]["result"]["error_code"] == error
    artifacts = dispatch.audit.for_task(task["task_id"], kind="artifact")
    assert len(artifacts) == 1 and artifacts[0]["http_status"] == status
    assert (settings.project_root / artifacts[0]["raw_path"]).exists()
    assert dispatch.audit.for_task(task["task_id"], kind="validation") == []
    assert dispatch.audit.for_task(task["task_id"], kind="incident")[0]["error_code"] == error


def test_network_denial_has_failure_record_but_no_artifact(setup):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup)
    result = dispatch.run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert dispatch.audit.for_task(task["task_id"], kind="artifact") == []
    assert dispatch.audit.for_task(task["task_id"], kind="incident")[0]["error_code"] == "LICENSE_SECURITY"
    assert not settings.raw_dir.exists()


@pytest.mark.parametrize("change", [lambda d: d[1][0].update(value=True),
                                        lambda d: d[1][0].update(countryiso3code="JPN")])
def test_schema_failure_is_preserved_before_quality_stage(setup, change):
    _, _, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(modified(change)))
    result = dispatch.run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW" and len(result["stages"]) == 1
    assert result["stages"][0]["result"]["error_code"] == "SCHEMA_CHANGED"
    assert len(dispatch.audit.for_task(task["task_id"], kind="artifact")) == 1


@pytest.mark.parametrize("which", ["raw_path", "manifest_path"])
def test_tampered_files_prevent_completed_result_reuse(setup, which):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    transport = FixtureTransport(fixture_download())
    dispatch = handler(setup, transport)
    result = dispatch.run(task["task_id"])
    artifact = dispatch.audit.get(payload(result)["artifact_id"])
    (settings.project_root / artifact[which]).write_bytes(b"tampered fixture")
    with pytest.raises(ValueError, match="hash mismatch"):
        dispatch.run(task["task_id"])
    assert len(transport.calls) == 1


def test_normalized_row_tampering_is_detected_on_read_and_completed_run(setup):
    _, store, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download()))
    result = dispatch.run(task["task_id"])
    identifier = payload(result)["validation_id"]
    with store.transaction() as connection:
        connection.execute("UPDATE gate_a_observations SET document='{}' WHERE validation_id=?",
                           (identifier,))
    with pytest.raises(ValueError, match="observation integrity"):
        dispatch.audit.observations(identifier)
    with pytest.raises(ValueError, match="observation integrity"):
        dispatch.run(task["task_id"])


def test_tampering_between_collection_and_validation_records_quality_failure(setup, monkeypatch):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download()))
    original = WorldBankValidation.run

    def tamper_then_validate(engine, request):
        (settings.project_root / request.upstream["raw_path"]).write_bytes(b"fixture tamper")
        return original(engine, request)

    monkeypatch.setattr(WorldBankValidation, "run", tamper_then_validate)
    result = dispatch.run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert payload(result)["quality"]["issues"] == ["raw_integrity_failed"]
    assert dispatch.audit.observations(payload(result)["validation_id"]) == []


def test_transient_retry_records_new_artifact_without_overwriting_old_one(setup):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    transport = FixtureTransport(fixture_download(status=503), fixture_download())
    dispatch = handler(setup, transport)
    first = dispatch.run(task["task_id"])
    first_artifact = dispatch.audit.for_task(task["task_id"], kind="artifact")[0]
    before = (settings.project_root / first_artifact["raw_path"]).read_bytes()
    final = dispatch.resume(task["task_id"])
    assert first["status"] == "FAILED" and final["status"] == "COMPLETED"
    assert len(transport.calls) == 2
    assert len(dispatch.audit.for_task(task["task_id"], kind="artifact")) == 2
    assert payload(final)["raw_path"] != first_artifact["raw_path"]
    assert (settings.project_root / first_artifact["raw_path"]).read_bytes() == before


def test_failed_validation_requires_review_and_refetches_on_approved_retry(setup):
    _, _, _, service = setup
    task = child(service, supplied(service))
    transport = FixtureTransport(modified(lambda d: d[1][1].update(date="2022")), fixture_download())
    dispatch = handler(setup, transport)
    first = dispatch.run(task["task_id"])
    with pytest.raises(ValueError, match="review acknowledgement"):
        dispatch.resume(task["task_id"])
    final = dispatch.resume(task["task_id"], approved=True)
    assert final["status"] == "COMPLETED" and len(transport.calls) == 2
    assert dispatch.audit.observations(payload(first)["validation_id"]) == []
    assert len(dispatch.audit.observations(payload(final)["validation_id"])) == 3


def test_valid_collection_reused_after_retryable_validation_interruption(setup, monkeypatch):
    _, _, _, service = setup
    task = child(service, supplied(service))
    transport = FixtureTransport(fixture_download())
    dispatch = handler(setup, transport)
    original = WorldBankValidation.run
    calls = []

    def interrupt_once(engine, request):
        calls.append(request)
        if len(calls) == 1:
            return StageResult(StageStatus.FAILED_RETRYABLE, error_code=ErrorCode.TRANSIENT)
        return original(engine, request)

    monkeypatch.setattr(WorldBankValidation, "run", interrupt_once)
    assert dispatch.run(task["task_id"])["status"] == "PARTIAL"
    final = dispatch.resume(task["task_id"])
    assert final["status"] == "COMPLETED" and len(transport.calls) == 1
    assert any(row["status"] == "SKIPPED_REUSED" for row in final["stages"])


def test_validation_and_rows_roll_back_as_one_batch(setup, monkeypatch):
    _, store, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download()))
    original = store.event

    def fail_validation_event(connection, task_id, body):
        original(connection, task_id, body)
        if body["kind"] == "AUDIT_VALIDATION":
            raise sqlite3.OperationalError("injected validation transaction failure")

    monkeypatch.setattr(store, "event", fail_validation_event)
    result = dispatch.run(task["task_id"])
    assert result["status"] == "PARTIAL"
    assert result["stages"][-1]["result"]["error_code"] == "INTERNAL_BUG"
    assert dispatch.audit.for_task(task["task_id"], kind="validation") == []
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) FROM gate_a_observations").fetchone()[0] == 0
    assert len(dispatch.audit.for_task(task["task_id"], kind="artifact")) == 1


def test_feedback_scope_idempotency_and_rollback_preserve_observations(setup, monkeypatch):
    _, store, _, service = setup
    task = child(service, supplied(service))
    other = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download()))
    result = dispatch.run(task["task_id"])
    validation_id = payload(result)["validation_id"]
    rows = dispatch.audit.observations(validation_id)
    with pytest.raises(ValueError, match="another scope"):
        dispatch.audit.add_feedback(other["task_id"], text="Correction", record_id=validation_id)
    with pytest.raises(ValueError, match="another task"):
        dispatch.audit.add_feedback(other["task_id"], text="Correction",
                                    stage_run_id=result["stages"][0]["stage_run_id"])
    saved = dispatch.audit.add_feedback(task["task_id"], text="User proposes a correction",
                                        category="correction", idempotency_key="correction")
    with pytest.raises(ValueError, match="conflict"):
        dispatch.audit.add_feedback(task["task_id"], text="Another proposal",
                                    idempotency_key="correction")
    original = store.event

    def fail(connection, task_id, body):
        original(connection, task_id, body)
        if body["kind"] == "AUDIT_FEEDBACK":
            raise sqlite3.OperationalError("injected feedback failure")

    monkeypatch.setattr(store, "event", fail)
    with pytest.raises(sqlite3.OperationalError):
        dispatch.audit.add_feedback(task["task_id"], text="Not committed")
    assert dispatch.audit.for_task(task["task_id"], kind="feedback") == [saved]
    assert dispatch.audit.observations(validation_id) == rows


def test_gate_a_is_explicit_and_existing_plan_schema_and_json_remain_intact(setup):
    settings, store, clock, service = setup
    task = child(service, supplied(service))
    old = WorldBankRequestDispatcher(settings, store, clock=clock,
                                     transport=FixtureTransport(fixture_download()))
    old.prepare(task["task_id"])
    before = store.get(task["task_id"])
    with pytest.raises(ValueError, match="Saved plan differs"):
        handler(setup, FixtureTransport()).run(task["task_id"])
    assert store.get(task["task_id"]) == before
    assert old.run(task["task_id"])["status"] == "COMPLETED"
    with store._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert "artifact_id" not in store.get(task["task_id"])["stages"][0]["result"]["payload"]


def test_link_only_is_not_a_gate_a_collection(setup):
    settings, _, _, service = setup
    task = child(service, supplied(service, "link"))
    transport = FixtureTransport()
    dispatch = handler(setup, transport)
    result = dispatch.run(task["task_id"])
    assert result["status"] == "COMPLETED" and result["stages"] == []
    assert dispatch.audit.for_task(task["task_id"]) == []
    assert transport.calls == [] and not settings.raw_dir.exists()


def test_changed_confirmation_cannot_resume_audit_work(setup):
    settings, _, _, service = setup
    root = supplied(service)
    task = child(service, root)
    dispatch = handler(setup, FixtureTransport())
    dispatch.prepare(task["task_id"])
    from macro_data_platform.workflow_contracts import DataRequest

    request = DataRequest.from_dict(root["workflow_request"]["draft"]["request"])
    service.revise(root["task_id"], expected_revision=1, request=replace(request, period_end="2021"))
    with pytest.raises(ValueError, match="invalidated"):
        dispatch.resume(task["task_id"], approved=True)
    assert not settings.raw_dir.exists()


def test_verification_read_budget_and_paths_are_enforced(setup):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    dispatch = handler(setup, FixtureTransport(fixture_download()))
    result = dispatch.run(task["task_id"])
    artifact = dispatch.audit.get(payload(result)["artifact_id"])
    forged = {**artifact, "raw_path": "data/elsewhere/response.json",
              "manifest_path": "data/elsewhere/request.json"}
    with pytest.raises(ValueError, match="World Bank raw directory"):
        verified_download(dispatch.audit, forged)
    (settings.project_root / artifact["raw_path"]).write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="read budget"):
        verified_download(dispatch.audit, artifact)


def test_feedback_validation_bounds(setup):
    _, store, _, service = setup
    task = child(service, supplied(service))
    audit = AuditStore(store)
    for changes in ({"text": ""}, {"text": "x" * 2001}, {"category": "approve"},
                    {"origin": "inferred"}, {"idempotency_key": "x" * 129}):
        with pytest.raises(ValueError):
            audit.add_feedback(task["task_id"], **{"text": "A note", **changes})
    assert audit.for_task(task["task_id"], kind="feedback") == []
