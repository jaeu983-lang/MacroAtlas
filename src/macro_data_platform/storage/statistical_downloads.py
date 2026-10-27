"""Write-once raw API bodies and credential-free request manifests."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import MAX_BYTES, ApiDownload
from macro_data_platform.performance.metrics import measured_phase, observe_download

MAX_COMPARISON_ARTIFACTS = 1000
MAX_MANIFEST_BYTES = 64 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024


def _request_fingerprint(source_url: str, request_metadata: dict) -> str:
    document = json.dumps(
        {"source_url": source_url, "request": request_metadata},
        ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(document).hexdigest()


def _comparison_fingerprint(source: str, raw: bytes) -> tuple[str, str]:
    def reject_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        document = json.loads(raw, parse_constant=reject_constant)
        if source == "bls" and isinstance(document, dict):
            document = dict(document)
            document.pop("responseTime", None)
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode()
        method = ("bls_json_without_responseTime_v1" if source == "bls"
                  else "census_json_canonical_v1")
        return hashlib.sha256(canonical).hexdigest(), method
    except (UnicodeError, ValueError, TypeError, RecursionError):
        return hashlib.sha256(raw).hexdigest(), "raw_sha256_fallback_v1"


def _comparison_fingerprint_for_source(source: str, raw: bytes) -> tuple[str, str]:
    if source == "boj":
        try:
            def reject_constant(value):
                raise ValueError(f"invalid JSON constant: {value}")

            document = json.loads(raw, parse_constant=reject_constant)
            if isinstance(document, dict):
                document = dict(document)
                # The BOJ API changes this top-level request timestamp on every response.
                document.pop("DATE", None)
            canonical = json.dumps(
                document, ensure_ascii=False, allow_nan=False, sort_keys=True,
                separators=(",", ":"),
            ).encode()
            return hashlib.sha256(canonical).hexdigest(), "boj_json_without_date_v1"
        except (UnicodeError, ValueError, TypeError, RecursionError):
            return hashlib.sha256(raw).hexdigest(), "raw_sha256_fallback_v1"
    comparison, method = _comparison_fingerprint(source, raw)
    if source == "census":
        method = "census_json_canonical_v1"
    return comparison, method


def _previous_source_status(settings: Settings, root: Path, source: str, source_url: str,
                            fingerprint: str, current_comparison_sha256: str) -> str:
    if not root.exists():
        return "first_observation"
    if root.is_symlink() or not root.is_dir():
        return "unknown_history_integrity"
    entries = sorted(root.iterdir(), key=lambda path: path.name)
    if len(entries) > MAX_COMPARISON_ARTIFACTS:
        return "unknown_history_limit"
    matches = []
    bytes_scanned = 0
    for directory in entries:
        if directory.is_symlink() or not directory.is_dir():
            continue
        manifest_path = directory / "request.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            continue
        try:
            manifest_size = manifest_path.stat().st_size
            if manifest_size > MAX_MANIFEST_BYTES:
                continue
            bytes_scanned += manifest_size
            if bytes_scanned > MAX_HISTORY_BYTES:
                return "unknown_history_limit"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if not isinstance(manifest, dict) or manifest.get("source_url") != source_url:
            continue
        prior_fingerprint = manifest.get("request_fingerprint")
        if prior_fingerprint is None and isinstance(manifest.get("request"), dict):
            try:
                prior_fingerprint = _request_fingerprint(source_url, manifest["request"])
            except (TypeError, ValueError):
                continue
        if prior_fingerprint != fingerprint:
            continue
        expected_raw = (Path(settings.data_dir) / "raw" / source / directory.name
                        / "response.json").as_posix()
        if manifest.get("raw_path") != expected_raw:
            return "unknown_history_integrity"
        raw_path = directory / "response.json"
        if raw_path.is_symlink() or not raw_path.is_file():
            return "unknown_history_integrity"
        try:
            raw_size = raw_path.stat().st_size
            if raw_size > MAX_BYTES:
                return "unknown_history_integrity"
            bytes_scanned += raw_size
            if bytes_scanned > MAX_HISTORY_BYTES:
                return "unknown_history_limit"
            previous_body = raw_path.read_bytes()
        except OSError:
            return "unknown_history_integrity"
        previous_hash = hashlib.sha256(previous_body).hexdigest()
        recorded_hash = manifest.get("raw_sha256")
        if recorded_hash is not None and recorded_hash != previous_hash:
            return "unknown_history_integrity"
        previous_comparison_hash, _ = _comparison_fingerprint_for_source(source, previous_body)
        recorded_comparison_hash = manifest.get("comparison_sha256")
        if (recorded_comparison_hash is not None
                and recorded_comparison_hash != previous_comparison_hash):
            return "unknown_history_integrity"
        retrieved_at = manifest.get("retrieved_at")
        if not isinstance(retrieved_at, str):
            return "unknown_history_integrity"
        try:
            modified_ns = manifest_path.stat().st_mtime_ns
        except OSError:
            return "unknown_history_integrity"
        matches.append((retrieved_at, modified_ns, directory.name, previous_comparison_hash,
                        recorded_hash is not None))
    if not matches:
        return "first_observation"
    _, _, _, previous_hash, history_verified = max(matches)
    if not history_verified:
        return "unknown_history_integrity"
    return "unchanged" if previous_hash == current_comparison_sha256 else "changed"


@measured_phase("raw_write")
def save_statistical_download(settings: Settings, source: str, download: ApiDownload,
                              request_metadata: dict) -> dict[str, str]:
    observe_download(download)
    if source not in {"bls", "census", "boj"}:
        raise ValueError("unsupported statistical source")
    root_relative = Path(settings.data_dir) / "raw" / source
    root = settings._inside(str(root_relative))
    root.mkdir(parents=True, exist_ok=True)
    raw_sha256 = hashlib.sha256(download.body).hexdigest()
    comparison_sha256, comparison_method = _comparison_fingerprint_for_source(source, download.body)
    fingerprint = _request_fingerprint(download.source_url, request_metadata)
    source_change_status = _previous_source_status(
        settings, root, source, download.source_url, fingerprint, comparison_sha256,
    )
    relative = root_relative / uuid4().hex
    directory = settings._inside(str(relative))
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    raw = settings._inside(str(relative / "response.json"))
    with raw.open("xb") as stream:
        stream.write(download.body)
    manifest = settings._inside(str(relative / "request.json"))
    document = {
        "source_agency": {
            "bls": "U.S. Bureau of Labor Statistics",
            "census": "U.S. Census Bureau",
            "boj": "Bank of Japan",
        }[source],
        "source_url": download.source_url,
        "retrieved_at": download.retrieved_at.isoformat(),
        "http_status": download.status_code,
        "content_type": download.content_type,
        "mode": download.kind.value,
        "byte_count": len(download.body),
        "raw_path": raw.relative_to(settings.project_root).as_posix(),
        "raw_sha256": raw_sha256,
        "comparison_sha256": comparison_sha256,
        "comparison_method": comparison_method,
        "request_fingerprint": fingerprint,
        "source_change_status": source_change_status,
        "request": request_metadata,
    }
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return {"raw_path": document["raw_path"],
            "manifest_path": manifest.relative_to(settings.project_root).as_posix(),
            "raw_sha256": raw_sha256, "source_change_status": source_change_status}
