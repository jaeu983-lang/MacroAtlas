"""Frequency-aware freshness checks for source observation periods.

Freshness is based on the newest observed period, never on retrieval or source refresh time.
"""
import hashlib
import json
import re
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlsplit

DEFAULT_MAX_AGE_DAYS = {
    "daily": 7,
    "weekly": 21,
    "monthly": 120,
    "quarterly": 240,
    "semiannual": 183,
    "annual": 730,
}
DEFAULT_POLICY_ID = "frequency_max_age_v2"
_FORMAT_FREQUENCIES = {
    "YYYY": "annual",
    "YYYY-MM": "monthly",
    "YYYY-MM-DD": "daily",
    "YYYY-Www": "weekly",
    "YYYY-Qn": "quarterly",
    "YYYY-Hn": "semiannual",
}


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    FRESHNESS_UNVERIFIED = "FRESHNESS_UNVERIFIED"


class FreshnessEvidenceType(StrEnum):
    OFFICIAL_RELEASE_CALENDAR = "official_release_calendar"
    OFFICIAL_FREQUENCY_METADATA = "official_frequency_metadata"
    DOCUMENTED_RELEASE_LAG = "documented_release_lag"


class FreshnessEvidenceReviewStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class FreshnessEvidence:
    """Reference and review record for an exact-series freshness tolerance.

    The URL and digest identify evidence captured by an operator. This model
    does not fetch or independently verify the referenced document.
    """

    evidence_id: str
    source_url: str
    source_sha256: str
    captured_at: datetime
    evidence_type: FreshnessEvidenceType | str
    citation: str
    review_status: FreshnessEvidenceReviewStatus | str = (
        FreshnessEvidenceReviewStatus.PENDING_REVIEW
    )
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be nonempty")
        if not isinstance(self.source_url, str):
            raise TypeError("source_url must be an HTTPS URL")
        parsed = urlsplit(self.source_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("source_url must be credential-free HTTPS without query or fragment")
        if (not isinstance(self.source_sha256, str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", self.source_sha256) is None):
            raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
        if not isinstance(self.evidence_type, FreshnessEvidenceType):
            try:
                object.__setattr__(self, "evidence_type", FreshnessEvidenceType(self.evidence_type))
            except (TypeError, ValueError) as exc:
                raise ValueError("unsupported freshness evidence_type") from exc
        if not isinstance(self.citation, str) or not self.citation.strip():
            raise ValueError("citation must be nonempty")
        if not isinstance(self.review_status, FreshnessEvidenceReviewStatus):
            try:
                object.__setattr__(
                    self, "review_status", FreshnessEvidenceReviewStatus(self.review_status)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("unsupported freshness evidence review_status") from exc
        object.__setattr__(self, "source_sha256", self.source_sha256.lower())
        object.__setattr__(self, "captured_at", _aware_utc(self.captured_at, "captured_at"))
        if self.review_status == FreshnessEvidenceReviewStatus.APPROVED:
            if not isinstance(self.reviewer_id, str) or not self.reviewer_id.strip():
                raise ValueError("approved evidence requires reviewer_id")
            if self.reviewed_at is None:
                raise ValueError("approved evidence requires reviewed_at")
        elif self.reviewer_id is not None or self.reviewed_at is not None:
            raise ValueError("reviewer_id and reviewed_at require approved evidence")
        if self.reviewed_at is not None:
            object.__setattr__(self, "reviewed_at", _aware_utc(self.reviewed_at, "reviewed_at"))
            if self.reviewed_at < self.captured_at:
                raise ValueError("reviewed_at cannot precede captured_at")

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "source_url": self.source_url,
            "source_sha256": self.source_sha256,
            "captured_at": self.captured_at.isoformat(),
            "evidence_type": self.evidence_type.value,
            "citation": self.citation,
            "review_status": self.review_status.value,
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


def normalize_frequency(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return {
        "d": "daily", "day": "daily", "daily": "daily",
        "w": "weekly", "week": "weekly", "weekly": "weekly",
        "m": "monthly", "month": "monthly", "monthly": "monthly",
        "q": "quarterly", "qtr": "quarterly", "quarter": "quarterly",
        "quarterly": "quarterly",
        "half-year": "semiannual", "semiannual": "semiannual",
        "a": "annual", "y": "annual", "year": "annual", "yearly": "annual",
        "annual": "annual", "annually": "annual",
    }.get(value.strip().casefold())


def frequency_from_period_format(period_format: str | None) -> str | None:
    """Return the exact calendar resolution represented by a documented period format."""
    return _FORMAT_FREQUENCIES.get(period_format)


def series_key_override_key(series_key: Mapping[str, str]) -> str:
    if not isinstance(series_key, Mapping) or not series_key:
        raise ValueError("series_key must be a nonempty mapping")
    if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value
           for key, value in series_key.items()):
        raise ValueError("series_key must contain nonempty strings")
    canonical = json.dumps(dict(series_key), sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)
    return "series_key:" + canonical


@dataclass(frozen=True)
class FreshnessPolicy:
    """Versioned fallback tolerances with optional exact-series overrides.

    Override keys use ``series_id:<source ID>`` or the value returned by
    :func:`series_key_override_key`.
    """

    policy_id: str = DEFAULT_POLICY_ID
    frequency_max_age_days: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAX_AGE_DAYS)
    )
    series_overrides: Mapping[str, int] = field(default_factory=dict)
    series_evidence: Mapping[str, FreshnessEvidence] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be nonempty")
        defaults = {}
        for frequency, days in self.frequency_max_age_days.items():
            normalized = normalize_frequency(frequency)
            if normalized is None or type(days) is not int or not 0 <= days <= 36500:
                raise ValueError("invalid frequency freshness tolerance")
            defaults[normalized] = days
        overrides = {}
        for key, days in self.series_overrides.items():
            if (not isinstance(key, str) or not key.strip()
                    or type(days) is not int or not 0 <= days <= 36500):
                raise ValueError("invalid series freshness override")
            overrides[key] = days
        evidence = {}
        for key, record in self.series_evidence.items():
            if not isinstance(key, str) or key not in overrides:
                raise ValueError("freshness evidence must match an exact-series override")
            if not isinstance(record, FreshnessEvidence):
                raise TypeError("series_evidence values must be FreshnessEvidence records")
            evidence[key] = record
        object.__setattr__(self, "frequency_max_age_days", MappingProxyType(defaults))
        object.__setattr__(self, "series_overrides", MappingProxyType(overrides))
        object.__setattr__(self, "series_evidence", MappingProxyType(evidence))

    @property
    def fingerprint_sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def max_age_days(self, frequency: str | None, *, series_id=None, series_key=None):
        keys = []
        if isinstance(series_id, str) and series_id:
            keys.append("series_id:" + series_id)
        if isinstance(series_key, Mapping) and series_key:
            keys.append(series_key_override_key(series_key))
        for key in keys:
            if key in self.series_overrides:
                return self.series_overrides[key], key
        normalized = normalize_frequency(frequency)
        if normalized is None:
            return None, None
        return self.frequency_max_age_days.get(normalized), None

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "frequency_max_age_days": dict(sorted(self.frequency_max_age_days.items())),
            "series_overrides": dict(sorted(self.series_overrides.items())),
            "series_evidence": {
                key: self.series_evidence[key].to_dict()
                for key in sorted(self.series_evidence)
            },
        }


DEFAULT_FRESHNESS_POLICY = FreshnessPolicy()


def _period_end(period: str, frequency: str) -> date:
    if frequency == "annual" and re.fullmatch(r"[0-9]{4}", period, flags=re.ASCII):
        return date(int(period), 12, 31)
    if frequency == "monthly" and re.fullmatch(r"[0-9]{4}-[0-9]{2}", period, flags=re.ASCII):
        year, month = map(int, period.split("-"))
        return date(year, month, monthrange(year, month)[1])
    if frequency == "quarterly":
        match = re.fullmatch(r"([0-9]{4})-Q([1-4])", period, flags=re.ASCII)
        if match:
            year, quarter = map(int, match.groups())
            month = quarter * 3
            return date(year, month, monthrange(year, month)[1])
    if frequency == "semiannual":
        match = re.fullmatch(r"([0-9]{4})-H([1-2])", period, flags=re.ASCII)
        if match:
            year, half = map(int, match.groups())
            month = half * 6
            return date(year, month, monthrange(year, month)[1])
    if frequency == "weekly":
        match = re.fullmatch(r"([0-9]{4})-W([0-9]{2})", period, flags=re.ASCII)
        if match:
            year, week = map(int, match.groups())
            return date.fromisocalendar(year, week, 7)
    if frequency == "daily" and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                               period, flags=re.ASCII):
        return date.fromisoformat(period)
    raise ValueError("observation period does not match its frequency")


def period_end(period: str, frequency: str) -> date:
    """Validate one canonical observation period and return its calendar end date."""
    normalized = normalize_frequency(frequency)
    if normalized is None:
        raise ValueError("frequency is unknown")
    return _period_end(period, normalized)


def assess_freshness(
    periods,
    *,
    frequency: str | None,
    frequency_basis: str | None = None,
    as_of: datetime | date | None = None,
    series_id: str | None = None,
    series_key: Mapping[str, str] | None = None,
    period_format: str | None = None,
    policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
) -> dict:
    """Assess the latest source period and return an auditable, JSON-safe decision."""
    if not isinstance(policy, FreshnessPolicy):
        raise TypeError("policy must be a FreshnessPolicy")
    if as_of is None:
        evaluated_at = datetime.now(UTC)
    elif isinstance(as_of, datetime):
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of timestamp must be timezone-aware")
        evaluated_at = as_of.astimezone(UTC)
    elif isinstance(as_of, date):
        evaluated_at = datetime.combine(as_of, datetime.min.time(), tzinfo=UTC)
    else:
        raise ValueError("as_of must be a date or timezone-aware datetime")

    allowed_frequency_bases = {
        None, "source_metadata", "request_contract", "period_format", "unknown",
    }
    if frequency_basis not in allowed_frequency_bases:
        raise ValueError("frequency_basis is invalid")
    normalized_frequency = normalize_frequency(frequency)
    resolved_frequency_basis = (
        frequency_basis if normalized_frequency and frequency_basis not in {None, "unknown"}
        else "source_metadata" if normalized_frequency else None
    )
    if normalized_frequency is None:
        normalized_frequency = frequency_from_period_format(period_format)
        if normalized_frequency is not None:
            resolved_frequency_basis = "observation_period_format"
        elif frequency_basis == "unknown":
            resolved_frequency_basis = "unknown"

    maximum, override_key = policy.max_age_days(
        normalized_frequency, series_id=series_id, series_key=series_key
    )
    result = {
        "status": FreshnessStatus.FRESHNESS_UNVERIFIED.value,
        "policy_id": policy.policy_id,
        "policy_fingerprint_sha256": policy.fingerprint_sha256,
        "frequency": normalized_frequency,
        "frequency_basis": resolved_frequency_basis,
        "policy_basis": None,
        "latest_period": None,
        "period_end": None,
        "age_days": None,
        "max_age_days": maximum,
        "series_override_key": override_key,
        "policy_evidence_status": "not_applicable",
        "policy_evidence": None,
        "evaluated_at": evaluated_at.isoformat(),
        "reason": None,
    }
    if normalized_frequency is None:
        result["policy_basis"] = "unconfigured"
        result["reason"] = "frequency_unknown"
        return result
    if maximum is None:
        result["policy_basis"] = "unconfigured"
        result["reason"] = "frequency_tolerance_unconfigured"
        return result
    result["policy_basis"] = "series_override" if override_key else "frequency_fallback"
    if override_key:
        evidence = policy.series_evidence.get(override_key)
        if evidence is None:
            result["policy_evidence_status"] = "missing"
            result["reason"] = "series_override_evidence_missing"
            return result
        result["policy_evidence"] = evidence.to_dict()
        result["policy_evidence_status"] = evidence.review_status.value
        if evidence.review_status != FreshnessEvidenceReviewStatus.APPROVED:
            result["reason"] = f"series_override_evidence_{evidence.review_status.value}"
            return result
    else:
        result["policy_evidence_status"] = "frequency_fallback"
    if not isinstance(periods, (tuple, list)) or not periods:
        result["reason"] = "observation_period_missing"
        return result
    if any(not isinstance(period, str) or not period for period in periods):
        result["reason"] = "observation_period_invalid"
        return result
    try:
        dated = [(_period_end(period, normalized_frequency), period) for period in periods]
    except (ValueError, OverflowError):
        result["reason"] = "observation_period_invalid"
        return result
    period_end, latest_period = max(dated)
    age_days = (evaluated_at.date() - period_end).days
    result.update(latest_period=latest_period, period_end=period_end.isoformat(), age_days=age_days)
    if age_days < 0:
        result["reason"] = "latest_observation_is_in_the_future"
        return result
    if age_days > maximum:
        result.update(status=FreshnessStatus.STALE.value, reason="latest_observation_exceeds_tolerance")
        return result
    result.update(status=FreshnessStatus.FRESH.value, reason="within_frequency_tolerance")
    return result
