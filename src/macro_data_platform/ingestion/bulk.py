"""Explicit, bounded sample/full collection planning; this module never executes a plan."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

MAX_SERIES = 200
MAX_COUNTRIES = 1_000
MAX_PERIODS = 100_000
MAX_PLAN_REQUESTS = 500
COUNTRIES_PER_UNIT = 10
PERIODS_PER_UNIT = 120


@dataclass(frozen=True)
class CollectionBudget:
    max_requests: int = 100
    max_observations: int = 500_000
    max_bytes: int = 64 * 1024 * 1024
    max_seconds: int = 600

    def __post_init__(self):
        if (type(self.max_requests) is not int or not 1 <= self.max_requests <= MAX_PLAN_REQUESTS
                or type(self.max_observations) is not int or self.max_observations < 1
                or type(self.max_bytes) is not int or self.max_bytes < 1
                or type(self.max_seconds) is not int or self.max_seconds < 1):
            raise ValueError("collection budgets must be positive and within the request limit")


@dataclass(frozen=True)
class CollectionUnit:
    series_id: str
    countries: tuple[str, ...]
    period_start: str
    period_end: str
    period_count: int

    @property
    def estimated_observations(self):
        return self.period_count * len(self.countries)


@dataclass(frozen=True)
class CollectionPlan:
    mode: str | None
    units: tuple[CollectionUnit, ...]
    total_requests: int
    planned_requests: int
    omitted_requests: int
    estimated_observations: int
    estimated_bytes: int | None
    estimated_seconds: float | None
    questions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_confirmation: bool = True
    budget: CollectionBudget = field(default_factory=CollectionBudget)
    series_ids: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    period_start: str | None = None
    period_end: str | None = None
    frequency: str | None = None


def _period_list(start: str, end: str, frequency: str) -> list[str]:
    patterns = {
        "annual": r"(\d{4})",
        "quarterly": r"(\d{4})-Q([1-4])",
        "monthly": r"(\d{4})-(\d{2})",
        "daily": r"(\d{4})-(\d{2})-(\d{2})",
    }
    pattern = patterns.get(frequency)
    if pattern is None:
        raise ValueError("unsupported collection frequency")
    first, last = re.fullmatch(pattern, start), re.fullmatch(pattern, end)
    if first is None or last is None:
        raise ValueError("periods do not match the declared source frequency")
    if frequency == "annual":
        lo, hi = int(first[1]), int(last[1])
        count = hi - lo + 1
        value = lambda index: str(index)
        low, high = lo, hi
    elif frequency == "quarterly":
        low = int(first[1]) * 4 + int(first[2]) - 1
        high = int(last[1]) * 4 + int(last[2]) - 1
        count = high - low + 1
        value = lambda index: f"{index // 4:04}-Q{index % 4 + 1}"
    elif frequency == "monthly":
        low = int(first[1]) * 12 + int(first[2]) - 1
        high = int(last[1]) * 12 + int(last[2]) - 1
        count = high - low + 1
        value = lambda index: f"{index // 12:04}-{index % 12 + 1:02}"
        if not 1 <= int(first[2]) <= 12 or not 1 <= int(last[2]) <= 12:
            raise ValueError("invalid month in collection period")
    else:
        try:
            first_date = date(int(first[1]), int(first[2]), int(first[3]))
            last_date = date(int(last[1]), int(last[2]), int(last[3]))
        except ValueError:
            raise ValueError("invalid day in collection period") from None
        count = (last_date - first_date).days + 1
        low = 0
        value = lambda index: (first_date + timedelta(days=index)).isoformat()
        high = count - 1
    if count < 1 or count > MAX_PERIODS:
        raise ValueError("collection period range is empty or exceeds the planning limit")
    if frequency != "daily" and high < low:
        raise ValueError("collection period range is reversed")
    return [value(index) for index in range(low, high + 1)]


def build_collection_plan(*, series_ids, countries, period_start, period_end, frequency,
                          mode: str | None = None, sample_periods: int = 3,
                          bytes_per_observation: int | None = None,
                          seconds_per_request: float | None = None,
                          budget: CollectionBudget | None = None) -> CollectionPlan:
    """Return a bounded plan; a caller must ask and record explicit confirmation before execution."""
    if budget is None:
        budget = CollectionBudget()
    if mode not in {None, "sample", "full"}:
        raise ValueError("collection mode must be sample or full")
    if type(sample_periods) is not int or not 1 <= sample_periods <= PERIODS_PER_UNIT:
        raise ValueError("sample period count is outside the supported range")
    for name, values, maximum in (("series", series_ids, MAX_SERIES),
                                  ("country", countries, MAX_COUNTRIES)):
        if (not isinstance(values, (tuple, list)) or not 1 <= len(values) <= maximum
                or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"invalid or excessive {name} selection")
    if (bytes_per_observation is not None and
            (type(bytes_per_observation) is not int or bytes_per_observation < 1)):
        raise ValueError("byte estimate must be a positive integer or unknown")
    if (seconds_per_request is not None and
            (type(seconds_per_request) not in {int, float} or
             not math.isfinite(seconds_per_request) or seconds_per_request <= 0)):
        raise ValueError("request-time estimate must be positive and finite or unknown")
    periods = _period_list(period_start, period_end, frequency)
    if mode is None:
        return CollectionPlan(None, (), 0, 0, 0, 0, None, None,
                              ("collection_mode",), ("sample_or_full_scope_not_selected",),
                              budget=budget, series_ids=tuple(series_ids),
                              countries=tuple(countries), period_start=period_start,
                              period_end=period_end, frequency=frequency)

    chosen_periods = periods[:sample_periods] if mode == "sample" else periods
    period_chunks = [chosen_periods[index:index + PERIODS_PER_UNIT]
                     for index in range(0, len(chosen_periods), PERIODS_PER_UNIT)]
    country_chunks = [tuple(countries[index:index + COUNTRIES_PER_UNIT])
                      for index in range(0, len(countries), COUNTRIES_PER_UNIT)]
    total_requests = len(series_ids) * len(country_chunks) * len(period_chunks)
    units = []
    observations = 0
    stopped_by_budget = False
    for series_id in series_ids:
        for country_group in country_chunks:
            for period_group in period_chunks:
                unit = CollectionUnit(series_id, country_group, period_group[0],
                                      period_group[-1], len(period_group))
                unit_observations = unit.estimated_observations
                next_count = len(units) + 1
                if next_count > budget.max_requests or observations + unit_observations > budget.max_observations:
                    stopped_by_budget = True
                    break
                next_bytes = ((observations + unit_observations) * bytes_per_observation
                              if bytes_per_observation is not None else None)
                if next_bytes is not None and next_bytes > budget.max_bytes:
                    stopped_by_budget = True
                    break
                if seconds_per_request is not None and next_count * seconds_per_request > budget.max_seconds:
                    stopped_by_budget = True
                    break
                units.append(unit)
                observations += unit_observations
            if stopped_by_budget:
                break
        if stopped_by_budget:
            break
    planned = len(units)
    omitted = total_requests - planned
    warnings = []
    if omitted:
        warnings.append("plan_truncated_by_budget")
    if bytes_per_observation is None:
        warnings.append("estimated_bytes_unknown")
    if seconds_per_request is None:
        warnings.append("estimated_time_unknown")
    expected_bytes = observations * bytes_per_observation if bytes_per_observation is not None else None
    expected_seconds = planned * seconds_per_request if seconds_per_request is not None else None
    return CollectionPlan(mode, tuple(units), total_requests, planned, omitted, observations,
                          expected_bytes, expected_seconds, ("confirm_collection_plan",),
                          tuple(warnings), budget=budget, series_ids=tuple(series_ids),
                          countries=tuple(countries), period_start=period_start,
                          period_end=period_end, frequency=frequency)
