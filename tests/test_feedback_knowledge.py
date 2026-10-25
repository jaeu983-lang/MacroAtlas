"""Iteration 11: explicit feedback history and scoped, provenance-aware knowledge inputs."""
import sqlite3
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 25, tzinfo=UTC)

    def __call__(self):
        return self.value


@pytest.fixture
def stores(tmp_path):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    clock = Clock()
    task = Orchestrator(history, {}, clock=clock).create("explicit local feedback task")
    return settings, history, AuditStore(history, clock=clock), KnowledgeStore(settings, clock=clock), task


def test_feedback_edits_review_cancellation_and_error_query_are_append_only(stores):
    settings, history, audit, _, task = stores
    with history.transaction() as connection:
        incident = audit._insert(connection, "incident", task.task_id, "stage-1", {
            "error_code": "SCHEMA_CHANGED", "message": "safe fixture detail",
        })

    saved = audit.add_feedback(
        task.task_id, text="These nominal and real GDP candidates belong together.",
        category="correction", record_id=incident["record_id"], institution_id="worldbank",
        dataset_id="WDI", concept_id="GDP", classification_axis="price_basis",
        correction_type="candidate_grouping", provenance="user_statement",
        effective_from="2026-01-01T00:00:00Z", version_no=1,
    )
    assert saved["scope"]["validation_status"] == "unverified"
    assert audit.feedback_for_task(task.task_id)[0]["text"] == saved["text"]
    assert audit.feedback_for_error(task.task_id, "SCHEMA_CHANGED")[0]["record_id"] == saved["record_id"]

    event = audit.edit_feedback(saved["record_id"], expected_revision=1, changes={
        "text": "Include both GDP price bases and ask before collection.",
        "scope": {"correction_type": "question_order", "version_no": 2},
    })
    assert event["revision"] == 2 and event["action"] == "edit"
    reviewed = audit.review_feedback(saved["record_id"], expected_revision=2,
                                     review_status="accepted", reviewer="user")
    assert reviewed["revision"] == 3
    current = audit.get_feedback(saved["record_id"])
    assert current["original_text"] == saved["text"]
    assert current["text"] == "Include both GDP price bases and ask before collection."
    assert current["scope"]["correction_type"] == "question_order"
    assert current["review_status"] == "accepted"
    with pytest.raises(ValueError, match="revision conflict"):
        audit.edit_feedback(saved["record_id"], expected_revision=1, changes={"text": "stale"})

    audit.cancel_feedback(saved["record_id"], expected_revision=3, reason="superseded by task guidance")
    cancelled = audit.get_feedback(saved["record_id"])
    assert cancelled["cancelled"] and cancelled["review_status"] == "cancelled"
    assert [event["action"] for event in audit.feedback_history(saved["record_id"])] == [
        "edit", "review", "cancel",
    ]
    reopened = AuditStore(HistoryStore(settings), clock=Clock())
    assert reopened.get_feedback(saved["record_id"]) == cancelled
    with (sqlite3.connect(settings.database_path) as connection,
          pytest.raises(sqlite3.IntegrityError, match="append-only")):
        connection.execute("DELETE FROM gate_a_feedback_events")
    assert history.events(task.task_id)[-1]["kind"] == "AUDIT_FEEDBACK_CANCEL"


def test_feedback_scope_and_origin_validation_prevent_cross_task_links(stores):
    _, history, audit, _, task = stores
    second = Orchestrator(history, {}).create("another task")
    with history.transaction() as connection:
        incident = audit._insert(connection, "incident", task.task_id, "stage", {
            "error_code": "TRANSIENT",
        })
    with pytest.raises(ValueError, match="another scope"):
        audit.add_feedback(second.task_id, text="cross-task link", record_id=incident["record_id"])
    with pytest.raises(ValueError, match="evidence reference"):
        audit.add_feedback(task.task_id, text="unsubstantiated source claim", origin="verification")
    with pytest.raises(ValueError, match="must match"):
        audit.add_feedback(task.task_id, text="user source claim", provenance="official_evidence",
                           evidence_refs=("fixture:unverified-user-claim",))
    with pytest.raises(ValueError, match="effective range"):
        audit.add_feedback(task.task_id, text="invalid time", effective_from="2026-02-01T00:00:00Z",
                           effective_to="2026-01-01T00:00:00Z")


def test_legacy_feedback_idempotency_is_readable_and_gets_a_scoped_index(stores):
    _, history, audit, _, task = stores
    with history.transaction() as connection:
        incident = audit._insert(connection, "incident", task.task_id, "stage", {
            "error_code": "TRANSIENT",
        })
        legacy = audit._insert(connection, "feedback", task.task_id, None, {
            "text": "Legacy explicit feedback", "category": "problem", "origin": "user",
            "related_record_id": incident["record_id"], "status": "recorded_unreviewed",
        }, "legacy-feedback-key")
    replayed = audit.add_feedback(
        task.task_id, text="Legacy explicit feedback", category="problem",
        record_id=incident["record_id"], idempotency_key="legacy-feedback-key",
    )
    assert replayed == legacy
    assert audit.get_feedback(legacy["record_id"])["scope"]["provenance"] == "user_statement"
    assert audit.feedback_for_error(task.task_id, "TRANSIENT")[0]["record_id"] == legacy["record_id"]


def test_knowledge_inputs_keep_provenance_scope_version_and_relations(stores):
    settings, _, audit, knowledge, task = stores
    feedback = audit.add_feedback(
        task.task_id, text="Do not treat nominal GDP as real GDP.", category="correction",
        institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
        classification_axis="price_basis", correction_type="concept_mapping",
    )
    user_claim = knowledge.register(
        provenance="user_statement", feedback_id=feedback["record_id"],
        source_version="feedback-v1", effective_from="2026-01-01T00:00:00Z",
        effective_to="2027-01-01T00:00:00Z",
    )
    assert user_claim["statement"] == feedback["text"]
    assert user_claim["task_id"] == task.task_id
    assert user_claim["provenance"] == "user_statement"
    assert user_claim["validation_status"] == "unverified"
    assert user_claim["review_status"] == "pending"
    assert user_claim["record_version"] == 1

    replacement = knowledge.register(
        "Use explicit price-basis metadata when grouping GDP candidates.",
        provenance="official_evidence", evidence_refs=("fixture:concept-policy-v1",),
        institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
        classification_axis="price_basis", source_version="catalog-v1",
        supersedes_id=user_claim["record_id"], task_id=task.task_id,
    )
    assert replacement["record_version"] == 2
    assert replacement["supersedes_id"] == user_claim["record_id"]
    assert knowledge.get(user_claim["record_id"])["superseded_by"] == replacement["record_id"]
    assert knowledge.get(replacement["record_id"])["provenance"] == "official_evidence"
    assert knowledge.get(replacement["record_id"])["validation_status"] == "unverified"

    inferred = knowledge.register(
        "A broader classification might apply to other GDP providers.",
        provenance="inference", institution_id="worldbank", dataset_id="WDI",
        concept_id="GDP", classification_axis="price_basis", task_id=task.task_id,
    )
    assert inferred["validation_status"] == "inferred"
    with pytest.raises(ValueError, match="cannot be approved"):
        knowledge.review(inferred["record_id"], status="accepted", reviewer="user")
    knowledge.review(replacement["record_id"], status="accepted", reviewer="user",
                     note="approved for its recorded scope")
    assert knowledge.get(replacement["record_id"])["review_status"] == "accepted"
    knowledge.cancel(replacement["record_id"], reason="source evidence expired", actor="user")
    assert knowledge.get(replacement["record_id"])["cancelled"]
    assert [item["action"] for item in knowledge.history_for(replacement["record_id"])] == [
        "review", "cancel",
    ]
    assert len(knowledge.for_task(task.task_id)) == 3
    assert KnowledgeStore(settings, clock=Clock()).get(user_claim["record_id"])["record_id"] == (
        user_claim["record_id"]
    )


def test_knowledge_scope_mismatch_and_unreferenced_official_claim_are_rejected(stores):
    _, _, audit, knowledge, task = stores
    feedback = audit.add_feedback(
        task.task_id, text="institution-scoped correction", institution_id="worldbank",
        concept_id="GDP",
    )
    with pytest.raises(ValueError, match="conflicts with linked feedback"):
        knowledge.register("scope drift", provenance="user_statement",
                           feedback_id=feedback["record_id"], institution_id="imf")
    with pytest.raises(ValueError, match="cannot upgrade"):
        knowledge.register("promoted assertion", provenance="official_evidence",
                           feedback_id=feedback["record_id"],
                           evidence_refs=("fixture:unsupported-upgrade",))
    with pytest.raises(ValueError, match="evidence reference"):
        knowledge.register("unsupported source statement", provenance="official_evidence",
                           institution_id="worldbank")
    with pytest.raises(ValueError, match="cannot be marked"):
        knowledge.register("inferred", provenance="inference", validation_status="verified",
                           concept_id="GDP")
