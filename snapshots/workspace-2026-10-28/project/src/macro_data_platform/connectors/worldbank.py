"""One documented WDI GDP endpoint; no discovery, credentials or bulk queries."""
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

from macro_data_platform.config import Settings
from macro_data_platform.connectors.http_transport import (
    BoundedHttpTransport,
    HttpEndpointPolicy,
    HttpTransportError,
)
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus, utc

INDICATOR = "NY.GDP.MKTP.CD"
SOURCE = "2"
API_DOCS = "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"
TERMS_URL = "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets"
MAX_BYTES = 1024 * 1024


class ConnectorFailure(Exception):
    """Only fixed safe messages cross the engine/history boundary."""

    def __init__(self, status: StageStatus, code: ErrorCode, message: str,
                 retry_after_seconds: float | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after_seconds = retry_after_seconds


def schema_failure(message: str) -> ConnectorFailure:
    return ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED, message)


@dataclass(frozen=True)
class GDPQuery:
    start_year: int = 2020
    end_year: int = 2022

    def __post_init__(self) -> None:
        if (
            type(self.start_year) is not int or type(self.end_year) is not int
            or not 1960 <= self.start_year <= self.end_year <= 2100
            or self.end_year - self.start_year >= 10
        ):
            raise ValueError("request requires 1 to 10 years in 1960..2100")

    @property
    def url(self) -> str:
        params = {"source": SOURCE, "date": f"{self.start_year}:{self.end_year}",
                  "format": "json", "per_page": "100", "page": "1"}
        return f"https://api.worldbank.org/v2/country/USA/indicator/{INDICATOR}?{urlencode(params)}"


@dataclass(frozen=True)
class Download:
    source_url: str
    body: bytes
    status_code: int
    retrieved_at: datetime
    content_type: str
    kind: EvidenceKind
    retry_after_seconds: float | None = None
    retry_after_exceeds_limit: bool = False

    def __post_init__(self) -> None:
        utc(self.retrieved_at)
        if not isinstance(self.kind, EvidenceKind) or self.kind not in {
            EvidenceKind.FIXTURE, EvidenceKind.LIVE_API,
        }:
            raise ValueError("download must distinguish fixture from live API")
        if len(self.body) > MAX_BYTES:
            raise ValueError("download exceeds response limit")
        if (type(self.status_code) is not int or not 100 <= self.status_code <= 599
                or type(self.retry_after_exceeds_limit) is not bool
                or self.retry_after_seconds is not None and (
                    type(self.retry_after_seconds) not in {int, float}
                    or not math.isfinite(self.retry_after_seconds)
                    or not 0 <= self.retry_after_seconds <= 86_400)):
            raise ValueError("invalid HTTP status or retry-after value")


def _retry_after(value: str | None, now: datetime) -> tuple[float | None, bool]:
    if not value:
        return None, False
    try:
        seconds = float(value.strip())
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            seconds = (target - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None, False
    if not math.isfinite(seconds) or seconds < 0:
        return None, False
    if seconds > 86_400:
        return None, True
    return seconds, False


class WorldBankTransport:
    """Live GET only. Disabled by default through Settings; no implicit retries."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.http = BoundedHttpTransport(settings, session_factory)

    def fetch(self, query: GDPQuery) -> Download:
        if self.settings.network_enabled is not True:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                   "Network access is not enabled for this collection.")
        endpoint = query.url
        try:
            response = self.http.get(
                endpoint,
                policy=HttpEndpointPolicy(
                    hostname="api.worldbank.org",
                    path_prefix="/v2/country/USA/indicator/NY.GDP.MKTP.CD",
                    exact_path="/v2/country/USA/indicator/NY.GDP.MKTP.CD",
                    allow_query_in_url=True,
                ),
                parameters=None,
                headers={"Accept": "application/json", "User-Agent": "MacroAtlas/0.1"},
                max_response_bytes=MAX_BYTES,
                max_elapsed_seconds=30,
                body_statuses=None,
            )
        except HttpTransportError as exc:
            if exc.reason == "tls_failure":
                raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                       "TLS verification failed; access stopped.") from None
            if exc.reason == "elapsed_timeout":
                raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                       "Response exceeded the collection time budget.") from None
            if exc.reason == "response_too_large":
                raise schema_failure("Response exceeds the one MiB collection budget.") from None
            if exc.reason == "unsafe_endpoint":
                raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                       "The official endpoint failed its HTTPS safety check.") from None
            if exc.reason == "invalid_chunk":
                raise schema_failure("Response failed bounded transport validation.") from None
            if exc.reason == "request_failure":
                raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                       "World Bank transport failed; no complete response saved.") from None
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.INTERNAL_BUG,
                                   "World Bank transport stopped unexpectedly; details were suppressed.") from None

        retry_after, retry_after_exceeds = _retry_after(response.retry_after, response.retrieved_at)
        return Download(
            endpoint, response.body, response.status_code, response.retrieved_at,
            response.content_type, EvidenceKind.LIVE_API, retry_after, retry_after_exceeds,
        )


def check_http(download: Download) -> None:
    status = download.status_code
    if status == 200:
        return
    if status == 429 and download.retry_after_exceeds_limit:
        raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.TRANSIENT,
                               "Source Retry-After exceeds the supported wait policy; review required.")
    if status in {401, 403}:
        raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                               "World Bank access was denied; no authentication bypass attempted.")
    if status == 429 or 500 <= status < 600 or status == 408:
        raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                               "World Bank returned a temporary HTTP failure; resume after bounded backoff.",
                               download.retry_after_seconds)
    if 300 <= status < 400:
        raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                               "Redirect refused; the official endpoint requires review.")
    if status in {404, 410}:
        raise ConnectorFailure(StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                               "The documented endpoint was not found.")
    raise schema_failure("Unexpected HTTP status from the documented endpoint.")


def parse_gdp(download: Download, query: GDPQuery) -> dict[str, Any]:
    """Minimal parsing only. Preserve source rows, empty units and null values."""
    check_http(download)
    if download.source_url != query.url:
        raise schema_failure("Response request identity does not match the selected query.")
    media_type = download.content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"application/json", "text/json"}:
        raise schema_failure("Expected a documented JSON response.")
    try:
        def reject_constant(value):
            raise ValueError("Nonstandard JSON numeric constant")
        content = json.loads(download.body, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise schema_failure("Response is not valid JSON; original bytes retained.") from None
    if (
        not isinstance(content, list) or len(content) != 2
        or not isinstance(content[0], dict) or not isinstance(content[1], list)
        or "message" in content[0]
    ):
        raise schema_failure("Unexpected World Bank envelope or API error response.")
    meta, rows = content
    if (
        type(meta.get("page")) is not int or meta["page"] != 1
        or type(meta.get("pages")) is not int or meta["pages"] != 1
        or type(meta.get("total")) is not int or meta["total"] != len(rows)
        or not 1 <= len(rows) <= query.end_year - query.start_year + 1
    ):
        raise schema_failure("Empty, inconsistent or multi-page response; partial success refused.")
    if meta.get("sourceid") not in (None, SOURCE, int(SOURCE)):
        raise schema_failure("Response source identifier differs from WDI.")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("indicator"), dict):
            raise schema_failure("Observation structure changed.")
        if row["indicator"].get("id") != INDICATOR or row.get("countryiso3code") != "USA":
            raise schema_failure("Observation country or indicator differs from the request.")
        year = row.get("date")
        if (not isinstance(year, str) or len(year) != 4 or not year.isascii()
                or not year.isdecimal() or not query.start_year <= int(year) <= query.end_year):
            raise schema_failure("Observation year differs from the selected annual window.")
        if "value" not in row:
            raise schema_failure("Observation value field is missing.")
        value = row["value"]
        if value is not None and (
            type(value) not in {int, float} or (type(value) is float and not math.isfinite(value))
        ):
            raise schema_failure("Observation value must be a finite JSON number or null.")
    return {
        "source_agency": "World Bank", "dataset_id": SOURCE, "indicator_id": INDICATOR,
        "series_id": None, "series_key": {"source": SOURCE, "country": "USA",
                                            "indicator": INDICATOR},
        "source_url": query.url, "retrieved_at": download.retrieved_at.isoformat(),
        # A refresh date is not an immutable release/vintage identifier.
        "source_version": None, "source_last_updated": meta.get("lastupdated"),
        "frequency": None, "unit": None, "period_format": "YYYY", "page_metadata": meta,
        "observations": rows, "api_documentation_url": API_DOCS,
        "attribution": "World Bank, World Development Indicators; see original source metadata.",
        "license_note": "Dataset-specific terms apply; no blanket license inferred.",
        "terms_url": TERMS_URL,
    }
