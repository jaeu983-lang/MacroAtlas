"""Deterministic calendar-boundary and policy tests for frequency freshness."""
from datetime import UTC, date, datetime

import pytest

from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessEvidence,
    FreshnessEvidenceReviewStatus,
    FreshnessEvidenceType,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
    series_key_override_key,
)


def approved_evidence(evidence_id="fixture-evidence"):
    return FreshnessEvidence(
        evidence_id=evidence_id,
        source_url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        source_sha256="a" * 64,
        captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        evidence_type=FreshnessEvidenceType.OFFICIAL_FREQUENCY_METADATA,
        citation="Fixture metadata record used for policy behavior tests",
        review_status=FreshnessEvidenceReviewStatus.APPROVED,
        reviewer_id="test-reviewer",
        reviewed_at=datetime(2026, 10, 2, tzinfo=UTC),
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
    policy = FreshnessPolicy(
        series_overrides={override_key: 1500},
        series_evidence={override_key: approved_evidence()},
    )
    result = assess_freshness(
        ["2022"], frequency="annual", series_key=key, as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.FRESH
    assert result["max_age_days"] == 1500
    assert result["series_override_key"] == override_key
    assert result["policy_basis"] == "series_override"
    assert result["policy_id"] == policy.policy_id
    assert result["policy_evidence_status"] == "approved"
    assert result["policy_evidence"]["source_sha256"] == "a" * 64


def test_series_id_override_precedes_series_key_override():
    key = {"database": "FM08", "series_code": "FXERD01"}
    policy = FreshnessPolicy(series_overrides={
        "series_id:FXERD01": 1,
        series_key_override_key(key): 100,
    }, series_evidence={"series_id:FXERD01": approved_evidence("boj-evidence")})
    result = assess_freshness(
        ["2026-10-20"], frequency="daily", series_id="FXERD01", series_key=key,
        as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.STALE
    assert result["series_override_key"] == "series_id:FXERD01"
    assert result["max_age_days"] == 1
    assert result["policy_basis"] == "series_override"


def test_exact_override_without_evidence_fails_closed():
    key = {"country": "USA", "indicator": "NY.GDP.MKTP.CD", "source": "2"}
    override_key = series_key_override_key(key)
    policy = FreshnessPolicy(series_overrides={override_key: 1500})
    result = assess_freshness(
        ["2022"], frequency="annual", series_key=key, as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.FRESHNESS_UNVERIFIED
    assert result["policy_evidence_status"] == "missing"
    assert result["reason"] == "series_override_evidence_missing"


def test_pending_exact_override_evidence_does_not_activate_policy():
    key = "series_id:CPI"
    evidence = FreshnessEvidence(
        evidence_id="pending-cpi-evidence",
        source_url="https://www.bls.gov/cpi/",
        source_sha256="b" * 64,
        captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        evidence_type="official_release_calendar",
        citation="Release calendar",
    )
    policy = FreshnessPolicy(series_overrides={key: 3650}, series_evidence={key: evidence})
    result = assess_freshness(
        ["2024"], frequency="annual", series_id="CPI", as_of=date(2026, 10, 24), policy=policy,
    )
    assert result["status"] == FreshnessStatus.FRESHNESS_UNVERIFIED
    assert result["policy_evidence_status"] == "pending_review"
    assert result["reason"] == "series_override_evidence_pending_review"


def test_evidence_is_bound_to_policy_fingerprint_and_override():
    override = "series_id:monthly-series"
    first = FreshnessPolicy(
        series_overrides={override: 120},
        series_evidence={override: approved_evidence("first")},
    )
    second = FreshnessPolicy(
        series_overrides={override: 120},
        series_evidence={override: approved_evidence("second")},
    )
    assert first.fingerprint_sha256 != second.fingerprint_sha256
    with pytest.raises(ValueError, match="match an exact-series override"):
        FreshnessPolicy(series_evidence={override: approved_evidence()})


@pytest.mark.parametrize("kwargs", [
    {"source_url": "http://example.org/calendar"},
    {"source_url": "https://user:secret@example.org/calendar"},
    {"source_url": "https://example.org/calendar?token=secret"},
    {"source_sha256": "not-a-hash"},
    {"captured_at": datetime(2026, 10, 1)},
    {
        "review_status": "approved",
        "reviewer_id": "reviewer",
        "reviewed_at": datetime(2026, 9, 1, tzinfo=UTC),
    },
])
def test_invalid_freshness_source_evidence_is_rejected(kwargs):
    values = {
        "evidence_id": "bad-evidence",
        "source_url": "https://example.org/calendar",
        "source_sha256": "c" * 64,
        "captured_at": datetime(2026, 10, 1, tzinfo=UTC),
        "evidence_type": "official_release_calendar",
        "citation": "Official release calendar",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        FreshnessEvidence(**values)


@pytest.mark.parametrize("value", [True, -1, 36501, 1.5])
def test_invalid_freshness_tolerance_is_rejected(value):
    with pytest.raises(ValueError, match="tolerance|override"):
        FreshnessPolicy(frequency_max_age_days={"daily": value})


def test_naive_evaluation_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_freshness(["2026-10-20"], frequency="daily",
                         as_of=datetime(2026, 10, 24))
