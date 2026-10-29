from datetime import UTC, datetime

import pytest

from macro_data_platform.contracts import (
    Observation,
    ObservationStatus,
    TimeSeries,
)
from macro_data_platform.metadata.series import (
    normalize_bls_series,
    normalize_boj_series,
    normalize_census_series,
    normalize_worldbank_series,
    worldbank_metadata_evidence,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def test_common_contract_keeps_zero_and_missing_distinct_and_serializes_stably():
    series = TimeSeries(
        source_agency="Example Agency",
        dataset_id="dataset-1",
        series_id="series-1",
        dimensions={"country": "CA"},
        calendar="gregorian",
        observations=(
            Observation("2025", 0, ObservationStatus.OBSERVED),
            Observation("2024", None, ObservationStatus.MISSING),
        ),
        retrieved_at=NOW,
        source_url="https://example.test/data",
        raw_ref="data/raw/input.json",
        manifest_ref="data/raw/input.manifest.json",
        frequency="annual",
        frequency_basis="period_format",
    )

    serialized = series.to_dict()
    assert serialized["schema_version"] == "time-series-v1"
    assert serialized["dimensions"] == {"country": "CA"}
    assert serialized["observations"] == [
        {"period": "2025", "raw_value": 0, "status": "observed", "source_period": None},
        {"period": "2024", "raw_value": None, "status": "missing", "source_period": None},
    ]
    with pytest.raises(TypeError):
        series.dimensions["country"] = "US"


@pytest.mark.parametrize("kwargs", [
    {"observations": ()},
    {"frequency": "monthly", "frequency_basis": "unknown"},
    {"frequency": None, "frequency_basis": "source_metadata"},
    {"source_url": "https://example.test/data?api_key=secret"},
])
def test_common_contract_rejects_invalid_series_metadata(kwargs):
    values = {
        "source_agency": "Example Agency", "dataset_id": "dataset-1",
        "series_id": "series-1", "dimensions": {}, "calendar": "gregorian",
        "observations": (Observation("2025", 1, ObservationStatus.OBSERVED),),
        "retrieved_at": NOW, "source_url": "https://example.test/data",
        "raw_ref": "raw.json", "manifest_ref": "manifest.json",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        TimeSeries(**values)


@pytest.mark.parametrize(("raw_value", "status"), [
    (None, ObservationStatus.OBSERVED),
    (0, ObservationStatus.MISSING),
    (True, ObservationStatus.OBSERVED),
    (float("inf"), ObservationStatus.OBSERVED),
])
def test_observation_rejects_ambiguous_or_nonfinite_values(raw_value, status):
    with pytest.raises((TypeError, ValueError)):
        Observation("2025", raw_value, status)


def test_world_bank_adapter_marks_annual_period_resolution_without_inventing_unit():
    series = normalize_worldbank_series({
        "source_agency": "World Bank", "dataset_id": "2",
        "indicator_id": "SP.POP.TOTL", "series_key": {
            "source": "2", "country": "CAN", "indicator": "SP.POP.TOTL",
        }, "period_format": "YYYY", "frequency": None, "unit": None,
        "source_version": None, "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.worldbank.org/v2/country/CAN/indicator/SP.POP.TOTL?date=2025",
        "raw_path": "data/raw/wdi.json", "manifest_path": "data/raw/wdi.manifest.json",
        "observations": [{"date": "2025", "value": 0}, {"date": "2024", "value": None}],
    })

    assert series.dataset_id == "2"
    assert series.series_id == "SP.POP.TOTL"
    assert series.dimensions == {"country_iso3": "CAN"}
    assert series.frequency == "annual"
    assert series.frequency_basis == "period_format"
    assert series.unit is None and series.currency is None
    assert [item.status for item in series.observations] == [
        ObservationStatus.OBSERVED, ObservationStatus.MISSING,
    ]


def test_world_bank_gdp_uses_only_exact_ai_reviewed_official_unit_mapping():
    payload = {
        "source_agency": "World Bank", "dataset_id": "2",
        "indicator_id": "NY.GDP.MKTP.CD", "series_key": {
            "source": "2", "country": "CAN", "indicator": "NY.GDP.MKTP.CD",
        }, "period_format": "YYYY", "frequency": None, "unit": None,
        "source_version": None, "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.worldbank.org/v2/country/CAN/indicator/NY.GDP.MKTP.CD",
        "raw_path": "data/raw/wdi.json", "manifest_path": "data/raw/wdi.manifest.json",
        "observations": [{"date": "2024", "value": 1}],
    }

    series = normalize_worldbank_series(payload)
    evidence, = worldbank_metadata_evidence(payload)

    assert series.unit == "current U.S. dollars"
    assert series.currency == "USD"
    assert evidence["reviewer_type"] == "AI"
    assert evidence["source_metadata"]["sha256"] == (
        "51cec1e144a5bad8d92238630c0a305e20116e86d34ad95c7c315ed166255b28"
    )

    population = {
        **payload, "indicator_id": "SP.POP.TOTL",
        "series_key": {**payload["series_key"], "indicator": "SP.POP.TOTL"},
    }
    assert worldbank_metadata_evidence(population) == []
    assert normalize_worldbank_series(population).unit is None
    assert normalize_worldbank_series(population).currency is None

    provider_typed = {**payload, "unit": "provider-defined unit"}
    assert worldbank_metadata_evidence(provider_typed) == []
    assert normalize_worldbank_series(provider_typed).unit == "provider-defined unit"
    assert normalize_worldbank_series(provider_typed).currency is None


def test_boj_adapter_keeps_source_unit_and_daily_frequency():
    series = normalize_boj_series({
        "source_agency": "Bank of Japan", "dataset_id": "FM08",
        "series_id": "FXERD01", "unit": "US dollar per yen", "frequency": "D",
        "retrieved_at": NOW.isoformat(), "source_url": "https://www.stat-search.boj.or.jp/api/v1/getData",
        "raw_path": "data/raw/boj.json", "manifest_path": "data/raw/boj.manifest.json",
        "observations": [{"date": "2026-10-27", "value": 0},
                         {"date": "2026-10-26", "value": None}],
    })

    assert series.dataset_id == "FM08"
    assert series.series_id == "FXERD01"
    assert series.unit == "US dollar per yen"
    assert series.frequency == "daily"
    assert series.frequency_basis == "source_metadata"
    assert series.observations[1].status == ObservationStatus.MISSING


def test_bls_adapter_preserves_source_period_codes_and_unknown_metadata():
    series, = normalize_bls_series({
        "source_agency": "U.S. Bureau of Labor Statistics", "dataset_id": None,
        "series_ids": ["CUUR0000SA0"], "unit": None, "frequency": None,
        "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "raw_path": "data/raw/bls.json", "manifest_path": "data/raw/bls.manifest.json",
        "observations": [{"seriesID": "CUUR0000SA0", "data": [
            {"year": "2024", "period": "M01", "value": "0"},
            {"year": "2024", "period": "M02", "value": ""},
        ]}],
    })

    assert series.dataset_id is None
    assert series.series_id == "CUUR0000SA0"
    assert series.frequency == "monthly"
    assert series.frequency_basis == "period_format"
    assert series.observations[0].period == "2024-01"
    assert series.observations[0].source_period == "2024:M01"
    assert series.observations[0].raw_value == "0"
    assert series.observations[0].status == ObservationStatus.OBSERVED
    assert series.observations[1].raw_value == ""
    assert series.observations[1].status == ObservationStatus.MISSING
    assert series.unit is None and series.currency is None


def test_bls_adapter_marks_mixed_annual_average_and_month_periods_unknown():
    series, = normalize_bls_series({
        "source_agency": "U.S. Bureau of Labor Statistics", "dataset_id": None,
        "series_ids": ["CUUR0000SA0"], "unit": None, "frequency": None,
        "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "raw_path": "data/raw/bls.json", "manifest_path": "data/raw/bls.manifest.json",
        "observations": [{"seriesID": "CUUR0000SA0", "data": [
            {"year": "2024", "period": "M01", "value": "308.417"},
            {"year": "2024", "period": "M13", "value": "310.000"},
        ]}],
    })

    assert series.frequency is None
    assert series.frequency_basis == "unknown"
    assert [row.source_period for row in series.observations] == ["2024:M01", "2024:M13"]


def test_bls_adapter_normalizes_quarter_and_half_year_codes():
    quarterly, = normalize_bls_series({
        "source_agency": "U.S. Bureau of Labor Statistics", "dataset_id": None,
        "series_ids": ["CUUR0000SA0"], "unit": None, "frequency": None,
        "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "raw_path": "data/raw/bls.json", "manifest_path": "data/raw/bls.manifest.json",
        "observations": [{"seriesID": "CUUR0000SA0", "data": [
            {"year": "2024", "period": "Q01", "value": "1"},
            {"year": "2024", "period": "Q02", "value": "2"},
        ]}],
    })
    semiannual, = normalize_bls_series({
        "source_agency": "U.S. Bureau of Labor Statistics", "dataset_id": None,
        "series_ids": ["CUUR0000SA0"], "unit": None, "frequency": None,
        "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "raw_path": "data/raw/bls.json", "manifest_path": "data/raw/bls.manifest.json",
        "observations": [{"seriesID": "CUUR0000SA0", "data": [
            {"year": "2024", "period": "S01", "value": "1"},
        ]}],
    })

    assert [row.period for row in quarterly.observations] == ["2024-Q1", "2024-Q2"]
    assert quarterly.frequency == "quarterly"
    assert semiannual.observations[0].period == "2024-H1"
    assert semiannual.frequency == "semiannual"


def test_census_adapter_keeps_each_estimate_variable_and_geography_separate():
    series, = normalize_census_series({
        "source_agency": "U.S. Census Bureau", "dataset_id": "acs/acs1", "year": 2024,
        "variable_ids": ["NAME", "B01001_001E"], "geography": "us:1",
        "geography_dimensions": {"us": "1"}, "unit": None,
        "retrieved_at": NOW.isoformat(),
        "source_url": "https://api.census.gov/data/2024/acs/acs1",
        "raw_path": "data/raw/census.json", "manifest_path": "data/raw/census.manifest.json",
        "observations": [{"NAME": "United States", "us": "1", "B01001_001E": "0"}],
    })

    assert series.dataset_id == "acs/acs1"
    assert series.series_id == "B01001_001E"
    assert series.dimensions == {"us": "1"}
    assert series.observations[0].period == "2024"
    assert series.observations[0].source_period == "2024"
    assert series.observations[0].raw_value == "0"
    assert series.observations[0].status == ObservationStatus.OBSERVED
    assert series.frequency is None and series.unit is None and series.currency is None
