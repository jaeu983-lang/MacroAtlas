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

DEFAULT_MAX_AGE_DAYS = {
    "daily": 7,
    "weekly": 21,
    "monthly": 120,
    "quarterly": 240,
    "semiannual": 183,
    "annual": 730,
}
DEFAULT_POLICY_ID = "frequency_max_age_v1"
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
        object.__setattr__(self, "frequency_max_age_days", MappingProxyType(defaults))
        object.__setattr__(self, "series_overrides", MappingProxyType(overrides))

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


def assess_freshness(
    periods,
    *,
    frequency: str | None,
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

    normalized_frequency = normalize_frequency(frequency)
    frequency_basis = "source_metadata" if normalized_frequency else None
    if normalized_frequency is None:
        normalized_frequency = frequency_from_period_format(period_format)
        if normalized_frequency is not None:
            frequency_basis = "observation_period_format"

    maximum, override_key = policy.max_age_days(
        normalized_frequency, series_id=series_id, series_key=series_key
    )
    result = {
        "status": FreshnessStatus.FRESHNESS_UNVERIFIED.value,
        "policy_id": policy.policy_id,
        "policy_fingerprint_sha256": policy.fingerprint_sha256,
        "frequency": normalized_frequency,
        "frequency_basis": frequency_basis,
        "policy_basis": None,
        "latest_period": None,
        "period_end": None,
        "age_days": None,
        "max_age_days": maximum,
        "series_override_key": override_key,
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
