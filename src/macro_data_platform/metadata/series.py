"""Adapters from verified provider payloads into the common typed time-series model."""
from collections.abc import Mapping
from datetime import datetime

from macro_data_platform.contracts import Observation, ObservationStatus, TimeSeries
from macro_data_platform.ingestion.freshness import (
    frequency_from_period_format,
    normalize_frequency,
)


def _retrieved_at(payload: Mapping) -> datetime:
    value = payload.get("retrieved_at")
    if not isinstance(value, str):
        raise TypeError("provider payload must contain retrieved_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("provider payload retrieved_at is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("provider payload retrieved_at must be timezone-aware")
    return parsed


def _observations(rows: object, *, period_field: str) -> tuple[Observation, ...]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("provider payload must contain observations")
    values = []
    for row in rows:
        if not isinstance(row, Mapping) or period_field not in row or "value" not in row:
            raise ValueError("provider observation does not match the common contract")
        if not isinstance(row[period_field], str):
            raise TypeError("provider observation period must be a string")
        raw_value = row["value"]
        status = (ObservationStatus.MISSING if raw_value is None
                  else ObservationStatus.OBSERVED)
        values.append(Observation(row[period_field], raw_value, status))
    return tuple(values)


def normalize_worldbank_series(payload: Mapping) -> TimeSeries:
    """Normalize a validated annual WDI payload without inferring its unit or currency."""
    if not isinstance(payload, Mapping) or payload.get("source_agency") != "World Bank":
        raise ValueError("expected a validated World Bank payload")
    key = payload.get("series_key")
    if not isinstance(key, Mapping):
        raise TypeError("World Bank payload is missing its series identity")
    indicator = payload.get("indicator_id")
    source = payload.get("dataset_id")
    country = key.get("country")
    if not all(isinstance(value, str) and value for value in (indicator, source, country)):
        raise ValueError("World Bank payload has incomplete series identity")
    frequency = normalize_frequency(payload.get("frequency"))
    basis = "source_metadata" if frequency else None
    if frequency is None:
        frequency = frequency_from_period_format(payload.get("period_format"))
        basis = "period_format" if frequency else None
    return TimeSeries(
        source_agency="World Bank",
        dataset_id=source,
        series_id=indicator,
        dimensions={"country_iso3": country},
        calendar="gregorian",
        observations=_observations(payload.get("observations"), period_field="date"),
        retrieved_at=_retrieved_at(payload),
        source_url=payload.get("source_url"),
        raw_ref=payload.get("raw_path"),
        manifest_ref=payload.get("manifest_path"),
        unit=payload.get("unit"),
        currency=None,
        frequency=frequency,
        frequency_basis=basis or "unknown",
        source_revision=payload.get("source_version"),
    )


def normalize_boj_series(payload: Mapping) -> TimeSeries:
    """Normalize the verified BOJ FX series while preserving source unit and null rows."""
    if (not isinstance(payload, Mapping) or payload.get("source_agency") != "Bank of Japan"
            or payload.get("metadata_status") not in (None, "verified")):
        raise ValueError("expected a verified BOJ payload")
    dataset = payload.get("dataset_id")
    series = payload.get("series_id")
    if not all(isinstance(value, str) and value for value in (dataset, series)):
        raise ValueError("BOJ payload has incomplete series identity")
    frequency = normalize_frequency(payload.get("frequency"))
    return TimeSeries(
        source_agency="Bank of Japan",
        dataset_id=dataset,
        series_id=series,
        dimensions={},
        calendar="gregorian",
        observations=_observations(payload.get("observations"), period_field="date"),
        retrieved_at=_retrieved_at(payload),
        source_url=payload.get("source_url"),
        raw_ref=payload.get("raw_path"),
        manifest_ref=payload.get("manifest_path"),
        unit=payload.get("unit"),
        currency=None,
        frequency=frequency,
        frequency_basis="source_metadata" if frequency else "unknown",
        source_revision=None,
    )
