"""Offline integration tests: real SQLite and injected deterministic engines."""
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus, TaskStatus
from macro_data_platform.orchestration.models import StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 24, tzinfo=UTC)

    def __call__(self):
        return self.value


class MockEngine:
    def __init__(self, *results):
        self.results = results
        self.calls = []

    def run(self, request):
        result = self.results[min(len(self.calls), len(self.results) - 1)]
        self.calls.append(request)
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return result(request)
        return result


def success(value=None, ref="fixture:e1"):
    return StageResult(StageStatus.SUCCEEDED, value, (ref,))


def retryable():
    return StageResult(StageStatus.FAILED_RETRYABLE, error_code=ErrorCode.TRANSIENT,
                       retry_hint="Retry after operator checks the transient condition.")


@pytest.fixture
def store(tmp_path):
    return HistoryStore(Settings(tmp_path))


def setup_task(store, engines, *, stages=None, clock=None, validator=None):
    runner = Orchestrator(store, engines, clock=clock or Clock(), reuse_validator=validator)
    task = runner.create("fixture request", idempotency_key="request-1")
    specs = stages or tuple(StageSpec(name, name) for name, _ in engines)
    runner.plan(task.task_id, TaskPlan(specs))
    return runner, task.task_id


def test_success_persists_plan_attempts_events_and_inputs_across_reopen(store):
    first = MockEngine(success({"value": None}, "fixture:first"))
    second = MockEngine(success({"value": 0}, "fixture:second"))
    runner, task_id = setup_task(store, {("discover", "1"): first, ("collect", "1"): second})
    result = runner.run(task_id)
    reopened = HistoryStore(store.settings)
    assert reopened.get(task_id) == result
    assert result["status"] == TaskStatus.COMPLETED
    assert len(result["attempts"]) == 1
    assert all(row["finished_at"] is not None for row in result["stages"])
    assert result["stages"][1]["input_refs"] == ["fixture:first"]
    assert result["stages"][1]["input_stage_run_id"] == result["stages"][0]["stage_run_id"]
    assert second.calls[0].upstream == {"value": None}
    assert result["stages"][1]["result"]["payload"] == {"value": 0}
    assert second.calls[0].input_refs == ("fixture:first",)
    events = reopened.events(task_id)
    assert [row["kind"] for row in events] == [
        "TASK_CREATED", "TASK_PLANNED", "TASK_STARTED", "STAGE_STARTED", "STAGE_FINISHED",
        "STAGE_STARTED", "STAGE_FINISHED", "TASK_FINISHED",
    ]
    assert [row["task_status"] for row in events[:3]] == ["CREATED", "PLANNED", "RUNNING"]
    assert events[-1]["task_status"] == "COMPLETED"
    assert len({row["event_id"] for row in events}) == len(events)
    assert all(datetime.fromisoformat(row["at"]).utcoffset() == timedelta(0) for row in events)


def test_idempotent_create_plan_and_completed_run_do_not_duplicate_execution(store):
    engine = MockEngine(success())
    runner, task_id = setup_task(store, {("one", "1"): engine})
    result = runner.run(task_id)
    event_count = len(store.events(task_id))
    assert runner.create("fixture request", idempotency_key="request-1").task_id == task_id
    runner.plan(task_id, TaskPlan((StageSpec("one", "one"),)))
    assert runner.run(task_id) == result
    assert runner.resume(task_id) == result
    assert len(engine.calls) == 1
    assert len(store.events(task_id)) == event_count
    with pytest.raises(ValueError, match="conflicts"):
        runner.create("different request", idempotency_key="request-1")
    assert runner.create("fixture request").task_id != task_id


def test_saved_plan_is_detached_and_cannot_be_replaced(store):
    payload = {"countries": ["JP"]}
    spec = StageSpec("one", "one", payload)
    runner, task_id = setup_task(store, {("one", "1"): MockEngine(success())}, stages=(spec,))
    payload["countries"].append("US")
    assert store.get(task_id)["plan"][0]["input_data"] == {"countries": ["JP"]}
    with pytest.raises(ValueError, match="immutable"):
        runner.plan(task_id, TaskPlan((spec,)))


def test_resume_reuses_valid_prefix_and_only_retries_failed_stage_after_restart(store):
    first = MockEngine(success({"series": "fixture"}))
    second = MockEngine(retryable(), success({"observations": []}))
    engines = {("one", "1"): first, ("two", "1"): second}
    runner, task_id = setup_task(store, engines)
    initial = runner.run(task_id)
    assert initial["status"] == TaskStatus.PARTIAL
    assert initial["stages"][-1]["status"] == StageStatus.FAILED_RETRYABLE
    resumed = Orchestrator(HistoryStore(store.settings), engines, clock=Clock(),
                           reuse_validator=lambda spec, row: row["result"]["evidence_refs"]
                           == ["fixture:e1"])
    result = resumed.resume(task_id)
    assert result["status"] == TaskStatus.COMPLETED
    assert len(first.calls) == 1
    assert len(second.calls) == 2
    assert [row["status"] for row in result["stages"]] == [
        "SUCCEEDED", "FAILED_RETRYABLE", "SKIPPED_REUSED", "SUCCEEDED",
    ]
    assert result["stages"][2]["reused_from"] == initial["stages"][0]["stage_run_id"]
    assert result["stages"][-1]["attempt_no"] == 2
    assert [row["attempt_no"] for row in result["attempts"]] == [1, 2]
    assert store.get(task_id)["stages"][:2] == initial["stages"]


def test_transient_retry_backoff_is_durable_and_enforced_even_with_approval(store):
    clock = Clock()
    engine = MockEngine(
        StageResult(StageStatus.FAILED_RETRYABLE, error_code=ErrorCode.TRANSIENT,
                    retry_after_seconds=2.0),
        success(),
    )
    runner, task_id = setup_task(store, {("one", "1"): engine}, clock=clock)

    first = runner.run(task_id)
    due = datetime.fromisoformat(first["stages"][-1]["result"]["retry_not_before"])
    assert engine.calls[0].attempt_no == 1
    with pytest.raises(ValueError, match="backoff"):
        runner.resume(task_id, approved=True)

    clock.value = due - timedelta(seconds=1)
    with pytest.raises(ValueError, match="backoff"):
        runner.resume(task_id)
    clock.value = due
    final = runner.resume(task_id)

    assert final["status"] == TaskStatus.COMPLETED
    assert engine.calls[1].attempt_no == 2
    assert [row["attempt_no"] for row in final["stages"]] == [1, 2]


@pytest.mark.parametrize("reason", ["missing_validator", "denied", "exception", "expired",
                                         "zero_ttl", "clock_reversed"])
def test_unverified_or_stale_prefix_is_reexecuted(store, reason):
    clock = Clock()
    first = MockEngine(success())
    second = MockEngine(retryable(), success())
    validator = None
    if reason != "missing_validator":
        def validator(spec, row):
            if reason == "exception":
                raise RuntimeError("validator failure")
            return reason != "denied"
    ttl = 0 if reason == "zero_ttl" else 10
    runner, task_id = setup_task(
        store, {("one", "1"): first, ("two", "1"): second}, clock=clock, validator=validator,
        stages=(StageSpec("one", "one", reuse_ttl_seconds=ttl), StageSpec("two", "two")),
    )
    runner.run(task_id)
    if reason == "expired":
        clock.value += timedelta(seconds=10)
    elif reason == "clock_reversed":
        clock.value -= timedelta(seconds=1)
    assert runner.resume(task_id)["status"] == TaskStatus.COMPLETED
    assert len(first.calls) == 2


def test_invalid_upstream_prevents_reusing_downstream_even_if_data_is_identical(store):
    first, second = MockEngine(success()), MockEngine(success())
    third = MockEngine(retryable(), success())
    runner, task_id = setup_task(
        store, {("one", "1"): first, ("two", "1"): second, ("three", "1"): third},
        validator=lambda spec, row: spec.stage_id != "one",
    )
    runner.run(task_id)
    runner.resume(task_id)
    assert len(first.calls) == 2
    assert len(second.calls) == 2


def test_reuse_does_not_extend_original_freshness_window(store):
    clock = Clock()
    first, second = MockEngine(success()), MockEngine(retryable(), retryable(), success())
    runner, task_id = setup_task(
        store, {("one", "1"): first, ("two", "1"): second}, clock=clock,
        validator=lambda spec, row: True,
        stages=(StageSpec("one", "one", reuse_ttl_seconds=10), StageSpec("two", "two")),
    )
    runner.run(task_id)
    clock.value += timedelta(seconds=9)
    runner.resume(task_id)
    assert len(first.calls) == 1
    clock.value += timedelta(seconds=2)
    runner.resume(task_id)
    assert len(first.calls) == 2


def test_review_stops_downstream_until_explicit_acknowledgement(store):
    first = MockEngine(StageResult(StageStatus.NEEDS_REVIEW,
                                  error_code=ErrorCode.SEMANTIC_AMBIGUITY), success())
    second = MockEngine(success())
    runner, task_id = setup_task(store, {("one", "1"): first, ("two", "1"): second})
    assert runner.run(task_id)["status"] == TaskStatus.NEEDS_REVIEW
    assert not second.calls
    with pytest.raises(ValueError, match="acknowledgement"):
        runner.resume(task_id)
    runner.cancel(task_id)
    with pytest.raises(ValueError, match="acknowledgement"):
        runner.resume(task_id)
    assert runner.resume(task_id, approved=True)["status"] == TaskStatus.COMPLETED


@pytest.mark.parametrize("error", [ErrorCode.AUTH_ACCESS, ErrorCode.LICENSE_SECURITY])
def test_access_errors_cannot_be_marked_as_automatic_retry_by_engine(store, error):
    engine = MockEngine(StageResult(StageStatus.FAILED_RETRYABLE, error_code=error), success())
    runner, task_id = setup_task(store, {("one", "1"): engine})
    result = runner.run(task_id)
    assert result["status"] == TaskStatus.NEEDS_REVIEW
    assert result["stages"][-1]["result"]["error_code"] == error
    with pytest.raises(ValueError, match="acknowledgement"):
        runner.resume(task_id)
    assert len(engine.calls) == 1


def test_pending_cancellation_is_preserved_during_interrupt_recovery(store):
    def cancel_then_interrupt(request):
        runner.cancel(request.task_id)
        raise KeyboardInterrupt
    runner, task_id = setup_task(store, {("one", "1"): MockEngine(cancel_then_interrupt)})
    with pytest.raises(KeyboardInterrupt):
        runner.run(task_id)
    runner.recover_interrupted(task_id)
    assert store.get(task_id)["status"] == TaskStatus.CANCELLED


def test_plan_cannot_be_added_after_unplanned_task_is_cancelled(store):
    runner = Orchestrator(store, {})
    task = runner.create("request")
    runner.cancel(task.task_id)
    with pytest.raises(ValueError, match="only a created"):
        runner.plan(task.task_id, TaskPlan((StageSpec("one", "one"),)))


def test_resume_uses_saved_plan_engine_version(store):
    engine = MockEngine(retryable())
    runner, task_id = setup_task(store, {("one", "1"): engine})
    runner.run(task_id)
    updated = Orchestrator(store, {("one", "2"): MockEngine(success())})
    with pytest.raises(ValueError, match="unregistered engine version"):
        updated.resume(task_id)
    assert len(engine.calls) == 1


def test_mutating_validator_cannot_change_saved_result_or_input_identity(store):
    def validator(spec, row):
        row["result"]["payload"]["value"] = 100
        return True
    first = MockEngine(success({"value": 0}))
    second = MockEngine(retryable(), success())
    runner, task_id = setup_task(store, {("one", "1"): first, ("two", "1"): second},
                                 validator=validator)
    runner.run(task_id)
    result = runner.resume(task_id)
    assert result["stages"][0]["result"]["payload"] == {"value": 0}
    assert second.calls[-1].upstream == {"value": 0}


def test_validator_cannot_mutate_input_when_reuse_is_denied(store):
    def validator(spec, row):
        spec.input_data["value"] = 100
        return False
    first = MockEngine(success())
    second = MockEngine(retryable(), success())
    runner, task_id = setup_task(
        store, {("one", "1"): first, ("two", "1"): second}, validator=validator,
        stages=(StageSpec("one", "one", {"value": 0}), StageSpec("two", "two")),
    )
    runner.run(task_id)
    runner.resume(task_id)
    assert first.calls[-1].input_data == {"value": 0}


def test_terminal_failure_cannot_be_bypassed_via_cancel_or_approval(store):
    engine = MockEngine(StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.AUTH_ACCESS))
    runner, task_id = setup_task(store, {("one", "1"): engine})
    assert runner.run(task_id)["status"] == TaskStatus.FAILED
    with pytest.raises(ValueError, match="terminal"):
        runner.resume(task_id, approved=True)
    runner.cancel(task_id)
    with pytest.raises(ValueError, match="terminal"):
        runner.resume(task_id, approved=True)
    assert len(engine.calls) == 1


def test_retry_budget_is_total_invocations_and_cannot_be_reset_by_approval(store):
    engine = MockEngine(retryable())
    runner, task_id = setup_task(store, {("one", "1"): engine},
                                 stages=(StageSpec("one", "one", max_attempts=2),))
    runner.run(task_id)
    runner.resume(task_id)
    assert runner.resume(task_id)["status"] == TaskStatus.NEEDS_REVIEW
    assert runner.resume(task_id, approved=True)["status"] == TaskStatus.NEEDS_REVIEW
    assert len(engine.calls) == 2
    assert "RETRY_LIMIT_REACHED" in [row["kind"] for row in store.events(task_id)]


def test_cancel_before_run_and_repeated_cancel_are_idempotent(store):
    engine = MockEngine(success())
    runner, task_id = setup_task(store, {("one", "1"): engine})
    runner.cancel(task_id)
    before = store.events(task_id)
    runner.cancel(task_id)
    assert store.events(task_id) == before
    with pytest.raises(ValueError, match="resume"):
        runner.run(task_id)
    assert not engine.calls
    assert runner.resume(task_id)["status"] == TaskStatus.COMPLETED
    runner.cancel(task_id)
    assert store.get(task_id)["status"] == TaskStatus.COMPLETED


def test_cancel_during_engine_preserves_result_and_stops_at_stage_boundary(store):
    def cancel_and_complete(request):
        # Separate connection can update cancellation: engine runs outside DB transaction.
        other = Orchestrator(HistoryStore(store.settings), {})
        other.cancel(request.task_id)
        return success({"retained": True})
    first, second = MockEngine(cancel_and_complete), MockEngine(success())
    runner, task_id = setup_task(store, {("one", "1"): first, ("two", "1"): second},
                                 validator=lambda spec, row: True)
    result = runner.run(task_id)
    assert result["status"] == TaskStatus.CANCELLED
    assert result["stages"][-1]["result"]["payload"] == {"retained": True}
    assert not second.calls
    assert runner.resume(task_id)["status"] == TaskStatus.COMPLETED
    assert len(first.calls) == 1


def test_interrupt_requires_explicit_recovery_and_preserves_failed_attempt(store):
    engine = MockEngine(KeyboardInterrupt(), success())
    runner, task_id = setup_task(store, {("one", "1"): engine})
    with pytest.raises(KeyboardInterrupt):
        runner.run(task_id)
    running = store.get(task_id)
    assert running["status"] == TaskStatus.RUNNING
    assert running["stages"][-1]["status"] == StageStatus.RUNNING
    with pytest.raises(ValueError, match="already running"):
        runner.resume(task_id)
    runner.recover_interrupted(task_id)
    recovered = store.get(task_id)
    assert recovered["status"] == TaskStatus.FAILED
    assert recovered["stages"][-1]["status"] == StageStatus.FAILED_RETRYABLE
    assert recovered["stages"][-1]["finished_at"] is not None
    assert runner.resume(task_id)["status"] == TaskStatus.COMPLETED
    assert len(store.get(task_id)["attempts"]) == 2


def test_stale_worker_cannot_commit_after_explicit_recovery(store):
    def recover_before_return(request):
        runner.recover_interrupted(request.task_id)
        return success({"stale": True})
    runner, task_id = setup_task(store, {("one", "1"): MockEngine(recover_before_return)})
    with pytest.raises(ValueError, match="ownership changed"):
        runner.run(task_id)
    result = store.get(task_id)
    assert result["status"] == TaskStatus.FAILED
    assert result["stages"][-1]["result"]["payload"] is None


def test_another_worker_cannot_execute_running_task(store):
    def try_duplicate(request):
        other = Orchestrator(HistoryStore(store.settings), {("one", "1"): engine})
        with pytest.raises(ValueError, match="already running"):
            other.run(request.task_id)
        assert store.get(request.task_id)["stages"][-1]["status"] == StageStatus.RUNNING
        return success()
    engine = MockEngine(try_duplicate)
    runner, task_id = setup_task(store, {("one", "1"): engine})
    assert runner.run(task_id)["status"] == TaskStatus.COMPLETED
    assert len(engine.calls) == 1


@pytest.mark.parametrize("bad_result", [RuntimeError("pretend-private-value"), None,
                                        StageResult(StageStatus.RUNNING),
                                        StageResult(StageStatus.SKIPPED_REUSED),
                                        success({"value": math.nan}), success(object())])
def test_engine_exceptions_and_invalid_results_fail_safely_without_details(store, bad_result):
    runner, task_id = setup_task(store, {("one", "1"): MockEngine(bad_result)})
    result = runner.run(task_id)
    assert result["status"] == TaskStatus.FAILED
    assert result["stages"][-1]["result"]["error_code"] == ErrorCode.INTERNAL_BUG
    assert "pretend-private-value" not in str(store.get(task_id)) + str(store.events(task_id))


def test_invalid_transitions_missing_engine_unknown_ids_and_schema_are_rejected(store):
    runner = Orchestrator(store, {})
    task = runner.create("request")
    with pytest.raises(ValueError, match="requires a plan"):
        runner.run(task.task_id)
    with pytest.raises(KeyError):
        runner.run("missing")
    with pytest.raises(KeyError):
        store.events("missing")
    with pytest.raises(ValueError, match="no interrupted"):
        runner.recover_interrupted(task.task_id)
    runner.plan(task.task_id, TaskPlan((StageSpec("one", "one"),)))
    with pytest.raises(ValueError, match="unregistered"):
        runner.run(task.task_id)
    assert store.get(task.task_id)["status"] == TaskStatus.PLANNED
    assert not store.get(task.task_id)["attempts"]
    with store.transaction() as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="schema version"):
        HistoryStore(store.settings)


def test_atomic_create_rolls_back_document_when_event_write_fails(store, monkeypatch):
    def fail_event(*args, **kwargs):
        raise RuntimeError("simulated storage failure")
    monkeypatch.setattr(store, "event", fail_event)
    with pytest.raises(RuntimeError):
        Orchestrator(store, {}).create("request")
    with store.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM task_events").fetchone()[0] == 0


def test_stage_result_and_its_event_roll_back_together_on_storage_failure(store, monkeypatch):
    runner, task_id = setup_task(store, {("one", "1"): MockEngine(success())})
    original = store.event

    def fail_completion(connection, task_id, body):
        if body["kind"] == "STAGE_FINISHED":
            raise RuntimeError("simulated commit failure")
        original(connection, task_id, body)
    monkeypatch.setattr(store, "event", fail_completion)
    with pytest.raises(RuntimeError, match="commit failure"):
        runner.run(task_id)
    result = store.get(task_id)
    assert result["status"] == TaskStatus.RUNNING
    assert result["stages"][-1]["status"] == StageStatus.RUNNING
    assert result["stages"][-1]["result"] is None
    assert store.events(task_id)[-1]["kind"] == "STAGE_STARTED"


def test_task_completion_failure_preserves_committed_stage_for_recovery(store, monkeypatch):
    engine = MockEngine(success())
    runner, task_id = setup_task(store, {("one", "1"): engine},
                                 validator=lambda spec, row: True)
    original = store.event

    def fail_task_completion(connection, task_id, body):
        if body["kind"] == "TASK_FINISHED":
            raise RuntimeError("simulated task completion failure")
        original(connection, task_id, body)
    monkeypatch.setattr(store, "event", fail_task_completion)
    with pytest.raises(RuntimeError, match="completion failure"):
        runner.run(task_id)
    result = store.get(task_id)
    assert result["status"] == TaskStatus.RUNNING
    assert result["stages"][-1]["status"] == StageStatus.SUCCEEDED
    assert store.events(task_id)[-1]["kind"] == "STAGE_FINISHED"
    monkeypatch.setattr(store, "event", original)
    runner.recover_interrupted(task_id)
    assert runner.resume(task_id)["status"] == TaskStatus.COMPLETED
    assert len(engine.calls) == 1


def test_concurrent_idempotent_requests_share_one_task(store):
    def create(_):
        return Orchestrator(store, {}).create("request", idempotency_key="same").task_id
    with ThreadPoolExecutor(max_workers=4) as workers:
        ids = list(workers.map(create, range(4)))
    assert len(set(ids)) == 1
    assert len(store.events(ids[0])) == 1


@pytest.mark.parametrize("kwargs", [{"stage_id": ""}, {"max_attempts": 0},
                                     {"max_attempts": True}, {"max_attempts": 11},
                                     {"reuse_ttl_seconds": -1}])
def test_invalid_stage_specs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        StageSpec(**{"stage_id": "one", "engine": "mock", **kwargs})


def test_empty_and_duplicate_plans_are_rejected():
    with pytest.raises(ValueError):
        TaskPlan(())
    with pytest.raises(ValueError):
        TaskPlan((StageSpec("one", "mock"), StageSpec("one", "other")))


def test_invalid_request_never_creates_history(store):
    runner = Orchestrator(store, {})
    with pytest.raises(ValueError):
        runner.create(" ")
    with pytest.raises(ValueError):
        runner.create("valid", idempotency_key=" ")
