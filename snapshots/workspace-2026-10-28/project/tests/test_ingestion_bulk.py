from __future__ import annotations

import pytest

from macro_data_platform.ingestion.bulk import (
    CollectionBudget,
    build_collection_plan,
)


def plan(**overrides):
    values = {
        "series_ids": ("GDP",),
        "countries": ("USA",),
        "period_start": "2020-01",
        "period_end": "2020-05",
        "frequency": "monthly",
        "mode": "full",
    }
    values.update(overrides)
    return build_collection_plan(**values)


def test_collection_mode_must_be_selected_before_units_are_planned():
    result = plan(mode=None)

    assert result.mode is None
    assert result.units == ()
    assert result.total_requests == result.omitted_requests == 0
    assert result.planned_requests == 0
    assert result.estimated_observations == 0
    assert result.estimated_bytes is result.estimated_seconds is None
    assert result.questions == ("collection_mode",)
    assert result.requires_confirmation


def test_sample_and_full_plans_have_distinct_explicit_period_scopes():
    sample = plan(mode="sample", sample_periods=2)
    full = plan(mode="full")

    assert (sample.units[0].period_start, sample.units[0].period_end,
            sample.units[0].period_count) == ("2020-01", "2020-02", 2)
    assert (full.units[0].period_start, full.units[0].period_end,
            full.units[0].period_count) == ("2020-01", "2020-05", 5)
    assert sample.estimated_observations == 2
    assert full.estimated_observations == 5
    assert sample.questions == full.questions == ("confirm_collection_plan",)


def test_plan_chunks_country_and_period_ranges_with_stable_boundaries():
    countries = tuple(f"C{i:02}" for i in range(11))
    result = plan(countries=countries, period_start="2000", period_end="2120",
                  frequency="annual")

    assert result.total_requests == result.planned_requests == 4
    assert result.omitted_requests == 0
    assert [(len(unit.countries), unit.period_start, unit.period_end,
             unit.period_count) for unit in result.units] == [
        (10, "2000", "2119", 120),
        (10, "2120", "2120", 1),
        (1, "2000", "2119", 120),
        (1, "2120", "2120", 1),
    ]
    assert result.estimated_observations == 1_331


def test_budget_truncation_reports_omitted_units_without_exceeding_limit():
    result = plan(
        countries=tuple(f"C{i:02}" for i in range(11)),
        period_start="2000",
        period_end="2120",
        frequency="annual",
        budget=CollectionBudget(max_requests=2, max_observations=100_000,
                                max_bytes=1_000_000, max_seconds=600),
    )

    assert result.planned_requests == 2
    assert result.omitted_requests == 2
    assert result.estimated_observations == 1_210
    assert "plan_truncated_by_budget" in result.warnings


@pytest.mark.parametrize(
    ("budget", "bytes_per_observation", "seconds_per_request"),
    [
        (CollectionBudget(max_requests=10, max_observations=4,
                          max_bytes=1_000, max_seconds=600), None, None),
        (CollectionBudget(max_requests=10, max_observations=100,
                          max_bytes=9, max_seconds=600), 2, None),
        (CollectionBudget(max_requests=10, max_observations=100,
                          max_bytes=1_000, max_seconds=1), None, 2.0),
    ],
)
def test_observation_byte_and_time_budgets_bound_the_plan(
    budget, bytes_per_observation, seconds_per_request
):
    result = plan(
        budget=budget,
        bytes_per_observation=bytes_per_observation,
        seconds_per_request=seconds_per_request,
    )

    assert result.planned_requests == 0
    assert result.omitted_requests == result.total_requests == 1
    assert "plan_truncated_by_budget" in result.warnings


def test_unknown_resource_estimates_remain_unknown():
    result = plan()

    assert result.estimated_bytes is None
    assert result.estimated_seconds is None
    assert "estimated_bytes_unknown" in result.warnings
    assert "estimated_time_unknown" in result.warnings


@pytest.mark.parametrize(
    ("start", "end", "frequency"),
    [
        ("2020-00", "2020-03", "monthly"),
        ("2020-Q1", "2019-Q4", "quarterly"),
        ("2021-02-30", "2021-03-01", "daily"),
        ("2020", "2021", "weekly"),
    ],
)
def test_invalid_or_reversed_period_ranges_are_rejected(start, end, frequency):
    with pytest.raises(ValueError):
        plan(period_start=start, period_end=end, frequency=frequency)


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "all"},
        {"sample_periods": 0},
        {"series_ids": ()},
        {"countries": ("USA", "USA")},
        {"bytes_per_observation": 0},
        {"seconds_per_request": float("inf")},
    ],
)
def test_invalid_collection_selection_or_estimates_are_rejected(overrides):
    with pytest.raises(ValueError):
        plan(**overrides)


@pytest.mark.parametrize(
    "values",
    [
        {"max_requests": 0},
        {"max_observations": 0},
        {"max_bytes": 0},
        {"max_seconds": 0},
        {"max_requests": 1.5},
    ],
)
def test_invalid_collection_budgets_are_rejected(values):
    defaults = {"max_requests": 10, "max_observations": 100,
                "max_bytes": 1_000, "max_seconds": 60}
    defaults.update(values)

    with pytest.raises(ValueError):
        CollectionBudget(**defaults)
