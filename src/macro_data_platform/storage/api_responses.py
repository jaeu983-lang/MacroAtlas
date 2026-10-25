"""Write-once API response archives with source-aware, verifiable manifests."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import JsonApiResponse, _redact_payload
from macro_data_platform.connectors.official_files import (
    OfficialFileResponse,
    validate_official_file_identity,
)
from macro_data_platform.connectors.sdmx import SdmxApiResponse
from macro_data_platform.connectors.worldbank import API_DOCS as WORLDBANK_API_DOCS
from macro_data_platform.connectors.worldbank import TERMS_URL as WORLDBANK_TERMS_URL
from macro_data_platform.connectors.worldbank import Download
from macro_data_platform.contracts import EvidenceKind

MAX_ARCHIVE_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ID = re.compile(r"(?:INT|US|EU|JP)-[0-9]{2}\Z", re.ASCII)
_SENSITIVE_QUERY_NAMES = frozenset({
    "userid", "appid", "apikey", "api_key", "applicationid", "application_id",
    "bea_api_key", "estat_app_id", "fred_api_key", "census_api_key", "bls_api_key",
    "key", "registrationkey",
})

# These are the API clients currently implemented. A provider is not inferred
# from a display label: its institution ID and official HTTPS host must agree.
_SOURCE_PROFILES = {
    "INT-02": ("BIS", "stats.bis.org"),
    "INT-03": ("OECD", "sdmx.oecd.org"),
    "EU-01": ("ECB", "data-api.ecb.europa.eu"),
    "EU-02": ("Eurostat", "ec.europa.eu"),
    "EU-03": ("Deutsche Bundesbank", "api.statistiken.bundesbank.de"),
    "EU-05": ("INSEE", "bdm.insee.fr"),
    "INT-04": ("World Bank", "api.worldbank.org"),
    "US-04": ("BEA", "apps.bea.gov"),
    "JP-03": ("e-Stat", "api.e-stat.go.jp"),
    "US-02": ("FRED", "api.stlouisfed.org"),
    "US-05": ("BLS", "api.bls.gov"),
    "US-06": ("Census", "api.census.gov"),
    "US-03": ("U.S. Treasury TIC", "ticdata.treasury.gov"),
    "EU-04": ("Bank of England", "www.bankofengland.co.uk"),
}
_FILE_SOURCE_IDS = frozenset({"US-03", "EU-04"})
_JSON_SOURCE_IDS = {
    "BEA": "US-04", "e-Stat": "JP-03", "FRED": "US-02", "BLS": "US-05", "Census": "US-06",
}


@dataclass(frozen=True)
class SavedApiArtifact:
    institution_id: str
    raw_path: str
    manifest_path: str
    raw_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class LoadedApiArtifact:
    manifest: dict[str, Any]
    body: bytes


def _safe_text(value: str, secrets: tuple[str, ...], *, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError("API artifact metadata contains invalid text")
    safe = value
    for secret in secrets:
        if not secret:
            continue
        for variant in {secret, quote(secret, safe=""), quote_plus(secret, safe="")}:
            if variant:
                safe = safe.replace(variant, "[REDACTED]")
    return safe


def _safe_source_url(value: str, institution_id: str, secrets: tuple[str, ...]) -> str:
    _source_agency, expected_host = _SOURCE_PROFILES[institution_id]
    if not isinstance(value, str) or len(value) > 8_192:
        raise ValueError("API artifact source URL exceeds the supported format")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError("API artifact source URL is malformed") from None
    if (parts.scheme != "https" or parts.hostname != expected_host or port not in {None, 443}
            or parts.username is not None or parts.password is not None or parts.fragment):
        raise ValueError("API artifact source URL does not match its official provider")
    safe_query = [
        (name, _safe_text(item, secrets, limit=4_096))
        for name, item in parse_qsl(parts.query, keep_blank_values=True)
        if name.casefold() not in _SENSITIVE_QUERY_NAMES
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), ""))


def _safe_request_parameters(
    parameters: tuple[tuple[str, str], ...], secrets: tuple[str, ...],
) -> list[dict[str, str]]:
    result = []
    for name, value in parameters:
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("API request metadata must contain text pairs")
        if name.casefold() in _SENSITIVE_QUERY_NAMES:
            continue
        result.append({
            "name": _safe_text(name, secrets, limit=128),
            "value": _safe_text(value, secrets, limit=4_096),
        })
    return result


def _response_envelope(
    settings: Settings,
    response: Download | JsonApiResponse | SdmxApiResponse | OfficialFileResponse,
    dataset_id: str | None,
    series_id: str | None,
) -> tuple[str, dict[str, Any], bytes, str]:
    secrets = tuple(
        value for value in (
            settings.bea_api_key, settings.estat_app_id, settings.fred_api_key,
            settings.census_api_key, settings.bls_api_key,
        ) if value
    )
    if isinstance(response, Download):
        institution_id, source_agency = "INT-04", "World Bank"
        source_url = response.source_url
        operation = "indicator_data"
        status, retrieved_at, content_type = (
            response.status_code, response.retrieved_at, response.content_type,
        )
        body = response.body
        representation = "http_entity_bytes_after_requests_content_decoding"
        request_parameters: list[dict[str, str]] = []
        mode = response.kind.value
    elif isinstance(response, JsonApiResponse):
        institution_id = _JSON_SOURCE_IDS.get(response.source_agency)
        if institution_id is None:
            raise ValueError("JSON API response source is not registered for archival")
        source_agency = response.source_agency
        source_url = response.source_url
        operation = response.method
        status, retrieved_at, content_type = (
            response.http_status, response.retrieved_at, response.content_type,
        )
        try:
            body = json.dumps(
                _redact_payload(response.payload, secrets), ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise ValueError("Sanitized JSON API payload could not be serialized") from None
        representation = "sanitized_json_payload_canonical_utf8"
        request_parameters = _safe_request_parameters(response.request_parameters, secrets)
        mode = "api_response"
    elif isinstance(response, OfficialFileResponse):
        institution_id, source_agency = response.institution_id, response.source_agency
        if (institution_id not in _FILE_SOURCE_IDS or response.format != "csv"
                or response.kind not in {EvidenceKind.FIXTURE, EvidenceKind.LIVE_INGESTION}):
            raise ValueError("Official file identity, format or evidence is unsupported")
        if dataset_id is not None and dataset_id != response.dataset_id:
            raise ValueError("Official file dataset cannot differ from the downloaded selection")
        dataset_id, source_url = response.dataset_id, response.source_url
        operation = "official_csv_download"
        status, retrieved_at, content_type = response.http_status, response.retrieved_at, response.content_type
        body = response.body
        if any(value.encode("utf-8") in body for value in secrets):
            raise ValueError("Official file contains a configured credential; archival was refused")
        representation = "http_entity_bytes_after_requests_content_decoding"
        request_parameters = _safe_request_parameters(response.request_parameters, secrets)
        mode = response.kind.value
    elif isinstance(response, SdmxApiResponse):
        institution_id = response.institution_id
        expected = _SOURCE_PROFILES.get(institution_id)
        if expected is None or response.source_agency != expected[0]:
            raise ValueError("SDMX API response source identity is inconsistent")
        source_agency = response.source_agency
        source_url = response.source_url
        operation = response.operation
        status, retrieved_at, content_type = (
            response.http_status, response.retrieved_at, response.content_type,
        )
        body = response.body
        if any(value.encode("utf-8") in body for value in secrets):
            raise ValueError("SDMX response contains a configured credential; archival was refused")
        representation = "http_entity_bytes_after_requests_content_decoding"
        request_parameters = []
        mode = "api_response"
    else:
        raise TypeError("unsupported API response type")

    profile = _SOURCE_PROFILES.get(institution_id)
    if profile is None or profile[0] != source_agency or not _ID.fullmatch(institution_id):
        raise ValueError("API artifact source identity is not registered")
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("API artifact HTTP status is invalid")
    if status != 200 and not isinstance(response, Download):
        raise ValueError("only complete HTTP 200 API responses can be archived")
    if not isinstance(retrieved_at, datetime) or retrieved_at.utcoffset() is None:
        raise ValueError("API artifact retrieval timestamp must include a timezone")
    if not isinstance(body, bytes) or len(body) > MAX_ARCHIVE_RESPONSE_BYTES:
        raise ValueError("API artifact body exceeds the archive limit")
    if not isinstance(content_type, str) or len(content_type) > 512:
        raise ValueError("API artifact content type is invalid")
    if not isinstance(operation, str) or not operation or len(operation) > 128:
        raise ValueError("API artifact operation is invalid")
    http_method = response.http_method if isinstance(response, JsonApiResponse) else "GET"
    if http_method not in {"GET", "POST"}:
        raise ValueError("API artifact HTTP method is unsupported")

    safe_url = _safe_source_url(source_url, institution_id, secrets)
    safe_dataset = None if dataset_id is None else _safe_text(dataset_id, secrets, limit=2_048)
    safe_series = None if series_id is None else _safe_text(series_id, secrets, limit=2_048)
    suffix = ("csv" if isinstance(response, OfficialFileResponse) else "json"
              if representation == "sanitized_json_payload_canonical_utf8" or institution_id == "INT-04" else "bin")
    representation_label = (
        "HTTP entity bytes after requests content decoding; not wire bytes."
        if representation == "http_entity_bytes_after_requests_content_decoding"
        else "Sanitized JSON payload serialized as canonical UTF-8; not original HTTP bytes."
    )
    retrieved_utc = retrieved_at.astimezone(UTC).isoformat()
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "institution_id": institution_id,
        "source_agency": source_agency,
        "api_provider": source_agency,
        "source_url": safe_url,
        "operation": _safe_text(operation, secrets, limit=128),
        "http_method": http_method,
        "dataset_id": safe_dataset,
        "series_id": safe_series,
        "retrieved_at": retrieved_utc,
        "http_status": status,
        "response_accepted": status == 200,
        "content_type": _safe_text(content_type, secrets, limit=512),
        "mode": mode,
        "representation": representation_label,
        "representation_code": representation,
        "request_parameters": request_parameters,
        "byte_count": len(body),
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "raw_filename": f"response.{suffix}",
        "access_method": "official_file" if isinstance(response, OfficialFileResponse) else "api",
    }
    if isinstance(response, Download):
        metadata.update({
            "api_documentation_url": WORLDBANK_API_DOCS,
            "terms_url": WORLDBANK_TERMS_URL,
            "license_note": "Dataset-specific terms apply; no blanket license inferred.",
        })
    if institution_id == "US-02":
        metadata.update({
            "api_provider": "Federal Reserve Bank of St. Louis (FRED)",
            "original_source_agency": None,
            "source_role": "API provider; original agency requires release/source metadata.",
        })
    if isinstance(response, OfficialFileResponse):
        metadata.update({"api_provider": None, "file_provider": source_agency, "source_format": "csv",
                         "etag": _safe_text(response.etag, secrets, limit=512) if response.etag is not None else None,
                         "last_modified": _safe_text(response.last_modified, secrets, limit=512)
                         if response.last_modified is not None else None})
    return institution_id, metadata, body, suffix


def save_api_response(
    settings: Settings,
    response: Download | JsonApiResponse | SdmxApiResponse | OfficialFileResponse,
    *,
    dataset_id: str | None = None,
    series_id: str | None = None,
    expected_institution_id: str | None = None,
    _artifact_id: str | None = None,
) -> SavedApiArtifact:
    """Save a completed response once; JSON payloads stay explicitly marked as sanitized."""
    institution_id, metadata, body, _suffix = _response_envelope(
        settings, response, dataset_id, series_id,
    )
    if expected_institution_id is not None and institution_id != expected_institution_id:
        raise ValueError("Response institution differs from the selected dataset")
    artifact_id = uuid4().hex if _artifact_id is None else _artifact_id
    if not isinstance(artifact_id, str) or not re.fullmatch(r"[0-9a-f]{32}", artifact_id):
        raise ValueError("API artifact ID must be a 32-character lowercase hex value")
    relative_dir = Path(settings.data_dir) / "raw" / "api" / institution_id / artifact_id
    if institution_id == "INT-04":
        # Keep the established World Bank workflow's path contract.
        relative_dir = Path(settings.data_dir) / "raw" / "worldbank" / artifact_id
    directory = settings._inside(relative_dir.as_posix())
    raw = directory / metadata["raw_filename"]
    manifest = directory / "request.json"
    metadata["raw_path"] = raw.relative_to(settings.project_root).as_posix()
    manifest_bytes = json.dumps(
        metadata, ensure_ascii=False, allow_nan=False, indent=2,
    ).encode("utf-8") + b"\n"
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("API artifact manifest exceeds the supported size")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    try:
        with raw.open("xb") as stream:
            stream.write(body)
        with manifest.open("xb") as stream:
            stream.write(manifest_bytes)
    except BaseException:
        # This directory was just created with a unique ID; remove only these files.
        for created in (manifest, raw):
            try:
                created.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            directory.rmdir()
        except OSError:
            pass
        raise
    return SavedApiArtifact(
        institution_id=institution_id,
        raw_path=metadata["raw_path"],
        manifest_path=manifest.relative_to(settings.project_root).as_posix(),
        raw_sha256=metadata["raw_sha256"],
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def read_api_response(
    settings: Settings,
    artifact: SavedApiArtifact | str,
) -> LoadedApiArtifact:
    """Read back an archived response and reject path, manifest, or payload tampering."""
    if isinstance(artifact, SavedApiArtifact):
        manifest_relative = artifact.manifest_path
        expected_raw_hash = artifact.raw_sha256
        expected_manifest_hash = artifact.manifest_sha256
        expected_institution_id = artifact.institution_id
    elif isinstance(artifact, str):
        manifest_relative = artifact
        expected_raw_hash = expected_manifest_hash = None
        expected_institution_id = None
    else:
        raise TypeError("artifact must be a saved API artifact or manifest path")

    lexical_manifest = settings.project_root / manifest_relative
    if lexical_manifest.is_symlink():
        raise ValueError("API artifact manifest must not be a symbolic link")
    manifest_path = settings._inside(manifest_relative)
    if (not manifest_path.is_relative_to(settings.raw_dir)
            or manifest_path.name != "request.json" or not manifest_path.is_file()):
        raise ValueError("API artifact manifest path is outside the raw archive")
    manifest_bytes = _read_bounded(manifest_path, MAX_MANIFEST_BYTES,
                                   "API artifact manifest exceeds the read limit")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if expected_manifest_hash is not None and manifest_hash != expected_manifest_hash:
        raise ValueError("API artifact manifest hash mismatch")
    try:
        metadata = json.loads(manifest_bytes)
    except (ValueError, UnicodeError):
        raise ValueError("API artifact manifest is not valid JSON") from None
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("API artifact manifest schema is unsupported")
    institution_id = metadata.get("institution_id")
    profile = _SOURCE_PROFILES.get(institution_id) if isinstance(institution_id, str) else None
    if (profile is None or metadata.get("source_agency") != profile[0]
            or expected_institution_id is not None and institution_id != expected_institution_id):
        raise ValueError("API artifact manifest source identity is invalid")
    expected_representation = (
        "sanitized_json_payload_canonical_utf8"
        if institution_id in _JSON_SOURCE_IDS.values()
        else "http_entity_bytes_after_requests_content_decoding"
    )
    if metadata.get("representation_code") != expected_representation:
        raise ValueError("API artifact representation does not match its source")
    safe_url = metadata.get("source_url")
    if not isinstance(safe_url, str) or _safe_source_url(safe_url, institution_id, ()) != safe_url:
        raise ValueError("API artifact manifest source URL is invalid")
    relative_raw = metadata.get("raw_path")
    if not isinstance(relative_raw, str):
        raise ValueError("API artifact manifest has no raw response path")  # noqa: TRY004
    if (Path(relative_raw).parent != Path(manifest_relative).parent
            or Path(relative_raw).name not in {"response.json", "response.bin", "response.csv"}):
        raise ValueError("API artifact raw response does not match its manifest")
    lexical_raw = settings.project_root / relative_raw
    if lexical_raw.is_symlink():
        raise ValueError("API artifact response must not be a symbolic link")
    raw_path = settings._inside(relative_raw)
    if not raw_path.is_relative_to(settings.raw_dir) or not raw_path.is_file():
        raise ValueError("API artifact response path is outside the raw archive")
    if raw_path.parent != manifest_path.parent:
        raise ValueError("API artifact response and manifest are in different folders")
    raw_filename = (
        "response.csv" if institution_id in _FILE_SOURCE_IDS else "response.json"
        if metadata.get("representation_code") == "sanitized_json_payload_canonical_utf8"
        or institution_id == "INT-04"
        else "response.bin"
    )
    if metadata.get("raw_filename") != raw_filename or raw_path.name != raw_filename:
        raise ValueError("API artifact response filename does not match its representation")
    if institution_id in _FILE_SOURCE_IDS and (
        metadata.get("access_method") != "official_file" or metadata.get("source_format") != "csv"
    ):
        raise ValueError("Official file manifest requires its explicit access method and format")
    if institution_id in _FILE_SOURCE_IDS:
        validate_official_file_identity(institution_id, metadata.get("dataset_id"), safe_url)
    if institution_id == "INT-04":
        expected_folder = settings._inside(f"{settings.data_dir}/raw/worldbank")
    else:
        expected_folder = settings._inside(f"{settings.data_dir}/raw/api/{institution_id}")
    if not manifest_path.parent.is_relative_to(expected_folder):
        raise ValueError("API artifact is stored under the wrong institution folder")
    body = _read_bounded(raw_path, MAX_ARCHIVE_RESPONSE_BYTES,
                         "API artifact response exceeds the read limit")
    raw_hash = hashlib.sha256(body).hexdigest()
    if (not isinstance(metadata.get("raw_sha256"), str)
            or not _SHA256.fullmatch(metadata["raw_sha256"])
            or raw_hash != metadata["raw_sha256"]
            or type(metadata.get("byte_count")) is not int
            or len(body) != metadata["byte_count"]):
        raise ValueError("API artifact response hash or length mismatch")
    if expected_raw_hash is not None and raw_hash != expected_raw_hash:
        raise ValueError("API artifact response hash differs from its saved reference")
    return LoadedApiArtifact(metadata, body)


def _read_bounded(path: Path, limit: int, error_message: str) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError(error_message)
    return value
