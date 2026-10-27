"""Iteration 08 search ranking, evidence gating, and confirmed collection tests."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from freshness_support import HISTORICAL_FIXTURE_POLICY
from test_worldbank import FIXTURE, FixtureTransport, fixture_download

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.contracts import EvidenceKind, SourceEvidence, StageStatus
from macro_data_platform.discovery.series_search import (
    CandidateSearchEngine,
    SelectionReceiptEngine,
    build_confirmed_collection_plan,
    candidate_collection_engines,
    rank_candidates,
)
from macro_data_platform.metadata.normalize import normalize_bls_catalog
from macro_data_platform.orchestration import Orchestrator, StageInput
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.metadata_archives import save_metadata_package
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    ConfirmedSelection,
    DataRequest,
    OutputSpec,
)

AT = datetime(2026, 10, 26, tzinfo=UTC)
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def wb_request(**changes):
    values = {
        "request_id": "request-gdp", "text": "GDP USA 2020 to 2022",
        "concept": "GDP", "countries": ("USA",), "dimensions": {},
        "period_start": "2020", "period_end": "2022", "frequency": "source",
        "unit_policy": "preserve", "vintage_requirement": "latest_available",
    }
    return DataRequest(**{**values, **changes})


def fixture_candidate(**changes):
    evidence = SourceEvidence(
        "fixture-evidence", "Fixture Statistical Agency", "https://example.org/data",
        AT, EvidenceKind.FIXTURE, "tests/fixtures/series-search/gdp.json",
    )
    values = {
        "candidate_id": "fixture:gdp", "institution_id": "fixture",
        "label": "GDP annual", "definition": "Fixture GDP series; not production metadata.",
        "dataset_id": "fixture-1", "series_id": "GDP001", "series_key": {},
        "countries": ("USA",), "dimensions": {}, "frequency": "annual", "unit": "USD",
        "available_start": "2010", "available_end": "2024", "evidence": (evidence,),
        "verification_status": "metadata_verified", "availability_status": "available",
        "auth_requirement": "none", "support_status": "supported",
        "supported_outputs": ("raw_json",),
    }
    return Candidate(**{**values, **changes})


def selection(request, candidate, *, output=None):
    proposal = CandidateProposal("proposal-1", request.request_id, 1, AT, (candidate,))
    return ConfirmedSelection(
        request, proposal, candidate.candidate_id, 1,
        output or OutputSpec("raw_json", "data/raw"), AT + timedelta(minutes=1),
        "explicit_request",
    )


def test_ranking_uses_terms_and_hard_excludes_known_country_or_institution_mismatch(tmp_path):
    settings = Settings(tmp_path)
    result = CandidateSearchEngine(settings, clock=lambda: AT).run(StageInput(
        "task", "GDP USA 2020 to 2022", "series_search",
        {"request": wb_request().to_dict(), "limit": 10}, None, (),
    ))
    assert result.status is StageStatus.SUCCEEDED
    proposal = CandidateProposal.from_dict(result.payload["proposal"])
    assert [item.candidate_id for item in proposal.candidates] == [
        "worldbank:2:USA:NY.GDP.MKTP.CD",
    ]
    assert result.payload["ranking"][0]["match_status"] == "review_required"
    assert result.payload["selection_requires_explicit_confirmation"] is True

    correct = fixture_candidate(candidate_id="fixture:gdp", label="GDP", institution_id="fixture")
    wrong_country = fixture_candidate(candidate_id="fixture:japan", label="GDP", countries=("JPN",))
    wrong_institution = fixture_candidate(candidate_id="other:gdp", label="GDP", institution_id="other")
    ranked = rank_candidates(wb_request(institution_hint="fixture"),
                              [correct, wrong_country, wrong_institution])
    assert [item["candidate"].candidate_id for item in ranked] == ["fixture:gdp"]


@pytest.mark.parametrize("measure", ["transactions", None])
def test_holdings_request_cannot_confirm_transaction_or_unknown_measure(measure):
    """Gate C X04: explicit source dimensions outrank an identical holdings label."""
    request = wb_request(
        text="Treasury holdings USA", concept="Treasury holdings",
        dimensions={"measure": ("holdings",)},
    )
    holdings = fixture_candidate(
        candidate_id="fixture:holdings", label="Treasury holdings USA",
        definition="Fixture end-of-period holdings, not transactions.",
        dimensions={"measure": ("holdings",)},
    )
    other = fixture_candidate(
        candidate_id="fixture:other", label=holdings.label,
        definition="Fixture measure is transactions or remains unverified.",
        dimensions=None if measure is None else {"measure": (measure,)},
    )
    ranked = rank_candidates(request, [other, holdings])
    by_id = {item["candidate"].candidate_id: item for item in ranked}
    assert holdings.candidate_id in by_id
    assert selection(request, holdings).candidate_id == holdings.candidate_id
    if measure is None:
        assert by_id[other.candidate_id]["match_status"] == "review_required"
        assert "dimensions_unknown" in by_id[other.candidate_id]["missing_constraints"]
    else:
        assert other.candidate_id not in by_id
    with pytest.raises(ValueError, match="Dimension (coverage|selection) mismatch"):
        selection(request, other)


def test_offline_archived_bls_metadata_enters_index_but_stays_unverified_for_selection(tmp_path):
    settings = Settings(tmp_path)
    payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{
        "seriesID": "CUUR0000SA0", "catalog": {
            "series_title": "All items in U.S. city average",
            "seasonality": "Not Seasonally Adjusted", "area": "U.S. city average",
            "survey_name": "Consumer Price Index for All Urban Consumers (CPI-U)",
        },
    }]}}
    raw = json.dumps(payload).encode()
    download = ApiDownload(BLS_URL, raw, 200, AT, "application/json", EvidenceKind.FIXTURE)
    record = normalize_bls_catalog(
        payload, source_url=BLS_URL, retrieved_at=AT.isoformat(), raw_path="",
        start_year=2024, end_year=2024, expected_series_id="CUUR0000SA0",
    )
    save_metadata_package(settings, "bls", download, [record], {"fixture": True})
    result = CandidateSearchEngine(settings, clock=lambda: AT).run(StageInput(
        "task", "CPI", "series_search", {"request": DataRequest(
            "cpi-request", "CPI", concept="CPI",
        ).to_dict()}, None, (),
    ))
    proposal = CandidateProposal.from_dict(result.payload["proposal"])
    bls = next(item for item in proposal.candidates if item.candidate_id == "bls:CUUR0000SA0")
    assert bls.verification_status == "unknown"
    assert bls.availability_status == "unknown"
    assert bls.auth_requirement == "optional"
    assert bls.unit is None and bls.frequency is None
    assert result.payload["ranking"][0]["match_status"] == "review_required"


def test_unconfirmed_or_out_of_scope_selection_cannot_build_collection_plan(tmp_path):
    settings = Settings(tmp_path)
    with pytest.raises(TypeError):
        build_confirmed_collection_plan({"candidate_id": "anything"}, settings)
    valid = selection(wb_request(), fixture_candidate())
    with pytest.raises(ValueError, match="raw_json"):
        build_confirmed_collection_plan(
            selection(wb_request(), fixture_candidate(supported_outputs=("raw_json", "csv")),
                      output=OutputSpec("csv", "data/raw")), settings,
        )
    assert valid.confirmation_method == "explicit_request"


def test_confirmed_candidate_builds_audited_search_to_worldbank_collection_e2e(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    search = CandidateSearchEngine(settings, clock=lambda: AT).run(StageInput(
        "search-task", "GDP USA 2020 to 2022", "series_search",
        {"request": wb_request().to_dict()}, None, (),
    ))
    request = DataRequest.from_dict(search.payload["request"])
    proposal = CandidateProposal.from_dict(search.payload["proposal"])
    chosen = proposal.candidates[0]
    confirmed = ConfirmedSelection(
        request, proposal, chosen.candidate_id, proposal.revision,
        OutputSpec("raw_json", "data/raw"), AT + timedelta(minutes=1), "explicit_request",
    )
    plan = build_confirmed_collection_plan(confirmed, settings)
    assert [step.engine for step in plan.stages] == ["record_selection", "worldbank_gdp"]

    transport = FixtureTransport(fixture_download())
    runner = Orchestrator(HistoryStore(settings), candidate_collection_engines(
        settings, worldbank_transport=transport, clock=lambda: AT + timedelta(minutes=2),
        freshness_policy=HISTORICAL_FIXTURE_POLICY,
    ), clock=lambda: AT + timedelta(minutes=2))
    task = runner.create(request.text)
    runner.plan(task.task_id, plan)
    result = runner.run(task.task_id)
    assert result["status"] == "COMPLETED"
    receipt = result["stages"][0]["result"]["payload"]
    assert receipt["confirmation_fingerprint"] == confirmed.fingerprint
    assert receipt["candidate"]["candidate_id"] == chosen.candidate_id
    collected = result["stages"][1]["result"]["payload"]
    assert collected["mode"] == "fixture"
    assert Path(tmp_path, collected["raw_path"]).read_bytes() == FIXTURE.read_bytes()
    assert len(transport.calls) == 1


@pytest.mark.parametrize(("institution", "query_request", "candidate", "expected"), [
    ("bls", DataRequest(
        "bls-r", "CPI monthly", concept="CPI", countries=("USA",), dimensions={},
        period_start="2020", period_end="2022", frequency="monthly", unit_policy="preserve",
        vintage_requirement="latest_available",
    ), fixture_candidate(
        candidate_id="bls:CUUR0000SA0", institution_id="bls", series_id="CUUR0000SA0",
        dataset_id=None, frequency="monthly", unit=None, countries=("USA",),
        available_start="2020", available_end="2022", auth_requirement="required",
        credential_env_var="BLS_API_KEY", evidence=(SourceEvidence(
            "bls-e", "BLS", BLS_URL, AT, EvidenceKind.FIXTURE, "fixture:catalog"),
        ),
    ), "bls"),
    ("census", DataRequest(
        "census-r", "Census total population", concept="population", countries=("USA",),
        dimensions={"for": ("state:06",)}, period_start="2022", period_end="2022",
        frequency="source", unit_policy="preserve", vintage_requirement="latest_available",
    ), fixture_candidate(
        candidate_id="census:acs/acs1:B01001_001E", institution_id="census",
        label="Total population", series_id="B01001_001E", dataset_id="acs/acs1",
        series_key={"dataset": "acs/acs1", "variable_id": "B01001_001E", "year": "2022"},
        countries=("USA",), dimensions={"for": ("state:06",)}, frequency=None, unit=None,
        available_start="2022", available_end="2022", auth_requirement="required",
        credential_env_var="CENSUS_API_KEY", evidence=(SourceEvidence(
            "census-e", "Census", "https://api.census.gov/data/2022/acs/acs1/variables/B01001_001E.json",
            AT, EvidenceKind.FIXTURE, "fixture:variable"),
        ),
    ), "census"),
])
def test_confirmed_bls_and_census_selections_map_only_explicit_supported_parameters(
    tmp_path, institution, query_request, candidate, expected,
):
    plan = build_confirmed_collection_plan(selection(query_request, candidate), Settings(tmp_path))
    assert plan.stages[0].engine == "record_selection"
    assert plan.stages[1].engine == expected
    if expected == "bls":
        assert plan.stages[1].input_data == {
            "series_ids": ["CUUR0000SA0"], "start_year": 2020, "end_year": 2022,
        }
    else:
        assert plan.stages[1].input_data == {
            "year": 2022, "dataset": "acs/acs1",
            "variables": ["NAME", "B01001_001E"], "geography": "state:06",
        }


def test_selection_receipt_rejects_tampered_confirmation():
    value = selection(wb_request(), fixture_candidate())
    snapshot = value.to_dict()
    snapshot["candidate_id"] = "other"
    result = SelectionReceiptEngine().run(StageInput(
        "task", "request", "record_selection", {"selection": snapshot}, None, (),
    ))
    assert result.status is StageStatus.NEEDS_REVIEW
