"""Bounded knowledge lookup keeps scope, evidence, and explicit-choice boundaries."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore

AT = datetime(2026, 10, 26, tzinfo=UTC)


def setup_stores(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    with history.transaction() as connection:
        for task_id in ("task-a", "task-b", "task-c"):
            document = history.document("explicit test task", AT.isoformat())
            document["task_id"] = task_id
            history.insert(connection, document)
    feedback = FeedbackStore(history, clock=lambda: AT)
    return history, feedback, KnowledgeStore(history, feedback=feedback, clock=lambda: AT)


def accepted(feedback, *, task_id="task-a", text="Use a table.", category="output_preference",
             kind="user_instruction", scope=None, evidence_refs=()):
    item = feedback.record(task_id, text=text, category=category, knowledge_kind=kind,
                          scope=scope or {}, evidence_refs=evidence_refs)
    return feedback.review(item["feedback_id"], expected_revision=1, status="accepted")


def test_lookup_is_institution_and_dataset_scoped_and_uses_explicit_refresh(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    broad = accepted(feedback, text="Ask before choosing output.",
                     scope={"institution_id": "agency_a"})
    dataset = accepted(feedback, text="Dataset-specific instruction.",
                       scope={"institution_id": "agency_a", "dataset_id": "dataset_1"})
    other_institution = accepted(feedback, text="Never cross institutions.",
                                 scope={"institution_id": "agency_b"})

    pending = knowledge.query(institution_id="agency_a")
    assert pending["status"] == "NEEDS_REFRESH"
    assert pending["items"] == []
    assert knowledge.refresh(max_changes=1)["status"] == "partial"
    assert knowledge.query(institution_id="agency_a")["status"] == "NEEDS_REFRESH"
    while knowledge.refresh(max_changes=10)["status"] == "partial":
        pass

    unqualified = knowledge.query(institution_id="agency_a")
    assert {item["feedback_id"] for item in unqualified["items"]} == {broad["feedback_id"]}
    exact = knowledge.query(institution_id="agency_a", dataset_id="dataset_1")
    assert {item["feedback_id"] for item in exact["items"]} == {
        broad["feedback_id"], dataset["feedback_id"]}
    assert next(item for item in exact["items"]
                if item["feedback_id"] == dataset["feedback_id"])["scope_match"] == "exact"
    assert other_institution["feedback_id"] not in {
        item["feedback_id"] for item in knowledge.query(institution_id="agency_a")["items"]}


def test_inference_is_opt_in_and_never_presented_as_a_fact(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    source = accepted(feedback, text="Official guide defines this label.", kind="official_evidence",
                      category="statistical_definition",
                      scope={"institution_id": "agency_a"},
                      evidence_refs=[{"source_url": "https://example.org/guide"}])
    inference = accepted(feedback, text="These series may be comparable.", kind="inference",
                         category="statistical_definition",
                         scope={"institution_id": "agency_a"})
    knowledge.refresh()

    default = knowledge.query(institution_id="agency_a")
    assert [item["feedback_id"] for item in default["items"]] == [source["feedback_id"]]
    assert default["items"][0]["fact_status"] == "reference_only"
    assert default["items"][0]["applicability"] == "reference_only"
    extended = knowledge.query(institution_id="agency_a", include_inference=True)
    inferred = next(item for item in extended["items"]
                    if item["feedback_id"] == inference["feedback_id"])
    assert inferred["fact_status"] == "not_promoted"
    assert inferred["applicability"] == "review_required"


def test_validity_and_version_filtering_and_cache_invalidation(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    valid = accepted(feedback, text="Prefer version 2 output.", category="output_preference",
                     scope={"institution_id": "agency_a", "version": "v2",
                            "valid_from": (AT + timedelta(days=1)).isoformat()})
    knowledge.refresh()
    query = {"institution_id": "agency_a", "version": "v2"}
    assert knowledge.query(**query)["items"] == []
    future = (AT + timedelta(days=2)).isoformat()
    first = knowledge.query(**query, as_of=future)
    assert len(first["items"]) == 1
    cached = knowledge.query(**query, as_of=future)
    assert cached["cache"] == "hit"
    assert cached["candidate_rows_read"] == 0
    assert cached["candidate_logical_bytes_read"] == 0

    updated = feedback.revise(valid["feedback_id"], expected_revision=2,
                              changes={"text": "Prefer the updated version 2 output."})
    assert updated["review_status"] == "unreviewed"
    assert knowledge.query(**query, as_of=future)["status"] == "NEEDS_REFRESH"
    knowledge.refresh()
    assert knowledge.query(**query, as_of=future)["items"] == []

    feedback.review(valid["feedback_id"], expected_revision=3, status="accepted")
    knowledge.refresh()
    lookup = knowledge.query(**query, as_of=future)
    assert len(lookup["items"]) == 1
    assert knowledge.query(**query, as_of=future)["cache"] == "hit"
    feedback.withdraw(valid["feedback_id"], expected_revision=4, reason="No longer wanted.")
    assert knowledge.query(**query, as_of=future)["status"] == "NEEDS_REFRESH"
    knowledge.refresh()
    assert knowledge.query(**query, as_of=future)["items"] == []


def test_conflicts_and_reuse_policy_require_a_person_to_choose(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    first = accepted(feedback, text="Use a table.",
                     scope={"institution_id": "agency_a", "dataset_id": "dataset_1"})
    accepted(feedback, text="Use a chart.",
             scope={"institution_id": "agency_a", "dataset_id": "dataset_1"})
    knowledge.refresh()
    lookup = knowledge.query(institution_id="agency_a", dataset_id="dataset_1")
    assert lookup["conflict_groups"] == 1
    assert all(item["applicability"] == "review_required" for item in lookup["items"])
    decision = knowledge.decide_reuse(lookup, category="output_preference")
    assert decision["status"] == "ask_to_resolve_conflict"
    assert first["feedback_id"] in decision["feedback_ids"]

    current = knowledge.decide_reuse(
        {"status": "NEEDS_REFRESH", "items": []}, category="output_preference",
        current_instruction="Use neither; ask me each time.")
    assert current == {"status": "current_instruction",
                       "value": "Use neither; ask me each time.", "feedback_ids": []}
    assert knowledge.decide_reuse({"status": "ready", "items": []},
                                  category="output_preference")["status"] == "ask_for_output_choice"


def test_unreviewed_records_are_visible_only_on_request_and_are_not_reuse_choices(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    item = feedback.record("task-a", text="Use the compact table.",
                           category="output_preference",
                           scope={"institution_id": "agency_a"})
    knowledge.refresh()
    assert knowledge.query(institution_id="agency_a")["items"] == []
    visible = knowledge.query(institution_id="agency_a", include_unreviewed=True)
    assert visible["items"][0]["feedback_id"] == item["feedback_id"]
    assert visible["items"][0]["applicability"] == "review_required"
    assert knowledge.decide_reuse(visible, category="output_preference")["status"] == "ask_for_output_choice"


def test_refresh_and_query_limits_are_enforced(tmp_path):
    _history, _feedback, knowledge = setup_stores(tmp_path)
    for value in (0, 501, True):
        with pytest.raises(ValueError, match="max_changes"):
            knowledge.refresh(max_changes=value)
    for value in (0, 51, True):
        with pytest.raises(ValueError, match="limit"):
            knowledge.query(institution_id="agency_a", limit=value)
    with pytest.raises(ValueError, match="institution_id"):
        knowledge.query(institution_id="")
    with pytest.raises(ValueError, match="booleans"):
        knowledge.query(institution_id="agency_a", include_inference="yes")
    with pytest.raises(ValueError, match="dataset_id"):
        knowledge.query(institution_id="agency_a", dataset_id=[])


def test_cache_has_entry_and_byte_budgets(tmp_path):
    _history, _feedback, knowledge = setup_stores(tmp_path)
    for day in range(80):
        knowledge.query(institution_id="agency_a", as_of=(AT + timedelta(days=day)).isoformat())
    assert len(knowledge._cache) <= 64
    assert knowledge._cache_bytes <= 1_000_000


def test_request_lookup_does_not_decode_task_history(tmp_path):
    history, feedback, knowledge = setup_stores(tmp_path)
    accepted(feedback, text="Keep this institution-specific.",
             scope={"institution_id": "agency_a"})
    knowledge.refresh()
    with history.transaction() as connection:
        connection.execute("UPDATE tasks SET document='not-json' WHERE task_id='task-a'")
    result = knowledge.query(institution_id="agency_a")
    assert len(result["items"]) == 1


def test_candidate_scan_cap_reports_incomplete_results_and_blocks_reuse(tmp_path):
    history, _feedback, knowledge = setup_stores(tmp_path)
    now = AT.isoformat()
    with history.transaction() as connection:
        for number in range(502):
            feedback_id = str(uuid4())
            document = {
                "feedback_id": feedback_id, "task_id": "task-a",
                "text": f"Preference {number}", "category": "output_preference",
                "knowledge_kind": "user_instruction",
                "scope": {"institution_id": "agency_a", "dataset_id": "dataset_1"},
                "evidence_refs": [], "review_status": "accepted", "revision": 1,
                "updated_at": now,
            }
            connection.execute("INSERT INTO feedback_current VALUES (?, ?, NULL, 1, ?)",
                               (feedback_id, "task-a", json.dumps(document)))
    assert knowledge.refresh(max_changes=500)["pending_changes"] == 2
    knowledge.refresh(max_changes=500)
    result = knowledge.query(institution_id="agency_a", dataset_id="dataset_1",
                             category="output_preference")
    assert result["status"] == "partial"
    assert result["candidate_scan_cap"] == 500
    assert result["candidate_rows_read"] == 501
    assert result["truncated"] is True
    assert len(result["items"]) == 20
    assert knowledge.decide_reuse(result, category="output_preference")["status"] == (
        "lookup_incomplete_requires_review")


def test_result_cap_reports_incomplete_candidates_and_blocks_reuse(tmp_path):
    _history, feedback, knowledge = setup_stores(tmp_path)
    for number in range(21):
        accepted(feedback, text=f"Preference {number}",
                 scope={"institution_id": "agency_a"})
    knowledge.refresh()
    result = knowledge.query(institution_id="agency_a", category="output_preference", limit=20)
    assert result["status"] == "partial"
    assert result["candidate_scan_truncated"] is False
    assert result["result_truncated"] is True
    assert result["candidate_rows_read"] == 21
    assert len(result["items"]) == 20
    assert knowledge.decide_reuse(result, category="output_preference")["status"] == (
        "lookup_incomplete_requires_review")
