"""Privacy-bounded bridge from accepted feedback to a local case-authoring seed."""

import json
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.evaluation.cli import main as evaluation_cli
from macro_data_platform.evaluation.feedback_bridge import (
    build_feedback_case_draft,
    write_feedback_case_draft,
)
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore

AT = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
RAW_TEXT = "My private email is alice@example.com. Please show yearly GDP."


def setup_feedback(tmp_path, *, knowledge_kind="user_instruction"):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    task = history.document("test task", AT.isoformat())
    with history.transaction() as connection:
        history.insert(connection, task)
    store = FeedbackStore(history, clock=lambda: AT)
    evidence_refs = ([{"source_url": "https://example.org/source",
                      "source_version": "v1", "captured_at": AT.isoformat()}]
                    if knowledge_kind == "official_evidence" else [])
    feedback = store.record(
        task["task_id"], text=RAW_TEXT, category="output_preference",
        knowledge_kind=knowledge_kind, scope={"institution_id": "worldbank"},
        evidence_refs=evidence_refs,
    )
    return settings, store, feedback


def create_draft(store, feedback, *, privacy_cleared=True, revision=None):
    return build_feedback_case_draft(
        store,
        feedback_id=feedback["feedback_id"],
        expected_revision=feedback["revision"] if revision is None else revision,
        sanitized_question="Show annual GDP values for the requested period.",
        reviewer_id="reviewer-01",
        privacy_cleared=privacy_cleared,
    )


def test_only_accepted_current_user_instruction_can_seed_a_case(tmp_path):
    _settings, store, feedback = setup_feedback(tmp_path)
    with pytest.raises(ValueError, match="only accepted feedback"):
        create_draft(store, feedback)

    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    with pytest.raises(ValueError, match="stale feedback revision"):
        create_draft(store, accepted, revision=1)
    draft = create_draft(store, accepted)
    assert draft["provenance"]["feedback_revision"] == accepted["revision"]
    assert draft["target_split"] == "development"
    assert draft["draft_status"] == "case_authoring_required"
    assert draft["promotion_status"] == "not_promoted"


@pytest.mark.parametrize("knowledge_kind", ["official_evidence", "inference"])
def test_evidence_and_inference_records_cannot_seed_user_cases(tmp_path, knowledge_kind):
    _settings, store, feedback = setup_feedback(tmp_path, knowledge_kind=knowledge_kind)
    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")

    with pytest.raises(ValueError, match="only user-instruction"):
        create_draft(store, accepted)


def test_privacy_clearance_and_safe_reviewer_id_are_required(tmp_path):
    _settings, store, feedback = setup_feedback(tmp_path)
    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    with pytest.raises(ValueError, match="privacy clearance"):
        create_draft(store, accepted, privacy_cleared=False)
    with pytest.raises(ValueError, match="reviewer ID"):
        build_feedback_case_draft(
            store, feedback_id=accepted["feedback_id"],
            expected_revision=accepted["revision"],
            sanitized_question="Show annual GDP.", reviewer_id="reviewer@example.com",
            privacy_cleared=True,
        )


def test_local_seed_contains_only_sanitized_question_and_cannot_overwrite(tmp_path):
    settings, store, feedback = setup_feedback(tmp_path)
    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    draft = create_draft(store, accepted)
    path = write_feedback_case_draft(settings, draft)
    content = path.read_text(encoding="utf-8")

    assert path.parent == settings._inside("data/feedback_case_drafts")
    assert "Show annual GDP values for the requested period." in content
    assert "alice@example.com" not in content
    assert RAW_TEXT not in content
    assert accepted["task_id"] not in content
    assert "worldbank" not in content
    assert "evidence_refs" not in content
    assert json.loads(content)["privacy_review"]["decision"] == "cleared"
    with pytest.raises(FileExistsError):
        write_feedback_case_draft(settings, draft)


def test_seed_writer_rejects_extra_raw_feedback_fields(tmp_path):
    settings, store, feedback = setup_feedback(tmp_path)
    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    draft = create_draft(store, accepted)
    draft["raw_feedback_text"] = RAW_TEXT

    with pytest.raises(ValueError, match="invalid feedback case draft"):
        write_feedback_case_draft(settings, draft)
    assert not (settings._inside("data/feedback_case_drafts") / f"{draft['draft_id']}.json").exists()


def test_feedback_revision_edit_removes_accepted_status_before_bridge(tmp_path):
    _settings, store, feedback = setup_feedback(tmp_path)
    accepted = store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    revised = store.revise(
        accepted["feedback_id"], expected_revision=accepted["revision"],
        changes={"text": "Please show annual GDP."},
    )

    with pytest.raises(ValueError, match="only accepted feedback"):
        create_draft(store, revised)


def test_feedback_draft_cli_requires_explicit_privacy_flag_and_emits_safe_receipt(
        tmp_path, capsys):
    _settings, store, feedback = setup_feedback(tmp_path)
    store.review(feedback["feedback_id"], expected_revision=1, status="accepted")
    args = [
        "feedback-draft", "--project-root", str(tmp_path),
        "--feedback-id", feedback["feedback_id"], "--expected-revision", "2",
        "--sanitized-question", "Show annual GDP values for the requested period.",
        "--reviewer-id", "reviewer-01",
    ]
    with pytest.raises(SystemExit):
        evaluation_cli(args)

    assert evaluation_cli([*args, "--privacy-cleared"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "DRAFT_CREATED"
    assert report["promotion_status"] == "not_promoted"
    assert RAW_TEXT not in json.dumps(report)
    assert "alice@example.com" not in json.dumps(report)
    draft_path = (tmp_path / "data" / "feedback_case_drafts"
                  / f"feedback-{feedback['feedback_id']}-r2.json")
    assert draft_path.is_file()
