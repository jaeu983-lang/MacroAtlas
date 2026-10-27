"""Orchestrator engines for official and supplied metadata sources."""
import json
from datetime import UTC, datetime

from macro_data_platform.config import Settings
from macro_data_platform.connectors.metadata import fetch_bls_catalog, fetch_census_variable
from macro_data_platform.connectors.statistical_http import ApiDownload, SourceFailure
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageResult, StageStatus
from macro_data_platform.metadata.normalize import (
    normalize_bls_catalog,
    normalize_census_variable,
    normalize_codebook_rows,
)
from macro_data_platform.metadata.sdmx import parse_sdmx_structure_xml
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.performance.metrics import measured_phase
from macro_data_platform.storage.metadata_archives import (
    begin_metadata_package,
    complete_metadata_package,
    save_metadata_package,
)


class BLSMetadataEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return _network_disabled()
        data = request.input_data
        if (not isinstance(data, dict) or set(data) != {"series_id", "start_year", "end_year"}
                or not isinstance(data.get("series_id"), str)):
            return _invalid("Expected one BLS series_id and year bounds.")
        source_package = None
        try:
            download = fetch_bls_catalog(data["series_id"], data["start_year"], data["end_year"])
            context = {
                "series_id": data["series_id"], "start_year": data["start_year"],
                "end_year": data["end_year"], "catalogue": True,
            }
            source_package = begin_metadata_package(self.settings, "bls", download, context)
            payload = _json(download)
            if not isinstance(payload, dict) or payload.get("status") != "REQUEST_SUCCEEDED":
                raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                    "BLS did not confirm a successful catalogue request.")
            record = normalize_bls_catalog(
                payload, source_url=download.source_url,
                retrieved_at=download.retrieved_at.isoformat(), raw_path=source_package["raw_path"],
                start_year=data["start_year"], end_year=data["end_year"],
                expected_series_id=data["series_id"],
            )
            saved = complete_metadata_package(self.settings, source_package, [record], context)
        except SourceFailure as failure:
            return _source_failure(failure, source_package)
        except (TypeError, ValueError):
            if source_package is not None:
                return _normalization_failure(source_package)
            return _invalid("BLS catalogue metadata failed structural validation.")
        except OSError:
            return _storage_failure(source_package)
        return _success(saved, ("Definition, unit, and frequency were not exposed by this catalogue response.",))


class CensusVariableMetadataEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return _network_disabled()
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"year", "dataset", "variable_id"}:
            return _invalid("Expected Census year, dataset, and variable_id.")
        source_package = None
        try:
            download = fetch_census_variable(data["year"], data["dataset"], data["variable_id"])
            context = {"year": data["year"], "dataset": data["dataset"],
                       "variable_id": data["variable_id"]}
            source_package = begin_metadata_package(self.settings, "census", download, context)
            payload = _json(download)
            if not isinstance(payload, dict):
                raise TypeError("Census variable metadata must be a JSON object")
            record = normalize_census_variable(
                payload, source_url=download.source_url,
                retrieved_at=download.retrieved_at.isoformat(), raw_path=source_package["raw_path"],
                dataset_id=data["dataset"], reference_year=data["year"],
                expected_variable_id=data["variable_id"],
            )
            saved = complete_metadata_package(self.settings, source_package, [record], context)
        except SourceFailure as failure:
            return _source_failure(failure, source_package)
        except (TypeError, ValueError):
            if source_package is not None:
                return _normalization_failure(source_package)
            return _invalid("Census variable metadata failed structural validation.")
        except OSError:
            return _storage_failure(source_package)
        return _success(saved, ("Definition, unit, and frequency remain unknown unless exposed by source fields.",))


class CodebookMetadataEngine:
    """Normalize caller-supplied, already-read table or worksheet rows."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        required = {"source_agency", "source_url", "rows", "columns"}
        if not isinstance(data, dict) or set(data) != required:
            return _invalid("Expected codebook source_agency, source_url, rows, and columns.")
        now = datetime.now(UTC)
        try:
            body = json.dumps(data["rows"], ensure_ascii=False, allow_nan=False).encode()
            download = _fixture_download(data["source_url"], body, "application/json", now)
            records = normalize_codebook_rows(
                data["rows"], columns=data["columns"], source_agency=data["source_agency"],
                source_url=data["source_url"], retrieved_at=now.isoformat(), raw_path="",
            )
            saved = save_metadata_package(self.settings, "codebook", download, records,
                                          {"row_count": len(data["rows"])})
        except (TypeError, ValueError):
            return _invalid("Codebook rows or source mapping failed validation.")
        except OSError:
            return _storage_failure()
        return _success(saved)


class SDMXMetadataEngine:
    """Parse supplied SDMX-ML structure XML; network retrieval is separate."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        required = {"source_agency", "source_url", "xml"}
        if not isinstance(data, dict) or set(data) != required or not isinstance(data["xml"], str):
            return _invalid("Expected SDMX source_agency, source_url, and XML text.")
        now = datetime.now(UTC)
        body = data["xml"].encode()
        try:
            download = _fixture_download(data["source_url"], body, "application/xml", now)
            records = parse_sdmx_structure_xml(
                body, source_agency=data["source_agency"], source_url=data["source_url"],
                retrieved_at=now, raw_path="",
            )
            saved = save_metadata_package(self.settings, "sdmx", download, records,
                                          {"format": "SDMX-ML 2.1"})
        except (TypeError, ValueError):
            return _invalid("SDMX structure metadata failed bounded XML validation.")
        except OSError:
            return _storage_failure()
        return _success(saved, ("SDMX input was supplied locally; no SDMX network collector is registered.",))


@measured_phase("parse")
def _json(download: ApiDownload):
    from macro_data_platform.connectors.statistical_http import decode_json
    return decode_json(download)


def _fixture_download(source_url: str, body: bytes, content_type: str,
                      retrieved_at: datetime) -> ApiDownload:
    return ApiDownload(source_url, body, 200, retrieved_at, content_type, EvidenceKind.FIXTURE)


def _network_disabled() -> StageResult:
    return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                       warnings=("Network collection is disabled in settings.",))


def _invalid(message: str) -> StageResult:
    return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                       warnings=(message,))


def _source_failure(failure: SourceFailure, source_package: dict[str, str] | None = None) -> StageResult:
    refs = _source_refs(source_package)
    return StageResult(failure.status, _source_payload(source_package), refs,
                       (str(failure),), failure.code)


def _normalization_failure(source_package: dict[str, str]) -> StageResult:
    return StageResult(
        StageStatus.NEEDS_REVIEW, _source_payload(source_package), _source_refs(source_package),
        ("Source response was preserved, but its metadata could not be normalized.",),
        ErrorCode.SCHEMA_CHANGED,
    )


def _storage_failure(source_package: dict[str, str] | None = None) -> StageResult:
    return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                       payload=_source_payload(source_package),
                       evidence_refs=_source_refs(source_package),
                       warnings=("Metadata source/normalized preservation failed.",))


def _source_refs(source_package: dict[str, str] | None) -> tuple[str, ...]:
    if source_package is None:
        return ()
    return (source_package["raw_path"], source_package["request_manifest_path"])


def _source_payload(source_package: dict[str, str] | None) -> dict | None:
    if source_package is None:
        return None
    return {key: source_package[key] for key in
            ("package_id", "raw_path", "request_manifest_path")}


def _success(saved: dict[str, str], warnings: tuple[str, ...] = ()) -> StageResult[dict]:
    return StageResult(StageStatus.SUCCEEDED, saved,
                       (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]),
                       warnings)
