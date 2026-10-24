"""Iteration 01 value contracts; execution and persistence belong to iteration 02."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, Protocol, TypeVar
from urllib.parse import urlsplit


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
        parsed = urlsplit(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("source_url must not contain credentials")
        utc(self.retrieved_at)
        if not isinstance(self.kind, EvidenceKind):
            raise ValueError("invalid evidence kind")  # noqa: TRY004 - public validation contract


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

    def __post_init__(self) -> None:
        if not isinstance(self.status, StageStatus):
            raise ValueError("invalid stage status")  # noqa: TRY004 - public validation contract
        if self.error_code is not None and not isinstance(self.error_code, ErrorCode):
            raise ValueError("invalid error code")
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
