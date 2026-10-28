"""Orchestrator stages for the verified BOJ FXERD01 monthly API path."""
import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import (
    METADATA_ENDPOINT,
    BOJQuery,
    BOJRangeQuery,
    BOJTransport,
    parse_boj_metadata,
    parse_boj_observations,
    parse_boj_range_observations,
)
from macro_data_platform.connectors.statistical_http import MAX_BYTES, ApiDownload, SourceFailure
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
)
from macro_data_platform.orchestration import Orchestrator, StageInput, StageSpec, TaskPlan
from macro_data_platform.performance.metrics import measure_current
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.statistical_downloads import save_statistical_download


class Transport(Protocol):
    def fetch_metadata(self, query: BOJQuery) -> ApiDownload: ...

    def fetch_observations(self, query: BOJQuery | BOJRangeQuery) -> ApiDownload: ...


def _retry_fields(failure: SourceFailure) -> tuple[str | None, int | None]:
    if failure.status != StageStatus.FAILED_RETRYABLE:
        return None, None
    if failure.retry_after_seconds is not None:
        return (f"Wait at least {failure.retry_after_seconds} seconds before manual resume; "
                "no automatic retry was sent."), failure.retry_after_seconds
    return "Resume manually after the temporary provider condition clears; no retry was sent.", None


class BOJMetadataEngine:
    def __init__(self, settings: Settings, transport: Transport | None = None):
        self.settings = settings
        self.transport = transport if transport is not None else BOJTransport()

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"database", "series_code"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected the fixed BOJ database and series code.",))
        try:
            query = BOJQuery("202609", data["database"], data["series_code"])
        except (TypeError, ValueError):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("BOJ metadata query failed local validation.",))
        saved = {}
        try:
            download = self.transport.fetch_metadata(query)
            saved = save_statistical_download(self.settings, "boj", download, {
                "database": query.database, "series_code": query.series_code,
                "request_kind": "metadata",
            })
            metadata = parse_boj_metadata(download, query)
        except SourceFailure as failure:
            retry_hint, retry_after = _retry_fields(failure)
            payload = {**saved, **({"http_status": failure.status_code}
                                   if failure.status_code is not None else {})}
            refs = tuple(saved[key] for key in ("raw_path", "manifest_path") if key in saved)
            return StageResult(failure.status, payload or None, refs, (str(failure),),
                               failure.code, retry_hint, retry_after)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                               warnings=("BOJ metadata raw preservation failed.",))
        payload = {**metadata, **saved}
        refs = (saved["raw_path"], saved["manifest_path"])
        if saved["source_change_status"] == "changed":
            return StageResult(StageStatus.NEEDS_REVIEW, payload, refs,
                               ("BOJ metadata changed since the previous exact request; review required.",),
                               ErrorCode.SCHEMA_CHANGED)
        return StageResult(StageStatus.SUCCEEDED, payload, refs)


class BOJObservationEngine:
    def __init__(self, settings: Settings, transport: Transport | None = None, *,
                 clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY):
        self.settings = settings
        self.transport = transport if transport is not None else BOJTransport()
        self.clock, self.freshness_policy = clock, freshness_policy

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"database", "series_code", "month"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected BOJ database, series code and YYYYMM month.",))
        try:
            query = BOJQuery(data["month"], data["database"], data["series_code"])
        except (TypeError, ValueError):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("BOJ observation query failed local validation.",))
        metadata = request.upstream
        if (not isinstance(metadata, dict) or metadata.get("metadata_status") != "verified"
                or metadata.get("database") != query.database
                or metadata.get("series_code") != query.series_code):
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SEMANTIC_AMBIGUITY,
                               warnings=("Verified metadata for the exact BOJ series is required.",))
        saved = {}
        try:
            download = self.transport.fetch_observations(query)
            saved = save_statistical_download(self.settings, "boj", download, {
                "database": query.database, "series_code": query.series_code,
                "month": query.month, "request_kind": "observations",
            })
            if saved["source_change_status"] == "changed":
                payload = {**saved, "source_url": download.source_url, "mode": download.kind.value}
                return StageResult(
                    StageStatus.NEEDS_REVIEW, payload,
                    (saved["raw_path"], saved["manifest_path"]),
                    (("BOJ observations changed since the previous exact request; "
                      "new normalized output was withheld."),), ErrorCode.SCHEMA_CHANGED,
                )
            parsed = parse_boj_observations(download, query, metadata)
        except SourceFailure as failure:
            retry_hint, retry_after = _retry_fields(failure)
            payload = {**saved, **({"http_status": failure.status_code}
                                   if failure.status_code is not None else {})}
            refs = tuple(saved[key] for key in ("raw_path", "manifest_path") if key in saved)
            return StageResult(failure.status, payload or None, refs, (str(failure),),
                               failure.code, retry_hint, retry_after)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, {**saved},
                               tuple(saved[key] for key in ("raw_path", "manifest_path")
                                     if key in saved),
                               ("BOJ observation raw preservation failed.",), ErrorCode.INTERNAL_BUG)
        parsed.update({**saved, "mode": download.kind.value})
        with measure_current("quality"):
            freshness = assess_freshness(
                [row["date"] for row in parsed["observations"] if row["value"] is not None],
                frequency=metadata.get("frequency"), series_id=query.series_code,
                series_key={"database": query.database, "series_code": query.series_code},
                as_of=self.clock(), policy=self.freshness_policy,
            )
        freshness_issue = (
            "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
            "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
        )
        parsed["quality"] = {
            **parsed["quality"], "freshness": freshness,
            "issues": [freshness_issue] if freshness_issue else [],
            "status": "failed" if freshness_issue else "passed",
        }
        refs = (saved["raw_path"], saved["manifest_path"])
        if freshness_issue:
            parsed["withheld_observation_count"] = len(parsed["observations"])
            parsed["observations"] = []
            return StageResult(
                StageStatus.NEEDS_REVIEW, parsed, refs,
                (freshness_issue, freshness["status"]), ErrorCode.QUALITY_FAILURE,
            )
        return StageResult(StageStatus.SUCCEEDED, parsed, refs)


class BOJRangeObservationEngine:
    """Collect at most one year of the same verified daily FX series."""

    def __init__(self, settings: Settings, transport: Transport | None = None, *,
                 clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY):
        self.settings = settings
        self.transport = transport if transport is not None else BOJTransport()
        self.clock, self.freshness_policy = clock, freshness_policy

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        fields = {"database", "series_code", "start_month", "end_month"}
        if not isinstance(data, dict) or set(data) != fields:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected BOJ database, series code and month range.",))
        try:
            query = BOJRangeQuery(
                data["start_month"], data["end_month"], data["database"], data["series_code"],
            )
        except (TypeError, ValueError):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("BOJ observation range failed local validation.",))
        metadata = request.upstream
        if (not isinstance(metadata, dict) or metadata.get("metadata_status") != "verified"
                or metadata.get("database") != query.database
                or metadata.get("series_code") != query.series_code):
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SEMANTIC_AMBIGUITY,
                               warnings=("Verified metadata for the exact BOJ series is required.",))

        saved = {}
        try:
            download = self.transport.fetch_observations(query)
            saved = save_statistical_download(self.settings, "boj", download, {
                "database": query.database, "series_code": query.series_code,
                "start_month": query.start_month, "end_month": query.end_month,
                "request_kind": "observations",
            })
            if saved["source_change_status"] == "changed":
                payload = {**saved, "source_url": download.source_url, "mode": download.kind.value}
                return StageResult(
                    StageStatus.NEEDS_REVIEW, payload,
                    (saved["raw_path"], saved["manifest_path"]),
                    (("BOJ observations changed since the previous exact range; "
                      "new normalized output was withheld."),), ErrorCode.SCHEMA_CHANGED,
                )
            parsed = parse_boj_range_observations(download, query, metadata)
        except SourceFailure as failure:
            retry_hint, retry_after = _retry_fields(failure)
            payload = {**saved, **({"http_status": failure.status_code}
                                   if failure.status_code is not None else {})}
            refs = tuple(saved[key] for key in ("raw_path", "manifest_path") if key in saved)
            return StageResult(failure.status, payload or None, refs, (str(failure),),
                               failure.code, retry_hint, retry_after)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, {**saved},
                               tuple(saved[key] for key in ("raw_path", "manifest_path")
                                     if key in saved),
                               ("BOJ observation raw preservation failed.",), ErrorCode.INTERNAL_BUG)

        parsed.update({**saved, "mode": download.kind.value})
        with measure_current("quality"):
            freshness = assess_freshness(
                [row["date"] for row in parsed["observations"] if row["value"] is not None],
                frequency=metadata.get("frequency"), series_id=query.series_code,
                series_key={"database": query.database, "series_code": query.series_code},
                as_of=self.clock(), policy=self.freshness_policy,
            )
        issue = (
            "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
            "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
        )
        parsed["quality"] = {
            **parsed["quality"], "freshness": freshness,
            "issues": [issue] if issue else [], "status": "failed" if issue else "passed",
        }
        refs = (saved["raw_path"], saved["manifest_path"])
        if issue:
            parsed["withheld_observation_count"] = len(parsed["observations"])
            parsed["observations"] = []
            return StageResult(StageStatus.NEEDS_REVIEW, parsed, refs,
                               (issue, freshness["status"]), ErrorCode.QUALITY_FAILURE)
        return StageResult(StageStatus.SUCCEEDED, parsed, refs)


def build_boj_plan(query: BOJQuery) -> TaskPlan:
    """Metadata and data are separate durable one-request stages."""
    if not isinstance(query, BOJQuery):
        raise TypeError("expected a BOJQuery")
    return TaskPlan((
        StageSpec("metadata", "boj_metadata", {
            "database": query.database, "series_code": query.series_code,
        }, max_attempts=2, reuse_ttl_seconds=3600),
        StageSpec("collect", "boj_observations", {
            "database": query.database, "series_code": query.series_code,
            "month": query.month,
        }, engine_version="2", max_attempts=2),
    ))


def build_boj_range_plan(query: BOJRangeQuery) -> TaskPlan:
    """Keep verified metadata and bounded multi-month observations in separate stages."""
    if not isinstance(query, BOJRangeQuery):
        raise TypeError("expected a BOJRangeQuery")
    return TaskPlan((
        StageSpec("metadata", "boj_metadata", {
            "database": query.database, "series_code": query.series_code,
        }, max_attempts=2, reuse_ttl_seconds=3600),
        StageSpec("collect", "boj_observations_range", {
            "database": query.database, "series_code": query.series_code,
            "start_month": query.start_month, "end_month": query.end_month,
        }, engine_version="1", max_attempts=2),
    ))


def metadata_reusable(spec: StageSpec, candidate: dict, settings: Settings) -> bool:
    if (spec.engine != "boj_metadata" or candidate.get("status") != StageStatus.SUCCEEDED
            or not isinstance(candidate.get("result"), dict)):
        return False
    payload = candidate["result"].get("payload")
    if not isinstance(payload, dict) or payload.get("metadata_status") != "verified":
        return False
    raw_path, manifest_path = payload.get("raw_path"), payload.get("manifest_path")
    digest = payload.get("raw_sha256")
    if not all(isinstance(value, str) for value in (raw_path, manifest_path, digest)):
        return False
    try:
        raw = settings._inside(raw_path)
        manifest = settings._inside(manifest_path)
        if (not raw.is_file() or raw.is_symlink() or raw.stat().st_size > MAX_BYTES
                or not manifest.is_file() or manifest.is_symlink()
                or manifest.stat().st_size > 64 * 1024):
            return False
        raw_bytes = raw.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != digest:
            return False
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    request = document.get("request") if isinstance(document, dict) else None
    return (isinstance(document, dict) and isinstance(request, dict)
            and document.get("raw_sha256") == digest
            and document.get("source_url") == METADATA_ENDPOINT
            and payload.get("source_url") == METADATA_ENDPOINT
            and request == {
                "database": spec.input_data.get("database"),
                "series_code": spec.input_data.get("series_code"),
                "request_kind": "metadata",
            })


def make_boj_orchestrator(store: HistoryStore, settings: Settings,
                          transport: Transport | None = None, *,
                          clock=lambda: datetime.now(UTC),
                          freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY
                          ) -> Orchestrator:
    from macro_data_platform.orchestration.composition import build_engine_registry

    registry = build_engine_registry(
        settings, store, boj_transport=transport, clock=clock,
        freshness_policy=freshness_policy,
    )
    return registry.orchestrator_for(engine_keys={
        ("boj_metadata", "1"), ("boj_observations", "2"),
    })


def make_boj_range_orchestrator(store: HistoryStore, settings: Settings,
                                transport: Transport | None = None, *,
                                clock=lambda: datetime.now(UTC),
                                freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY
                                ) -> Orchestrator:
    from macro_data_platform.orchestration.composition import build_engine_registry

    registry = build_engine_registry(
        settings, store, boj_transport=transport, clock=clock,
        freshness_policy=freshness_policy,
    )
    return registry.orchestrator_for(engine_keys={
        ("boj_metadata", "1"), ("boj_observations_range", "1"),
    })


def create_boj_task(store: HistoryStore, settings: Settings, query: BOJQuery,
                    transport: Transport | None = None) -> dict:
    if not isinstance(query, BOJQuery):
        raise TypeError("expected a BOJQuery")
    runner = make_boj_orchestrator(store, settings, transport)
    created = runner.create(
        f"BOJ {query.database}/{query.series_code} observations for {query.month}")
    runner.plan(created.task_id, build_boj_plan(query))
    return store.get(created.task_id)
