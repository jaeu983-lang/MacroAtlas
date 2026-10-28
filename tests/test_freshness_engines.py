"""End-to-end freshness gating at the current observation engine boundaries."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import DATA_ENDPOINT, METADATA_ENDPOINT, BOJQuery
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.connectors.worldbank import Download
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus
from macro_data_platform.ingestion.bls import BLSEngine
from macro_data_platform.ingestion.boj import build_boj_plan, make_boj_orchestrator
from macro_data_platform.ingestion.census import CensusEngine
from macro_data_platform.ingestion.freshness import FreshnessPolicy
from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine
from macro_data_platform.orchestration.models import StageInput as OrchestrationInput
from macro_data_platform.storage.history import HistoryStore

AS_OF = datetime(2026, 10, 26, tzinfo=UTC)
WORLD_BANK_FIXTURE = Path(__file__).parent / "fixtures" / "worldbank_gdp.json"
WB_SERIES_KEY = {"source": "2", "country": "USA", "indicator": "NY.GDP.MKTP.CD"}


def _download(url, body, *, at=AS_OF):
    return ApiDownload(url, json.dumps(body).encode(), 200, at, "application/json",
                       EvidenceKind.FIXTURE)


class WorldBankFixture:
    def fetch(self, query):
        return Download(query.url, WORLD_BANK_FIXTURE.read_bytes(), 200, AS_OF,
                        "application/json", EvidenceKind.FIXTURE)


class WorldBankLatestNullFixture:
    def fetch(self, query):
        body = [{"page": 1, "pages": 1, "per_page": 100, "total": 2,
                 "sourceid": "2", "lastupdated": "2026-10-28"}, [
            {"indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
             "country": {"id": "US", "value": "United States"}, "countryiso3code": "USA",
             "date": "2026", "value": None, "unit": "", "obs_status": "", "decimal": 0},
            {"indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
             "country": {"id": "US", "value": "United States"}, "countryiso3code": "USA",
             "date": "2025", "value": 123.5, "unit": "", "obs_status": "", "decimal": 0},
        ]]
        return Download(query.url, json.dumps(body).encode(), 200, AS_OF,
                        "application/json", EvidenceKind.FIXTURE)


class BOJFixture:
    def fetch_metadata(self, query):
        return _download(METADATA_ENDPOINT, {
            "STATUS": 200, "DB": query.database, "DATE": "20261026",
            "RESULTSET": [{
                "SERIES_CODE": query.series_code,
                "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
                "UNIT": "Yen per U.S. Dollar", "FREQUENCY": "DAILY",
                "CATEGORY": "Foreign Exchange Rates", "LAST_UPDATE": "20261026",
            }],
        })

    def fetch_observations(self, query):
        return _download(DATA_ENDPOINT, {
            "STATUS": 200, "DATE": "20261026", "NEXTPOSITION": None,
            "RESULTSET": [{
                "SERIES_CODE": query.series_code,
                "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
                "UNIT": "Yen per U.S. Dollar", "FREQUENCY": "DAILY", "LAST_UPDATE": 20261026,
                "VALUES": {"SURVEY_DATES": [20260901, 20260902], "VALUES": [159.77, None]},
            }],
        })


class ApiFixture:
    def __init__(self, url, body):
        self.url, self.body = url, body

    def fetch(self, query):
        return _download(self.url, self.body)


def test_worldbank_old_observation_is_blocked_despite_recent_retrieval_and_lastupdated(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    result = WorldBankGDPEngine(settings, WorldBankFixture(), clock=lambda: AS_OF).run(
        OrchestrationInput("freshness-wb", "GDP", "collect",
                           {"start_year": 2020, "end_year": 2022}, None, ()),
    )
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.error_code == ErrorCode.QUALITY_FAILURE
    assert result.payload["quality"]["freshness"]["status"] == "STALE"
    assert result.payload["quality"]["freshness"]["frequency"] == "annual"
    assert result.payload["observations"] == []
    assert result.payload["withheld_observation_count"] == 3
    assert Path(tmp_path, result.payload["raw_path"]).is_file()


def test_worldbank_latest_null_period_does_not_make_actual_value_look_future(tmp_path):
    policy = FreshnessPolicy(frequency_max_age_days={"annual": 400})
    result = WorldBankGDPEngine(
        Settings(tmp_path, network_enabled=True), WorldBankLatestNullFixture(),
        clock=lambda: datetime(2026, 10, 28, tzinfo=UTC), freshness_policy=policy,
    ).run(OrchestrationInput(
        "freshness-wb-null-latest", "GDP", "collect",
        {"start_year": 2025, "end_year": 2026}, None, (),
    ))

    assert result.status == StageStatus.SUCCEEDED
    assert result.payload["quality"]["freshness"]["latest_period"] == "2025"
    assert result.payload["quality"]["freshness"]["status"] == "FRESH"
    assert len(result.payload["observations"]) == 2
    assert next(row for row in result.payload["observations"]
                if row["date"] == "2026")["value"] is None
    assert Path(tmp_path, result.payload["typed_series_artifact"]["typed_series_path"]).is_file()


def test_boj_daily_old_observations_are_withheld_after_raw_capture(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    store = HistoryStore(settings)
    runner = make_boj_orchestrator(
        store, settings, BOJFixture(), clock=lambda: AS_OF,
    )
    task = runner.create("BOJ daily freshness fixture")
    runner.plan(task.task_id, build_boj_plan(BOJQuery("202609")))
    result = runner.run(task.task_id)
    payload = result["stages"][-1]["result"]["payload"]
    assert result["status"] == "NEEDS_REVIEW"
    assert payload["quality"]["freshness"]["status"] == "STALE"
    assert payload["observations"] == []
    assert payload["withheld_observation_count"] == 2
    assert Path(tmp_path, payload["raw_path"]).is_file()


def test_boj_future_null_calendar_rows_do_not_hide_latest_available_observation(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    as_of = datetime(2026, 10, 28, tzinfo=UTC)

    class CurrentMonthBOJFixture(BOJFixture):
        def fetch_observations(self, query):
            return _download(DATA_ENDPOINT, {
                "STATUS": 200, "DATE": "20261028", "NEXTPOSITION": None,
                "RESULTSET": [{
                    "SERIES_CODE": query.series_code,
                    "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
                    "UNIT": "Yen per U.S. Dollar", "FREQUENCY": "DAILY",
                    "LAST_UPDATE": 20261028,
                    "VALUES": {
                        "SURVEY_DATES": [20261026, 20261027, 20261028, 20261029,
                                         20261030, 20261031],
                        "VALUES": [152.1, 152.2, None, None, None, None],
                    },
                }],
            }, at=as_of)

    store = HistoryStore(settings)
    runner = make_boj_orchestrator(
        store, settings, CurrentMonthBOJFixture(), clock=lambda: as_of,
    )
    task = runner.create("BOJ current-month null calendar rows fixture")
    runner.plan(task.task_id, build_boj_plan(BOJQuery("202610")))
    result = runner.run(task.task_id)
    payload = result["stages"][-1]["result"]["payload"]

    assert result["status"] == "COMPLETED"
    assert payload["quality"]["freshness"]["status"] == "FRESH"
    assert payload["quality"]["freshness"]["latest_period"] == "2026-10-27"
    assert payload["quality"]["freshness"]["age_days"] == 1
    assert payload["quality"]["missing_value_count"] == 4
    assert [row["value"] for row in payload["observations"][-4:]] == [None] * 4
    assert Path(tmp_path, payload["typed_series_artifact"]["typed_series_path"]).is_file()


def test_bls_old_monthly_observation_is_not_returned_from_quality_failure(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    result = BLSEngine(settings, ApiFixture(url, {
        "status": "REQUEST_SUCCEEDED", "Results": {"series": [{
            "seriesID": "CUUR0000SA0", "data": [{
                "year": "2024", "period": "M01", "periodName": "January",
                "value": "308.4", "footnotes": [],
            }],
        }]},
    }), clock=lambda: AS_OF).run(OrchestrationInput(
        "freshness-bls", "CPI", "bls",
        {"series_ids": ["CUUR0000SA0"], "start_year": 2024, "end_year": 2024}, None, (),
    ))
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.payload["quality"]["issues"] == ["stale_observations"]
    assert result.payload["quality"]["freshness"][0]["frequency"] == "monthly"
    assert result.payload["observations"] == []
    assert result.payload["withheld_observation_count"] == 1


def test_bls_empty_latest_month_does_not_make_older_value_look_fresh(tmp_path):
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    result = BLSEngine(Settings(tmp_path, network_enabled=True), ApiFixture(url, {
        "status": "REQUEST_SUCCEEDED", "Results": {"series": [{
            "seriesID": "CUUR0000SA0", "data": [
                {"year": "2026", "period": "M01", "periodName": "January",
                 "value": "100.0", "footnotes": []},
                {"year": "2026", "period": "M10", "periodName": "October",
                 "value": "", "footnotes": []},
            ],
        }]},
    }), clock=lambda: datetime(2026, 10, 28, tzinfo=UTC)).run(OrchestrationInput(
        "freshness-bls-empty-latest", "CPI", "bls",
        {"series_ids": ["CUUR0000SA0"], "start_year": 2026, "end_year": 2026}, None, (),
    ))

    freshness = result.payload["quality"]["freshness"][0]
    assert result.status == StageStatus.NEEDS_REVIEW
    assert freshness["latest_period"] == "2026-01"
    assert freshness["status"] == "STALE"


def test_census_old_annual_observation_is_withheld(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    url = "https://api.census.gov/data/2022/acs/acs1"
    result = CensusEngine(settings, ApiFixture(url, [
        ["NAME", "B01001_001E", "state"], ["California", "39029342", "06"],
    ]), clock=lambda: AS_OF).run(OrchestrationInput(
        "freshness-census", "population", "census", {
            "year": 2022, "dataset": "acs/acs1", "variables": ["NAME", "B01001_001E"],
            "geography": "state:06",
        }, None, (),
    ))
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.payload["quality"]["freshness"][0]["status"] == "STALE"
    assert result.payload["observations"] == []
    assert result.payload["withheld_observation_count"] == 1


def test_census_all_missing_values_have_no_freshness_anchor(tmp_path):
    url = "https://api.census.gov/data/2025/acs/acs1"
    result = CensusEngine(Settings(tmp_path, network_enabled=True), ApiFixture(url, [
        ["NAME", "B01001_001E", "us"], ["United States", "", "1"],
    ]), clock=lambda: datetime(2026, 10, 28, tzinfo=UTC)).run(OrchestrationInput(
        "freshness-census-missing", "population", "census", {
            "year": 2025, "dataset": "acs/acs1", "variables": ["NAME", "B01001_001E"],
            "geography": "us:1",
        }, None, (),
    ))

    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.payload["quality"]["freshness"][0]["status"] == "FRESHNESS_UNVERIFIED"
    assert result.payload["observations"] == []


def test_empty_bls_observations_are_freshness_unverified_not_fresh(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    result = BLSEngine(settings, ApiFixture(url, {
        "status": "REQUEST_SUCCEEDED", "Results": {"series": [{
            "seriesID": "CUUR0000SA0", "data": [],
        }]},
    }), clock=lambda: AS_OF).run(OrchestrationInput(
        "freshness-empty", "CPI", "bls",
        {"series_ids": ["CUUR0000SA0"], "start_year": 2024, "end_year": 2024}, None, (),
    ))
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.payload["quality"]["freshness"][0]["status"] == "FRESHNESS_UNVERIFIED"
    assert result.payload["observations"] == []


@pytest.mark.parametrize(("frequency", "period_format", "periods", "fresh"), [
    ("daily", None, ["2026-10-19"], True),
    ("monthly", None, ["2026-06"], True),
    ("annual", None, ["2024"], True),
    (None, "YYYY-MM-DD", ["2026-10-20"], True),
    (None, None, ["2026-10-01"], False),
])
def test_fresh_and_unverified_engine_cases_are_explicit(frequency, period_format, periods, fresh):
    from macro_data_platform.ingestion.freshness import assess_freshness

    result = assess_freshness(periods, frequency=frequency, period_format=period_format,
                              as_of=AS_OF)
    assert (result["status"] == "FRESH") is fresh
    if not fresh:
        assert result["status"] == "FRESHNESS_UNVERIFIED"


def test_series_override_is_exact_and_persisted_in_freshness_evidence():
    from macro_data_platform.ingestion.freshness import (
        FreshnessEvidence,
        assess_freshness,
        series_key_override_key,
    )

    override_key = series_key_override_key(WB_SERIES_KEY)
    policy = FreshnessPolicy(
        series_overrides={override_key: 1500},
        series_evidence={override_key: FreshnessEvidence(
            evidence_id="world-bank-fixture",
            source_url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
            source_sha256="d" * 64,
            captured_at=AS_OF,
            evidence_type="official_frequency_metadata",
            citation="Test fixture only",
            review_status="approved",
            reviewer_id="fixture-reviewer",
            reviewed_at=AS_OF,
        )},
    )
    result = assess_freshness(["2022"], frequency=None, period_format="YYYY",
                              series_key=WB_SERIES_KEY, as_of=AS_OF, policy=policy)
    assert result["status"] == "FRESH"
    assert result["max_age_days"] == 1500
    assert result["policy_id"] == policy.policy_id
    assert result["series_override_key"] == series_key_override_key(WB_SERIES_KEY)
