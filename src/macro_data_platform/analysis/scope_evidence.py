"""Read-only, allowlisted resolution of institution and dataset from saved file evidence."""
import hashlib
import json
import re
import zipfile
import zlib
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

BIS_FLAT_URL = "https://data.bis.org/static/bulk/WS_GLI_csv_flat.zip"
BIS_FLAT_AGENCY = "Bank for International Settlements"
BIS_FLAT_DATASET = "WS_GLI_csv_flat"
_PACKAGE_ID = re.compile(r"[a-f0-9]{32}\Z")
_RAW_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_RAW_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVES = 1000
_MAX_SCAN_BYTES = 64 * 1024 * 1024
_MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024


def _safe_file(project_root: Path, data_dir: str, relative: str, *, limit: int):
    if (not isinstance(relative, str) or not relative or len(relative) > 512
            or "\\" in relative):
        return None
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        return None
    if not parsed.parts or parsed.parts[0] != data_dir:
        return None
    root = project_root.resolve()
    current = root
    try:
        for part in parsed.parts:
            current = current / part
            if current.is_symlink():
                return None
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return None
        size = resolved.stat().st_size
        if size <= 0 or size > limit:
            return None
        return resolved
    except OSError:
        return None


def _hash_file(path: Path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _valid_flat_archive(path: Path):
    """Require the bounded, known one-member CSV profile without extracting it."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if (len(members) != 1 or members[0].filename != "WS_GLI_csv_flat.csv"
                    or members[0].file_size <= 0
                    or members[0].file_size > _MAX_ZIP_MEMBER_BYTES):
                return False
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError,
            EOFError, NotImplementedError, zlib.error):
        return False


def _verified_manifest(project_root: Path, data_dir: str, relative: str,
                       *, expected_url: str, expected_agency: str | None):
    manifest_path = _safe_file(project_root, data_dir, relative, limit=_MAX_MANIFEST_BYTES)
    if manifest_path is None:
        return None
    try:
        raw_manifest = manifest_path.read_bytes()
        document = json.loads(raw_manifest)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    package_id = document.get("package_id")
    context = document.get("request_context")
    raw = document.get("raw")
    captured_at = context.get("source_captured_at") if isinstance(context, dict) else None
    try:
        parsed_captured_at = (datetime.fromisoformat(captured_at)
                              if isinstance(captured_at, str) and len(captured_at) <= 64
                              else None)
    except ValueError:
        parsed_captured_at = None
    if (not isinstance(package_id, str) or not _PACKAGE_ID.fullmatch(package_id)
            or not isinstance(context, dict) or not isinstance(raw, dict)
            or context.get("source_url") != expected_url
            or context.get("source_agency") != BIS_FLAT_AGENCY
            or (expected_agency is not None and expected_agency != BIS_FLAT_AGENCY)
            or context.get("source_http_status") != 200
            or parsed_captured_at is None or parsed_captured_at.utcoffset() != timedelta(0)):
        return None
    relative_dir = PurePosixPath(data_dir) / "raw" / "tabular" / package_id
    expected_manifest = relative_dir / "request.json"
    format_name = context.get("format")
    raw_relative = raw.get("path")
    if (manifest_path.relative_to(project_root.resolve()).as_posix()
            != expected_manifest.as_posix()
            or format_name != "zip"
            or raw_relative != (relative_dir / f"source.{format_name}").as_posix()):
        return None
    expected_digest = raw.get("sha256")
    expected_bytes = raw.get("bytes")
    if (not isinstance(expected_digest, str) or not _RAW_SHA256.fullmatch(expected_digest)
            or type(expected_bytes) is not int or expected_bytes <= 0):
        return None
    raw_path = _safe_file(project_root, data_dir, raw_relative, limit=_MAX_RAW_BYTES)
    if raw_path is None or raw_path.stat().st_size != expected_bytes:
        return None
    actual_digest = _hash_file(raw_path)
    if actual_digest != expected_digest or not _valid_flat_archive(raw_path):
        return None
    return {
        "request_manifest_path": relative,
        "request_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "raw_path": raw_relative,
        "raw_sha256": actual_digest,
        "source_url": expected_url,
        "source_agency": BIS_FLAT_AGENCY,
    }


def _find_manifest_for_raw(project_root: Path, data_dir: str, expected_url: str,
                           candidate_sha256: str, expected_agency: str | None):
    archive_root = project_root / data_dir / "raw" / "tabular"
    try:
        if archive_root.is_symlink() or not archive_root.is_dir():
            return None
        manifests = []
        for path in archive_root.glob("*/request.json"):
            manifests.append(path)
            if len(manifests) > _MAX_ARCHIVES:
                return None
    except OSError:
        return None
    scanned = 0
    verified = []
    for path in sorted(manifests):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            size = path.stat().st_size
            if size <= 0 or size > _MAX_MANIFEST_BYTES:
                continue
            scanned += size
            if scanned > _MAX_SCAN_BYTES:
                return None
            contents = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        context = contents.get("request_context") if isinstance(contents, dict) else None
        if not isinstance(context, dict) or context.get("source_url") != expected_url:
            continue
        relative = path.relative_to(project_root.resolve()).as_posix()
        capture = _verified_manifest(project_root, data_dir, relative,
                                     expected_url=expected_url,
                                     expected_agency=expected_agency)
        if capture is not None and capture["raw_sha256"] == candidate_sha256:
            verified.append(capture)
    return verified[0] if verified else None


def resolve_bis_flat_scope(project_root: Path, data_dir: str, *, source_url: str | None,
                           source_agency: str | None, source_raw_path: str | None,
                           request_manifest_path: str | None):
    """Resolve only the exact archived BIS flat ZIP profile with verified raw provenance."""
    if source_url != BIS_FLAT_URL:
        return None
    if source_agency is not None and source_agency != BIS_FLAT_AGENCY:
        return None
    candidate = _safe_file(project_root, data_dir, source_raw_path or "",
                           limit=_MAX_RAW_BYTES)
    if candidate is None:
        return None
    candidate_sha256 = _hash_file(candidate)
    if candidate_sha256 is None:
        return None
    if request_manifest_path is not None:
        capture = _verified_manifest(project_root, data_dir, request_manifest_path,
                                     expected_url=source_url,
                                     expected_agency=source_agency)
        if capture is None or capture["raw_sha256"] != candidate_sha256:
            return None
        if candidate.relative_to(project_root.resolve()).as_posix() != capture["raw_path"]:
            return None
    else:
        capture = _find_manifest_for_raw(project_root, data_dir, source_url,
                                         candidate_sha256, source_agency)
        if capture is None:
            return None
    return {
        "institution_id": "bis",
        "dataset_id": BIS_FLAT_DATASET,
        "adapter_id": "bis_flat_zip_verified_manifest_v1",
        "source_evidence": capture,
    }
