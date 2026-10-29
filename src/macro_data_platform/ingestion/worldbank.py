"""Selected WDI GDP retrieval engine, independently testable with a fixture transport."""
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import (
    ConnectorFailure,
    Download,
    GDPQuery,
    WorldBankTransport,
    parse_gdp,
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


class GDPTransport(Protocol):
    def fetch(self, query: GDPQuery) -> Download: ...


class WorldBankGDPEngine:
    def __init__(self, settings: Settings, transport: GDPTransport | None = None, *,
                 clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
                 check_freshness: bool = True):
        self.settings = settings
        self.transport = transport if transport is not None else WorldBankTransport(settings)
        self.clock, self.freshness_policy = clock, freshness_policy
        if type(check_freshness) is not bool:
            raise ValueError("check_freshness must be a boolean")
        self.check_freshness = check_freshness

    def run(self, request: StageInput) -> StageResult[dict]:
        # Whitelist fields: keys, arbitrary URLs and unrelated inputs must not enter history/files.
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"start_year", "end_year"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected only start_year and end_year query fields.",))
        try:
            query = GDPQuery(**data)
        except ValueError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected 1 to 10 annual periods in 1960..2100.",))
        paths = {}
        refs = ()
        try:
            download = self.transport.fetch(query)
            if download.source_url != query.url:
                raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                       "Transport response URL differs from the approved endpoint.")
            saved = save_worldbank_download(self.settings, download)
            paths = asdict(saved)
            refs = (saved.raw_path, saved.manifest_path)
            parsed = parse_gdp(download, query)
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
        if not self.check_freshness:
            return StageResult(
                StageStatus.SUCCEEDED, payload, refs,
                ("Source bytes preserved; freshness is evaluated in the validation stage.",),
            )
        with measure_current("quality"):
            freshness = assess_freshness(
                [row["date"] for row in parsed["observations"]
                 if row.get("value") is not None],
                frequency=parsed.get("frequency"), period_format=parsed.get("period_format"),
                series_id=parsed.get("series_id"), series_key=parsed.get("series_key"),
                as_of=self.clock(), policy=self.freshness_policy,
            )
        quality_issue = (
            "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
            "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
        )
        quality = {"status": "failed" if quality_issue else "passed",
                   "issues": [quality_issue] if quality_issue else [],
                   "freshness": freshness}
        metadata_evidence = worldbank_metadata_evidence(payload)
        if metadata_evidence:
            quality["metadata_evidence"] = metadata_evidence
        payload["quality"] = quality
        if quality_issue:
            payload["withheld_observation_count"] = len(payload["observations"])
            payload["observations"] = []
            return StageResult(StageStatus.NEEDS_REVIEW, payload, refs,
                               (quality_issue, freshness["status"]), ErrorCode.QUALITY_FAILURE)
        return persist_typed_series_result(
            self.settings, payload=payload, series=(typed_series,), engine_id="worldbank_gdp/1",
            refs=refs,
        )
