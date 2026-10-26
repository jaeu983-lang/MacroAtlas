"""Orchestrator engine for safe local tabular file intake and archival."""
from datetime import datetime
from urllib.parse import urlsplit

from macro_data_platform.config import Settings
from macro_data_platform.connectors.tabular_files import (
    MAX_INPUT_BYTES,
    SUPPORTED_FORMATS,
    parse_tabular_document,
)
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, inspect_file
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.storage.tabular_archives import (
    begin_tabular_package,
    complete_tabular_package,
)

_INPUT_KEYS = {
    "relative_path", "source_url", "format", "delimiter", "sheet_name", "table_index",
    "zip_member", "header_row", "source_agency", "source_captured_at",
    "source_content_type", "source_http_status", "source_last_modified", "source_table_name",
}
_PROVENANCE_LIMITS = {
    "source_agency": 128,
    "source_content_type": 128,
    "source_last_modified": 128,
    "source_table_name": 256,
}
_PROVENANCE_KEYS = {
    "source_agency", "source_captured_at", "source_content_type", "source_http_status",
    "source_last_modified", "source_table_name",
}


def _safe_source_url(value) -> bool:
    if value is None:
        return True
    if (not isinstance(value, str) or not value or len(value) > 512
            or value.strip() != value or any(character.isspace() for character in value)
            or "?" in value or "#" in value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and parsed.hostname is not None
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _safe_provenance(data: dict) -> bool:
    for key, limit in _PROVENANCE_LIMITS.items():
        value = data.get(key)
        if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > limit):
            return False
    captured_at = data.get("source_captured_at")
    if captured_at is not None:
        if not isinstance(captured_at, str) or len(captured_at) > 40:
            return False
        try:
            parsed = datetime.fromisoformat(captured_at)
        except ValueError:
            return False
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds():
            return False
    status = data.get("source_http_status")
    return not (status is not None and (
        isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599
    ))


class TabularFileEngine:
    """Register as (\"tabular_file\", \"1\"); files must be under data/inbox/."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) - _INPUT_KEYS
                or not isinstance(data.get("relative_path"), str)
                or data.get("format") not in SUPPORTED_FORMATS
                or not _safe_source_url(data.get("source_url"))
                or not _safe_provenance(data)):
            return _invalid("Expected a repository-local inbox path and an explicit supported format.")
        try:
            relative = data["relative_path"]
            source_path = self.settings._inside(relative)
            inbox = self.settings._inside(f"{self.settings.data_dir}/inbox")
            if not source_path.is_relative_to(inbox) or not source_path.is_file():
                return _invalid("Tabular input must be an existing file under data/inbox/.")
            capacity = inspect_file(source_path, data["format"], data)
            if capacity:
                record = DeferredNonAPIStore(self.settings).register(
                    data, request.task_id, request.stage_id, capacity)
                return StageResult(StageStatus.NEEDS_REVIEW,
                                   {"non_api_deferral": record},
                                   warnings=("File deferred for separate engine inspection.",),
                                   error_code=ErrorCode.SCHEMA_CHANGED)
            size = source_path.stat().st_size
            if size <= 0 or size > MAX_INPUT_BYTES:
                return _invalid("Tabular input must be between one byte and sixteen MiB.")
            raw = source_path.read_bytes()
            context = {key: data.get(key) for key in (
                "delimiter", "header_row", "sheet_name", "table_index", "zip_member",
            ) if key in data}
            if "source_url" in data:
                context["source_url"] = data["source_url"]
            context.update({key: data[key] for key in _PROVENANCE_KEYS if key in data})
            package = begin_tabular_package(self.settings, raw, data["format"], context)
        except (OSError, ValueError):
            return _invalid("Tabular input path or local archive could not be validated.")

        if package["source_change_status"] not in {
                "not_tracked", "first_observation", "unchanged"}:
            return StageResult(
                StageStatus.NEEDS_REVIEW,
                {"package_id": package["package_id"], "raw_path": package["raw_path"],
                 "request_manifest_path": package["request_manifest_path"],
                 "source_change_status": package["source_change_status"],
                 "source_url": data.get("source_url")},
                (package["raw_path"], package["request_manifest_path"]),
                ("Prior source bytes differ or history integrity is unknown; review before normalization.",),
                ErrorCode.SCHEMA_CHANGED,
            )

        try:
            table = parse_tabular_document(
                raw, data["format"], delimiter=data.get("delimiter"),
                sheet_name=data.get("sheet_name"), table_index=data.get("table_index"),
                zip_member=data.get("zip_member"), header_row=data.get("header_row", 1),
            )
            saved = complete_tabular_package(self.settings, package, table)
        except (TypeError, ValueError) as failure:
            if any(word in str(failure) for word in ("limit", "exceed")):
                from macro_data_platform.ingestion.non_api_capacity import decision
                record = DeferredNonAPIStore(self.settings).register(
                    data, request.task_id, request.stage_id,
                    decision("parser_capacity_limit", status="inspection_required"))
                return StageResult(StageStatus.NEEDS_REVIEW,
                                   {"non_api_deferral": record, **package},
                                   warnings=("Parsing stopped at its bounded capacity guard.",),
                                   error_code=ErrorCode.SCHEMA_CHANGED)
            return StageResult(
                StageStatus.NEEDS_REVIEW,
                {"package_id": package["package_id"], "raw_path": package["raw_path"],
                 "request_manifest_path": package["request_manifest_path"]},
                (package["raw_path"], package["request_manifest_path"]),
                ("Original file was preserved, but table parsing needs review.",),
                ErrorCode.SCHEMA_CHANGED,
            )
        except OSError:
            return StageResult(
                StageStatus.FAILED_TERMINAL,
                {"package_id": package["package_id"], "raw_path": package["raw_path"]},
                (package["raw_path"],),
                ("Original file was preserved, but normalized table storage failed.",),
                ErrorCode.INTERNAL_BUG,
            )
        return StageResult(StageStatus.SUCCEEDED, {
            **saved, "mode": "local_file", "source_url": data.get("source_url"),
            "table": {"format": table.format, "headers": list(table.headers),
                      "row_count": len(table.rows),
                      "duplicate_data_rows": list(table.duplicate_data_rows),
                      "blank_data_rows": list(table.blank_data_rows),
                      "warnings": list(table.warnings)},
        }, (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]))


def _invalid(message: str) -> StageResult:
    return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                       warnings=(message,))
