from datetime import UTC, datetime

import pytest

from macro_data_platform.contracts import (
    Observation,
    ObservationStatus,
    TimeSeries,
)
from macro_data_platform.metadata.series import (
    normalize_boj_series,
    normalize_worldbank_series,
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
        {"period": "2025", "raw_value": 0, "status": "observed"},
        {"period": "2024", "raw_value": None, "status": "missing"},
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
