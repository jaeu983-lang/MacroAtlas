"""Iteration 13 bounded pattern analysis contracts."""
import io
import json
import zipfile
from datetime import UTC, datetime

import pytest

from macro_data_platform.analysis.patterns import PatternAnalyzer
from macro_data_platform.config import Settings
from macro_data_platform.pattern_cli import main as pattern_cli
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore

AT = datetime(2026, 10, 26, tzinfo=UTC).isoformat()


def add_task(history, task_id, *, scope=None, outcomes=None, task_status="FAILED"):
    outcomes = outcomes or [("FAILED_RETRYABLE", "TRANSIENT")]
    document = history.document("synthetic test task", AT)
    document.update(task_id=task_id, status=task_status)
    stage_id, engine, version = "collect", "fixture_api", "2"
    document["plan"] = [{
        "stage_id": stage_id, "engine": engine, "engine_version": version,
        "input_data": dict(scope or {}),
    }]
    document["stages"] = [{
        "stage_run_id": f"stage:{task_id}:{index}", "stage_id": stage_id,
        "engine": engine, "engine_version": version,
        "task_attempt_no": index + 1, "attempt_no": index + 1,
        "status": status, "started_at": AT, "finished_at": AT,
        "result": {"status": status, "error_code": error,
                   "payload": {"raw_provider_payload": "RAW_PAYLOAD_SHOULD_NOT_ESCAPE"}},
    } for index, (status, error) in enumerate(outcomes)]
    with history.transaction() as connection:
        history.insert(connection, document)
    return document


def scoped(institution="agency_a", dataset="dataset_1", concept="gdp"):
    return {"institution_id": institution, "dataset_id": dataset, "concept": concept}


def test_three_distinct_tasks_create_traceable_draft_without_raw_payload(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for index in range(3):
        add_task(history, f"task-{index}", scope=scoped())
    before = [history.get(f"task-{index}") for index in range(3)]

    report = PatternAnalyzer(history).analyze()
    after = [history.get(f"task-{index}") for index in range(3)]

    assert report["status"] == "complete"
    assert report["read_only"] is True
    assert after == before
    assert len(report["proposals"]) == 1
    proposal = report["proposals"][0]
    assert proposal["proposal_type"] == "recurring_stage_error"
    assert proposal["review_status"] == "draft"
    assert proposal["promotion_status"] == "not_promoted"
    assert proposal["distinct_task_count"] == 3
    assert proposal["scope"] == scoped()
    assert len(proposal["evidence_ids"]) == 3
    assert "RAW_PAYLOAD_SHOULD_NOT_ESCAPE" not in json.dumps(report)


def test_same_task_retries_do_not_count_as_independent_cases(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    add_task(history, "one-task", scope=scoped(), outcomes=[
        ("FAILED_RETRYABLE", "TRANSIENT") for _ in range(8)
    ])

    report = PatternAnalyzer(history).analyze()

    assert report["proposals"] == []
    assert report["summary"]["one_off_count"] == 1
    assert report["summary"]["one_off_sample"][0]["distinct_task_count"] == 1


def test_unknown_or_different_scope_dimensions_never_merge(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    add_task(history, "unknown-a", scope={"dataset_id": "dataset_1", "concept": "gdp"})
    add_task(history, "unknown-b", scope={"dataset_id": "dataset_1", "concept": "gdp"})
    add_task(history, "unknown-c", scope={"dataset_id": "dataset_1", "concept": "gdp"})
    add_task(history, "other-agency", scope=scoped(institution="agency_b"))
    add_task(history, "other-dataset", scope=scoped(dataset="dataset_2"))
    add_task(history, "other-engine", scope=scoped())
    # A different engine is persisted as part of the stage result metadata.
    with history.transaction() as connection:
        doc = history.load(connection, "other-engine")
        doc["stages"][0]["engine"] = "other_api"
        history.save(connection, doc)

    report = PatternAnalyzer(history).analyze()

    assert report["proposals"] == []
    assert report["summary"]["insufficient_evidence_count"] == 3
    assert report["summary"]["one_off_count"] == 3


def test_confirmed_workflow_scope_is_extracted_without_reading_request_text(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for index in range(3):
        task_id = f"workflow-{index}"
        add_task(history, task_id, scope={})
        with history.transaction() as connection:
            doc = history.load(connection, task_id)
            doc["workflow_context"] = {"confirmation": {"offer": {
                "candidate_id": "selected",
                "request": {"concept": "consumer_prices"},
                "proposal": {"proposal": {"candidates": [{
                    "candidate_id": "selected", "institution_id": "agency_c",
                    "dataset_id": "prices_v2",
                }, {"candidate_id": "not_selected", "institution_id": "other_agency",
                     "dataset_id": "other_dataset"}]}},
            }}}
            history.save(connection, doc)

    report = PatternAnalyzer(history).analyze()

    assert len(report["proposals"]) == 1
    assert report["proposals"][0]["scope"] == {
        "institution_id": "agency_c", "dataset_id": "prices_v2",
        "concept": "consumer_prices",
    }


def test_only_accepted_explicit_feedback_can_create_a_scoped_draft(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history)
    for index in range(3):
        task_id = f"feedback-task-{index}"
        add_task(history, task_id, scope=scoped(), outcomes=[("SUCCEEDED", None)],
                 task_status="COMPLETED")
        item = feedback.record(
            task_id, text="Keep holdings separate from transactions.",
            category="candidate_group", knowledge_kind="user_instruction",
            scope=scoped(),
        )
        feedback.review(item["feedback_id"], expected_revision=1, status="accepted")
    # These records must not contribute: inference is excluded even if accepted;
    # an unreviewed instruction is also excluded.
    inference = feedback.record(
        "feedback-task-0", text="Maybe group the related series.",
        category="candidate_group", knowledge_kind="inference", scope=scoped(),
    )
    feedback.review(inference["feedback_id"], expected_revision=1, status="accepted")
    feedback.record("feedback-task-1", text="Keep holdings separate from flows.",
                    category="candidate_group", knowledge_kind="user_instruction",
                    scope=scoped())
    secret = feedback.record(
        "feedback-task-2", text="Retry using api_key=sk-test-secret-value.",
        category="source_method", knowledge_kind="user_instruction", scope=scoped(),
    )
    feedback.review(secret["feedback_id"], expected_revision=1, status="accepted")

    report = PatternAnalyzer(history).analyze()

    proposals = [item for item in report["proposals"]
                 if item["proposal_type"] == "recurring_accepted_feedback"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["distinct_task_count"] == 3
    assert proposal["review_status"] == "draft"
    assert "Keep holdings separate from transactions." not in json.dumps(report)
    assert report["metrics"]["feedback_records_scanned"] == 4
    assert report["summary"]["unsafe_feedback_excluded"] == 1
    assert "sk-test-secret-value" not in json.dumps(report)


def test_conflicting_accepted_instructions_are_reported_not_proposed(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history)
    for index, instruction in enumerate([
        "Keep the series separate.", "Keep the series separate.",
        "Keep the series separate.", "Combine the series.",
    ]):
        task_id = f"conflict-task-{index}"
        add_task(history, task_id, scope=scoped(), outcomes=[("SUCCEEDED", None)],
                 task_status="COMPLETED")
        item = feedback.record(task_id, text=instruction, category="candidate_group",
                               knowledge_kind="user_instruction", scope=scoped())
        feedback.review(item["feedback_id"], expected_revision=1, status="accepted")

    report = PatternAnalyzer(history).analyze()

    assert not [item for item in report["proposals"]
                if item["proposal_type"] == "recurring_accepted_feedback"]
    assert report["summary"]["possible_conflict_count"] == 1
    assert report["summary"]["possible_conflicts"][0]["review_status"] == (
        "possible_conflict_requires_human_review"
    )


def test_retryable_failure_draft_contains_success_counterexample(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for index in range(3):
        add_task(history, f"failed-{index}", scope=scoped())
    add_task(history, "success", scope=scoped(), outcomes=[("SUCCEEDED", None)],
             task_status="COMPLETED")

    proposal = PatternAnalyzer(history).analyze()["proposals"][0]

    assert proposal["counterexamples"] == [{
        "evidence_id": "stage:success:0", "task_id": "success",
        "status": "SUCCEEDED", "error_category": None,
    }]


def test_unknown_error_categories_are_not_exposed_or_merged(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for index in range(3):
        task_id = f"unknown-error-{index}"
        add_task(history, task_id, scope=scoped())
        with history.transaction() as connection:
            doc = history.load(connection, task_id)
            doc["stages"][0]["result"]["error_code"] = "private-token=do-not-report"
            history.save(connection, doc)

    report = PatternAnalyzer(history).analyze()

    assert report["proposals"] == []
    assert report["summary"]["insufficient_evidence_count"] == 3
    assert "private-token=do-not-report" not in json.dumps(report)


def test_task_and_record_caps_report_partial_without_claiming_no_patterns(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    for index in range(501):
        add_task(history, f"many-{index}", scope=scoped())
    task_report = PatternAnalyzer(history).analyze()
    assert task_report["status"] == "partial"
    assert task_report["truncation"]["tasks"] is True
    assert task_report["metrics"]["tasks_scanned"] == 500

    limited = HistoryStore(Settings(tmp_path / "record-cap"))
    add_task(limited, "many-retries", scope=scoped(), outcomes=[
        ("FAILED_RETRYABLE", "TRANSIENT") for _ in range(2_501)
    ])
    record_report = PatternAnalyzer(limited).analyze()
    assert record_report["status"] == "partial"
    assert record_report["truncation"]["records"] is True
    assert record_report["metrics"]["records_scanned"] == 2_500
    assert record_report["proposals"] == []


def test_proposal_and_evidence_caps_are_explicit(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    documents = []
    for task_index in range(3):
        document = history.document("synthetic test task", AT)
        document.update(task_id=f"wide-{task_index}", status="FAILED")
        document["plan"] = []
        document["stages"] = []
        for pattern_index in range(21):
            stage_id = f"collect-{pattern_index}"
            document["plan"].append({
                "stage_id": stage_id, "engine": "fixture_api", "engine_version": "2",
                "input_data": scoped(),
            })
            document["stages"].append({
                "stage_run_id": f"stage:wide-{task_index}:{pattern_index}",
                "stage_id": stage_id, "engine": "fixture_api", "engine_version": "2",
                "task_attempt_no": 1, "attempt_no": 1, "status": "FAILED_RETRYABLE",
                "started_at": AT, "finished_at": AT,
                "result": {"error_code": "TRANSIENT", "payload": None},
            })
        documents.append(document)
    with history.transaction() as connection:
        for document in documents:
            history.insert(connection, document)

    report = PatternAnalyzer(history).analyze()

    assert report["status"] == "partial"
    assert report["metrics"]["candidate_count"] == 21
    assert report["metrics"]["proposal_count"] == 20
    assert report["truncation"]["proposals"] is True
    assert all(len(item["evidence_ids"]) <= 10 for item in report["proposals"])


def test_cli_does_not_create_a_database_for_empty_project(tmp_path, capsys):
    assert pattern_cli(["--project-root", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "complete"
    assert report["read_only"] is True
    assert report["metrics"]["records_scanned"] == 0
    assert not (tmp_path / "data" / "catalog.sqlite").exists()


def test_persisted_file_scope_adapter_preserves_unknown_concept():
    import sqlite3

    from macro_data_platform.analysis.patterns import _stage_scope_sql

    connection = sqlite3.connect(':memory:')
    try:
        for source, expected in [('tic', 'TIC_TABLE5'), ('bis', 'WS_GLI_csv_col'),
                                 ('unknown', None)]:
            plan = json.dumps({'engine': 'gate_c_file_watch', 'input_data': {'source_id': source}})
            expressions = [_stage_scope_sql(field, field, field)
                           for field in ('institution_id', 'dataset_id', 'concept')]
            row = connection.execute(
                'SELECT ' + ','.join(expressions) +
                ' FROM (SELECT ? AS value) p, (SELECT ? AS document) t',
                (plan, '{}'),
            ).fetchone()
            assert row == ((source if expected else None), expected, None)
    finally:
        connection.close()


def test_technical_errors_allow_unknown_concept_but_meaning_errors_do_not(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    scope = {"institution_id": "bis", "dataset_id": "WS_GLI_csv_flat"}
    for index in range(3):
        add_task(history, f"technical-{index}", scope=scope)
        add_task(history, f"meaning-{index}", scope=scope,
                 outcomes=[("NEEDS_REVIEW", "SEMANTIC_AMBIGUITY")])

    report = PatternAnalyzer(history).analyze()

    technical = [item for item in report["proposals"]
                 if item["analysis_domain"] == "technical_error"]
    meaning = [item for item in report["proposals"]
               if item["analysis_domain"] == "economic_meaning"]
    assert len(technical) == 1
    assert technical[0]["scope"]["concept"] is None
    assert technical[0]["required_dimensions"] == [
        "institution_id", "engine", "engine_version", "stage_id", "dataset_id",
    ]
    assert technical[0]["scope_unknown"] == []
    assert meaning == []
    assert report["summary"]["technical_error_missing_concept_count"] == 3
    assert report["summary"]["economic_meaning_missing_concept_count"] == 3
    assert report["summary"]["insufficient_evidence_count"] == 3


def test_trials_leave_operational_aggregate_only_with_matching_saved_event(tmp_path):
    history = HistoryStore(Settings(tmp_path))

    def trial_task(task_id, seq, path, event_path):
        document = add_task(history, task_id, scope={},
                            outcomes=[("NEEDS_REVIEW", "SCHEMA_CHANGED")])
        document["trial_only"] = True
        plan = document["plan"][0]
        plan["engine"] = "large_file_trial"
        plan["stage_id"] = "qualify"
        plan["input_data"].update({
            "deferral_id": f"deferral-{seq}", "deferral_event_seq": seq,
            "origin_task_id": f"origin-{seq}",
            "scope": {"relative_path": path, "format": "csv"},
        })
        stage = document["stages"][0]
        stage["engine"] = "large_file_trial"
        stage["stage_id"] = "qualify"
        stage["result"]["payload"] = {
            "trial_attempted": True, "production_execution": "NOT_EXECUTED",
            "execution_state": "NOT_EXECUTED", "reason": "ragged_rows",
        }
        with history.transaction() as connection:
            history.save(connection, document)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS deferred_non_api_events "
                "(seq INTEGER PRIMARY KEY, id TEXT NOT NULL, document TEXT NOT NULL)"
            )
            body = {
                "id": f"deferral-{seq}", "task_id": f"origin-{seq}",
                "reason": "qualification_candidate", "status": "inspection_required",
                "scope": {"relative_path": event_path, "format": "csv"},
            }
            connection.execute(
                "INSERT INTO deferred_non_api_events(seq,id,document) VALUES (?,?,?)",
                (seq, f"deferral-{seq}", json.dumps(body)),
            )

    fixture_path = "data/inbox/qualification-fixtures-test/ragged.csv"
    trial_task("verified-trial", 1, fixture_path, fixture_path)
    trial_task("unverified-trial", 2, fixture_path, "data/inbox/other.csv")

    report = PatternAnalyzer(history).analyze()

    assert report["metrics"]["qualification_fixture_stage_records_scanned"] == 1
    assert report["metrics"]["operational_stage_records_scanned"] == 1
    assert report["summary"]["qualification_fixture_count"] == 1
    assert report["summary"]["insufficient_evidence_count"] == 1
    assert report["summary"]["insufficient_evidence_sample"][0]["task_id"] == (
        "unverified-trial"
    )


@pytest.mark.parametrize("modify_raw", [False, True])
def test_bis_scope_projection_requires_matching_saved_manifest(tmp_path, modify_raw):
    import hashlib

    from macro_data_platform.analysis.scope_evidence import BIS_FLAT_AGENCY, BIS_FLAT_URL

    history = HistoryStore(Settings(tmp_path))
    package_id = "c" * 32
    package = tmp_path / "data" / "raw" / "tabular" / package_id
    package.mkdir(parents=True)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as contents:
        contents.writestr("WS_GLI_csv_flat.csv", "TIME_PERIOD,OBS_VALUE\n2026,1\n")
    preserved = archive.getvalue()
    raw_saved = package / "source.zip"
    raw_saved.write_bytes(preserved)
    manifest = package / "request.json"
    manifest.write_text(json.dumps({
        "package_id": package_id,
        "request_context": {
            "source_url": BIS_FLAT_URL, "source_http_status": 200,
            "source_agency": BIS_FLAT_AGENCY,
            "source_captured_at": "2026-10-26T09:18:10.929482+00:00", "format": "zip",
        },
        "raw": {
            "path": f"data/raw/tabular/{package_id}/source.zip",
            "sha256": hashlib.sha256(preserved).hexdigest(), "bytes": len(preserved),
        },
    }), encoding="utf-8")
    inbox = tmp_path / "data" / "inbox"
    inbox.mkdir(parents=True)
    raw_inbox = inbox / "bis-flat.zip"
    raw_inbox.write_bytes(b"tampered archive" if modify_raw else preserved)

    add_task(history, "bis-scope", scope={}, outcomes=[("NEEDS_REVIEW", "SCHEMA_CHANGED")])
    with history.transaction() as connection:
        document = history.load(connection, "bis-scope")
        document["plan"][0].update(engine="tabular_file", input_data={
            "format": "zip", "relative_path": "data/inbox/bis-flat.zip",
            "source_url": BIS_FLAT_URL, "source_agency": BIS_FLAT_AGENCY,
        })
        document["stages"][0]["engine"] = "tabular_file"
        history.save(connection, document)

    report = PatternAnalyzer(history).analyze()

    if modify_raw:
        assert report["summary"]["scope_resolution_count"] == 0
        assert report["summary"]["insufficient_evidence_count"] == 1
        assert report["summary"]["insufficient_evidence_sample"][0]["unknown_dimensions"] == [
            "institution_id", "dataset_id",
        ]
    else:
        assert report["summary"]["scope_resolution_count"] == 1
        evidence = report["summary"]["scope_resolution_sample"][0]
        assert evidence["institution_id"] == "bis"
        assert evidence["dataset_id"] == "WS_GLI_csv_flat"
        assert evidence["concept"] is None
        assert evidence["concept_status"] == "unknown_not_inferred_from_file_identity"
        assert evidence["raw_sha256"] == hashlib.sha256(preserved).hexdigest()
        assert evidence["request_manifest_path"] == (
            f"data/raw/tabular/{package_id}/request.json"
        )
        assert report["summary"]["insufficient_evidence_count"] == 0
