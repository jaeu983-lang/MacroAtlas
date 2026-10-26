"""Iteration 13 bounded pattern analysis contracts."""
import json
from datetime import UTC, datetime

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
