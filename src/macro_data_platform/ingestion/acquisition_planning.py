"""Plan bounded sample/full API requests without issuing network calls."""
import re

from macro_data_platform.connectors.bls import BLSQuery
from macro_data_platform.connectors.census import CensusQuery
from macro_data_platform.connectors.worldbank import INDICATOR, GDPQuery

MAX_PLAN_CHUNKS = 1000
MAX_IDENTIFIERS = 1000
_SERIES = re.compile(r"^[A-Z0-9]{2,30}$")
_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")


def _year_range(request: dict) -> tuple[int, int]:
    start, end = request.get("start_year"), request.get("end_year")
    if (type(start) is not int or type(end) is not int
            or not 1900 <= start <= end <= 2100):
        raise ValueError("year range must contain integer bounds from 1900..2100")
    return start, end


def _year_windows(start: int, end: int, width: int) -> list[tuple[int, int]]:
    result = []
    cursor = start
    while cursor <= end:
        last = min(end, cursor + width - 1)
        result.append((cursor, last))
        cursor = last + 1
    return result


def _groups(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def plan_source_collection(source: str, request: dict, *, mode: str = "full",
                           output_format: str = "raw_json",
                           expected_size_bytes: int | None = None,
                           max_chunks: int = MAX_PLAN_CHUNKS) -> dict:
    """Split only documented source inputs; return an estimate as unknown when absent.

    A sample plan selects the first explicitly supplied identifier/geography and first year.
    The function is planning-only and never downloads data.
    """
    if source not in {"worldbank_gdp", "bls", "census"}:
        raise ValueError("no bounded planner is registered for this source")
    if not isinstance(request, dict):
        raise TypeError("request must be an object")
    if mode not in {"sample", "full"}:
        raise ValueError("mode must be sample or full")
    if output_format != "raw_json":
        raise ValueError("only the implemented raw_json output is supported")
    if (type(max_chunks) is not int or not 1 <= max_chunks <= MAX_PLAN_CHUNKS
            or (expected_size_bytes is not None
                and (type(expected_size_bytes) is not int or expected_size_bytes < 0))):
        raise ValueError("invalid chunk or size estimate limit")

    chunks: list[tuple[dict, tuple]] = []
    split_axes: tuple[str, ...]
    sample_policy = None
    if source == "worldbank_gdp":
        if (request.get("country") != "USA" or request.get("indicator") != INDICATOR):
            raise ValueError("only the implemented USA WDI GDP path can be planned")
        start, end = _year_range(request)
        if mode == "sample":
            end = start
            sample_policy = "first_requested_year"
        windows = _year_windows(start, end, 10)
        for window in windows:
            GDPQuery(*window)
            chunks.append(({"start_year": window[0], "end_year": window[1]}, window))
        split_axes = ("year_window",)
    elif source == "bls":
        series = request.get("series_ids")
        if (not isinstance(series, list) or not 1 <= len(series) <= MAX_IDENTIFIERS
                or not all(isinstance(value, str) and _SERIES.fullmatch(value) for value in series)
                or len(set(series)) != len(series)):
            raise ValueError("BLS planner requires 1..1000 unique valid series IDs")
        start, end = _year_range(request)
        if mode == "sample":
            series, end = series[:1], start
            sample_policy = "first_requested_series_and_year"
        for group in _groups(series, 20):
            for window in _year_windows(start, end, 20):
                BLSQuery(tuple(group), *window)
                chunks.append(({
                    "series_ids": group, "start_year": window[0], "end_year": window[1],
                }, (group[0], window)))
        split_axes = ("series_ids", "year_window")
    else:
        year, dataset = request.get("year"), request.get("dataset")
        variables, geographies = request.get("variables"), request.get("geographies")
        if type(year) is not int or not isinstance(variables, list) or not isinstance(geographies, list):
            raise ValueError("Census planner requires a reference year, variables and geographies")
        source_variables = [item for item in variables if item != "NAME"]
        if (not 1 <= len(source_variables) <= MAX_IDENTIFIERS
                or not all(isinstance(value, str) and _VARIABLE.fullmatch(value)
                           for value in source_variables)
                or len(set(variables)) != len(variables)
                or not 1 <= len(geographies) <= MAX_IDENTIFIERS
                or not all(isinstance(value, str) for value in geographies)
                or len(set(geographies)) != len(geographies)):
            raise ValueError("Census planner requires unique variable and geography selections")
        if mode == "sample":
            source_variables, geographies = source_variables[:1], geographies[:1]
            sample_policy = "first_requested_variable_and_geography"
        variable_groups = _groups(source_variables, 49)
        for geography in geographies:
            for group in variable_groups:
                variables_for_call = ["NAME", *group]
                CensusQuery(year, dataset, tuple(variables_for_call), geography)
                chunks.append(({
                    "year": year, "dataset": dataset,
                    "variables": variables_for_call, "geography": geography,
                }, (geography, group[0])))
        split_axes = ("variables", "geography")

    if not chunks or len(chunks) > max_chunks:
        raise ValueError("planned chunk count is empty or exceeds the configured limit")
    return {
        "source": source, "mode": mode, "output_format": output_format,
        "split_axes": list(split_axes), "chunk_count": len(chunks),
        "chunks": [
            {"chunk_id": f"{source}:{index + 1:04d}",
             "engine": "worldbank_gdp" if source == "worldbank_gdp" else source,
             "input_data": inputs}
            for index, (inputs, _) in enumerate(chunks)
        ],
        "expected_size_bytes": expected_size_bytes,
        "expected_size_state": "known_from_caller" if expected_size_bytes is not None else "unknown",
        "sample_policy": sample_policy,
        "network_requests_made": 0,
    }
