"""BLS Public Data API v2 ingestion engine."""
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bls import BLSQuery, BLSTransport, parse_bls
from macro_data_platform.connectors.statistical_http import ApiDownload, SourceFailure
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.statistical_quality import validate_bls_result
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.storage.statistical_downloads import save_statistical_download


class Transport(Protocol):
    def fetch(self, query: BLSQuery) -> ApiDownload: ...


class BLSEngine:
    def __init__(self, settings: Settings, transport: Transport | None = None):
        self.settings = settings
        self.transport = transport if transport is not None else BLSTransport()

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        if (not isinstance(data, dict) or set(data) != {"series_ids", "start_year", "end_year"}
                or not isinstance(data.get("series_ids"), list)):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected BLS series_ids and year bounds.",))
        saved = {}
        try:
            query = BLSQuery(tuple(data["series_ids"]), data["start_year"], data["end_year"])
        except (TypeError, ValueError):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("BLS query failed local validation.",))
        try:
            download = self.transport.fetch(query)
            if download.source_url != "https://api.bls.gov/publicAPI/v2/timeseries/data/":
                raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                    "Transport endpoint differed from the official BLS API.")
            saved = save_statistical_download(self.settings, "bls", download, {
                "series_ids": list(query.series_ids), "start_year": query.start_year,
                "end_year": query.end_year,
            })
            parsed = parse_bls(download, query)
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
                               warnings=("BLS raw response preservation failed.",))
        parsed.update({**saved, "mode": download.kind.value})
        quality = validate_bls_result(parsed, saved["source_change_status"])
        parsed["quality"] = quality
        if quality["status"] == "failed":
            return StageResult(
                StageStatus.NEEDS_REVIEW, parsed,
                (saved["raw_path"], saved["manifest_path"]),
                tuple(quality["warnings"] + quality["issues"]), ErrorCode.QUALITY_FAILURE,
            )
        return StageResult(StageStatus.SUCCEEDED, parsed,
                           (saved["raw_path"], saved["manifest_path"]),
                           tuple(quality["warnings"]))
