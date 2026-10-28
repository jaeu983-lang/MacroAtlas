"""Bounded World Bank series collection uses fixture transports only."""
import json
from datetime import UTC, datetime

import pytest
import requests
from freshness_support import HISTORICAL_FIXTURE_POLICY

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import (
    ConnectorFailure,
    Download,
    WorldBankSeriesQuery,
    parse_series,
)
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus
from macro_data_platform.ingestion.freshness import FreshnessPolicy
from macro_data_platform.ingestion.worldbank_series import WorldBankSeriesEngine
from macro_data_platform.orchestration.models import StageInput

NOW = datetime(2026, 10, 26, tzinfo=UTC)
QUERY = WorldBankSeriesQuery("CAN", "SP.POP.TOTL", "2", 2024, 2025)


def body():
    return [
        {"page": 1, "pages": 1, "per_page": 100, "total": 2,
         "sourceid": "2", "lastupdated": "2026-10-08"},
        [
            {"indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
             "country": {"id": "CA", "value": "Canada"}, "countryiso3code": "CAN",
             "date": "2025", "value": 41288599, "unit": "", "obs_status": "", "decimal": 0},
            {"indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
             "country": {"id": "CA", "value": "Canada"}, "countryiso3code": "CAN",
             "date": "2024", "value": None, "unit": "", "obs_status": "", "decimal": 0},
        ],
    ]


def download(content=None, *, url=None, status=200, content_type="application/json"):
    return Download(url or QUERY.url,
                    json.dumps(body() if content is None else content, allow_nan=False).encode(),
                    status, NOW, content_type, EvidenceKind.FIXTURE)


def request_input(data=None):
    return StageInput("test-task", "explicit WDI series", "collect", data or {
        "country_iso3": "CAN", "indicator_id": "SP.POP.TOTL", "source_id": "2",
        "start_year": 2024, "end_year": 2025,
    }, None, ())


class FixtureTransport:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        return self.result


@pytest.fixture(autouse=True)
def deny_real_http(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "request",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("real HTTP is forbidden in tests")))


@pytest.mark.parametrize("kwargs", [
    {"country_iso3": "Can"}, {"country_iso3": "../../"},
    {"indicator_id": "SP.POP.TOTL?format=json"}, {"indicator_id": "../other"},
    {"source_id": "0"}, {"source_id": "3"}, {"source_id": "2/3"},
    {"start_year": 2020, "end_year": 2120}, {"start_year": True},
])
def test_query_rejects_unbounded_or_url_shaping_inputs(kwargs):
    data = {"country_iso3": "CAN", "indicator_id": "SP.POP.TOTL", "source_id": "2",
            "start_year": 2024, "end_year": 2025}
    data.update(kwargs)
    with pytest.raises(ValueError):
        WorldBankSeriesQuery(**data)


def test_query_constructs_only_the_fixed_https_world_bank_endpoint():
    assert QUERY.url == (
        "https://api.worldbank.org/v2/country/CAN/indicator/SP.POP.TOTL"
        "?source=2&date=2024%3A2025&format=json&per_page=100&page=1"
    )


def test_query_allows_one_full_page_of_annual_periods_and_rejects_overflow():
    query = WorldBankSeriesQuery("CAN", "SP.POP.TOTL", "2", 1960, 2059)
    assert query.end_year - query.start_year + 1 == 100
    with pytest.raises(ValueError, match="1 to 100 years"):
        WorldBankSeriesQuery("CAN", "SP.POP.TOTL", "2", 1960, 2060)


def test_parser_preserves_rows_unknown_units_null_values_and_request_identity():
    rows = body()[1]
    parsed = parse_series(download(), QUERY)
    assert parsed["observations"] == rows
    assert parsed["observations"][1]["value"] is None
    assert parsed["unit"] is None and parsed["frequency"] is None
    assert parsed["series_id"] is None
    assert parsed["series_key"] == {
        "source": "2", "country": "CAN", "indicator": "SP.POP.TOTL",
    }
    assert parsed["source_version"] is None


@pytest.mark.parametrize("mutate", [
    lambda data: data[0].update(sourceid=True),
    lambda data: data[0].update(pages=2),
    lambda data: data[1][0].update(countryiso3code="USA"),
    lambda data: data[1][0]["indicator"].update(id="NY.GDP.MKTP.CD"),
    lambda data: data[1][0].update(date="2023"),
    lambda data: data[1][1].update(date="2025"),
    lambda data: data[1][0].update(value=True),
])
def test_parser_rejects_identity_schema_pagination_and_duplicate_errors(mutate):
    content = body()
    mutate(content)
    with pytest.raises(ConnectorFailure) as caught:
        parse_series(download(content), QUERY)
    assert caught.value.status == StageStatus.NEEDS_REVIEW
    assert caught.value.code == ErrorCode.SCHEMA_CHANGED


def test_engine_persists_raw_before_returning_validated_series(tmp_path):
    transport = FixtureTransport(download())
    engine = WorldBankSeriesEngine(
        Settings(tmp_path), transport, clock=lambda: NOW,
        freshness_policy=HISTORICAL_FIXTURE_POLICY,
    )
    result = engine.run(request_input())
    assert result.status == StageStatus.SUCCEEDED
    assert [row["value"] for row in result.payload["observations"]] == [41288599, None]
    assert (tmp_path / result.payload["raw_path"]).read_bytes() == transport.result.body
    assert json.loads((tmp_path / result.payload["manifest_path"]).read_text())["source_url"] == QUERY.url
    assert (tmp_path / result.payload["typed_series_artifact"]["typed_series_path"]).is_file()


def test_engine_withholds_stale_observations_but_retains_source_bytes(tmp_path):
    result = WorldBankSeriesEngine(
        Settings(tmp_path), FixtureTransport(download()), clock=lambda: NOW,
        freshness_policy=FreshnessPolicy(
            policy_id="test_short_annual_tolerance",
            frequency_max_age_days={"annual": 100},
        ),
    ).run(request_input())
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.error_code == ErrorCode.QUALITY_FAILURE
    assert result.payload["quality"]["freshness"]["status"] == "STALE"
    assert result.payload["observations"] == []
    assert result.payload["withheld_observation_count"] == 2
    assert (tmp_path / result.payload["raw_path"]).is_file()


def test_engine_rejects_extra_inputs_before_network_or_storage(tmp_path):
    transport = FixtureTransport(download())
    data = {"country_iso3": "CAN", "indicator_id": "SP.POP.TOTL", "source_id": "2",
            "start_year": 2024, "end_year": 2025, "url": "https://example.org"}
    result = WorldBankSeriesEngine(Settings(tmp_path), transport).run(request_input(data))
    assert result.status == StageStatus.FAILED_TERMINAL
    assert result.error_code == ErrorCode.SCHEMA_CHANGED
    assert transport.queries == []
    assert not (tmp_path / "data").exists()


def test_engine_refuses_mismatched_response_url_and_preserves_no_untrusted_body(tmp_path):
    result = WorldBankSeriesEngine(
        Settings(tmp_path), FixtureTransport(download(url="https://example.org")),
    ).run(request_input())
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.error_code == ErrorCode.LICENSE_SECURITY
    assert result.payload["source_url"] == QUERY.url
    assert not (tmp_path / "data").exists()
