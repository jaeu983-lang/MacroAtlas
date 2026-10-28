"""Deterministic calendar-boundary and policy tests for frequency freshness."""
from datetime import UTC, date, datetime

import pytest

from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
    series_key_override_key,
)


@pytest.mark.parametrize(("frequency", "period", "fresh", "stale"), [
    ("daily", "2026-10-17", "FRESH", "2026-10-16"),
    ("weekly", "2026-W40", "FRESH", "2026-W39"),
    ("monthly", "2026-06", "FRESH", "2026-05"),
    ("quarterly", "2026-Q1", "FRESH", "2025-Q4"),
    ("semiannual", "2026-H1", "FRESH", "2025-H2"),
    ("annual", "2024", "FRESH", "2023"),
])
def test_frequency_specific_threshold_boundaries(frequency, period, fresh, stale):
    now = date(2026, 10, 24)
    fresh_result = assess_freshness([period], frequency=frequency, as_of=now)
    stale_result = assess_freshness([stale], frequency=frequency, as_of=now)
    assert fresh_result["status"] == FreshnessStatus.FRESH
    assert stale_result["status"] == FreshnessStatus.STALE
    assert fresh_result["policy_id"] == DEFAULT_FRESHNESS_POLICY.policy_id
    assert fresh_result["policy_basis"] == "frequency_fallback"
    assert len(fresh_result["policy_fingerprint_sha256"]) == 64
    assert fresh_result["age_days"] <= fresh_result["max_age_days"]
    assert stale_result["age_days"] > stale_result["max_age_days"]


def test_monthly_period_end_and_calendar_day_age_are_explicit():
    result = assess_freshness(["2026-06"], frequency="monthly", as_of=date(2026, 10, 24))
    assert result["period_end"] == "2026-06-30"
    assert result["age_days"] == 116
    assert result["status"] == FreshnessStatus.FRESH


def test_recent_retrieval_does_not_refresh_old_observation_period():
    result = assess_freshness(
        ["2022"], frequency="annual", as_of=datetime(2026, 10, 24, tzinfo=UTC),
    )
    assert result["status"] == FreshnessStatus.STALE
    assert result["latest_period"] == "2022"


def test_source_frequency_can_remain_unknown_while_period_resolution_is_used():
    result = assess_freshness(
        ["2026-10-20"], frequency=None, period_format="YYYY-MM-DD",
        as_of=date(2026, 10, 24),
    )
    assert result["status"] == FreshnessStatus.FRESH
    assert result["frequency"] == "daily"
    assert result["frequency_basis"] == "observation_period_format"


@pytest.mark.parametrize(("periods", "frequency", "period_format", "reason"), [
    (["2026-10-20"], None, None, "frequency_unknown"),
    ([], "daily", None, "observation_period_missing"),
    (["2026-02-30"], "daily", None, "observation_period_invalid"),
    (["2026-10-25"], "daily", None, "latest_observation_is_in_the_future"),
    (["2026"], "daily", None, "observation_period_invalid"),
])
def test_missing_or_invalid_freshness_evidence_is_unverified(
    periods, frequency, period_format, reason,
):
    result = assess_freshness(
        periods, frequency=frequency, period_format=period_format, as_of=date(2026, 10, 24),
    )
    assert result["status"] == FreshnessStatus.FRESHNESS_UNVERIFIED
    if reason in {"frequency_unknown", "frequency_tolerance_unconfigured"}:
        assert result["policy_basis"] == "unconfigured"
    assert result["reason"] == reason


def test_per_series_override_takes_precedence_and_is_recorded():
    key = {"country": "USA", "indicator": "NY.GDP.MKTP.CD", "source": "2"}
    override_key = series_key_override_key(key)
    policy = FreshnessPolicy(series_overrides={override_key: 1500})
    result = assess_freshness(
        ["2022"], frequency="annual", series_key=key, as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.FRESH
    assert result["max_age_days"] == 1500
    assert result["series_override_key"] == override_key
    assert result["policy_basis"] == "series_override"
    assert result["policy_id"] == policy.policy_id


def test_series_id_override_precedes_series_key_override():
    key = {"database": "FM08", "series_code": "FXERD01"}
    policy = FreshnessPolicy(series_overrides={
        "series_id:FXERD01": 1,
        series_key_override_key(key): 100,
    })
    result = assess_freshness(
        ["2026-10-20"], frequency="daily", series_id="FXERD01", series_key=key,
        as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.STALE
    assert result["series_override_key"] == "series_id:FXERD01"
    assert result["max_age_days"] == 1
    assert result["policy_basis"] == "series_override"


@pytest.mark.parametrize("value", [True, -1, 36501, 1.5])
def test_invalid_freshness_tolerance_is_rejected(value):
    with pytest.raises(ValueError, match="tolerance|override"):
        FreshnessPolicy(frequency_max_age_days={"daily": value})


def test_naive_evaluation_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_freshness(["2026-10-20"], frequency="daily",
                         as_of=datetime(2026, 10, 24))
