"""Alignment 02: offline SQLite/service integration with declared fixture metadata."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta

import pytest
from test_orchestration import Clock, MockEngine, retryable, success
from test_workflow_contracts import candidate, data_request, proposal
from test_workflow_extensions import data_link, grouped, offer, selected

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan, WorkflowService
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_contracts import DataRequest, OutputSpec
from macro_data_platform.workflow_extensions import DeliverySpec, VariantAttributes


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import requests

    def no_network(*args, **kwargs):
        pytest.fail("workflow service must not access HTTP")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    store = HistoryStore(Settings(tmp_path))
    clock = Clock()
    return store, clock, WorkflowService(store, clock=clock)


def start(service, mode="file", **overrides):
    chosen = selected(mode)
    settings = {"candidate_id": "c1", "delivery": chosen.delivery,
                "links": chosen.offer.links, "confirmation_method": "explicit_request"}
    settings.update(overrides)
    return service.begin(chosen.offer.request, chosen.offer.proposal, **settings)


def work(service, doc, **kwargs):
    return service.create_work(doc["task_id"],
                               expected_revision=doc["workflow_request"]["revision"], **kwargs)


def plan(runner, child, *stages):
    runner.plan(child["task_id"], TaskPlan(stages or (StageSpec("collect", "collect"),)))


def test_missing_fields_batched_no_auto_selection_or_prior_output(setup):
    store, clock, service = setup
    start(service)  # Previous explicit output is never a preference default.
    doc = service.begin(DataRequest("r1", "GDP"), grouped(second=True))
    state = doc["workflow_request"]
    fields = [q["field"] for q in state["questions"]]
    assert len(fields) == len(set(fields))
    assert set(fields) == {"candidate_id", "concept", "countries", "dimensions", "period_start",
                           "period_end", "frequency", "unit_policy", "vintage_requirement",
                           "delivery.mode"}
    assert state["questions"][0]["choices"] == ["c1", "c2"]
    assert state["state"] == "NEEDS_INPUT"
    with pytest.raises(ValueError, match="confirmation required"):
        work(service, doc)
    runner = Orchestrator(store, {}, clock=clock)
    with pytest.raises(ValueError, match="containers cannot execute"):
        runner.plan(doc["task_id"], TaskPlan((StageSpec("x", "x"),)))
    with pytest.raises(ValueError, match="containers cannot execute"):
        runner.resume(doc["task_id"], approved=True)
    assert store.get(doc["task_id"])["attempts"] == []
    assert not list(store.settings.project_root.glob("data/raw/**/*"))


@pytest.mark.parametrize("mode", ["file", "link", "both"])
def test_explicit_complete_request_confirmed_once_and_child_has_exact_context(setup, mode):
    store, clock, service = setup
    doc = start(service, mode)
    state = doc["workflow_request"]
    assert state["state"] == "CONFIRMED" and state["questions"] == []
    child = work(service, doc)
    assert child["task_id"] != doc["task_id"]
    assert child["plan"] is None and child["stages"] == []
    assert child["workflow_context"]["confirmation"] == state["confirmation"]
    assert child["workflow_context"]["intent"] == {
        "file": "collect", "link": "deliver_link", "both": "collect_and_link"}[mode]
    assert work(service, doc) == child
    count = len(store.events(doc["task_id"]))
    clock.value += timedelta(minutes=1)
    again = service.confirm(doc["task_id"], expected_revision=1, confirmation_method="followup")
    assert again["workflow_request"]["revision"] == 1
    assert again["workflow_request"]["confirmation"] == state["confirmation"]
    assert work(service, again) == child
    assert len(store.events(doc["task_id"])) == count


def test_ready_requires_explicit_confirmation_no_approved_boolean(setup):
    _, _, service = setup
    doc = start(service, confirmation_method=None)
    assert doc["workflow_request"]["state"] == "READY"
    with pytest.raises(ValueError, match="confirmation required"):
        work(service, doc)
    with pytest.raises(ValueError, match="confirmation method"):
        service.confirm(doc["task_id"], expected_revision=1, confirmation_method=True)
    confirmed = service.confirm(doc["task_id"], expected_revision=1,
                                confirmation_method="followup")
    assert confirmed["workflow_request"]["revision"] == 2
    assert work(service, confirmed)["status"] == "CREATED"


@pytest.mark.parametrize("status", ["available", "unavailable", "unknown", "blocked"])
def test_output_choices_and_link_status_manual_filter_disclosures(setup, status):
    _, _, service = setup
    changes = {"status": status, "manual_filter_required": True,
               "restrictions": ("Select the requested years on the source page.",)}
    if status != "available":
        changes.update(url=None, kind=None, reason="Declared fixture restriction")
    link = data_link(**changes)
    doc = start(service, delivery=DeliverySpec(), links=(link,), confirmation_method=None)
    state = doc["workflow_request"]
    expected = ["file", "link", "both"] if status == "available" else ["file"]
    assert state["available_modes"] == expected
    assert state["questions"] == [{"field": "delivery.mode", "kind": "input",
                                    "choices": expected}]
    assert state["link_statuses"][0]["status"] == status
    assert state["link_statuses"][0]["manual_filter_required"] is True
    assert state["link_statuses"][0]["restrictions"]


@pytest.mark.parametrize("mode", ["link", "both"])
def test_expired_link_never_falls_back_or_runs_collector(setup, mode):
    store, clock, service = setup
    doc = start(service, mode)
    child = work(service, doc)
    engine = MockEngine(success())
    runner = Orchestrator(store, {("collect", "1"): engine}, clock=clock)
    if mode == "both":
        plan(runner, child)
    else:
        with pytest.raises(ValueError, match="link-only"):
            plan(runner, child)
    clock.value += timedelta(hours=1)
    with pytest.raises(ValueError, match="unavailable"):
        runner.run(child["task_id"])
    with pytest.raises(ValueError, match="unavailable"):
        work(service, doc)
    revised = service.revise(doc["task_id"], expected_revision=1)
    assert revised["workflow_request"]["state"] == "NEEDS_REVIEW"
    assert revised["workflow_request"]["draft"]["delivery"]["mode"] == mode
    assert revised["workflow_request"]["confirmation"] is None
    assert revised["workflow_request"]["available_modes"] == ["file"]
    assert engine.calls == []


@pytest.mark.parametrize("change", ["period", "definition", "variant"])
def test_changes_invalidate_confirmation_cancel_work_and_require_new_work(setup, change):
    store, clock, service = setup
    doc = start(service, links=())
    child = work(service, doc, idempotency_key="child")
    engine = MockEngine(success())
    runner = Orchestrator(store, {("collect", "1"): engine}, clock=clock)
    plan(runner, child)
    changes = ({"request": data_request(period_end="2021")} if change == "period" else
               {"proposal": grouped(original=proposal(candidates=(candidate(
                   definition="A revised fixture definition"),)))} if change == "definition" else
               {"requirements": VariantAttributes(seasonal_adjustment="unadjusted")})
    revised = service.revise(doc["task_id"], expected_revision=1, **changes)
    assert revised["workflow_request"]["confirmation"] is None
    assert store.get(child["task_id"])["status"] == "CANCELLED"
    for operation in (runner.run, lambda task_id: runner.resume(task_id, approved=True)):
        with pytest.raises(ValueError, match="invalidated"):
            operation(child["task_id"])
    assert engine.calls == []
    with pytest.raises(ValueError, match="stale"):
        service.confirm(doc["task_id"], expected_revision=1, confirmation_method="followup")
    if change != "variant":
        confirmed = service.confirm(doc["task_id"], expected_revision=2,
                                    confirmation_method="followup")
        with pytest.raises(ValueError, match="conflicts"):
            work(service, confirmed, idempotency_key="child")
        assert work(service, confirmed)["task_id"] != child["task_id"]
    else:
        assert revised["workflow_request"]["state"] == "NEEDS_REVIEW"


def test_stale_link_binding_reported_without_silent_drop(setup):
    _, _, service = setup
    doc = start(service)
    revised = service.revise(doc["task_id"], expected_revision=1,
                             request=data_request(period_end="2021"),
                             confirmation_method="followup")
    state = revised["workflow_request"]
    assert any(q["field"] == "links_context" for q in state["questions"])
    assert state["draft"]["links"] == doc["workflow_request"]["draft"]["links"]
    assert state["confirmation"] is None


@pytest.mark.parametrize("mode", ["file", "both"])
def test_mock_child_executes_and_retry_preserves_workflow_context(setup, mode):
    store, clock, service = setup
    doc = start(service, mode)
    child = work(service, doc)
    engine = MockEngine(retryable(), success({"observation": None}))
    runner = Orchestrator(store, {("collect", "1"): engine}, clock=clock)
    plan(runner, child)
    assert runner.run(child["task_id"])["status"] == "FAILED"
    reopened = HistoryStore(store.settings)
    runner = Orchestrator(reopened, {("collect", "1"): engine}, clock=clock)
    result = runner.resume(child["task_id"])
    assert result["status"] == "COMPLETED" and len(result["attempts"]) == 2
    assert result["workflow_context"] == child["workflow_context"]
    assert result["stages"][-1]["result"]["payload"]["observation"] is None


def test_revision_during_running_stage_preserves_result_then_cancels(setup):
    store, clock, service = setup
    doc = start(service, links=())
    child = work(service, doc)

    def change_during_run(_):
        service.revise(doc["task_id"], expected_revision=1,
                       request=data_request(period_end="2021"))
        return success({"old_period": "preserved"})

    first, second = MockEngine(change_during_run), MockEngine(success())
    runner = Orchestrator(store, {("one", "1"): first, ("two", "1"): second}, clock=clock)
    plan(runner, child, StageSpec("one", "one"), StageSpec("two", "two"))
    result = runner.run(child["task_id"])
    assert result["status"] == "CANCELLED"
    assert result["stages"][0]["result"]["payload"] == {"old_period": "preserved"}
    assert second.calls == []


def test_link_expiry_between_stages_stops_with_review(setup):
    store, clock, service = setup
    doc = start(service, "both")
    child = work(service, doc)

    def expire(_):
        clock.value += timedelta(hours=1)
        return success()

    first, second = MockEngine(expire), MockEngine(success())
    runner = Orchestrator(store, {("one", "1"): first, ("two", "1"): second}, clock=clock)
    plan(runner, child, StageSpec("one", "one"), StageSpec("two", "two"))
    result = runner.run(child["task_id"])
    assert result["status"] == "NEEDS_REVIEW" and result["active_token"] is None
    assert second.calls == []
    with pytest.raises(ValueError, match="unavailable"):
        runner.resume(child["task_id"], approved=True)


def test_source_task_immutable_and_all_workflow_states_survive_reopen(setup):
    store, clock, service = setup
    runner = Orchestrator(store, {("discover", "1"): MockEngine(success())}, clock=clock)
    source = runner.create("original discovery")
    runner.plan(source.task_id, TaskPlan((StageSpec("discover", "discover"),)))
    original = runner.run(source.task_id)
    events = store.events(source.task_id)
    doc = start(service, confirmation_method=None, source_task_id=source.task_id)
    reopened = WorkflowService(HistoryStore(store.settings), clock=clock)
    assert reopened.get(doc["task_id"]) == doc
    doc = reopened.confirm(doc["task_id"], expected_revision=1, confirmation_method="followup")
    assert service.get(doc["task_id"]) == doc
    child = work(reopened, doc)
    assert service.get(doc["task_id"])["workflow_request"]["work_task_id"] == child["task_id"]
    assert child["workflow_context"]["source_task_id"] == source.task_id
    assert store.get(source.task_id) == original and store.events(source.task_id) == events
    pending = service.begin(DataRequest("r1", "GDP"), grouped())
    assert reopened.get(pending["task_id"]) == pending


def test_idempotency_conflicts_cross_context_and_legacy_namespaces(setup):
    store, clock, service = setup
    doc = start(service, idempotency_key="request")
    assert start(service, idempotency_key="request") == doc
    with pytest.raises(ValueError, match="conflicts"):
        start(service, "both", idempotency_key="request")
    runner = Orchestrator(store, {}, clock=clock)
    with pytest.raises(ValueError, match="conflicts"):
        runner.create(doc["request"], idempotency_key="request")
    runner.create("GDP data", idempotency_key="legacy")
    with pytest.raises(ValueError, match="conflicts"):
        start(service, idempotency_key="legacy")
    child = work(service, doc, idempotency_key="work")
    assert work(service, doc, idempotency_key="work") == child
    with pytest.raises(ValueError, match="another idempotency key"):
        work(service, doc, idempotency_key="different")


def test_concurrent_same_confirmation_creates_one_child(setup):
    store, _, service = setup
    doc = start(service)
    with ThreadPoolExecutor(max_workers=4) as executor:
        children = list(executor.map(lambda _: work(service, doc), range(8)))
    assert len({child["task_id"] for child in children}) == 1
    assert len([e for e in store.events(doc["task_id"])
                if e["kind"] == "WORKFLOW_WORK_LINKED"]) == 1


@pytest.mark.parametrize("failure_event", ["TASK_CREATED", "WORKFLOW_WORK_LINKED"])
def test_child_and_context_and_events_rollback_together(setup, monkeypatch, failure_event):
    store, _, service = setup
    doc = start(service)
    original_event = store.event
    events = store.events(doc["task_id"])

    def fail(connection, task_id, body):
        original_event(connection, task_id, body)
        if body["kind"] == failure_event:
            raise RuntimeError("injected transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "event", fail)
        with pytest.raises(RuntimeError, match="injected"):
            work(service, doc)
    assert store.get(doc["task_id"]) == doc
    assert store.events(doc["task_id"]) == events
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1
    assert work(service, doc)["task_id"]


def test_revision_rollback_restores_original_confirmation_and_child(setup, monkeypatch):
    store, _, service = setup
    doc = start(service, links=())
    child = work(service, doc)
    original = service.get(doc["task_id"])
    original_event = store.event

    def fail(connection, task_id, body):
        original_event(connection, task_id, body)
        if body["kind"] == "WORKFLOW_REVISED":
            raise RuntimeError("injected revision failure")

    monkeypatch.setattr(store, "event", fail)
    with pytest.raises(RuntimeError):
        service.revise(doc["task_id"], expected_revision=1,
                       request=data_request(period_end="2021"))
    assert service.get(doc["task_id"]) == original
    assert store.get(child["task_id"]) == child
    assert len(store.events(child["task_id"])) == 1


def test_workflow_hash_extends_legacy_without_changing_original_algorithm(setup):
    store, clock, service = setup
    spec = StageSpec("collect", "collect")
    runner = Orchestrator(store, {}, clock=clock)
    legacy = store.get(runner.create("GDP data").task_id)
    stage = asdict(spec)
    stage.pop("knowledge_reuse_category")
    expected = hashlib.sha256(json.dumps({"request": "GDP data", "stage": stage,
                                         "upstream": None}, sort_keys=True,
                                        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert runner._fingerprint(legacy, spec, None) == expected
    first = work(service, start(service, links=()))
    second = work(service, start(service, "both"))
    assert len({runner._fingerprint(item, spec, None)
                for item in (legacy, first, second)}) == 3
    assert "workflow_context" not in legacy and "workflow_request" not in legacy
    with store._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


@pytest.mark.parametrize("changes", [
    {"delivery": DeliverySpec("file")},
    {"delivery": DeliverySpec("file", OutputSpec("xlsx", "data/export"))},
    {"delivery": DeliverySpec("link")},
    {"delivery": DeliverySpec("link", link_ids=("unknown",))},
    {"requirements": VariantAttributes(seasonal_adjustment="unadjusted")},
])
def test_invalid_or_incomplete_conditions_are_questions_never_work(setup, changes):
    _, _, service = setup
    doc = start(service, **changes)
    assert doc["workflow_request"]["questions"]
    assert doc["workflow_request"]["confirmation"] is None
    with pytest.raises(ValueError, match="confirmation required"):
        work(service, doc)


def test_no_collector_support_still_allows_link_only(setup):
    _, _, service = setup
    suggested = grouped(original=proposal(candidates=(candidate(support_status="unsupported",
                                                               supported_outputs=()),)))
    offered = offer(suggested=suggested)
    doc = service.begin(offered.request, offered.proposal, candidate_id="c1", links=offered.links,
                        delivery=selected("link").delivery, confirmation_method="explicit_request")
    assert doc["workflow_request"]["available_modes"] == ["link"]
    assert work(service, doc)["workflow_context"]["intent"] == "deliver_link"


def test_cancelled_source_container_cannot_create_or_resume_work(setup):
    store, clock, service = setup
    doc = start(service)
    child = work(service, doc)
    runner = Orchestrator(store, {}, clock=clock)
    runner.cancel(doc["task_id"])
    with pytest.raises(ValueError, match="cancelled"):
        work(service, doc)
    with pytest.raises(ValueError, match="cancelled"):
        runner.resume(child["task_id"], approved=True)


def test_existing_error_codes_preserved_for_workflow_child(setup):
    store, clock, service = setup
    child = work(service, start(service))
    engine = MockEngine(StageResult(StageStatus.FAILED_RETRYABLE, error_code=ErrorCode.AUTH_ACCESS))
    runner = Orchestrator(store, {("collect", "1"): engine}, clock=clock)
    plan(runner, child)
    result = runner.run(child["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert result["stages"][0]["result"]["error_code"] == "AUTH_ACCESS"


def test_snapshot_budget_and_detached_reads(setup):
    store, _, service = setup
    doc = start(service)
    read = service.get(doc["task_id"])
    read["workflow_request"]["draft"]["candidate_id"] = "unrelated"
    assert service.get(doc["task_id"]) == doc
    with pytest.raises(ValueError, match="budget"):
        service.begin(replace(data_request(), text="x" * 262145), grouped())
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1


def test_unused_expired_link_does_not_invalidate_file_only_confirmation(setup):
    store, clock, service = setup
    doc = start(service)
    child = work(service, doc)
    clock.value += timedelta(hours=1)
    refreshed = service.revise(doc["task_id"], expected_revision=1)
    state = refreshed["workflow_request"]
    assert state["revision"] == 1 and state["state"] == "WORK_CREATED"
    assert state["work_task_id"] == child["task_id"]
    assert state["confirmation"] == doc["workflow_request"]["confirmation"]
    assert state["link_statuses"][0]["usable"] is False
    assert work(service, refreshed) == child
    runner = Orchestrator(store, {("collect", "1"): MockEngine(success())}, clock=clock)
    plan(runner, child)
    assert runner.run(child["task_id"])["status"] == "COMPLETED"


def test_completed_result_immutable_but_new_conditions_cannot_reuse_it(setup):
    store, clock, service = setup
    doc = start(service, links=())
    child = work(service, doc)
    engine = MockEngine(success({"value": 0}))
    runner = Orchestrator(store, {("collect", "1"): engine}, clock=clock,
                          reuse_validator=lambda *_: True)
    plan(runner, child)
    result = runner.run(child["task_id"])
    events = store.events(child["task_id"])
    updated = service.revise(doc["task_id"], expected_revision=1,
                             request=data_request(period_start="2021"),
                             confirmation_method="explicit_request")
    assert store.get(child["task_id"]) == result
    assert store.events(child["task_id"]) == events
    with pytest.raises(ValueError, match="invalidated"):
        runner.run(child["task_id"])
    new_child = work(service, updated)
    plan(runner, new_child)
    new_result = runner.run(new_child["task_id"])
    assert len(engine.calls) == 2
    assert new_result["stages"][0]["status"] == "SUCCEEDED"
    assert result["stages"][0]["fingerprint"] != new_result["stages"][0]["fingerprint"]


def test_missing_metadata_is_review_not_a_user_guess_or_label_equivalence(setup):
    _, _, service = setup
    suggested = grouped(original=proposal(candidates=(candidate(
        definition=None, dimensions=None, available_start=None, available_end=None,
        series_key={}, evidence=(), verification_status="unknown"),)))
    doc = service.begin(data_request(), suggested, candidate_id="c1",
                        delivery=DeliverySpec(), confirmation_method="explicit_request")
    state = doc["workflow_request"]
    assert state["state"] == "NEEDS_REVIEW" and state["confirmation"] is None
    assert {q["field"] for q in state["questions"] if q["kind"] == "review"} == {
        "candidate.definition", "candidate.dimensions", "candidate.available_start",
        "candidate.available_end", "candidate.identifier", "candidate.evidence",
        "candidate.verification_status"}


def test_confirmed_group_variant_and_uncertainty_preserved_in_child(setup):
    _, _, service = setup
    suggested = grouped(original=proposal(candidates=(candidate(
        uncertainties=("Fixture classification requires source-specific interpretation.",)),)))
    offered = offer(suggested=suggested,
                    requirements=VariantAttributes(seasonal_adjustment="adjusted"))
    doc = service.begin(offered.request, offered.proposal, candidate_id="c1",
                        delivery=selected("both").delivery, links=offered.links,
                        requirements=offered.requirements, confirmation_method="explicit_request")
    state = doc["workflow_request"]
    assert state["warnings"] == list(offered.candidate.uncertainties)
    confirmation = work(service, doc)["workflow_context"]["confirmation"]
    assert confirmation["offer"]["proposal"] == suggested.to_dict()
    assert confirmation["offer"]["requirements"] == offered.requirements.to_dict()


def test_begin_transaction_failure_leaves_no_request_or_events(setup, monkeypatch):
    store, _, service = setup
    original_event = store.event

    def fail(connection, task_id, body):
        original_event(connection, task_id, body)
        raise RuntimeError("injected begin failure")

    monkeypatch.setattr(store, "event", fail)
    with pytest.raises(RuntimeError):
        start(service)
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM task_events").fetchone()[0] == 0


@pytest.mark.parametrize("revision", [True, 0, 2])
def test_stale_or_non_integer_revisions_cannot_create_work(setup, revision):
    _, _, service = setup
    doc = start(service)
    with pytest.raises(ValueError, match="stale"):
        service.create_work(doc["task_id"], expected_revision=revision)


def test_invalid_update_and_revision_budget_do_not_mutate_history(setup):
    store, _, service = setup
    doc = start(service)
    with pytest.raises(ValueError, match="unknown workflow update"):
        service.revise(doc["task_id"], expected_revision=1, approved=True)
    with pytest.raises(ValueError, match="identity is immutable"):
        service.revise(doc["task_id"], expected_revision=1,
                       request=data_request(request_id="another"),
                       proposal=grouped(original=proposal(request_id="another")))
    assert store.get(doc["task_id"]) == doc
    with store.transaction() as connection:
        original = store.load(connection, doc["task_id"])
        original["workflow_request"]["revision"] = 100
        store.save(connection, original)
    with pytest.raises(ValueError, match="revision budget"):
        service.revise(doc["task_id"], expected_revision=100,
                       request=data_request(period_end="2021"))
    assert store.get(doc["task_id"]) == original


def test_unfinished_source_task_cannot_be_mislabeled_completed_discovery(setup):
    store, clock, service = setup
    runner = Orchestrator(store, {}, clock=clock)
    source = runner.create("unfinished discovery")
    with pytest.raises(ValueError, match="must be completed"):
        start(service, source_task_id=source.task_id)
    assert store.get(source.task_id)["status"] == "CREATED"


def test_service_can_receive_answers_without_reasking_known_fields(setup):
    _, _, service = setup
    initial = service.begin(data_request(period_end=None), grouped(), candidate_id="c1")
    assert {q["field"] for q in initial["workflow_request"]["questions"]} == {
        "period_end", "delivery.mode"}
    answered = service.revise(initial["task_id"], expected_revision=1, request=data_request(),
                              delivery=selected("file").delivery,
                              confirmation_method="followup")
    assert answered["workflow_request"]["questions"] == []
    assert answered["workflow_request"]["state"] == "CONFIRMED"
    assert work(service, answered)["workflow_context"]["workflow_revision"] == 2
