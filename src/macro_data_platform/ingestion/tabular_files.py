"""Orchestrator engine for safe local tabular file intake and archival."""
from datetime import UTC, datetime
from urllib.parse import urlsplit

from macro_data_platform.capacity import (
    CapacityDisposition,
    CapacityFinding,
    CapacityLimitExceeded,
    CapacityReason,
)
from macro_data_platform.config import Settings
from macro_data_platform.connectors.tabular_files import (
    MAX_INPUT_BYTES,
    SUPPORTED_FORMATS,
    parse_tabular_document,
)
from macro_data_platform.contracts import ErrorCode, ObservationStatus, StageResult, StageStatus
from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
)
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, inspect_file
from macro_data_platform.ingestion.typed_series import persist_typed_series_result
from macro_data_platform.metadata.series import normalize_tabular_series
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.performance.metrics import current_metrics
from macro_data_platform.storage.tabular_archives import (
    begin_tabular_package,
    complete_tabular_package,
)

_INPUT_KEYS = {
    "relative_path", "source_url", "format", "delimiter", "sheet_name", "table_index",
    "zip_member", "header_row", "source_agency", "source_captured_at",
    "source_content_type", "source_http_status", "source_last_modified", "source_table_name",
    "series_mapping",
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
    def __init__(self, settings: Settings, *, clock=lambda: datetime.now(UTC),
                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY):
        self.settings = settings
        self.clock, self.freshness_policy = clock, freshness_policy

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) - _INPUT_KEYS
                or not isinstance(data.get("relative_path"), str)
                or data.get("format") not in SUPPORTED_FORMATS
                or not _safe_source_url(data.get("source_url"))
                or ("series_mapping" in data and (
                    not isinstance(data.get("series_mapping"), dict)
                    or not isinstance(data.get("source_agency"), str)
                    or not data["source_agency"].strip()
                ))
                or not _safe_provenance(data)):
            return _invalid("Expected a repository-local inbox path and an explicit supported format.")
        try:
            relative = data["relative_path"]
            original = self.settings.project_root / relative
            if any(part.is_symlink() for part in (original, *original.parents)):
                return _invalid("Tabular input must not traverse a symbolic link.")
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
            with source_path.open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES)
            metrics = current_metrics()
            if metrics is not None:
                metrics.observe_input(byte_count=len(raw))
                metrics.observe_sample_class("stored")
            if len(raw) >= MAX_INPUT_BYTES:
                record = DeferredNonAPIStore(self.settings).register(
                    data, request.task_id, request.stage_id,
                    CapacityFinding(
                        CapacityReason.INPUT_BYTES, len(raw), MAX_INPUT_BYTES,
                        "intake.bounded_read", CapacityDisposition.DEFERRED,
                    ).to_record())
                return StageResult(StageStatus.NEEDS_REVIEW, {"non_api_deferral": record},
                                   warnings=("Input grew beyond the bounded file budget.",),
                                   error_code=ErrorCode.SCHEMA_CHANGED)
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
        except CapacityLimitExceeded as failure:
            record = DeferredNonAPIStore(self.settings).register(
                data, request.task_id, request.stage_id,
                failure.finding.to_record())
            return StageResult(StageStatus.NEEDS_REVIEW,
                               {"non_api_deferral": record, **package},
                               warnings=("Parsing stopped at its bounded capacity guard.",),
                               error_code=ErrorCode.SCHEMA_CHANGED)
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
        payload = {
            **saved, "mode": "local_file", "source_url": data.get("source_url"),
            "table": {"format": table.format, "headers": list(table.headers),
                      "row_count": len(table.rows),
                      "duplicate_data_rows": list(table.duplicate_data_rows),
                      "blank_data_rows": list(table.blank_data_rows),
                      "warnings": list(table.warnings)},
        }
        if "series_mapping" in data:
            try:
                retrieved_at = self.clock()
                typed = normalize_tabular_series(
                    headers=table.headers, rows=table.rows, mapping=data["series_mapping"],
                    source_agency=data["source_agency"], source_url=data.get("source_url"),
                    retrieved_at=retrieved_at, raw_ref=saved["raw_path"],
                    manifest_ref=saved["manifest_path"],
                )
                series_key = {
                    "source_agency": typed.source_agency,
                    "series_id": typed.series_id,
                }
                if typed.dataset_id is not None:
                    series_key["dataset_id"] = typed.dataset_id
                series_key.update({
                    f"dimension:{name}": value for name, value in typed.dimensions.items()
                })
                freshness = assess_freshness(
                    [observation.period for observation in typed.observations
                     if observation.status == ObservationStatus.OBSERVED],
                    frequency=typed.frequency,
                    frequency_basis=typed.frequency_basis,
                    series_key=series_key,
                    as_of=retrieved_at,
                    policy=self.freshness_policy,
                )
            except (TypeError, ValueError):
                return StageResult(
                    StageStatus.NEEDS_REVIEW, payload,
                    (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]),
                    ("File was archived, but its explicit series mapping needs review.",),
                    ErrorCode.SCHEMA_CHANGED,
                )
            payload["series_contract"] = {
                "schema_version": "time-series-v1", "series_id": typed.series_id,
                "dataset_id": typed.dataset_id, "observation_count": len(typed.observations),
                "unit": typed.unit, "currency": typed.currency,
                "frequency": typed.frequency, "frequency_basis": typed.frequency_basis,
                "dimensions": dict(typed.dimensions), "retrieved_at": typed.retrieved_at.isoformat(),
                "source_url": typed.source_url, "raw_ref": typed.raw_ref,
                "manifest_ref": typed.manifest_ref,
            }
            issue = (
                "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
                "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
            )
            payload["quality"] = {
                "status": "failed" if issue else "passed",
                "issues": [issue] if issue else [],
                "freshness": freshness,
            }
            if issue:
                payload["withheld_observation_count"] = len(typed.observations)
                return StageResult(
                    StageStatus.NEEDS_REVIEW, payload,
                    (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]),
                    (issue, freshness["status"]), ErrorCode.QUALITY_FAILURE,
                )
            return persist_typed_series_result(
                self.settings, payload=payload, series=(typed,), engine_id="tabular_file/1",
                refs=(saved["raw_path"], saved["normalized_path"], saved["manifest_path"]),
            )
        return StageResult(
            StageStatus.SUCCEEDED, payload,
            (saved["raw_path"], saved["normalized_path"], saved["manifest_path"]),
        )


def _invalid(message: str) -> StageResult:
    return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                       warnings=(message,))
