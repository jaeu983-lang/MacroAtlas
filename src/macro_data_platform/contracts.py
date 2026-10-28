"""Iteration 01 value contracts; execution and persistence belong to iteration 02."""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar
from urllib.parse import parse_qsl, urlsplit


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SKIPPED_REUSED = "SKIPPED_REUSED"


class ErrorCode(str, Enum):
    TRANSIENT = "TRANSIENT"
    AUTH_ACCESS = "AUTH_ACCESS"
    SITE_CHANGED = "SITE_CHANGED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    SEMANTIC_AMBIGUITY = "SEMANTIC_AMBIGUITY"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    LICENSE_SECURITY = "LICENSE_SECURITY"
    INTERNAL_BUG = "INTERNAL_BUG"


class EvidenceKind(str, Enum):
    OFFICIAL_DOCS = "official_docs"
    FIXTURE = "fixture"
    LIVE_API = "live_api"
    LIVE_INGESTION = "live_ingestion"


_CREDENTIAL_NAMES = {
    "key", "apikey", "token", "accesstoken", "password", "secret", "authorization",
    "appid", "applicationid", "userid", "clientsecret", "subscriptionkey", "sig",
    "signature", "credential", "sessionid", "auth", "authkey", "accesskey", "secretkey",
    "bearer",
}


def _credential_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return (normalized in _CREDENTIAL_NAMES
            or normalized.startswith(("xamz", "xgoog")))


def required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty")


def utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds():
        raise ValueError("timestamp must be timezone-aware UTC")


@dataclass(frozen=True)
class Task:
    task_id: str
    request: str
    created_at: datetime
    status: TaskStatus = TaskStatus.CREATED

    def __post_init__(self) -> None:
        required(self.task_id, "task_id")
        required(self.request, "request")
        utc(self.created_at)
        if not isinstance(self.status, TaskStatus):
            raise ValueError("invalid task status")  # noqa: TRY004 - public validation contract


@dataclass(frozen=True)
class SourceEvidence:
    evidence_id: str
    source_agency: str
    source_url: str
    retrieved_at: datetime
    kind: EvidenceKind
    original_ref: str
    dataset_id: str | None = None
    series_id: str | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        for field in ("evidence_id", "source_agency", "original_ref"):
            required(getattr(self, field), field)
        try:
            parsed = urlsplit(self.source_url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and parsed.username is None and parsed.password is None)
            names = [name for name, _ in parse_qsl(
                parsed.query, keep_blank_values=True, max_num_fields=256,
            )]
        except ValueError:
            raise ValueError("source_url must be a credential-free HTTP(S) URL") from None
        if not valid:
            raise ValueError("source_url must be a credential-free HTTP(S) URL")
        if any(_credential_name(name) for name in names):
            raise ValueError("source_url must not contain credentials")
        utc(self.retrieved_at)
        if not isinstance(self.kind, EvidenceKind):
            raise ValueError("invalid evidence kind")  # noqa: TRY004 - public validation contract


class ObservationStatus(str, Enum):
    OBSERVED = "observed"
    MISSING = "missing"
    SUPPRESSED = "suppressed"
    NOT_APPLICABLE = "not_applicable"


_SERIES_FREQUENCIES = {
    "daily", "weekly", "monthly", "quarterly", "semiannual", "annual",
}
_FREQUENCY_BASES = {"source_metadata", "request_contract", "period_format", "unknown"}


@dataclass(frozen=True)
class Observation:
    """One source period with explicit missingness and the provider's parsed value."""

    period: str
    raw_value: str | int | float | None
    status: ObservationStatus
    source_period: str | None = None

    def __post_init__(self) -> None:
        required(self.period, "period")
        if not isinstance(self.status, ObservationStatus):
            raise ValueError("invalid observation status")  # noqa: TRY004 - contract validation
        if isinstance(self.raw_value, bool) or not isinstance(
            self.raw_value, (str, int, float, type(None)),
        ):
            raise TypeError("raw_value must be a source string, finite number or null")
        if isinstance(self.raw_value, float) and not isfinite(self.raw_value):
            raise ValueError("raw_value must be finite")
        if self.status == ObservationStatus.OBSERVED and self.raw_value is None:
            raise ValueError("observed values cannot be null")
        if self.status == ObservationStatus.OBSERVED and self.raw_value == "":
            raise ValueError("empty source strings cannot be marked observed")
        if self.status == ObservationStatus.MISSING and self.raw_value not in {None, ""}:
            raise ValueError("missing values must preserve a null or empty source value")
        if self.source_period is not None:
            required(self.source_period, "source_period")


@dataclass(frozen=True)
class TimeSeries:
    """Common source-preserving contract used between provider adapters and outputs.

    ``raw_value`` is the parsed provider scalar. The raw response remains the authority
    for byte-exact numeric spelling and is addressed by ``raw_ref``/``manifest_ref``.
    """

    source_agency: str
    dataset_id: str | None
    series_id: str
    dimensions: Mapping[str, str]
    calendar: str
    observations: tuple[Observation, ...]
    retrieved_at: datetime
    source_url: str
    raw_ref: str
    manifest_ref: str
    unit: str | None = None
    currency: str | None = None
    frequency: str | None = None
    frequency_basis: str = "unknown"
    source_revision: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_agency", "series_id", "calendar", "raw_ref", "manifest_ref"):
            required(getattr(self, name), name)
        if self.dataset_id is not None:
            required(self.dataset_id, "dataset_id")
        if not isinstance(self.dimensions, Mapping):
            raise TypeError("dimensions must be a mapping")
        if any(not isinstance(key, str) or not key.strip()
               or not isinstance(value, str) or not value.strip()
               for key, value in self.dimensions.items()):
            raise ValueError("dimension names and values must be nonempty strings")
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))
        if self.frequency is not None and self.frequency not in _SERIES_FREQUENCIES:
            raise ValueError("frequency must use a canonical supported value")
        if self.frequency_basis not in _FREQUENCY_BASES:
            raise ValueError("frequency_basis is invalid")
        if (self.frequency is None) != (self.frequency_basis == "unknown"):
            raise ValueError("unknown frequency and frequency basis must agree")
        for name in ("unit", "currency", "source_revision"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be nonempty when supplied")
        utc(self.retrieved_at)
        try:
            parsed = urlsplit(self.source_url)
            valid_url = (parsed.scheme in {"http", "https"} and parsed.hostname
                         and parsed.username is None and parsed.password is None)
            names = [name for name, _ in parse_qsl(
                parsed.query, keep_blank_values=True, max_num_fields=256,
            )]
        except ValueError:
            raise ValueError("source_url must be a credential-free HTTP(S) URL") from None
        if not valid_url or any(_credential_name(name) for name in names):
            raise ValueError("source_url must be a credential-free HTTP(S) URL")
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("observations must be a nonempty tuple")
        if any(not isinstance(item, Observation) for item in self.observations):
            raise ValueError("observations must contain Observation values")

    def to_dict(self) -> dict:
        """Return a deterministic JSON-compatible representation."""
        return {
            "schema_version": "time-series-v1",
            "source_agency": self.source_agency,
            "dataset_id": self.dataset_id,
            "series_id": self.series_id,
            "dimensions": dict(sorted(self.dimensions.items())),
            "calendar": self.calendar,
            "unit": self.unit,
            "currency": self.currency,
            "frequency": self.frequency,
            "frequency_basis": self.frequency_basis,
            "source_revision": self.source_revision,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_url": self.source_url,
            "raw_ref": self.raw_ref,
            "manifest_ref": self.manifest_ref,
            "observations": [
                {"period": item.period, "raw_value": item.raw_value,
                 "status": item.status.value, "source_period": item.source_period}
                for item in self.observations
            ],
        }


T = TypeVar("T")
I_contra = TypeVar("I_contra", contravariant=True)


@dataclass(frozen=True)
class StageResult(Generic[T]):
    status: StageStatus
    payload: T | None = None
    evidence_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: ErrorCode | None = None
    retry_hint: str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, StageStatus):
            raise ValueError("invalid stage status")  # noqa: TRY004 - public validation contract
        if self.error_code is not None and not isinstance(self.error_code, ErrorCode):
            raise ValueError("invalid error code")
        if (self.retry_after_seconds is not None
                and (type(self.retry_after_seconds) is not int or self.retry_after_seconds < 0)):
            raise ValueError("retry_after_seconds must be a nonnegative integer")
        failed = self.status in {StageStatus.FAILED_RETRYABLE, StageStatus.FAILED_TERMINAL}
        if failed and self.error_code is None:
            raise ValueError("failed results require an error code")
        if (
            self.status in {StageStatus.SUCCEEDED, StageStatus.SKIPPED_REUSED}
            and self.error_code is not None
        ):
            raise ValueError("successful results cannot contain an error code")
        for ref in self.evidence_refs:
            required(ref, "evidence_ref")


class Engine(Protocol[I_contra, T]):
    """Independent engine boundary; implementations must be explicitly supplied."""

    def run(self, request: I_contra) -> StageResult[T]: ...
