"""Iteration 13: bounded repeat-pattern candidates with no automatic application."""
import json

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.improvement import ImprovementAnalyzer
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore


@pytest.fixture
def improvement_stores(tmp_path):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    audit = AuditStore(history)
    knowledge = KnowledgeStore(settings)
    orchestrator = Orchestrator(history, {})
    return settings, history, audit, knowledge, orchestrator


def _incident(audit, task_id, error_code, *, stage_run_id=None, message=None):
    with audit.history.transaction() as connection:
        return audit._insert(connection, "incident", task_id, stage_run_id, {
            "error_code": error_code,
            "message": message or "deterministic fixture diagnostic",
        })


def test_repeated_structured_errors_are_prioritized_without_leaking_messages(
    improvement_stores,
):
    _, history, audit, _, orchestrator = improvement_stores
    for index in range(3):
        task = orchestrator.create(f"fixture failure task {index}")
        _incident(audit, task.task_id, "SCHEMA_CHANGED",
                  message="private diagnostic must not be copied into a proposal")
    with history._connect() as connection:
        before = connection.execute("SELECT COUNT(*) FROM gate_a_records").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    result = ImprovementAnalyzer(history).analyze()

    assert result["status"] == "complete" and result["read_only"] is True
    assert result["approval_required"] is True
    assert len(result["patterns"]) == 1
    candidate = result["patterns"][0]
    assert candidate["error_code"] == "SCHEMA_CHANGED"
    assert candidate["distinct_task_count"] == 3
    assert candidate["classification"] == "recurring_across_multiple_tasks"
    assert candidate["priority"] == "P1"
    assert "reduce recurrence" in candidate["expected_impact"]
    assert candidate["apply_allowed"] is False
    assert len(candidate["record_refs"]) == 3
    assert "private diagnostic" not in json.dumps(result)
    assert candidate["generalization_status"] == "not_established"
    with history._connect() as connection:
        after = connection.execute("SELECT COUNT(*) FROM gate_a_records").fetchone()[0]
        after_version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert after == before and after_version == version


def test_feedback_uses_exact_normalized_text_and_keeps_institution_scope(
    improvement_stores,
):
    _, _, audit, _, orchestrator = improvement_stores
    worldbank_tasks = [orchestrator.create(f"worldbank task {index}") for index in range(2)]
    first = audit.add_feedback(
        worldbank_tasks[0].task_id, text="Ask before collecting.", category="correction",
        institution_id="worldbank", correction_type="output_preference",
    )
    audit.review_feedback(first["record_id"], expected_revision=1,
                          review_status="accepted", reviewer="fixture-review")
    audit.add_feedback(
        worldbank_tasks[1].task_id, text="  ASK   BEFORE collecting.  ", category="correction",
        institution_id="worldbank", correction_type="output_preference",
    )
    imf_task = orchestrator.create("imf scoped task")
    audit.add_feedback(
        imf_task.task_id, text="Ask before collecting.", category="correction",
        institution_id="imf", correction_type="output_preference",
    )

    result = ImprovementAnalyzer(audit.history).analyze()
    feedback = [item for item in result["patterns"] if item["pattern_type"] == "feedback"]
    by_institution = {item["scope"]["institution_id"]: item for item in feedback}
    assert set(by_institution) == {"worldbank", "imf"}
    assert by_institution["worldbank"]["observation_count"] == 2
    assert by_institution["worldbank"]["distinct_task_count"] == 2
    assert by_institution["worldbank"]["classification"] == "repeated_across_tasks"
    assert "within this declared scope" in by_institution["worldbank"]["expected_impact"]
    assert by_institution["imf"]["observation_count"] == 1
    assert by_institution["imf"]["classification"] == "single_observation"
    assert "input_review_states" in by_institution["worldbank"]
    assert all(item["apply_allowed"] is False for item in feedback)
    assert "Ask before collecting" not in json.dumps(result)


def test_inference_stays_quarantined_and_requires_counterexample_review(
    improvement_stores,
):
    _, history, _, knowledge, _ = improvement_stores
    inference = knowledge.register(
        "Possible GDP relation inferred from one fixture label.", provenance="inference",
        institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
        evidence_refs=("fixture:unverified-label",),
    )

    result = ImprovementAnalyzer(history).analyze()
    candidate = next(item for item in result["patterns"]
                     if item["pattern_type"] == "inference_review")
    assert candidate["premise_record_refs"] == [inference["record_id"]]
    assert candidate["evidence_refs"] == ["fixture:unverified-label"]
    assert candidate["counterexample_refs"] == []
    assert candidate["counterexample_search_required"] is True
    assert "changes no mapping or fact" in candidate["expected_impact"]
    assert candidate["apply_allowed"] is False
    assert candidate["scope"]["institution_id"] == "worldbank"
    assert "Possible GDP relation" not in json.dumps(result)


def test_scan_caps_report_incompleteness_and_withhold_complete_proposals(
    improvement_stores,
):
    _, history, audit, _, orchestrator = improvement_stores
    for index in range(2):
        task = orchestrator.create(f"budget fixture task {index}")
        _incident(audit, task.task_id, "INTERNAL_BUG")

    result = ImprovementAnalyzer(history).analyze(max_records=1)
    assert result["status"] == "partial"
    assert "record_budget_exhausted:audit_incident" in result["uncertainties"]
    assert result["patterns"][0]["apply_allowed"] is False
    assert result["patterns"][0]["proposal_status"] == "incomplete_scan_requires_review"

    with pytest.raises(ValueError, match="record budget"):
        ImprovementAnalyzer(history).analyze(max_records=True)
    with pytest.raises(ValueError, match="byte budget"):
        ImprovementAnalyzer(history).analyze(max_bytes=0)


def test_pattern_input_scan_uses_kind_index(improvement_stores):
    _, history, _, _, _ = improvement_stores
    with history._connect() as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT record_id, task_id, stage_run_id, document "
            "FROM gate_a_records WHERE kind=? ORDER BY rowid DESC LIMIT ?",
            ("incident", 501),
        ).fetchall()
    assert any("gate_a_by_kind" in str(row) for row in plan)
