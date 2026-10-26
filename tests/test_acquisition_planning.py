"""Bounded acquisition plans describe work without performing network requests."""

import pytest

from macro_data_platform.connectors.worldbank import INDICATOR
from macro_data_platform.ingestion.acquisition_planning import plan_source_collection


def test_worldbank_plan_splits_years_and_leaves_size_unknown():
    plan = plan_source_collection(
        "worldbank_gdp",
        {"country": "USA", "indicator": INDICATOR, "start_year": 2000, "end_year": 2020},
    )

    assert plan["chunk_count"] == 3
    assert [chunk["input_data"] for chunk in plan["chunks"]] == [
        {"start_year": 2000, "end_year": 2009},
        {"start_year": 2010, "end_year": 2019},
        {"start_year": 2020, "end_year": 2020},
    ]
    assert plan["expected_size_state"] == "unknown"
    assert plan["expected_size_bytes"] is None
    assert plan["network_requests_made"] == 0


def test_bls_plan_splits_series_and_inclusive_year_windows():
    series = [f"SERIES{index:04d}" for index in range(21)]
    plan = plan_source_collection(
        "bls", {"series_ids": series, "start_year": 2000, "end_year": 2020},
        expected_size_bytes=12345,
    )

    assert plan["chunk_count"] == 4
    assert [len(chunk["input_data"]["series_ids"]) for chunk in plan["chunks"]] == [20, 20, 1, 1]
    assert [
        (chunk["input_data"]["start_year"], chunk["input_data"]["end_year"])
        for chunk in plan["chunks"]
    ] == [(2000, 2019), (2020, 2020), (2000, 2019), (2020, 2020)]
    assert plan["expected_size_state"] == "known_from_caller"


def test_census_plan_splits_variables_and_geographies_with_name():
    variables = [f"B01001_{index:03d}E" for index in range(51)]
    plan = plan_source_collection(
        "census",
        {"year": 2022, "dataset": "acs/acs1", "variables": variables,
         "geographies": ["state:06", "state:36"]},
    )

    assert plan["chunk_count"] == 4
    assert [chunk["input_data"]["geography"] for chunk in plan["chunks"]] == [
        "state:06", "state:06", "state:36", "state:36",
    ]
    assert [len(chunk["input_data"]["variables"]) for chunk in plan["chunks"]] == [
        50, 3, 50, 3,
    ]
    assert all(chunk["input_data"]["variables"][0] == "NAME" for chunk in plan["chunks"])


def test_sample_plan_uses_first_explicit_series_and_year():
    plan = plan_source_collection(
        "bls", {"series_ids": ["CUUR0000SA0", "CES0000000001"],
                "start_year": 2020, "end_year": 2024}, mode="sample",
    )

    assert plan["chunk_count"] == 1
    assert plan["sample_policy"] == "first_requested_series_and_year"
    assert plan["chunks"][0]["input_data"] == {
        "series_ids": ["CUUR0000SA0"], "start_year": 2020, "end_year": 2020,
    }


@pytest.mark.parametrize("payload", [
    {"series_ids": [["not", "hashable"]], "start_year": 2020, "end_year": 2020},
    {"series_ids": ["OK", "OK"], "start_year": 2020, "end_year": 2020},
])
def test_bls_rejects_malformed_or_duplicate_inputs(payload):
    with pytest.raises(ValueError):
        plan_source_collection("bls", payload)


@pytest.mark.parametrize("payload", [
    {"year": 2022, "dataset": "acs/acs1", "variables": [["BAD"]],
     "geographies": ["state:06"]},
    {"year": 2022, "dataset": "acs/acs1", "variables": ["B01001_001E"],
     "geographies": [["state:06"]]},
])
def test_census_rejects_malformed_inputs(payload):
    with pytest.raises(ValueError):
        plan_source_collection("census", payload)


def test_plan_rejects_unsupported_output_and_chunk_overflow():
    with pytest.raises(ValueError, match="raw_json"):
        plan_source_collection(
            "worldbank_gdp",
            {"country": "USA", "indicator": INDICATOR, "start_year": 2000, "end_year": 2020},
            output_format="xlsx",
        )
    with pytest.raises(ValueError, match="chunk count"):
        plan_source_collection(
            "worldbank_gdp",
            {"country": "USA", "indicator": INDICATOR, "start_year": 2000, "end_year": 2020},
            max_chunks=2,
        )
