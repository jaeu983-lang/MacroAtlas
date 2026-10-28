"""Shared typed findings for bounded file and table processing."""
import math
from dataclasses import dataclass
from enum import StrEnum


class CapacityReason(StrEnum):
    INPUT_BYTES = "input_bytes"
    DOWNLOAD_BYTES = "download_bytes"
    MEMBER_BYTES = "member_bytes"
    ROWS = "rows"
    COLUMNS = "columns"
    CELLS = "cells"
    FIELD_CHARS = "field_chars"
    ZIP_ENTRIES = "zip_entries"
    ZIP_UNCOMPRESSED_BYTES = "zip_uncompressed_bytes"
    ZIP_RATIO = "zip_ratio"
    HTML_TABLES = "html_tables"
    UNSAFE_ARCHIVE = "unsafe_archive"
    ARCHIVE_SELECTION = "archive_selection"
    NESTED_ARCHIVE = "nested_archive"
    INVALID_ARCHIVE = "invalid_archive"
    DELIMITER_UNKNOWN = "delimiter_unknown"
    HEADER_UNKNOWN = "header_unknown"
    TEXT_INSPECTION_INCOMPLETE = "text_inspection_incomplete"
    WORKSHEET_SELECTION = "worksheet_selection"
    WORKSHEET_DIMENSIONS_UNKNOWN = "worksheet_dimensions_unknown"
    WORKSHEET_INSPECTION_INCOMPLETE = "worksheet_inspection_incomplete"
    QUALIFICATION_CANDIDATE = "qualification_candidate"
    PARSER_CAPACITY_LIMIT = "parser_capacity_limit"


class CapacityDisposition(StrEnum):
    DEFERRED = "deferred"
    INSPECTION_REQUIRED = "inspection_required"
    SECURITY_REVIEW = "security_review"


_UNITS = {
    CapacityReason.INPUT_BYTES: "bytes",
    CapacityReason.DOWNLOAD_BYTES: "bytes",
    CapacityReason.MEMBER_BYTES: "bytes",
    CapacityReason.ROWS: "rows",
    CapacityReason.COLUMNS: "columns",
    CapacityReason.CELLS: "cells",
    CapacityReason.FIELD_CHARS: "characters",
    CapacityReason.ZIP_ENTRIES: "entries",
    CapacityReason.ZIP_UNCOMPRESSED_BYTES: "bytes",
    CapacityReason.ZIP_RATIO: "ratio",
    CapacityReason.HTML_TABLES: "tables",
}


@dataclass(frozen=True)
class CapacityFinding:
    reason: CapacityReason
    observed: int | float | None = None
    threshold: int | float | None = None
    inspection_point: str = "bounded_preflight"
    disposition: CapacityDisposition = CapacityDisposition.DEFERRED

    def __post_init__(self) -> None:
        if not isinstance(self.reason, CapacityReason):
            raise TypeError("reason must be a CapacityReason")
        if not isinstance(self.disposition, CapacityDisposition):
            raise TypeError("disposition must be a CapacityDisposition")
        if not isinstance(self.inspection_point, str) or not self.inspection_point:
            raise ValueError("inspection_point must be non-empty")
        for name in ("observed", "threshold"):
            value = getattr(self, name)
            if value is not None and (type(value) not in (int, float)
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be a finite nonnegative number or None")

    def to_record(self, *, policy_version: str = "non_api_v1") -> dict:
        return {
            "reason": self.reason.value,
            "observed": self.observed,
            "threshold": self.threshold,
            "status": self.disposition.value,
            "disposition": self.disposition.value,
            "policy_version": policy_version,
            "unit": _UNITS.get(self.reason),
            "inspection_point": self.inspection_point,
        }


class CapacityLimitExceeded(ValueError):
    """A parser stopped at a configured limit and exposes structured evidence."""

    def __init__(self, finding: CapacityFinding):
        if not isinstance(finding, CapacityFinding):
            raise TypeError("finding must be a CapacityFinding")
        self.finding = finding
        messages = {
            CapacityReason.ZIP_RATIO: "ZIP member expansion ratio exceeds the safety limit",
            CapacityReason.ZIP_UNCOMPRESSED_BYTES: "ZIP exceeds the uncompressed capacity limit",
            CapacityReason.ZIP_ENTRIES: "ZIP entry count exceeds the capacity limit",
            CapacityReason.ROWS: "table exceeds the row capacity limit",
            CapacityReason.COLUMNS: "table exceeds the column capacity limit",
            CapacityReason.CELLS: "table exceeds the cell capacity limit",
            CapacityReason.FIELD_CHARS: "table field exceeds the character capacity limit",
            CapacityReason.INPUT_BYTES: "source file exceeds the input byte capacity limit",
            CapacityReason.MEMBER_BYTES: "selected ZIP member exceeds the byte capacity limit",
            CapacityReason.HTML_TABLES: "HTML source exceeds the table capacity limit",
        }
        super().__init__(messages.get(finding.reason, "bounded table capacity limit was reached"))
