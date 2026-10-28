"""Adapters from verified provider payloads into the common typed time-series model."""
import re
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
        status = (ObservationStatus.MISSING if raw_value in {None, ""}
                  else ObservationStatus.OBSERVED)
        values.append(Observation(row[period_field], raw_value, status))
    return tuple(values)


_BLS_MONTH = re.compile(r"M(?:0[1-9]|1[0-2])\Z")
_BLS_QUARTER = re.compile(r"Q0[1-4]\Z")
_BLS_SEMIANNUAL = re.compile(r"S0[1-2]\Z")


def _bls_period(row: Mapping) -> tuple[str, str | None, str]:
    year, period = row.get("year"), row.get("period")
    if (not isinstance(year, str) or not re.fullmatch(r"[0-9]{4}", year)
            or not isinstance(period, str) or not period):
        raise ValueError("BLS observation period is invalid")
    source_period = f"{year}:{period}"
    if _BLS_MONTH.fullmatch(period):
        return f"{year}-{period[1:]}", "monthly", source_period
    if _BLS_QUARTER.fullmatch(period):
        return f"{year}-Q{period[1:]}", "quarterly", source_period
    if _BLS_SEMIANNUAL.fullmatch(period):
        return f"{year}-H{period[1:]}", "semiannual", source_period
    if period in {"A01", "M13"}:
        return year, "annual", source_period
    return source_period, None, source_period


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


def normalize_bls_series(payload: Mapping) -> tuple[TimeSeries, ...]:
    """Normalize BLS response rows per series while retaining source period codes."""
    if (not isinstance(payload, Mapping)
            or payload.get("source_agency") != "U.S. Bureau of Labor Statistics"):
        raise ValueError("expected a validated BLS payload")
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise TypeError("BLS payload observations must be a list")
    results = []
    for series in rows:
        if not isinstance(series, Mapping) or not isinstance(series.get("seriesID"), str):
            raise TypeError("BLS payload has an invalid series identity")
        source_rows = series.get("data")
        if not isinstance(source_rows, list):
            raise TypeError("BLS series data must be a list")
        if not source_rows:
            continue
        normalized = []
        frequencies = set()
        for row in source_rows:
            if not isinstance(row, Mapping) or "value" not in row:
                raise ValueError("BLS observation does not match the common contract")
            period, frequency, source_period = _bls_period(row)
            frequencies.add(frequency)
            raw_value = row["value"]
            status = (ObservationStatus.MISSING if raw_value in {None, ""}
                      else ObservationStatus.OBSERVED)
            normalized.append(Observation(period, raw_value, status, source_period))
        frequency = (next(iter(frequencies))
                     if len(frequencies) == 1 and None not in frequencies else None)
        results.append(TimeSeries(
            source_agency="U.S. Bureau of Labor Statistics",
            dataset_id=payload.get("dataset_id"),
            series_id=series["seriesID"],
            dimensions={},
            calendar="gregorian",
            observations=tuple(normalized),
            retrieved_at=_retrieved_at(payload),
            source_url=payload.get("source_url"),
            raw_ref=payload.get("raw_path"),
            manifest_ref=payload.get("manifest_path"),
            unit=payload.get("unit"),
            currency=None,
            frequency=frequency,
            frequency_basis=("period_format" if frequency else "unknown"),
            source_revision=payload.get("source_version"),
        ))
    return tuple(results)


def normalize_census_series(payload: Mapping) -> tuple[TimeSeries, ...]:
    """Normalize Census estimates per requested variable and geography without metadata guesses."""
    if (not isinstance(payload, Mapping)
            or payload.get("source_agency") != "U.S. Census Bureau"):
        raise ValueError("expected a validated Census payload")
    dataset, year = payload.get("dataset_id"), payload.get("year")
    if not isinstance(dataset, str) or type(year) is not int:
        raise ValueError("Census payload has an invalid dataset or reference year")
    variables = payload.get("variable_ids")
    rows = payload.get("observations")
    dimensions = payload.get("geography_dimensions")
    if (not isinstance(variables, list) or not isinstance(rows, list) or not rows
            or not isinstance(dimensions, Mapping)):
        raise ValueError("Census payload is missing variables, geography or observations")
    results = []
    for variable in variables:
        if variable == "NAME":
            continue
        if not isinstance(variable, str) or not variable:
            raise ValueError("Census variable identity is invalid")
        observations = []
        for row in rows:
            if not isinstance(row, Mapping) or variable not in row:
                raise ValueError("Census observation does not match the common contract")
            raw_value = row[variable]
            status = (ObservationStatus.MISSING if raw_value in {None, ""}
                      else ObservationStatus.OBSERVED)
            observations.append(Observation(str(year), raw_value, status, str(year)))
        results.append(TimeSeries(
            source_agency="U.S. Census Bureau",
            dataset_id=dataset,
            series_id=variable,
            dimensions={str(key): str(value) for key, value in dimensions.items()},
            calendar="gregorian",
            observations=tuple(observations),
            retrieved_at=_retrieved_at(payload),
            source_url=payload.get("source_url"),
            raw_ref=payload.get("raw_path"),
            manifest_ref=payload.get("manifest_path"),
            unit=payload.get("unit"),
            currency=None,
            frequency=None,
            frequency_basis="unknown",
            source_revision=payload.get("source_version"),
        ))
    return tuple(results)
