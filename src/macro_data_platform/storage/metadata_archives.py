"""Separate write-once metadata source evidence from normalized records."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.performance.metrics import measured_phase, observe_download


@measured_phase("raw_write")
def begin_metadata_package(settings: Settings, source: str, download: ApiDownload,
                           request_context: dict) -> dict[str, str]:
    observe_download(download)
    if source not in {"bls", "census", "sdmx", "codebook"}:
        raise ValueError("unsupported metadata source")
    package_id = uuid4().hex
    raw_relative = Path(settings.data_dir) / "raw" / "metadata" / source / package_id
    normalized_relative = Path(settings.data_dir) / "processed" / "metadata" / source / package_id
    raw_directory = settings._inside(str(raw_relative))
    normalized_directory = settings._inside(str(normalized_relative))
    raw_directory.mkdir(parents=True, exist_ok=False)
    normalized_directory.mkdir(parents=True, exist_ok=False)
    suffix = "xml" if "xml" in download.content_type.lower() else "json"
    raw_path = raw_directory / f"source.{suffix}"
    raw_path.write_bytes(download.body)
    raw_reference = raw_path.relative_to(settings.project_root).as_posix()
    raw_digest = hashlib.sha256(download.body).hexdigest()
    request_manifest = {
        "package_id": package_id, "source": source, "source_url": download.source_url,
        "retrieved_at": download.retrieved_at.isoformat(),
        "http_status": download.status_code, "content_type": download.content_type,
        "evidence_kind": download.kind.value, "request_context": request_context,
        "raw": {"path": raw_reference, "sha256": raw_digest, "bytes": len(download.body)},
    }
    request_manifest_path = raw_directory / "request.json"
    with request_manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(request_manifest, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return {
        "package_id": package_id, "source": source, "source_url": download.source_url,
        "retrieved_at": download.retrieved_at.isoformat(), "http_status": str(download.status_code),
        "content_type": download.content_type, "evidence_kind": download.kind.value,
        "raw_path": raw_reference,
        "request_manifest_path": request_manifest_path.relative_to(settings.project_root).as_posix(),
        "raw_sha256": raw_digest,
        "normalized_directory": normalized_directory.relative_to(settings.project_root).as_posix(),
    }


@measured_phase("raw_write")
def complete_metadata_package(settings: Settings, source_package: dict[str, str],
                               records: list[dict], request_context: dict) -> dict[str, str]:
    if not isinstance(records, list) or not records:
        raise ValueError("metadata package requires normalized records")
    normalized_directory = settings._inside(source_package["normalized_directory"])
    raw_reference = source_package["raw_path"]
    for record in records:
        raw_ref = record.get("raw_ref")
        if isinstance(raw_ref, dict):
            raw_ref["path"] = raw_reference
    normalized_path = normalized_directory / "normalized.json"
    normalized_bytes = json.dumps(records, ensure_ascii=False, allow_nan=False,
                                  indent=2, sort_keys=True).encode()
    with normalized_path.open("xb") as stream:
        stream.write(normalized_bytes)
    manifest = {
        "package_id": source_package["package_id"], "source": source_package["source"],
        "source_url": source_package["source_url"],
        "retrieved_at": source_package["retrieved_at"],
        "http_status": int(source_package["http_status"]),
        "content_type": source_package["content_type"],
        "evidence_kind": source_package["evidence_kind"], "request_context": request_context,
        "raw": {"path": raw_reference, "sha256": source_package["raw_sha256"]},
        "normalized": {
            "path": normalized_path.relative_to(settings.project_root).as_posix(),
            "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
            "record_count": len(records),
        },
    }
    manifest_path = settings._inside(
        str(Path(source_package["request_manifest_path"]).parent / "manifest.json")
    )
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return {
        "package_id": source_package["package_id"],
        "raw_path": raw_reference,
        "normalized_path": manifest["normalized"]["path"],
        "manifest_path": manifest_path.relative_to(settings.project_root).as_posix(),
    }


def save_metadata_package(settings: Settings, source: str, download: ApiDownload,
                          records: list[dict], request_context: dict) -> dict[str, str]:
    source_package = begin_metadata_package(settings, source, download, request_context)
    return complete_metadata_package(settings, source_package, records, request_context)
