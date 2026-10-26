"""Orchestrator engine for safe local tabular file intake and archival."""
from macro_data_platform.config import Settings
from macro_data_platform.connectors.tabular_files import (
    MAX_INPUT_BYTES,
    SUPPORTED_FORMATS,
    parse_tabular_document,
)
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.storage.tabular_archives import (
    begin_tabular_package,
    complete_tabular_package,
)

_INPUT_KEYS = {
    "relative_path", "format", "delimiter", "sheet_name", "table_index",
    "zip_member", "header_row",
}


class TabularFileEngine:
    """Register as (\"tabular_file\", \"1\"); files must be under data/inbox/."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) - _INPUT_KEYS
                or not isinstance(data.get("relative_path"), str)
                or data.get("format") not in SUPPORTED_FORMATS):
            return _invalid("Expected a repository-local inbox path and an explicit supported format.")
        try:
            relative = data["relative_path"]
            source_path = self.settings._inside(relative)
            inbox = self.settings._inside(f"{self.settings.data_dir}/inbox")
            if not source_path.is_relative_to(inbox) or not source_path.is_file():
                return _invalid("Tabular input must be an existing file under data/inbox/.")
            size = source_path.stat().st_size
            if size <= 0 or size > MAX_INPUT_BYTES:
                return _invalid("Tabular input must be between one byte and sixteen MiB.")
            raw = source_path.read_bytes()
            context = {key: data.get(key) for key in (
                "delimiter", "header_row", "sheet_name", "table_index", "zip_member",
            ) if key in data}
            package = begin_tabular_package(self.settings, raw, data["format"], context)
        except (OSError, ValueError):
            return _invalid("Tabular input path or local archive could not be validated.")

        try:
            table = parse_tabular_document(
                raw, data["format"], delimiter=data.get("delimiter"),
                sheet_name=data.get("sheet_name"), table_index=data.get("table_index"),
                zip_member=data.get("zip_member"), header_row=data.get("header_row", 1),
            )
            saved = complete_tabular_package(self.settings, package, table)
        except (TypeError, ValueError):
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
            **saved, "mode": "local_file",
            "table": {"format": table.format, "headers": list(table.headers),
                      "row_count": len(table.rows),
                      "duplicate_data_rows": list(table.duplicate_data_rows),
                      "blank_data_rows": list(table.blank_data_rows),
                      "warnings": list(table.warnings)},
        }, (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]))


def _invalid(message: str) -> StageResult:
    return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                       warnings=(message,))
