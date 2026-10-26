"""Iteration 11 explicit, scoped and revisioned user feedback storage."""
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.feedback_cli import main as feedback_cli
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore

AT = datetime(2026, 10, 26, tzinfo=UTC)


def setup_store(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    with history.transaction() as connection:
        for task_id in ("task-a", "task-b"):
            document = history.document("explicit test task", AT.isoformat())
            document["task_id"] = task_id
            history.insert(connection, document)
    return history, FeedbackStore(history, clock=lambda: AT)


def test_explicit_feedback_keeps_scope_type_evidence_review_and_edit_history(tmp_path):
    history, store = setup_store(tmp_path)
    item = store.record(
        "task-a", text="Group holdings candidates before transactions.",
        category="candidate_group", knowledge_kind="user_instruction",
        scope={"institution_id": "treasury_tic", "concept": "foreign holdings",
               "classification_axis": "measure", "version": "2026-10"},
        idempotency_key="explicit-1",
    )
    assert item["review_status"] == "unreviewed"
    assert item["knowledge_kind"] == "user_instruction"
    assert store.record(
        "task-a", text=item["text"], category="candidate_group",
        knowledge_kind="user_instruction",
        scope={"institution_id": "treasury_tic", "concept": "foreign holdings",
               "classification_axis": "measure", "version": "2026-10"},
        idempotency_key="explicit-1",
    ) == item

    accepted = store.review(item["feedback_id"], expected_revision=1,
                             status="accepted", reviewer_note="Verified for this workflow only.")
    edited = store.revise(item["feedback_id"], expected_revision=2,
                          changes={"text": "Show holdings candidates before transactions."})
    assert edited["revision"] == 3 and edited["review_status"] == "unreviewed"
    assert [row["action"] for row in store.history_for(item["feedback_id"])] == [
        "created", "reviewed", "edited",
    ]
    assert store.for_task("task-a", institution_id="treasury_tic") == [edited]
    assert store.for_task("task-b") == []
    assert history.events("task-a")[-1]["kind"] == "FEEDBACK_EDITED"
    with pytest.raises(ValueError, match="stale feedback revision"):
        store.withdraw(item["feedback_id"], expected_revision=2, reason="stale edit")
    assert accepted["review_status"] == "accepted"


def test_official_evidence_and_inference_remain_separate_from_user_instruction(tmp_path):
    _, store = setup_store(tmp_path)
    with pytest.raises(ValueError, match="requires a source reference"):
        store.record("task-a", text="Source says X", knowledge_kind="official_evidence")
    with pytest.raises(ValueError, match="HTTPS"):
        store.record("task-a", text="Source says X", knowledge_kind="official_evidence",
                     evidence_refs=[{"source_url": "https://example.org/data?key=secret"}])
    source = store.record(
        "task-a", text="Official guide defines this label.", knowledge_kind="official_evidence",
        evidence_refs=[{"source_url": "https://example.org/guide",
                        "source_version": "v2", "captured_at": AT.isoformat()}],
        scope={"institution_id": "agency-a"},
    )
    inference = store.record("task-a", text="This may imply comparable coverage.",
                             knowledge_kind="inference", scope={"concept": "coverage"})
    assert source["knowledge_kind"] == "official_evidence"
    assert source["review_status"] == inference["review_status"] == "unreviewed"
    assert inference["knowledge_kind"] == "inference"


def test_withdrawal_is_audited_final_and_feedback_cannot_cross_tasks(tmp_path):
    _history, store = setup_store(tmp_path)
    item = store.record("task-a", text="Use this question order.", category="question_order",
                        scope={"institution_id": "agency-a"})
    withdrawn = store.withdraw(item["feedback_id"], expected_revision=1,
                               reason="User withdrew the preference.")
    assert withdrawn["review_status"] == "withdrawn"
    assert store.get(item["feedback_id"])["revision"] == 2
    with pytest.raises(ValueError, match="final"):
        store.review(item["feedback_id"], expected_revision=2, status="accepted")
    with pytest.raises(ValueError, match="unknown feedback"):
        store.get("not-a-feedback-id")
    with pytest.raises(KeyError, match="unknown task"):
        store.for_task("missing-task")


def test_replacement_links_versions_and_supersedes_only_within_the_same_task(tmp_path):
    _, store = setup_store(tmp_path)
    old = store.record("task-a", text="Use chart A.", category="output_preference",
                       scope={"institution_id": "agency-a"})
    replacement = store.record(
        "task-a", text="Use table B.", category="output_preference",
        scope={"institution_id": "agency-a"}, supersedes_feedback_id=old["feedback_id"],
        idempotency_key="replacement-1",
    )
    assert store.record(
        "task-a", text="Use table B.", category="output_preference",
        scope={"institution_id": "agency-a"}, supersedes_feedback_id=old["feedback_id"],
        idempotency_key="replacement-1",
    ) == replacement
    assert replacement["supersedes_feedback_id"] == old["feedback_id"]
    assert store.get(old["feedback_id"])["review_status"] == "superseded"
    assert store.history_for(old["feedback_id"])[-1]["action"] == "superseded"
    with pytest.raises(ValueError, match="another task"):
        store.record("task-b", text="Cross-task replacement.",
                     supersedes_feedback_id=old["feedback_id"])


def test_invalid_scope_and_stale_edit_do_not_append_revision(tmp_path):
    _, store = setup_store(tmp_path)
    with pytest.raises(ValueError, match="institution"):
        store.record("task-a", text="Do this", scope={"institution_id": "../other"})
    item = store.record("task-a", text="Keep source versions.",
                        knowledge_kind="user_instruction")
    with pytest.raises(ValueError, match="revision and nonempty"):
        store.revise(item["feedback_id"], expected_revision=True, changes={"text": "forged"})
    with pytest.raises(ValueError, match="unsupported"):
        store.revise(item["feedback_id"], expected_revision=1,
                     changes={"review_status": "accepted"})
    assert len(store.history_for(item["feedback_id"])) == 1


def test_cli_records_and_lists_only_explicitly_requested_task_scope(tmp_path, capsys):
    history, _ = setup_store(tmp_path)
    # The CLI opens the repository's default data/catalog.sqlite.
    assert history.get("task-a")["task_id"] == "task-a"
    assert feedback_cli([
        "--project-root", str(tmp_path), "add", "--task-id", "task-a",
        "--text", "Keep holdings before transactions.", "--category", "candidate_group",
        "--scope-json", '{"institution_id":"treasury_tic","concept":"foreign holdings"}',
    ]) == 0
    created = __import__("json").loads(capsys.readouterr().out)
    assert created["review_status"] == "unreviewed"
    assert feedback_cli([
        "--project-root", str(tmp_path), "list", "--task-id", "task-a",
        "--institution-id", "treasury_tic",
    ]) == 0
    listed = __import__("json").loads(capsys.readouterr().out)
    assert len(listed) == 1 and listed[0]["feedback_id"] == created["feedback_id"]
