"""Small bounded HTTPS transport shared by official statistical APIs."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil
from typing import Any
from urllib.parse import urlsplit

from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus, utc

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 25


class SourceFailure(Exception):
    """Fixed safe failure; never includes URLs, payloads, or credential values."""

    def __init__(self, status: StageStatus, code: ErrorCode, message: str,
                 status_code: int | None = None,
                 retry_after_seconds: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def parse_retry_after(value: str | None) -> int | None:
    """Parse the standard delay-seconds or HTTP-date form without trusting arbitrary text."""
    if not value:
        return None
    value = value.strip()
    if value.isascii() and value.isdecimal():
        try:
            return int(value)
        except ValueError:  # protects against excessively long integer headers
            return None
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            return None
        return max(0, ceil((retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class ApiDownload:
    source_url: str
    body: bytes
    status_code: int
    retrieved_at: datetime
    content_type: str
    kind: EvidenceKind = EvidenceKind.LIVE_API

    def __post_init__(self):
        parsed = urlsplit(self.source_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("source_url must be credential-free HTTPS")
        utc(self.retrieved_at)
        if not isinstance(self.kind, EvidenceKind) or self.kind not in {
            EvidenceKind.FIXTURE, EvidenceKind.LIVE_API,
        }:
            raise ValueError("API download must identify fixture or live evidence")
        if not isinstance(self.body, bytes) or len(self.body) > MAX_BYTES:
            raise ValueError("API download exceeds response-size limit")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                            f"Required {env_name} credential is not configured.")
    return value


def read_optional_api_key(env_name: str) -> str | None:
    """Read an optional credential without making its absence an access failure."""
    value = os.environ.get(env_name, "").strip()
    return value or None


def request_json(url: str, *, method: str, body: bytes | None = None,
                 headers: dict[str, str] | None = None) -> ApiDownload:
    request = urllib.request.Request(
        url, data=body, headers={"Accept": "application/json", **(headers or {})},
        method=method,
    )
    opener = urllib.request.build_opener(_NoRedirect)
    started = time.monotonic()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdecimal() and int(length) > MAX_BYTES:
                raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                    "Response exceeded the two MiB safety limit.")
            chunks = []
            size = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                        "Response exceeded the two MiB safety limit.")
                chunks.append(chunk)
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                        "Response exceeded the time limit.")
            return ApiDownload(url.split("?", 1)[0], b"".join(chunks), response.status,
                               datetime.now(UTC), response.headers.get("Content-Type", ""),
                               EvidenceKind.LIVE_API)
    except SourceFailure:
        raise
    except urllib.error.HTTPError as error:
        status = error.code
        retry_after = parse_retry_after(error.headers.get("Retry-After")) if error.headers else None
        error.close()
    except urllib.error.URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                "TLS verification failed; access stopped.") from None
        raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                            "Official API transport failed; no complete response saved.") from None
    except (TimeoutError, OSError):
        raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                            "Official API transport failed; no complete response saved.") from None
    if status in {401, 403}:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                            "Official API denied access; credentials were not logged.", status)
    if status == 429 or 500 <= status < 600:
        raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                            "Official API returned a temporary HTTP failure.", status,
                            retry_after)
    if 300 <= status < 400:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                            "Official API redirect requires review.", status)
    raise SourceFailure(StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                        "Official API returned an unexpected HTTP status.", status)


def decode_json(download: ApiDownload) -> Any:
    if download.status_code != 200:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Expected HTTP 200 from official API.")
    media_type = download.content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"application/json", "text/json", "application/vnd.api+json"}:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Expected JSON from official API.")
    try:
        def reject_constant(value):
            raise ValueError("invalid JSON constant")
        return json.loads(download.body, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Official API response was not valid JSON.") from None
