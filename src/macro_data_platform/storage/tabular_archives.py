"""Write-once raw and normalized local tabular-file packages with idempotent reuse."""
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.tabular_files import (
    MAX_INPUT_BYTES,
    SUPPORTED_FORMATS,
    ParsedTable,
)
from macro_data_platform.performance.metrics import measured_phase

PARSER_VERSION = "tabular-parser-v1"
MAX_EXISTING_PACKAGES = 1000
MAX_NORMALIZED_BYTES = 64 * 1024 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024
MAX_REQUEST_MANIFEST_BYTES = 64 * 1024
_CAPTURE_METADATA_KEYS = {
    "source_captured_at", "source_content_type", "source_http_status", "source_last_modified",
}
_CONTEXT_KEYS = {
    "delimiter", "format", "header_row", "sheet_name", "source_agency", "source_captured_at",
    "source_content_type", "source_http_status", "source_last_modified", "source_table_name",
    "source_url", "table_index", "zip_member",
}


def _safe_context(context: dict) -> dict:
    if not isinstance(context, dict) or set(context) - _CONTEXT_KEYS:
        raise ValueError("unexpected tabular request context")
    result = {}
    for key, value in context.items():
        if value is not None and not isinstance(value, (str, int)):
            raise ValueError("tabular request context must contain simple values")
        if isinstance(value, str) and len(value) > 512:
            raise ValueError("tabular request context value exceeds its limit")
        result[key] = value
    return result


def _scope(context: dict) -> dict:
    return {key: value for key, value in context.items() if key not in _CAPTURE_METADATA_KEYS}


def _source_change_status(settings: Settings, root: Path, entries: list[Path],
                          context: dict, raw_sha256: str) -> str:
    if context.get("source_url") is None:
        return "not_tracked"
    if not entries:
        return "first_observation"
    if len(entries) > MAX_EXISTING_PACKAGES:
        return "unknown_history_limit"

    current_scope = _scope(context)
    matches = []
    scanned_bytes = 0
    for request_path in entries:
        if (request_path.is_symlink() or request_path.parent.is_symlink()
                or not request_path.parent.resolve().is_relative_to(root)):
            return "unknown_history_integrity"
        try:
            manifest_size = request_path.stat().st_size
            if manifest_size > MAX_REQUEST_MANIFEST_BYTES:
                return "unknown_history_limit"
            scanned_bytes += manifest_size
            if scanned_bytes > MAX_HISTORY_BYTES:
                return "unknown_history_limit"
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return "unknown_history_integrity"
        if not isinstance(request, dict):
            return "unknown_history_integrity"
        prior_context = request.get("request_context")
        if not isinstance(prior_context, dict):
            return "unknown_history_integrity"
        if _scope(prior_context) != current_scope:
            continue

        package_id = request.get("package_id")
        raw_document = request.get("raw")
        raw_relative = raw_document.get("path") if isinstance(raw_document, dict) else None
        stored_format = prior_context.get("format")
        if (not isinstance(package_id, str) or not re.fullmatch(r"[a-f0-9]{32}", package_id)
                or package_id != request_path.parent.name or stored_format not in SUPPORTED_FORMATS):
            return "unknown_history_integrity"
        expected_raw = (Path(settings.data_dir) / "raw" / "tabular" / package_id
                        / f"source.{stored_format}").as_posix()
        if raw_relative != expected_raw:
            return "unknown_history_integrity"
        original_path = settings.project_root / raw_relative
        if original_path.is_symlink() or original_path.parent.is_symlink():
            return "unknown_history_integrity"
        raw_path = settings._inside(raw_relative)
        try:
            raw_size = raw_path.stat().st_size
            if not raw_path.is_file() or raw_size > MAX_INPUT_BYTES:
                return "unknown_history_integrity"
            scanned_bytes += raw_size
            if scanned_bytes > MAX_HISTORY_BYTES:
                return "unknown_history_limit"
            previous_raw = raw_path.read_bytes()
        except OSError:
            return "unknown_history_integrity"
        previous_sha256 = hashlib.sha256(previous_raw).hexdigest()
        recorded_sha256 = raw_document.get("sha256")
        if not isinstance(recorded_sha256, str) or recorded_sha256 != previous_sha256:
            return "unknown_history_integrity"

        captured_at = prior_context.get("source_captured_at")
        try:
            sort_time = (datetime.fromisoformat(captured_at)
                         .astimezone(UTC).timestamp() if isinstance(captured_at, str)
                         else request_path.stat().st_mtime)
            modified_ns = request_path.stat().st_mtime_ns
        except (OSError, ValueError):
            return "unknown_history_integrity"
        matches.append((sort_time, modified_ns, package_id, previous_sha256))

    if not matches:
        return "first_observation"
    previous_sha256 = max(matches)[-1]
    return "unchanged" if previous_sha256 == raw_sha256 else "changed"


@measured_phase("raw_write")
def begin_tabular_package(settings: Settings, raw: bytes, format_name: str,
                          request_context: dict) -> dict:
    if format_name not in SUPPORTED_FORMATS:
        raise ValueError("unsupported tabular format")
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("tabular source exceeds its size limit")
    context = _safe_context({**request_context, "format": format_name})
    raw_digest = hashlib.sha256(raw).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({
        "parser_version": PARSER_VERSION, "raw_sha256": raw_digest, "request_context": context,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    root = settings._inside(f"{settings.data_dir}/raw/tabular")
    if root.exists():
        existing = sorted(root.glob("*/request.json"))
        if len(existing) > MAX_EXISTING_PACKAGES:
            raise ValueError("tabular archive scan limit exceeded")
        for request_path in existing:
            if (request_path.is_symlink() or request_path.parent.is_symlink()
                    or not request_path.parent.resolve().is_relative_to(root)):
                raise ValueError("tabular request manifest must not be a symbolic link")
            if request_path.stat().st_size > 64 * 1024:
                continue
            try:
                request = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(request, dict) or request.get("fingerprint") != fingerprint:
                continue
            package_id = request.get("package_id")
            raw_document = request.get("raw")
            raw_relative = raw_document.get("path") if isinstance(raw_document, dict) else None
            request_context = request.get("request_context")
            stored_format = request_context.get("format") if isinstance(request_context, dict) else None
            if (not isinstance(package_id, str) or not re.fullmatch(r"[a-f0-9]{32}", package_id)
                    or package_id != request_path.parent.name or not isinstance(stored_format, str)
                    or stored_format not in SUPPORTED_FORMATS):
                continue
            expected_raw = (Path(settings.data_dir) / "raw" / "tabular" / package_id
                            / f"source.{stored_format}").as_posix()
            if raw_relative != expected_raw:
                raise ValueError("existing tabular raw path differs from its package location")
            original_path = settings.project_root / raw_relative
            if original_path.is_symlink() or original_path.parent.is_symlink():
                raise ValueError("tabular source archive must not use a symbolic link")
            raw_path = settings._inside(raw_relative)
            if (not raw_path.is_file() or raw_path.stat().st_size > MAX_INPUT_BYTES
                    or hashlib.sha256(raw_path.read_bytes()).hexdigest() != raw_digest):
                raise ValueError("existing tabular raw package failed integrity validation")
            normalized_relative = f"{settings.data_dir}/processed/tabular/{package_id}/table.json"
            manifest_relative = f"{settings.data_dir}/raw/tabular/{package_id}/manifest.json"
            normalized_path = settings._inside(normalized_relative)
            manifest_path = settings._inside(manifest_relative)
            complete = manifest_path.is_file() and normalized_path.is_file()
            return {
                "package_id": package_id, "raw_path": raw_relative,
                "request_manifest_path": request_path.relative_to(settings.project_root).as_posix(),
                "normalized_path": normalized_relative, "manifest_path": manifest_relative,
                "complete": complete, "reused": True,
                "source_change_status": request.get("source_change_status", "unknown_history_integrity"),
            }
    source_change_status = _source_change_status(settings, root, existing if root.exists() else [],
                                                 context, raw_digest)
    package_id = uuid4().hex
    raw_relative = Path(settings.data_dir) / "raw" / "tabular" / package_id
    processed_relative = Path(settings.data_dir) / "processed" / "tabular" / package_id
    raw_directory = settings._inside(str(raw_relative))
    settings._inside(str(processed_relative)).mkdir(parents=True, exist_ok=False)
    raw_directory.mkdir(parents=True, exist_ok=False)
    raw_path = raw_directory / f"source.{format_name}"
    with raw_path.open("xb") as stream:
        stream.write(raw)
    raw_reference = raw_path.relative_to(settings.project_root).as_posix()
    request_document = {
        "package_id": package_id, "fingerprint": fingerprint, "parser_version": PARSER_VERSION,
        "request_context": context, "source_change_status": source_change_status,
        "raw": {"path": raw_reference, "sha256": raw_digest, "bytes": len(raw)},
    }
    request_path = raw_directory / "request.json"
    with request_path.open("x", encoding="utf-8") as stream:
        json.dump(request_document, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return {
        "package_id": package_id, "raw_path": raw_reference,
        "request_manifest_path": request_path.relative_to(settings.project_root).as_posix(),
        "normalized_path": f"{processed_relative.as_posix()}/table.json",
        "manifest_path": f"{raw_relative.as_posix()}/manifest.json",
        "complete": False, "reused": False, "source_change_status": source_change_status,
    }


@measured_phase("raw_write")
def complete_tabular_package(settings: Settings, package: dict, table: ParsedTable) -> dict:
    normalized_path = settings._inside(package["normalized_path"])
    manifest_path = settings._inside(package["manifest_path"])
    table_bytes = json.dumps(table.to_dict(), ensure_ascii=False, allow_nan=False,
                             indent=2, sort_keys=True).encode()
    if len(table_bytes) > MAX_NORMALIZED_BYTES:
        raise ValueError("normalized table exceeds the 64 MiB output limit")
    if normalized_path.exists() or manifest_path.exists():
        if not normalized_path.is_file() or not manifest_path.is_file():
            raise ValueError("existing tabular normalized package is incomplete")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        normalized_manifest = manifest.get("normalized") if isinstance(manifest, dict) else None
        if (not isinstance(normalized_manifest, dict)
                or hashlib.sha256(normalized_path.read_bytes()).hexdigest()
                != normalized_manifest.get("sha256")):
            raise ValueError("existing tabular normalized package failed integrity validation")
        return {
            "package_id": package["package_id"], "raw_path": package["raw_path"],
            "normalized_path": package["normalized_path"],
            "manifest_path": package["manifest_path"], "reused": True,
            "source_change_status": manifest.get("source_change_status", "unknown_history_integrity"),
        }
    with normalized_path.open("xb") as stream:
        stream.write(table_bytes)
    request_path = settings._inside(package["request_manifest_path"])
    request_manifest = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request_manifest, dict) or not isinstance(request_manifest.get("raw"), dict):
        raise TypeError("existing tabular request manifest is invalid")
    manifest = {
        "package_id": package["package_id"], "parser_version": PARSER_VERSION,
        "request_context": request_manifest["request_context"], "raw": request_manifest["raw"],
        "source_change_status": request_manifest.get("source_change_status", "unknown_history_integrity"),
        "normalized": {"path": package["normalized_path"],
                       "sha256": hashlib.sha256(table_bytes).hexdigest(),
                       "bytes": len(table_bytes)},
        "table": {"format": table.format, "headers": len(table.headers),
                  "rows": len(table.rows), "header_row": table.header_row,
                  "sheet_name": table.sheet_name, "table_index": table.table_index,
                  "zip_member": table.zip_member,
                  "duplicate_data_rows": list(table.duplicate_data_rows),
                  "blank_data_rows": list(table.blank_data_rows),
                  "warnings": list(table.warnings)},
    }
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return {
        "package_id": package["package_id"], "raw_path": package["raw_path"],
        "normalized_path": package["normalized_path"], "manifest_path": package["manifest_path"],
        "reused": False, "source_change_status": manifest["source_change_status"],
    }
