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
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_AGENCY = "U.S. Bureau of Labor Statistics"
CENSUS_AGENCY = "U.S. Census Bureau"
_PACKAGE_ID = re.compile(r"[a-f0-9]{32}\Z")
_RAW_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_RAW_BYTES = 16 * 1024 * 1024
_MAX_API_RAW_BYTES = 4 * 1024 * 1024
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
    except (OSError, UnicodeError, ValueError, RecursionError):
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
                           request_manifest_path: str | None,
                           expected_raw_sha256: str | None = None,
                           expected_manifest_sha256: str | None = None):
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
    if (expected_raw_sha256 is not None and capture["raw_sha256"] != expected_raw_sha256
            or expected_manifest_sha256 is not None
            and capture["request_manifest_sha256"] != expected_manifest_sha256):
        return None
    return {
        "institution_id": "bis",
        "dataset_id": BIS_FLAT_DATASET,
        "adapter_id": "bis_flat_zip_verified_manifest_v1",
        "source_evidence": capture,
    }


def _verified_json_api_capture(project_root: Path, data_dir: str, *, engine: str,
                               source_url: str, source_agency: str,
                               source_raw_path: str | None, source_raw_sha256: str | None,
                               request_manifest_path: str | None,
                               expected_request: dict):
    """Verify one bounded JSON API response against its colocated saved request manifest."""
    if (not isinstance(source_raw_sha256, str)
            or not _RAW_SHA256.fullmatch(source_raw_sha256)
            or not isinstance(request_manifest_path, str)):
        return None
    manifest_relative = PurePosixPath(request_manifest_path)
    package_id = manifest_relative.parent.name
    expected_dir = PurePosixPath(data_dir) / "raw" / engine / package_id
    expected_manifest = expected_dir / "request.json"
    expected_raw = expected_dir / "response.json"
    if (not _PACKAGE_ID.fullmatch(package_id)
            or manifest_relative.as_posix() != expected_manifest.as_posix()
            or source_raw_path != expected_raw.as_posix()):
        return None
    manifest_path = _safe_file(project_root, data_dir, request_manifest_path,
                               limit=_MAX_MANIFEST_BYTES)
    raw_path = _safe_file(project_root, data_dir, source_raw_path,
                          limit=_MAX_API_RAW_BYTES)
    if manifest_path is None or raw_path is None:
        return None
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        response_bytes = raw_path.read_bytes()
        response = json.loads(response_bytes)
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None
    if not isinstance(manifest, dict):
        return None
    request = manifest.get("request")
    try:
        captured_at = datetime.fromisoformat(manifest.get("retrieved_at", ""))
    except (TypeError, ValueError):
        return None
    raw_digest = manifest.get("raw_sha256")
    if (manifest.get("mode") != "live_api"
            or manifest.get("source_url") != source_url
            or manifest.get("source_agency") != source_agency
            or type(manifest.get("http_status")) is not int
            or manifest["http_status"] != 200
            or not isinstance(manifest.get("content_type"), str)
            or manifest["content_type"].split(";", 1)[0].strip().lower() != "application/json"
            or captured_at.utcoffset() != timedelta(0)
            or manifest.get("raw_path") != expected_raw.as_posix()
            or not isinstance(raw_digest, str) or not _RAW_SHA256.fullmatch(raw_digest)
            or raw_digest != source_raw_sha256
            or type(manifest.get("byte_count")) is not int
            or manifest["byte_count"] != len(response_bytes)
            or _hash_file(raw_path) != raw_digest
            or not isinstance(request, dict)
            or any(request.get(key) != value for key, value in expected_request.items())):
        return None
    return {
        "request_manifest_path": request_manifest_path,
        "request_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "raw_path": source_raw_path,
        "raw_sha256": raw_digest,
        "source_url": source_url,
        "source_agency": source_agency,
        "response": response,
    }


def resolve_bls_scope(project_root: Path, data_dir: str, *, source_url: str | None,
                      source_agency: str | None, dataset_id: str | None,
                      source_raw_path: str | None, source_raw_sha256: str | None,
                      request_manifest_path: str | None, series_ids,
                      start_year, end_year):
    """Recover only BLS agency identity; this API response does not establish a dataset ID."""
    if (source_url != BLS_API_URL or source_agency != BLS_AGENCY or dataset_id is not None
            or not isinstance(series_ids, list) or not series_ids
            or any(not isinstance(item, str) or not re.fullmatch(r"[A-Z0-9]{2,30}", item)
                   for item in series_ids)
            or len(set(series_ids)) != len(series_ids)
            or type(start_year) is not int or type(end_year) is not int
            or not 1900 <= start_year <= end_year <= 2100):
        return None
    capture = _verified_json_api_capture(
        project_root, data_dir, engine="bls", source_url=BLS_API_URL,
        source_agency=BLS_AGENCY, source_raw_path=source_raw_path,
        source_raw_sha256=source_raw_sha256,
        request_manifest_path=request_manifest_path,
        expected_request={"series_ids": series_ids, "start_year": start_year,
                          "end_year": end_year},
    )
    if capture is None:
        return None
    response = capture.pop("response")
    results = response.get("Results") if isinstance(response, dict) else None
    returned_series = results.get("series") if isinstance(results, dict) else None
    returned_ids = (
        [item.get("seriesID") for item in returned_series]
        if isinstance(returned_series, list) and all(isinstance(item, dict)
                                                     for item in returned_series)
        else None
    )
    if (not isinstance(response, dict) or response.get("status") != "REQUEST_SUCCEEDED"
            or returned_ids is None or len(returned_ids) != len(series_ids)
            or any(not isinstance(item, str) for item in returned_ids)
            or set(returned_ids) != set(series_ids)):
        return None
    return {
        "institution_id": "bls",
        "dataset_id": None,
        "adapter_id": "bls_official_api_manifest_v1",
        "source_evidence": capture,
    }


def resolve_census_scope(project_root: Path, data_dir: str, *, source_url: str | None,
                         source_agency: str | None, payload_dataset_id: str | None,
                         plan_dataset_id: str | None, year, variables,
                         geography, source_raw_path: str | None,
                         source_raw_sha256: str | None,
                         request_manifest_path: str | None):
    """Recover a Census dataset only from matching URL, saved request, and raw JSON."""
    if (plan_dataset_id not in {"acs/acs1", "acs/acs5"}
            or payload_dataset_id != plan_dataset_id
            or type(year) is not int or not 2009 <= year <= 2100
            or not isinstance(variables, list) or not variables
            or any(not isinstance(item, str)
                   or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,30}", item) for item in variables)
            or len(set(variables)) != len(variables)
            or not isinstance(geography, str) or not geography
            or not re.fullmatch(r"(?:us:1|state:[0-9]{2})", geography)
            or source_agency != CENSUS_AGENCY):
        return None
    expected_url = f"https://api.census.gov/data/{year}/{plan_dataset_id}"
    if source_url != expected_url:
        return None
    capture = _verified_json_api_capture(
        project_root, data_dir, engine="census", source_url=expected_url,
        source_agency=CENSUS_AGENCY, source_raw_path=source_raw_path,
        source_raw_sha256=source_raw_sha256,
        request_manifest_path=request_manifest_path,
        expected_request={"dataset": plan_dataset_id, "year": year,
                          "variables": variables, "geography": geography},
    )
    if capture is None:
        return None
    response = capture.pop("response")
    headers = response[0] if isinstance(response, list) and response else None
    if (not isinstance(response, list) or not response
            or not isinstance(headers, list)
            or any(not isinstance(item, str) for item in headers)
            or headers != [*variables, geography.split(":", 1)[0]]):
        return None
    return {
        "institution_id": "census",
        "dataset_id": plan_dataset_id,
        "adapter_id": "census_official_api_manifest_v1",
        "source_evidence": capture,
    }
