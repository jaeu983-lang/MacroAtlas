"""Iteration 08 Gate B: offline search, consent and real local ingestion pipelines."""
import hashlib
import importlib.util
import io
import json
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
import requests
from test_metadata_discovery import AT, FIXTURES, document, institution, json_document
from test_worldbank import FixtureTransport, fixture_download

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus
from macro_data_platform.discovery.series import SeriesDiscoveryService, parse_request
from macro_data_platform.ingestion.batch import CollectionProgressStore, UnitOutcome
from macro_data_platform.ingestion.bulk import CollectionBudget, build_collection_plan
from macro_data_platform.ingestion.discovered import (
    DeclaredCSVRoute,
    DeclaredTableRoute,
    SourceDownload,
    WorldBankRoute,
)
from macro_data_platform.ingestion.worldbank_request import WorldBankRequestDispatcher
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.metadata import MetadataStore
from macro_data_platform.workflow_contracts import DataRequest, OutputSpec
from macro_data_platform.workflow_extensions import DeliverySpec, VariantAttributes

CSV_URL = "https://home.treasury.gov/fixture-only/holdings.csv"


class CSVTransport:
    kind = EvidenceKind.FIXTURE

    def __init__(self, body=None, status=200, *, statuses=None, retry_after_seconds=None,
                 content_type=None):
        self.body = body if body is not None else (FIXTURES / "tic_observations.csv").read_bytes()
        self.statuses = list(statuses or (status,))
        self.retry_after_seconds, self.content_type = retry_after_seconds, content_type
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        status = self.statuses[min(len(self.calls) - 1, len(self.statuses) - 1)]
        retry_after = self.retry_after_seconds if status == 429 else None
        return SourceDownload(url, self.body, AT, self.kind, status, retry_after,
                              self.content_type)


def tic_document(*, status="available", body_data=None, format="csv", access_options=None):
    data = body_data or json.loads(document(
        "tic_codebook.json", identifier="tic", host="home.treasury.gov", kind="sheet_codebook").body)
    data["columns"]["access"] = "Access"
    data["rows"][0]["Access"] = {
        "url": CSV_URL, "format": format,
        "columns": {"period":"Month", "country":"Holder", "value":"Amount"},
        "status": status, "shareable": True, "checked_at": AT.isoformat(),
        "expires_at": (AT + timedelta(days=365)).isoformat(),
        **(access_options or {}),
    }
    return json_document(data, file="tic_codebook.json", identifier="tic",
                         host="home.treasury.gov", kind="sheet_codebook")


def request(concept="gdp_nominal", *, institution_hint=None, **changes):
    defaults = {
        "concept": concept, "institution_hint": institution_hint, "countries": ("USA",),
        "dimensions": {}, "period_start": "2020", "period_end": "2022",
        "frequency": "source", "unit_policy": "preserve", "vintage_requirement": "latest_available",
    }
    if concept == "treasury_holdings":
        defaults.update(countries=("JPN",), period_start="2020-01", period_end="2020-03")
    return DataRequest("request-08", "explicit synthetic request", **{**defaults, **changes})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("unexpected real HTTP in Gate B fixture")
    monkeypatch.setattr(requests.sessions.Session, "request", deny)
    settings = Settings(tmp_path)
    history, metadata = HistoryStore(settings), MetadataStore(settings)
    metadata.ingest(document(), institution())
    metadata.ingest(tic_document(), institution("tic", "home.treasury.gov"))
    csv_transport = CSVTransport()
    wb_transport = FixtureTransport(fixture_download())
    service = SeriesDiscoveryService(metadata, history, (
        WorldBankRoute(wb_transport), DeclaredCSVRoute("tic", csv_transport),
    ), clock=lambda: AT)
    return settings, history, metadata, service, csv_transport, wb_transport


def start_csv(service, mode="file", **kwargs):
    req = request("treasury_holdings")
    outcome = service.search(req, **{k:v for k,v in kwargs.items() if k in {
        "requested_scope", "accepted_scope", "requirements"}})
    selected = outcome.proposal.proposal.candidates[0].candidate_id
    offer = service.offer(outcome, selected)
    delivery = DeliverySpec(
        mode, OutputSpec("raw_csv", "data/raw") if mode in {"file", "both"} else None,
        tuple(link.link_id for link in offer.links) if mode in {"link", "both"} else (),
    )
    return service.begin(req, candidate_id=selected, delivery=delivery,
                         confirmation_method="explicit_request", **kwargs)


def _zip_csv(body):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tables/holdings.csv", body)
    return output.getvalue()


def _start_table(service, file_format):
    req = request("treasury_holdings")
    outcome = service.search(req)
    selected = outcome.proposal.proposal.candidates[0].candidate_id
    return service.begin(
        req, candidate_id=selected,
        delivery=DeliverySpec("file", OutputSpec("raw_" + file_format, "data/raw")),
        confirmation_method="explicit_request",
    )


def child(service, root):
    return service.create_work(root["task_id"],
                               expected_revision=root["workflow_request"]["revision"])


def test_institution_unspecified_search_to_existing_worldbank_gate_a(setup):
    settings, history, _, service, _, transport = setup
    outcome = service.search(request())
    assert len(outcome.records) == 1
    assert outcome.rejections[0]["reasons"] == ["concept_mismatch_or_unmapped",
                                                "country_coverage_mismatch",
                                                "period_coverage_mismatch"]
    root = service.begin(request(), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
                         confirmation_method="explicit_request")
    assert root["workflow_request"]["state"] == "CONFIRMED"
    work = child(service, root)
    result = service.run(work["task_id"])
    assert result["status"] == "COMPLETED" and len(transport.calls) == 1
    assert [s["status"] for s in result["stages"]] == ["SUCCEEDED", "SUCCEEDED"]
    assert HistoryStore(settings).get(work["task_id"]) == history.get(work["task_id"])
    assert service.run(work["task_id"]) == result
    assert len(transport.calls) == 1


@pytest.mark.parametrize("mode", ["file", "both", "link"])
def test_tic_search_confirmation_and_file_or_link_e2e(setup, mode):
    settings, history, _, service, transport, _ = setup
    root = start_csv(service, mode)
    assert root["workflow_request"]["state"] == "CONFIRMED"
    assert root["workflow_request"]["questions"] == []
    task = child(service, root)
    result = service.run(task["task_id"])
    assert result["status"] == "COMPLETED"
    if mode == "link":
        assert transport.calls == []
        assert not settings.raw_dir.exists()
        assert result["delivery_result"]["links"][0]["url"] == CSV_URL
    else:
        payload = result["stages"][0]["result"]["payload"]
        assert [r["value"] for r in payload["observations"]] == ["123.5", None, "0"]
        assert payload["mode"] == "fixture" and transport.calls == [CSV_URL]
        raw = settings.project_root / payload["raw_path"]
        assert raw.read_bytes() == transport.body
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == payload["raw_sha256"]
        manifest = json.loads((settings.project_root / payload["manifest_path"]).read_bytes())
        assert manifest["metadata_revision"] == root["workflow_request"]["draft"]["proposal"][
            "proposal"]["candidates"][0]["metadata_revision"]
        if mode == "both":
            assert payload["links"][0]["url"] == CSV_URL
    assert service.run(task["task_id"]) == result
    assert history.get(root["task_id"])["workflow_request"]["work_task_id"] == task["task_id"]


@pytest.mark.parametrize(("format", "body", "options"), [
    ("tsv", b"Month\tHolder\tAmount\n2020-01\tJPN\t123.5\n2020-02\tJPN\t\n2020-03\tJPN\t0\n", {}),
    ("txt", b"Month|Holder|Amount\n2020-01|JPN|123.5\n2020-02|JPN|\n2020-03|JPN|0\n",
     {"delimiter": "|"}),
    ("html", (b"<table><tr><th>Month</th><th>Holder</th><th>Amount</th></tr>"
               b"<tr><td>2020-01</td><td>JPN</td><td>123.5</td></tr>"
               b"<tr><td>2020-02</td><td>JPN</td><td></td></tr>"
               b"<tr><td>2020-03</td><td>JPN</td><td>0</td></tr></table>"),
     {"table_index": 0}),
    ("zip", _zip_csv(b"Month,Holder,Amount\n2020-01,JPN,123.5\n2020-02,JPN,\n"
                      b"2020-03,JPN,0\n"), {"member": "tables/holdings.csv"}),
])
def test_declared_table_formats_preserve_original_and_parse_requested_observations(
        setup, format, body, options):
    settings, history, metadata, _, _, _ = setup
    source = tic_document(format=format, access_options=options)
    metadata.ingest(source, institution("tic", "home.treasury.gov"))
    transport = CSVTransport(body=body)
    service = SeriesDiscoveryService(metadata, history,
                                     (DeclaredTableRoute("tic", transport),), clock=lambda: AT)
    root = _start_table(service, format)
    assert root["workflow_request"]["state"] == "CONFIRMED", root["workflow_request"]["questions"]
    task = child(service, root)
    result = service.run(task["task_id"])
    assert result["status"] == "COMPLETED" and transport.calls == [CSV_URL]
    payload = result["stages"][0]["result"]["payload"]
    assert [row["value"] for row in payload["observations"]] == ["123.5", None, "0"]
    assert payload["source_format"] == format
    assert payload["raw_filename"] == "response." + format
    raw = settings.project_root / payload["raw_path"]
    assert raw.read_bytes() == body
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == payload["raw_sha256"]
    manifest = json.loads((settings.project_root / payload["manifest_path"]).read_bytes())
    assert manifest["parse_selection"]["member"] == options.get("member")


def test_legacy_xls_route_is_not_advertised_without_its_parser_backend(setup):
    _, history, metadata, _, _, _ = setup
    source = tic_document(format="xls")
    metadata.ingest(source, institution("tic", "home.treasury.gov"))
    service = SeriesDiscoveryService(metadata, history,
                                     (DeclaredTableRoute("tic", CSVTransport()),), clock=lambda: AT)
    outcome = service.search(request("treasury_holdings"))
    assert len(outcome.records) == 1
    candidate = outcome.proposal.proposal.candidates[0]
    if importlib.util.find_spec("xlrd") is None:
        assert candidate.support_status == "unsupported" and "raw_xls" not in candidate.supported_outputs
    else:
        assert candidate.support_status == "supported" and "raw_xls" in candidate.supported_outputs


def test_missing_delivery_is_only_question_for_otherwise_explicit_request(setup):
    settings, _, _, service, transport, _ = setup
    root = service.begin(request("treasury_holdings"), confirmation_method="explicit_request")
    questions = root["workflow_request"]["questions"]
    assert [q["field"] for q in questions] == ["delivery.mode"]
    assert questions[0]["choices"] == ["file", "link", "both"]
    with pytest.raises(ValueError, match="confirmation"):
        child(service, root)
    assert transport.calls == [] and not settings.raw_dir.exists()


def test_natural_language_known_terms_keep_missing_conditions_unresolved():
    parsed, requirements = parse_request("미국 재무부 TIC에서 일본 국채 보유잔액 월별 자료")
    assert parsed.institution_hint == "tic" and parsed.countries == ("JPN",)
    assert parsed.concept == "treasury_holdings" and requirements.stock_flow == "stock"
    assert parsed.period_start is None and parsed.unit_policy is None
    assert parsed.dimensions is None
    parsed, _ = parse_request("IMF USA portfolio investment 2020-Q1 ~ 2022-Q4 quarterly")
    assert parsed.period_start == "2020-Q1" and parsed.period_end == "2022-Q4"


def test_specified_institution_never_silently_falls_back(setup):
    _, _, _, service, _, _ = setup
    root = service.begin(request(institution_hint="imf"), confirmation_method="explicit_request")
    assert root["workflow_request"]["state"] == "NEEDS_REVIEW"
    assert root["workflow_request"]["draft"]["proposal"]["proposal"]["candidates"] == []
    with pytest.raises(ValueError):
        child(service, root)


def test_imf_structure_to_source_series_search_and_invalid_code_rejection(setup):
    _, _, metadata, service, _, _ = setup
    source = institution("imf", "data.imf.org")
    structure = document("imf_structure.xml", identifier="imf", host="data.imf.org",
                         kind="sdmx_structure")
    metadata.ingest(structure, source)
    data = json.loads((FIXTURES / "imf_catalogue.json").read_bytes())
    data["datasets"][0]["series"][0]["structure_document_id"] = structure.document_id
    catalogue = json_document(data, identifier="imf", host="data.imf.org")
    catalogue = replace(catalogue, source_url="https://data.imf.org/fixture-catalogue")
    metadata.ingest(catalogue, source)
    outcome = service.search(request("portfolio_investment", institution_hint="imf",
                                     period_start="2020-Q1", period_end="2022-Q4",
                                     frequency="quarterly"))
    assert len(outcome.records) == 1
    assert outcome.records[0].candidate.series_key == {"FREQ": "Q"}
    assert outcome.proposal.proposal.candidates[0].support_status == "unsupported"
    data["datasets"][0]["series"][0]["series_key"]["FREQ"] = "INVENTED"
    with pytest.raises(ValueError, match="not in the source codelist"):
        metadata.ingest(replace(catalogue, body=json.dumps(data).encode(),
                                retrieved_at=AT + timedelta(seconds=1)), source)
    metadata.ingest(replace(structure, body=structure.body.replace(b'id="Q"', b'id="S"'),
                            retrieved_at=AT + timedelta(seconds=2)), source)
    stale = service.search(request("portfolio_investment", institution_hint="imf",
                                   period_start="2020-Q1", period_end="2022-Q4",
                                   frequency="quarterly"))
    assert "source_structure_invalid" in next(iter(stale.reviews.values()))
    # A changed unrelated institution must not prevent an otherwise valid GDP search.
    assert len(service.search(request()).records) == 1


def test_holdings_and_transactions_cannot_match_or_form_one_group(setup):
    _, _, metadata, service, _, _ = setup
    data = json.loads(tic_document().body)
    flow = dict(data["rows"][0], Series="TEST_TRANSACTIONS", Concept="treasury_transactions",
                StockFlow="flow")
    data["rows"].append(flow)
    metadata.ingest(replace(tic_document(body_data=data),
                            retrieved_at=AT + timedelta(seconds=1)),
                    institution("tic", "home.treasury.gov"))
    outcome = service.search(request("treasury_holdings"))
    assert len(outcome.records) == 1
    assert outcome.records[0].attributes.stock_flow == "stock"
    assert not outcome.proposal.groups
    assert any("concept_mismatch_or_unmapped" in r["reasons"] for r in outcome.rejections)


def test_variant_question_and_explicit_requirements_filter(setup):
    _, _, metadata, service, _, _ = setup
    data = json.loads(document().body)
    row = data["datasets"][0]["series"][0]
    row["seasonal_adjustment"] = "unadjusted"
    other = dict(row, seasonal_adjustment="adjusted",
                 series_key={"source":"2","country":"USA","indicator":"FIXTURE_OTHER"})
    data["datasets"][0]["series"].append(other)
    metadata.ingest(replace(json_document(data), retrieved_at=AT + timedelta(seconds=1)),
                    institution())
    outcome = service.search(request())
    assert len(outcome.proposal.groups) == 1
    assert outcome.questions == ({"field":"variant.seasonal_adjustment", "kind":"input",
                                  "choices":["adjusted", "unadjusted"]},)
    filtered = service.search(request(), requirements=VariantAttributes(
        seasonal_adjustment="adjusted"))
    assert len(filtered.records) == 1
    assert filtered.records[0].attributes.seasonal_adjustment == "adjusted"


def test_broader_scope_requires_explicit_new_confirmation_and_keeps_source_definition(setup):
    _, history, metadata, service, transport, _ = setup
    data = json.loads(tic_document().body)
    data["columns"]["scope_relations"] = "Relations"
    data["rows"][0].update(Scope="public_sector", Relations=[{
        "target":"central_bank", "relation":"broader", "axis":"institutional_sector",
        "version":"fixture-v1", "includes":["central_bank"], "excludes":["private_sector"],
    }])
    metadata.ingest(replace(tic_document(body_data=data), retrieved_at=AT - timedelta(seconds=1)),
                    institution("tic", "home.treasury.gov"))
    root = start_csv(service, requested_scope="central_bank")
    assert root["workflow_request"]["state"] == "NEEDS_REVIEW"
    assert root["discovery_context"]["accepted_scope"] is None
    with pytest.raises(ValueError):
        child(service, root)
    # The legacy confirmation API cannot bypass the discovery semantic guard.
    direct = service.workflow.confirm(root["task_id"], expected_revision=1,
                                      confirmation_method="followup")
    with pytest.raises(ValueError, match="meaning"):
        service.workflow.create_work(direct["task_id"],
                                     expected_revision=direct["workflow_request"]["revision"])
    revised = service.revise(
        root["task_id"], expected_revision=direct["workflow_request"]["revision"],
        accepted_scope="public_sector", confirmation_method="followup")
    assert revised["workflow_request"]["state"] == "CONFIRMED"
    assert revised["discovery_context"]["requested_scope"] == "central_bank"
    assert revised["discovery_context"]["accepted_scope"] == "public_sector"
    result = service.run(child(service, revised)["task_id"])
    assert result["status"] == "COMPLETED" and transport.calls
    assert any(e["kind"] == "WORKFLOW_REVISED" for e in history.events(root["task_id"]))


def test_changed_metadata_invalidates_consent_even_with_direct_existing_dispatcher(setup):
    settings, history, metadata, service, _, transport = setup
    root = service.begin(request(), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
                         confirmation_method="explicit_request")
    task = child(service, root)
    data = json.loads(document().body)
    data["datasets"][0]["series"][0]["definition"] = "changed definition"
    metadata.ingest(replace(json_document(data), retrieved_at=AT + timedelta(seconds=1)),
                    institution())
    with pytest.raises(ValueError, match="metadata changed"):
        WorldBankRequestDispatcher(settings, history, transport=transport,
                                    clock=lambda: AT).run(task["task_id"])
    assert transport.calls == []


@pytest.mark.parametrize("body", [
    b"Changed,Holder,Amount\n2020-01,JPN,1\n",
    b"Month,Holder,Amount\n2020-01,JPN,1\n2020-01,JPN,2\n",
    b"Month,Holder,Amount\n2020-01,JPN,NaN\n",
])
def test_schema_or_quality_failure_retains_raw_and_stops(setup, body):
    settings, _, _, service, transport, _ = setup
    transport.body = body
    result = service.run(child(service, start_csv(service))["task_id"])
    assert result["status"] == "NEEDS_REVIEW"
    payload = result["stages"][0]["result"]["payload"]
    assert (settings.project_root / payload["raw_path"]).read_bytes() == body
    assert "observations" not in payload


def test_expired_access_and_unsupported_output_cannot_collect(setup):
    _, _, _, service, transport, _ = setup
    root = start_csv(service)
    task = child(service, root)
    service.clock = lambda: AT + timedelta(days=366)
    with pytest.raises(ValueError, match="expired"):
        service.run(task["task_id"])
    assert transport.calls == []
    service.clock = lambda: AT
    root = service.begin(request("treasury_holdings"),
                         delivery=DeliverySpec("file", OutputSpec("xlsx", "data/raw")),
                         confirmation_method="explicit_request")
    assert root["workflow_request"]["state"] == "NEEDS_REVIEW"
    with pytest.raises(ValueError):
        child(service, root)


def test_disabled_network_blocks_live_transport_before_fetch(setup):
    _, _, _, service, transport, _ = setup
    transport.kind = EvidenceKind.LIVE_INGESTION
    result = service.run(child(service, start_csv(service))["task_id"])
    assert result["status"] == "NEEDS_REVIEW" and transport.calls == []
    assert result["stages"][0]["result"]["error_code"] == "AUTH_ACCESS"


def test_link_delivery_works_without_a_collector_route(setup):
    settings, history, metadata, _, transport, _ = setup
    service = SeriesDiscoveryService(metadata, history, clock=lambda: AT)
    root = start_csv(service, "link")
    result = service.run(child(service, root)["task_id"])
    assert result["status"] == "COMPLETED"
    assert not settings.raw_dir.exists() and transport.calls == []


def test_completed_csv_checks_raw_integrity_before_reuse(setup):
    settings, _, _, service, transport, _ = setup
    work = child(service, start_csv(service))
    result = service.run(work["task_id"])
    payload = result["stages"][0]["result"]["payload"]
    (settings.project_root / payload["raw_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        service.run(work["task_id"])
    assert len(transport.calls) == 1


@pytest.mark.parametrize("status", ["unknown", "unavailable", "blocked"])
def test_unusable_source_links_are_disclosed_without_delivery_fallback(setup, status):
    settings, _, metadata, service, transport, _ = setup
    metadata.ingest(replace(tic_document(status=status), retrieved_at=AT - timedelta(seconds=1)),
                    institution("tic", "home.treasury.gov"))
    root = start_csv(service, "link")
    assert root["workflow_request"]["state"] == "NEEDS_REVIEW"
    assert root["workflow_request"]["link_statuses"][0]["status"] == status
    assert root["workflow_request"]["draft"]["delivery"]["mode"] == "link"
    with pytest.raises(ValueError):
        child(service, root)
    assert not settings.raw_dir.exists() and transport.calls == []


def test_revalidation_preserves_existing_confirmation_time_revision_and_child(setup):
    _, _, _, service, _, _ = setup
    root = start_csv(service)
    work = child(service, root)
    original = service.history.get(root["task_id"])["workflow_request"]
    service.clock = lambda: AT + timedelta(minutes=5)
    revised = service.revise(root["task_id"], expected_revision=original["revision"])
    assert revised["workflow_request"]["revision"] == original["revision"]
    assert revised["workflow_request"]["confirmation"] == original["confirmation"]
    assert revised["workflow_request"]["work_task_id"] == work["task_id"]


@pytest.mark.parametrize(("relation", "state"), [("exact", "CONFIRMED"),
                                              ("unknown", "NEEDS_REVIEW")])
def test_scope_aliases_require_explicit_relation_evidence(setup, relation, state):
    _, _, metadata, service, _, _ = setup
    data = json.loads(tic_document().body)
    data["columns"]["scope_relations"] = "Relations"
    data["rows"][0].update(Scope="monetary_authority", Relations=[{
        "target":"central_bank", "relation":relation, "axis":"institutional_sector",
        "version":"fixture-v1",
    }])
    metadata.ingest(replace(tic_document(body_data=data), retrieved_at=AT - timedelta(seconds=1)),
                    institution("tic", "home.treasury.gov"))
    root = start_csv(service, requested_scope="central_bank")
    assert root["workflow_request"]["state"] == state


def test_parser_keeps_unsupported_or_ambiguous_institutions_scoped():
    parsed, _ = parse_request("FRED USA GDP 2020~2022")
    assert parsed.institution_hint == "fred"
    parsed, _ = parse_request("ECB Eurostat GDP")
    assert parsed.institution_hint.startswith("unresolved:")
    with pytest.raises(ValueError, match="calendar"):
        parse_request("GDP 2020-13~2022-13")


def test_catalogue_institution_id_connects_to_existing_worldbank_adapter(setup):
    _, _, metadata, service, _, transport = setup
    metadata.ingest(replace(document(), institution_id="INT-04", source_agency="World Bank"),
                    institution("INT-04"))
    root = service.begin(
        request(institution_hint="INT-04"),
        delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    assert root["workflow_request"]["state"] == "CONFIRMED"
    result = service.run(child(service, root)["task_id"])
    assert result["status"] == "COMPLETED" and len(transport.calls) == 1


def test_explicit_reconfirmation_of_changed_metadata_cancels_old_child(setup):
    _, history, metadata, service, _, transport = setup
    root = service.begin(
        request(), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    old_child = child(service, root)
    data = json.loads(document().body)
    data["datasets"][0]["series"][0]["definition"] = "explicitly revised fixture definition"
    metadata.ingest(replace(json_document(data), retrieved_at=AT + timedelta(seconds=1)),
                    institution())
    service.clock = lambda: AT + timedelta(seconds=2)
    revised = service.revise(root["task_id"], expected_revision=1,
                             confirmation_method="followup")
    assert revised["workflow_request"]["revision"] == 2
    assert history.get(old_child["task_id"])["status"] == "CANCELLED"
    replacement = child(service, revised)
    assert replacement["task_id"] != old_child["task_id"]
    assert service.run(replacement["task_id"])["status"] == "COMPLETED"
    assert len(transport.calls) == 1


def test_csv_small_request_budget_is_checked_before_transport(setup):
    _, _, metadata, service, transport, _ = setup
    countries = ("JPN", *(f"FIXTURE_{i}" for i in range(10)))
    data = json.loads(tic_document().body)
    data["rows"][0]["Geography"] = list(countries)
    metadata.ingest(replace(tic_document(body_data=data), retrieved_at=AT - timedelta(seconds=1)),
                    institution("tic", "home.treasury.gov"))
    root = service.begin(
        request("treasury_holdings", countries=countries),
        delivery=DeliverySpec("file", OutputSpec("raw_csv", "data/raw")),
        confirmation_method="explicit_request")
    with pytest.raises(ValueError, match="country budget"):
        service.run(child(service, root)["task_id"])
    assert transport.calls == []


def test_rate_limit_resumes_only_after_durable_bounded_backoff(setup):
    _, history, _, service, transport, _ = setup
    now = [AT]
    service.clock = lambda: now[0]
    transport.statuses = [429, 200]
    transport.retry_after_seconds = 5
    task = child(service, start_csv(service))

    first = service.run(task["task_id"])
    failed = first["stages"][-1]["result"]
    assert first["status"] == "FAILED"
    assert failed["error_code"] == "TRANSIENT"
    assert failed["retry_after_seconds"] == 5
    assert transport.calls == [CSV_URL]
    first_raw = service.history.settings.project_root / failed["payload"]["raw_path"]
    first_bytes = first_raw.read_bytes()
    due = datetime.fromisoformat(failed["retry_not_before"])
    with pytest.raises(ValueError, match="backoff"):
        service.resume(task["task_id"])

    now[0] = due
    final = service.resume(task["task_id"])
    assert final["status"] == "COMPLETED" and len(transport.calls) == 2
    assert first_raw.read_bytes() == first_bytes
    assert final["stages"][-1]["result"]["payload"]["raw_path"] != failed["payload"]["raw_path"]
    assert history.get(task["task_id"])["status"] == "COMPLETED"


def test_forbidden_source_stops_for_review_without_retry_or_auth_fallback(setup):
    _, _, _, service, transport, _ = setup
    transport.statuses = [403]
    task = child(service, start_csv(service))

    result = service.run(task["task_id"])
    stage = result["stages"][-1]
    assert result["status"] == "NEEDS_REVIEW"
    assert stage["result"]["error_code"] == "AUTH_ACCESS"
    assert stage["result"].get("retry_not_before") is None
    assert transport.calls == [CSV_URL]


def test_declared_format_and_frequency_drift_stop_before_observations(setup):
    settings, _, _, service, transport, _ = setup
    transport.content_type = "application/json"
    task = child(service, start_csv(service))
    result = service.run(task["task_id"])

    stage = result["stages"][-1]
    payload = stage["result"]["payload"]
    assert result["status"] == "NEEDS_REVIEW"
    assert stage["result"]["error_code"] == "SCHEMA_CHANGED"
    assert "observations" not in payload
    assert (settings.project_root / payload["raw_path"]).read_bytes() == transport.body

    wrong_frequency = service.search(
        request("treasury_holdings", frequency="annual"))
    assert wrong_frequency.records == ()
    assert any("frequency_mismatch" in row["reasons"]
               for row in wrong_frequency.rejections)
    assert transport.calls == [CSV_URL]


def test_metadata_revision_change_during_download_retains_raw_and_blocks_parse(setup):
    settings, _, metadata, service, _, _ = setup
    now = [AT]
    service.clock = lambda: now[0]
    original = tic_document()
    data = json.loads(original.body)
    data["rows"][0]["Notes"] = "A revised source definition."

    class ChangingTransport:
        kind = EvidenceKind.FIXTURE
        calls = 0

        def fetch(self, url):
            self.calls += 1
            revised = replace(tic_document(body_data=data),
                              retrieved_at=AT + timedelta(seconds=1))
            metadata.ingest(revised, institution("tic", "home.treasury.gov"))
            return SourceDownload(url, (FIXTURES / "tic_observations.csv").read_bytes(),
                                  AT, self.kind)

    route = next(route for route in service.routes if isinstance(route, DeclaredCSVRoute))
    route.transport = ChangingTransport()
    task = child(service, start_csv(service))
    result = service.run(task["task_id"])

    stage = result["stages"][-1]
    payload = stage["result"]["payload"]
    assert result["status"] == "NEEDS_REVIEW"
    assert stage["result"]["error_code"] == "SEMANTIC_AMBIGUITY"
    assert "observations" not in payload
    assert (settings.project_root / payload["raw_path"]).read_bytes() == (
        FIXTURES / "tic_observations.csv").read_bytes()


def test_bulk_units_record_partial_results_and_resume_only_pending_work(setup):
    settings, history, metadata, service, _, _ = setup
    now = [AT + timedelta(seconds=2)]
    service.clock = lambda: now[0]
    countries = ("JPN", *(f"COUNTRY_{index:02}" for index in range(10)))
    data = json.loads(tic_document().body)
    data["rows"][0]["Geography"] = list(countries)
    metadata.ingest(
        replace(tic_document(body_data=data), retrieved_at=AT + timedelta(seconds=1)),
        institution("tic", "home.treasury.gov"),
    )
    requested = request("treasury_holdings", countries=countries)
    outcome = service.search(requested)
    assert len(outcome.records) == 1
    candidate = outcome.records[0].candidate
    root = service.begin(
        requested, candidate_id=candidate.candidate_id,
        delivery=DeliverySpec("file", OutputSpec("raw_csv", "data/raw")),
        confirmation_method="explicit_request",
    )
    work = child(service, root)
    confirmed = work["workflow_context"]["confirmation"]
    plan = build_collection_plan(
        series_ids=(candidate.series_id,), countries=countries,
        period_start="2020-01", period_end="2020-03", frequency="monthly",
        mode="full", bytes_per_observation=1, seconds_per_request=0.5,
    )
    progress = CollectionProgressStore(history, clock=lambda: now[0])
    progress.initialize(work["task_id"], plan, confirmed["fingerprint"])
    calls = []

    def first_attempt(unit, remaining_bytes, remaining_seconds):
        calls.append((unit, remaining_bytes, remaining_seconds))
        return UnitOutcome(
            StageStatus.FAILED_RETRYABLE, byte_count=4, elapsed_seconds=0.1,
            error_code=ErrorCode.TRANSIENT, retry_after_seconds=5,
        )

    first = progress.execute_pending(work["task_id"], first_attempt)
    assert len(first["units"]) == 2
    assert first["units"][0]["status"] == "FAILED_RETRYABLE"
    assert first["units"][1]["status"] == "NOT_RUN"
    assert progress.pending_units(work["task_id"]) == ()
    due = datetime.fromisoformat(first["pause_until"])
    now[0] = due
    resumed_calls = []

    def resume_attempt(unit, remaining_bytes, remaining_seconds):
        resumed_calls.append(unit)
        path = settings.raw_dir / f"unit-{len(resumed_calls)}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"period,country,value\n")
        return UnitOutcome(
            StageStatus.SUCCEEDED,
            (path.relative_to(settings.project_root).as_posix(),),
            observation_count=unit.estimated_observations,
            byte_count=10, elapsed_seconds=0.2,
        )

    final = progress.execute_pending(work["task_id"], resume_attempt)

    assert [row["status"] for row in final["units"]] == ["SUCCEEDED", "SUCCEEDED"]
    assert final["request_attempts"] == 3
    assert final["observation_count"] == 33
    assert final["byte_count"] == 24
    assert len(calls) == 1 and len(resumed_calls) == 2
    assert len(progress.pending_units(work["task_id"])) == 0
    assert [event["kind"] for event in history.events(work["task_id"])
            if event["kind"].startswith("COLLECTION_UNIT_")] == [
                "COLLECTION_UNIT_STARTED", "COLLECTION_UNIT_FINISHED",
                "COLLECTION_UNIT_STARTED", "COLLECTION_UNIT_FINISHED",
                "COLLECTION_UNIT_STARTED", "COLLECTION_UNIT_FINISHED",
            ]


def test_bulk_resource_budget_overrun_stops_remaining_units_and_retains_artifact(setup):
    settings, history, _, service, _, _ = setup
    task = child(service, start_csv(service))
    confirmed = task["workflow_context"]["confirmation"]
    plan = build_collection_plan(
        series_ids=("TEST_HOLDINGS",), countries=("JPN",),
        period_start="2020-01", period_end="2020-03", frequency="monthly",
        mode="full", budget=CollectionBudget(max_requests=10, max_observations=100,
                                              max_bytes=1, max_seconds=60),
    )
    progress = CollectionProgressStore(history, clock=lambda: AT)
    progress.initialize(task["task_id"], plan, confirmed["fingerprint"])

    def oversized_result(unit, remaining_bytes, remaining_seconds):
        path = settings.raw_dir / "bounded-unit.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"source")
        return UnitOutcome(
            StageStatus.SUCCEEDED, (path.relative_to(settings.project_root).as_posix(),),
            observation_count=unit.estimated_observations, byte_count=6,
            elapsed_seconds=0.1,
        )

    result = progress.execute_pending(task["task_id"], oversized_result)

    assert result["units"][0]["status"] == "NEEDS_REVIEW"
    assert result["units"][0]["artifact_refs"] == ["data/raw/bounded-unit.csv"]
    assert result["units"][0]["message"].startswith("Collection unit exceeded")
    assert result["stop_reason"] == "unit_requires_review"
    assert progress.pending_units(task["task_id"]) == ()
