"""Census ACS table ingestion engine."""
from datetime import UTC, datetime
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.census import CensusQuery, CensusTransport, parse_census
from macro_data_platform.connectors.statistical_http import ApiDownload, SourceFailure
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy
from macro_data_platform.ingestion.statistical_quality import validate_census_result
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.storage.statistical_downloads import save_statistical_download


class Transport(Protocol):
    def fetch(self, query: CensusQuery) -> ApiDownload: ...


class CensusEngine:
    def __init__(self, settings: Settings, transport: Transport | None = None, *,
                 clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY):
        self.settings = settings
        self.transport = transport if transport is not None else CensusTransport()
        self.clock, self.freshness_policy = clock, freshness_policy

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        if (not isinstance(data, dict)
                or set(data) - {"year", "dataset", "variables", "geography"}
                or not {"year", "dataset", "variables", "geography"}.issubset(data)
                or not isinstance(data.get("variables"), list)):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected Census ACS year, dataset, variables, geography.",))
        saved = {}
        try:
            query = CensusQuery(data["year"], data["dataset"], tuple(data["variables"]),
                                data["geography"])
        except (TypeError, ValueError):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Census query failed local validation.",))
        try:
            download = self.transport.fetch(query)
            endpoint = f"https://api.census.gov/data/{query.year}/{query.dataset}"
            if download.source_url != endpoint:
                raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                    "Transport endpoint differed from the approved Census API.")
            saved = save_statistical_download(self.settings, "census", download, {
                "year": query.year, "dataset": query.dataset,
                "variables": list(query.variables), "geography": query.geography,
            })
            parsed = parse_census(download, query)
        except SourceFailure as failure:
            retry_hint = (
                (f"Wait at least {failure.retry_after_seconds} seconds before manual resume; "
                 "no automatic retry was sent." if failure.retry_after_seconds is not None else
                 "Manual resume is available after the transient API condition clears; "
                 "no automatic retry was sent.")
                if failure.status == StageStatus.FAILED_RETRYABLE else None
            )
            payload = {**saved, **({"http_status": failure.status_code}
                                   if failure.status_code is not None else {})}
            refs = tuple(saved[key] for key in ("raw_path", "manifest_path") if key in saved)
            return StageResult(failure.status, payload or None, refs,
                               warnings=(str(failure),), error_code=failure.code,
                               retry_hint=retry_hint,
                               retry_after_seconds=failure.retry_after_seconds)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                               warnings=("Census raw response preservation failed.",))
        parsed.update({**saved, "mode": download.kind.value})
        quality = validate_census_result(
            parsed, saved["source_change_status"], as_of=self.clock(),
            freshness_policy=self.freshness_policy,
        )
        parsed["quality"] = quality
        if quality["status"] == "failed":
            if any(issue in quality["issues"]
                   for issue in ("stale_observations", "freshness_unverified")):
                parsed["withheld_observation_count"] = quality["row_count"]
                parsed["observations"] = []
            return StageResult(
                StageStatus.NEEDS_REVIEW, parsed,
                (saved["raw_path"], saved["manifest_path"]),
                tuple(quality["warnings"] + quality["issues"]), ErrorCode.QUALITY_FAILURE,
            )
        return StageResult(StageStatus.SUCCEEDED, parsed,
                           (saved["raw_path"], saved["manifest_path"]),
                           tuple(quality["warnings"]))
