"""Orchestrator applies only explicitly selected, institution-scoped experience."""
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageResult, StageStatus, TaskStatus
from macro_data_platform.orchestration.models import StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore

AT = datetime(2026, 10, 26, tzinfo=UTC)


class FixtureEngine:
    def __init__(self, stage_id):
        self.stage_id = stage_id
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        if self.stage_id == "search":
            return StageResult(StageStatus.SUCCEEDED,
                               {"source_method": "Official BLS API"}, ("fixture:search",))
        context = request.knowledge_context
        source_method = (context["text"] if context and context["status"] == "confirmed"
                         else request.upstream["source_method"])
        feedback_id = context.get("feedback_id") if context else None
        return StageResult(StageStatus.SUCCEEDED,
                           {"source_method": source_method, "feedback_id": feedback_id},
                           ("fixture:collect",))


def build_plan():
    return TaskPlan((
        StageSpec("search", "search", {"institution_id": "bls"},
                  knowledge_reuse_category="source_method"),
        StageSpec("collect", "collect", {"dataset_id": "cpi"}),
    ))


def test_confirmed_same_institution_method_skips_search_in_repeat_task(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history, clock=lambda: AT)
    knowledge = KnowledgeStore(history, feedback=feedback, clock=lambda: AT)
    search, collect = FixtureEngine("search"), FixtureEngine("collect")
    runner = Orchestrator(history, {("search", "1"): search, ("collect", "1"): collect},
                          clock=lambda: AT)

    first = runner.create("Find BLS CPI source and collect observations")
    runner.plan(first.task_id, build_plan())
    baseline = runner.run(first.task_id)
    assert baseline["status"] == TaskStatus.COMPLETED
    assert len(baseline["stages"]) == 2
    assert collect.calls[0].knowledge_context is None

    record = feedback.record(
        first.task_id, stage_run_id=baseline["stages"][0]["stage_run_id"],
        text="Official BLS API", category="source_method", scope={
            "institution_id": "bls", "dataset_id": "cpi",
        },
    )
    feedback.review(record["feedback_id"], expected_revision=1, status="accepted")
    knowledge.refresh()

    repeat = runner.create("Collect BLS CPI observations again")
    plan_result = runner.plan_with_knowledge(
        repeat.task_id, build_plan(), knowledge,
        institution_id="bls", dataset_id="cpi", category="source_method",
        feedback_id=record["feedback_id"],
    )
    assert plan_result["status"] == "confirmed"
    assert plan_result["skipped_stage_ids"] == ["search"]
    assert plan_result["index_revision"] == 2
    assert plan_result["lookup_metrics"]["candidate_rows_read"] == 1
    assert plan_result["lookup_metrics"]["candidate_logical_bytes_read"] > 0
    planned = history.get(repeat.task_id)
    assert [row["stage_id"] for row in planned["plan"]] == ["collect"]
    assert planned["knowledge_context"]["feedback_id"] == record["feedback_id"]
    assert planned["knowledge_context"]["confirmed_by"] == "explicit_feedback_id_selection"
    assert planned["knowledge_context"]["skipped_stage_ids"] == ["search"]

    result = runner.run(repeat.task_id)
    assert result["status"] == TaskStatus.COMPLETED
    assert len(result["stages"]) == 1
    assert result["stages"][0]["result"]["payload"]["source_method"] == "Official BLS API"
    assert collect.calls[1].knowledge_context["feedback_id"] == record["feedback_id"]
    assert len(search.calls) == 1
    assert len(collect.calls) == 2
    # Same-source repeat uses one execution stage instead of two: 50% fewer stage calls.
    assert len(result["stages"]) == len(baseline["stages"]) - 1
    event_kinds = [event["kind"] for event in history.events(repeat.task_id)]
    assert "KNOWLEDGE_REUSED" in event_kinds

    wrong_institution = runner.create("Collect a Census series")
    with pytest.raises(ValueError, match="feedback_not_in_scope"):
        runner.plan_with_knowledge(
            wrong_institution.task_id, build_plan(), knowledge,
            institution_id="census", dataset_id="cpi", category="source_method",
            feedback_id=record["feedback_id"],
        )
    assert history.get(wrong_institution.task_id)["plan"] is None


def test_knowledge_reuse_blocks_broad_conflicting_inferred_and_unreviewed_items(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history, clock=lambda: AT)
    knowledge = KnowledgeStore(history, feedback=feedback, clock=lambda: AT)
    task = Orchestrator(history, {}, clock=lambda: AT).create("feedback source task")

    broad = feedback.record(task.task_id, text="Use BLS API", category="source_method",
                            scope={"institution_id": "bls"})
    feedback.review(broad["feedback_id"], expected_revision=1, status="accepted")
    assert knowledge.refresh()["status"] == "refreshed"
    assert knowledge.confirm_reuse(
        institution_id="bls", dataset_id="cpi", category="source_method",
        feedback_id=broad["feedback_id"],
    )["status"] == "feedback_scope_too_broad"

    exact = feedback.record(task.task_id, text="Use the CPI endpoint", category="source_method",
                            scope={"institution_id": "bls", "dataset_id": "cpi"})
    feedback.review(exact["feedback_id"], expected_revision=1, status="accepted")
    conflict = feedback.record(task.task_id, text="Use a different CPI endpoint",
                               category="source_method",
                               scope={"institution_id": "bls", "dataset_id": "cpi"})
    feedback.review(conflict["feedback_id"], expected_revision=1, status="accepted")
    inference = feedback.record(task.task_id, text="Maybe use a third endpoint",
                                category="source_method", knowledge_kind="inference",
                                scope={"institution_id": "bls", "dataset_id": "cpi"})
    feedback.review(inference["feedback_id"], expected_revision=1, status="accepted")
    unreviewed = feedback.record(task.task_id, text="Use a fourth endpoint",
                                 category="source_method",
                                 scope={"institution_id": "bls", "dataset_id": "cpi"})
    knowledge.refresh()

    for feedback_id in (exact["feedback_id"], inference["feedback_id"],
                        unreviewed["feedback_id"]):
        outcome = knowledge.confirm_reuse(
            institution_id="bls", dataset_id="cpi", category="source_method",
            feedback_id=feedback_id,
        )
        expected = ("conflict_requires_review" if feedback_id == exact["feedback_id"] else
                    "feedback_not_in_scope")
        assert outcome["status"] == expected


def test_current_instruction_takes_precedence_over_selected_prior_knowledge(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history, clock=lambda: AT)
    knowledge = KnowledgeStore(history, feedback=feedback, clock=lambda: AT)
    engines = {("search", "1"): FixtureEngine("search"),
               ("collect", "1"): FixtureEngine("collect")}
    runner = Orchestrator(history, engines, clock=lambda: AT)
    task = runner.create("Use this task's explicit source request")

    result = runner.plan_with_knowledge(
        task.task_id, build_plan(), knowledge, institution_id="bls", category="source_method",
        feedback_id="stale-or-ignored-id", current_instruction="Use current official source",
    )
    planned = history.get(task.task_id)
    assert result["status"] == "current_instruction"
    assert result["skipped_stage_ids"] == []
    assert [row["stage_id"] for row in planned["plan"]] == ["search", "collect"]
    assert planned["knowledge_context"] == {
        "status": "current_instruction", "text": "Use current official source",
        "feedback_ids": [], "skipped_stage_ids": [],
    }
    completed = runner.run(task.task_id)
    assert completed["status"] == TaskStatus.COMPLETED
    assert engines[("collect", "1")].calls[0].knowledge_context["status"] == "current_instruction"


def test_feedback_change_between_confirmation_and_plan_blocks_stale_reuse(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history, clock=lambda: AT)
    knowledge = KnowledgeStore(history, feedback=feedback, clock=lambda: AT)
    runner = Orchestrator(history, {}, clock=lambda: AT)
    source_task = runner.create("source task")
    record = feedback.record(
        source_task.task_id, text="Use official BLS API", category="source_method",
        scope={"institution_id": "bls", "dataset_id": "cpi"},
    )
    feedback.review(record["feedback_id"], expected_revision=1, status="accepted")
    knowledge.refresh()

    confirm = knowledge.confirm_reuse

    def confirm_then_withdraw(**kwargs):
        outcome = confirm(**kwargs)
        feedback.withdraw(record["feedback_id"], expected_revision=2, reason="Source route retired.")
        return outcome

    knowledge.confirm_reuse = confirm_then_withdraw
    target = runner.create("repeat source task")
    with pytest.raises(ValueError, match="knowledge changed after confirmation"):
        runner.plan_with_knowledge(
            target.task_id, build_plan(), knowledge,
            institution_id="bls", dataset_id="cpi", category="source_method",
            feedback_id=record["feedback_id"],
        )
    assert history.get(target.task_id)["plan"] is None


def test_confirmed_feedback_does_not_skip_unmarked_stages(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    feedback = FeedbackStore(history, clock=lambda: AT)
    knowledge = KnowledgeStore(history, feedback=feedback, clock=lambda: AT)
    runner = Orchestrator(history, {}, clock=lambda: AT)
    source_task = runner.create("source task")
    record = feedback.record(
        source_task.task_id, text="Use official BLS API", category="source_method",
        scope={"institution_id": "bls", "dataset_id": "cpi"},
    )
    feedback.review(record["feedback_id"], expected_revision=1, status="accepted")
    knowledge.refresh()
    target = runner.create("repeat task")
    unmarked_plan = TaskPlan((StageSpec("search", "search"), StageSpec("collect", "collect")))

    with pytest.raises(ValueError, match="no stage enabled"):
        runner.plan_with_knowledge(
            target.task_id, unmarked_plan, knowledge,
            institution_id="bls", dataset_id="cpi", category="source_method",
            feedback_id=record["feedback_id"],
        )
    assert history.get(target.task_id)["plan"] is None
