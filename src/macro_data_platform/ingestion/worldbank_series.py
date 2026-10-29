"""Explicit, raw-preserving annual World Bank indicator collection."""
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import (
    ConnectorFailure,
    Download,
    WorldBankSeriesQuery,
    WorldBankTransport,
    parse_series,
)
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
)
from macro_data_platform.ingestion.typed_series import persist_typed_series_result
from macro_data_platform.metadata.series import (
    normalize_worldbank_series,
    worldbank_metadata_evidence,
)
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.performance.metrics import measure_current
from macro_data_platform.storage.raw_downloads import save_worldbank_download


class WorldBankSeriesTransport(Protocol):
    def fetch(self, query: WorldBankSeriesQuery) -> Download: ...


class WorldBankSeriesEngine:
    """Collect one user-selected series; parsing does not infer units or meanings."""

    def __init__(self, settings: Settings, transport: WorldBankSeriesTransport | None = None, *,
                 clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY):
        self.settings = settings
        self.transport = transport if transport is not None else WorldBankTransport(settings)
        self.clock, self.freshness_policy = clock, freshness_policy

    def run(self, request: StageInput) -> StageResult[dict]:
        fields = {"country_iso3", "indicator_id", "source_id", "start_year", "end_year"}
        data = request.input_data
        if not isinstance(data, dict) or set(data) != fields:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected explicit country, source, indicator and year fields.",))
        try:
            query = WorldBankSeriesQuery(**data)
        except ValueError:
            message = (
                "Expected one uppercase ISO3 country, a safe indicator ID, "
                "WDI source 2 and 1 to 10 years in 1960..2100."
            )
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=(message,))

        paths = {}
        refs = ()
        try:
            download = self.transport.fetch(query)
            if download.source_url != query.url:
                raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                       "Transport response URL differs from the selected endpoint.")
            saved = save_worldbank_download(self.settings, download)
            paths = asdict(saved)
            refs = (saved.raw_path, saved.manifest_path)
            parsed = parse_series(download, query)
        except ConnectorFailure as failure:
            return StageResult(failure.status, {**paths, "source_url": query.url}, refs,
                               (str(failure),), failure.code)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL,
                               {**paths, "source_url": query.url}, refs,
                               ("Local response preservation failed; existing files retained.",),
                               ErrorCode.INTERNAL_BUG)

        payload = {**parsed, **paths, "mode": download.kind.value}
        try:
            typed_series = normalize_worldbank_series(payload)
        except (TypeError, ValueError):
            return StageResult(
                StageStatus.NEEDS_REVIEW, payload, refs,
                ("World Bank response did not satisfy the common time-series contract.",),
                ErrorCode.SCHEMA_CHANGED,
            )
        with measure_current("quality"):
            freshness = assess_freshness(
                [row["date"] for row in parsed["observations"]
                 if row.get("value") is not None],
                frequency=parsed.get("frequency"), period_format=parsed.get("period_format"),
                series_id=parsed.get("series_id"), series_key=parsed.get("series_key"),
                as_of=self.clock(), policy=self.freshness_policy,
            )
        issue = (
            "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
            "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
        )
        quality = {"status": "failed" if issue else "passed",
                   "issues": [issue] if issue else [], "freshness": freshness}
        metadata_evidence = worldbank_metadata_evidence(payload)
        if metadata_evidence:
            quality["metadata_evidence"] = metadata_evidence
        payload["quality"] = quality
        if issue:
            payload["withheld_observation_count"] = len(payload["observations"])
            payload["observations"] = []
            return StageResult(StageStatus.NEEDS_REVIEW, payload, refs,
                               (issue, freshness["status"]), ErrorCode.QUALITY_FAILURE)
        return persist_typed_series_result(
            self.settings, payload=payload, series=(typed_series,), engine_id="worldbank_series/1",
            refs=refs,
        )
