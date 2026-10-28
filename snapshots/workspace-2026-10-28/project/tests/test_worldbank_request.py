"""Alignment 03: supplied fixture evidence, mock transport and real local history only."""
import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
import requests
from test_orchestration import Clock
from test_workflow_contracts import AT, candidate, data_request, evidence, proposal
from test_worldbank import FIXTURE, FixtureTransport, fixture_download

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import GDPQuery
from macro_data_platform.ingestion.worldbank_request import (
    WorldBankRequestDispatcher,
    build_worldbank_plan,
)
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan, WorkflowService
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_contracts import ConfirmedSelection, OutputSpec
from macro_data_platform.workflow_extensions import (
    CandidateVariant,
    DataLink,
    DeliveryOffer,
    DeliverySpec,
    GroupedProposal,
    VariantAttributes,
    link_target_fingerprint,
)


@pytest.fixture(autouse=True)
def deny_http(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Unexpected real HTTP call in mock integration test")
    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture
def setup(tmp_path):
    settings = Settings(tmp_path)
    store = HistoryStore(settings)
    clock = Clock()
    return settings, store, clock, WorkflowService(store, clock=clock)


def supplied(service, mode="file", *, request_changes=None, candidate_changes=None,
             output=None, requirements=None, url=None, manual=False, confirmed=True):
    request = data_request(**(request_changes or {}))
    selected = candidate(**{
        "institution_id": "worldbank", "dataset_id": "2", "countries": ("USA",),
        "series_key": {"source": "2", "country": "USA", "indicator": "NY.GDP.MKTP.CD"},
        "frequency": None, "unit": None, "supported_outputs": ("raw_json", "csv", "xlsx"),
        **(candidate_changes or {}),
    })
    suggested = GroupedProposal(proposal(candidates=(selected,)))
    if requirements is not None:
        suggested = replace(suggested, variants=(CandidateVariant(
            "c1", "gdp", requirements, (evidence(),)),))
    base = DeliveryOffer(request, suggested, "c1", requirements or VariantAttributes())
    links = ()
    if mode in ("link", "both"):
        links = (DataLink(
            "l1", "c1", suggested.proposal.proposal_id, 1,
            link_target_fingerprint(request, suggested, "c1", base.requirements),
            status="available", url=url or GDPQuery().url, kind="api", checked_at=AT,
            expires_at=AT + timedelta(hours=1), official=True, shareable=True,
            access_requirement="public", manual_filter_required=manual,
            restrictions=("Declared fixture restriction",), evidence=(evidence(),),
        ),)
    delivery = DeliverySpec(mode, (output or OutputSpec("raw_json", "data/raw"))
                            if mode in ("file", "both") else None,
                            ("l1",) if mode in ("link", "both") else ())
    return service.begin(request, suggested, candidate_id="c1", links=links,
                         requirements=base.requirements, delivery=delivery,
                         confirmation_method="explicit_request" if confirmed else None)


def child(service, root):
    return service.create_work(root["task_id"],
                               expected_revision=root["workflow_request"]["revision"])


def dispatcher(setup, transport):
    settings, store, clock, _ = setup
    return WorldBankRequestDispatcher(settings, store, clock=clock, transport=transport)


@pytest.mark.parametrize("mode", ["file", "both"])
def test_complete_request_to_mock_download_preserves_raw_and_metadata(setup, mode):
    settings, store, _, service = setup
    root = supplied(service, mode)
    assert root["workflow_request"]["questions"] == []
    task = child(service, root)
    transport = FixtureTransport(fixture_download())
    handler = dispatcher(setup, transport)
    prepared = handler.prepare(task["task_id"])
    assert prepared["plan"][0]["input_data"] == {"start_year": 2020, "end_year": 2022}
    result = handler.run(task["task_id"])
    assert result["status"] == "COMPLETED" and transport.calls == [GDPQuery()]
    parsed = result["stages"][0]["result"]["payload"]
    assert (settings.project_root / parsed["raw_path"]).read_bytes() == FIXTURE.read_bytes()
    source = json.loads(FIXTURE.read_bytes())
    assert parsed["observations"] == source[1]
    assert parsed["source_last_updated"] == source[0]["lastupdated"]
    assert parsed["unit"] is None and parsed["frequency"] is None
    assert parsed["mode"] == "fixture"
    assert parsed["observations"][1]["value"] is None
    assert any(row["value"] == 0 for row in parsed["observations"])
    manifest = json.loads((settings.project_root / parsed["manifest_path"]).read_text("utf-8"))
    assert manifest["source_url"] == GDPQuery().url and manifest["mode"] == "fixture"
    if mode == "both":
        delivered = result["stages"][1]["result"]["payload"]
        assert delivered["collection"] == parsed
        assert delivered["links"][0]["url"] == GDPQuery().url
        assert result["stages"][1]["result"]["evidence_refs"] == [
            parsed["raw_path"], parsed["manifest_path"]]
    assert handler.run(task["task_id"]) == result
    assert len(transport.calls) == 1
    assert HistoryStore(settings).get(task["task_id"]) == result
    assert store.get(root["task_id"])["workflow_request"]["work_task_id"] == task["task_id"]


def test_link_only_completes_without_transport_raw_or_collector_plan(setup):
    settings, store, clock, service = setup
    root = supplied(service, "link", manual=True,
                    candidate_changes={"support_status": "unsupported", "supported_outputs": ()})
    task = child(service, root)
    transport = FixtureTransport(AssertionError("transport must never run"))
    handler = dispatcher(setup, transport)
    assert handler.prepare(task["task_id"])["plan"] is None
    result = handler.run(task["task_id"])
    assert result["status"] == "COMPLETED" and result["plan"] is None
    assert result["stages"] == [] and transport.calls == []
    links = result["delivery_result"]["links"]
    assert links[0]["manual_filter_required"] is True
    assert links[0]["restrictions"] == ["Declared fixture restriction"]
    assert links[0]["evidence"][0]["kind"] == "fixture"
    assert not settings.raw_dir.exists()
    before = store.events(task["task_id"])
    assert handler.run(task["task_id"]) == result
    assert store.events(task["task_id"]) == before
    assert len(result["attempts"]) == 1
    with pytest.raises(ValueError, match="link-only"):
        Orchestrator(store, {}, clock=clock).plan(
            task["task_id"], TaskPlan((StageSpec("collect", "x"),)))
    with pytest.raises(ValueError, match="no collector attempt"):
        handler.resume(task["task_id"], approved=True)


@pytest.mark.parametrize("changes,message", [
    ({"candidate_changes": {"institution_id": "other"}}, "Only worldbank"),
    ({"candidate_changes": {"dataset_id": "3"}}, "Only worldbank"),
    ({"candidate_changes": {"series_id": "NY.GDP.MKTP.CD"}}, "Only worldbank"),
    ({"candidate_changes": {"series_key": {"source": "3", "country": "USA",
                                           "indicator": "NY.GDP.MKTP.CD"}}}, "Only worldbank"),
    ({"candidate_changes": {"series_key": {"source": "2", "country": "USA",
                                           "indicator": "OTHER"}}}, "Only worldbank"),
    ({"candidate_changes": {"countries": ("JPN",), "series_key": {
        "source": "2", "country": "JPN", "indicator": "NY.GDP.MKTP.CD"}},
      "request_changes": {"countries": ("JPN",)}}, "Only worldbank"),
    ({"candidate_changes": {"dimensions": {"sector": ("ALL",)}},
      "request_changes": {"dimensions": {"sector": ("ALL",)}}}, "without filters"),
    ({"request_changes": {"frequency": "annual"},
      "candidate_changes": {"frequency": "annual"}}, "source frequency"),
    ({"request_changes": {"unit_policy": "convert", "target_unit": "EUR"},
      "candidate_changes": {"unit": "USD"}}, "preserved units"),
    ({"request_changes": {"vintage_requirement": "v1"},
      "candidate_changes": {"source_version": "v1"}}, "latest_available"),
    ({"request_changes": {"period_start": "2010", "period_end": "2020"}}, "1 to 10 years"),
    ({"request_changes": {"period_start": "1959", "period_end": "1960"},
      "candidate_changes": {"available_start": "1959"}}, "1 to 10 years"),
    ({"output": OutputSpec("csv", "data/raw")}, "CSV/XLSX"),
    ({"output": OutputSpec("xlsx", "data/raw")}, "CSV/XLSX"),
    ({"output": OutputSpec("raw_json", "data/export")}, "raw directory"),
    ({"candidate_changes": {"auth_requirement": "required",
                             "credential_env_var": "WORLDBANK_API_KEY"}}, "no API credentials"),
    ({"requirements": VariantAttributes(price_basis="real")}, "Variant filtering"),
])
def test_out_of_scope_rejected_before_plan_transport_or_raw_write(setup, changes, message):
    settings, store, _, service = setup
    root = supplied(service, **changes)
    assert root["workflow_request"]["state"] == "CONFIRMED"
    task = child(service, root)
    transport = FixtureTransport(fixture_download())
    handler = dispatcher(setup, transport)
    with pytest.raises(ValueError, match=message):
        handler.run(task["task_id"])
    assert store.get(task["task_id"])["plan"] is None
    assert store.get(task["task_id"])["attempts"] == []
    assert transport.calls == [] and not settings.raw_dir.exists()


@pytest.mark.parametrize("mode", ["link", "both"])
def test_unrelated_or_different_query_url_never_delivered_or_fetched(setup, mode):
    settings, _, _, service = setup
    root = supplied(service, mode, url="https://example.org/data")
    task = child(service, root)
    transport = FixtureTransport(fixture_download())
    with pytest.raises(ValueError, match="fixed World Bank query URL"):
        dispatcher(setup, transport).run(task["task_id"])
    assert transport.calls == [] and not settings.raw_dir.exists()


@pytest.mark.parametrize("mode", ["file", "link", "both"])
def test_pending_confirmation_cannot_execute_or_be_approved_into_execution(setup, mode):
    settings, _, _, service = setup
    root = supplied(service, mode, confirmed=False)
    transport = FixtureTransport(fixture_download())
    handler = dispatcher(setup, transport)
    with pytest.raises(ValueError, match="linked confirmed"):
        handler.run(root["task_id"])
    with pytest.raises(ValueError, match="linked confirmed"):
        handler.resume(root["task_id"], approved=True)
    assert transport.calls == [] and not settings.raw_dir.exists()


@pytest.mark.parametrize("mode", ["link", "both"])
def test_expiry_prevents_delivery_without_file_fallback(setup, mode):
    settings, store, clock, service = setup
    task = child(service, supplied(service, mode))
    transport = FixtureTransport(fixture_download())
    handler = dispatcher(setup, transport)
    handler.prepare(task["task_id"])
    clock.value += timedelta(hours=1)
    with pytest.raises(ValueError, match="unavailable"):
        handler.run(task["task_id"])
    assert transport.calls == [] and not settings.raw_dir.exists()
    assert store.get(task["task_id"])["attempts"] == []


def test_changed_selection_invalidates_prepared_plan_and_resume_approval(setup):
    settings, _, _, service = setup
    root = supplied(service)
    task = child(service, root)
    transport = FixtureTransport(fixture_download())
    handler = dispatcher(setup, transport)
    handler.prepare(task["task_id"])
    service.revise(root["task_id"], expected_revision=1,
                   request=data_request(period_end="2021"))
    with pytest.raises(ValueError, match="invalidated"):
        handler.resume(task["task_id"], approved=True)
    assert transport.calls == [] and not settings.raw_dir.exists()


def test_existing_wrong_plan_cannot_change_confirmed_years(setup):
    settings, store, clock, service = setup
    task = child(service, supplied(service))
    runner = Orchestrator(store, {}, clock=clock)
    runner.plan(task["task_id"], TaskPlan((StageSpec("collect", "worldbank_gdp", {
        "start_year": 2020, "end_year": 2021,
    }),)))
    transport = FixtureTransport(fixture_download())
    with pytest.raises(ValueError, match="Saved plan differs"):
        dispatcher(setup, transport).run(task["task_id"])
    assert transport.calls == [] and not settings.raw_dir.exists()


def test_default_network_denial_preserves_error_contract(setup):
    settings, store, clock, service = setup
    task = child(service, supplied(service))
    result = WorldBankRequestDispatcher(settings, store, clock=clock).run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert result["stages"][0]["result"]["error_code"] == "LICENSE_SECURITY"
    assert not settings.raw_dir.exists()


@pytest.mark.parametrize("mode", ["file", "both"])
def test_http_failure_and_resume_retain_old_raw_and_source_observations(setup, mode):
    settings, store, clock, service = setup
    task = child(service, supplied(service, mode))
    transport = FixtureTransport(fixture_download(status=503), fixture_download())
    first = dispatcher(setup, transport).run(task["task_id"])
    assert first["status"] == "FAILED"
    failed = first["stages"][0]["result"]
    assert failed["error_code"] == "TRANSIENT"
    saved = settings.project_root / failed["payload"]["raw_path"]
    original = saved.read_bytes()
    clock.value = datetime.fromisoformat(failed["retry_not_before"])
    reopened = WorldBankRequestDispatcher(settings, HistoryStore(settings), clock=clock,
                                         transport=transport)
    result = reopened.resume(task["task_id"])
    assert result["status"] == "COMPLETED" and len(transport.calls) == 2
    assert result["workflow_context"] == first["workflow_context"]
    assert len(result["attempts"]) == 2
    assert saved.read_bytes() == original
    assert result["stages"][1]["result"]["payload"]["raw_path"] != failed["payload"]["raw_path"]
    assert store.get(task["task_id"])["status"] == "COMPLETED"


def test_link_delivery_transaction_failure_rolls_back_without_side_effect(setup, monkeypatch):
    settings, store, _, service = setup
    task = child(service, supplied(service, "link"))
    before = store.events(task["task_id"])
    original_event = store.event

    def fail(connection, task_id, body):
        original_event(connection, task_id, body)
        raise RuntimeError("injected link event failure")

    monkeypatch.setattr(store, "event", fail)
    with pytest.raises(RuntimeError, match="injected"):
        dispatcher(setup, FixtureTransport()).run(task["task_id"])
    assert store.get(task["task_id"]) == task
    assert store.events(task["task_id"]) == before
    assert not settings.raw_dir.exists()


def test_explicit_legacy_builder_keeps_old_json_and_uses_selected_period(setup):
    settings, _, _, service = setup
    root = supplied(service, request_changes={"period_start": "2021", "period_end": "2022"})
    draft = root["workflow_request"]["draft"]
    from macro_data_platform.workflow_extensions import ConfirmedDelivery

    confirmed = ConfirmedDelivery.from_dict(root["workflow_request"]["confirmation"])
    selection = ConfirmedSelection(confirmed.offer.request, confirmed.offer.proposal.proposal,
                                   "c1", 1, confirmed.delivery.file, AT, "explicit_request")
    original = selection.to_json()
    built = build_worldbank_plan(selection, settings)
    assert built.stages[0].input_data == {"start_year": 2021, "end_year": 2022}
    assert selection.to_json() == original
    assert draft["request"]["period_start"] == "2021"
    with pytest.raises(ValueError, match="legacy selection"):
        build_worldbank_plan(confirmed, settings)


def test_changed_output_resolution_rejected_before_plan(setup, monkeypatch):
    settings, _, _, service = setup
    task = child(service, supplied(service))
    monkeypatch.setattr(OutputSpec, "resolve_under", lambda self, root: root.parent / "outside")
    with pytest.raises(ValueError, match="raw directory"):
        dispatcher(setup, FixtureTransport()).prepare(task["task_id"])
    assert not settings.raw_dir.exists()


def test_both_link_expiry_after_download_preserves_raw_without_delivering_link(setup):
    settings, store, clock, service = setup
    task = child(service, supplied(service, "both"))

    class ExpiringTransport:
        calls = 0

        def fetch(self, query):
            self.calls += 1
            clock.value += timedelta(hours=1)
            return fixture_download()

    transport = ExpiringTransport()
    result = dispatcher(setup, transport).run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW" and result["active_token"] is None
    assert len(result["stages"]) == 1 and transport.calls == 1
    raw = result["stages"][0]["result"]["payload"]["raw_path"]
    assert (settings.project_root / raw).read_bytes() == FIXTURE.read_bytes()
    assert store.get(task["task_id"])["status"] == "NEEDS_REVIEW"


def test_link_stage_race_is_review_error_not_internal_failure(setup, monkeypatch):
    _, _, _, service = setup
    task = child(service, supplied(service, "both"))
    handler = dispatcher(setup, FixtureTransport(fixture_download()))
    original = handler._preflight
    calls = []

    def change_at_delivery(task_id):
        calls.append(task_id)
        if len(calls) == 2:
            raise ValueError("simulated condition change after stage claim")
        return original(task_id)

    monkeypatch.setattr(handler, "_preflight", change_at_delivery)
    result = handler.run(task["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    assert result["stages"][-1]["result"]["error_code"] == "SEMANTIC_AMBIGUITY"
    assert result["stages"][-1]["result"]["payload"] is None


@pytest.mark.parametrize("mode", ["link", "both"])
def test_cancelled_work_cannot_deliver_or_download(setup, mode):
    settings, store, clock, service = setup
    task = child(service, supplied(service, mode))
    Orchestrator(store, {}, clock=clock).cancel(task["task_id"])
    transport = FixtureTransport(fixture_download())
    with pytest.raises(ValueError):
        dispatcher(setup, transport).run(task["task_id"])
    assert transport.calls == [] and not settings.raw_dir.exists()


def test_dispatcher_rejects_unbound_tasks_and_another_history_root(setup):
    settings, store, clock, _ = setup
    task = Orchestrator(store, {}, clock=clock).create("legacy request")
    with pytest.raises(ValueError, match="linked confirmed"):
        dispatcher(setup, FixtureTransport()).run(task.task_id)
    with pytest.raises(ValueError, match="same configured storage"):
        WorldBankRequestDispatcher(Settings(settings.project_root / "other"), store)


def test_legacy_builder_rejects_missing_confirmation(setup):
    settings, _, _, _ = setup
    with pytest.raises(ValueError, match="confirmed legacy selection"):
        build_worldbank_plan(None, settings)


def test_no_window_defaulting_selected_annual_period_maps_exactly(setup):
    settings, _, _, service = setup
    task = child(service, supplied(service,
        request_changes={"period_start": "2011", "period_end": "2020"}))
    handler = dispatcher(setup, FixtureTransport())
    saved = handler.prepare(task["task_id"])
    assert saved["plan"][0]["input_data"] == {"start_year": 2011, "end_year": 2020}
    assert not settings.raw_dir.exists()
