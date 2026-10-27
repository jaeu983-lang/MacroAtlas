"""One documented WDI GDP endpoint; no discovery, credentials or bulk queries."""
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import requests

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus, utc

INDICATOR = "NY.GDP.MKTP.CD"
INDICATOR_LABEL = "GDP (current US$)"
SOURCE = "2"
API_DOCS = "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"
TERMS_URL = "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets"
MAX_BYTES = 1024 * 1024


class ConnectorFailure(Exception):
    """Only fixed safe messages cross the engine/history boundary."""

    def __init__(self, status: StageStatus, code: ErrorCode, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


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

    def __post_init__(self) -> None:
        utc(self.retrieved_at)
        if not isinstance(self.kind, EvidenceKind) or self.kind not in {
            EvidenceKind.FIXTURE, EvidenceKind.LIVE_API,
        }:
            raise ValueError("download must distinguish fixture from live API")
        if len(self.body) > MAX_BYTES:
            raise ValueError("download exceeds response limit")


class WorldBankTransport:
    """Live GET only. Disabled by default through Settings; no implicit retries."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self, query: GDPQuery) -> Download:
        if self.settings.network_enabled is not True:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                   "Network access is not enabled for this collection.")
        deadline = time.monotonic() + 30
        proxies = {}
        for scheme in ("http", "https"):
            value = (os.environ.get(f"{scheme.upper()}_PROXY")
                     or os.environ.get(f"{scheme}_proxy"))
            if value:
                proxies[scheme] = value
        verify = (os.environ.get("REQUESTS_CA_BUNDLE")
                  or os.environ.get("CURL_CA_BUNDLE") or True)
        try:
            with requests.Session() as session:
                # Keep .netrc/credential discovery disabled while explicitly honoring the
                # configured egress proxy and custom TLS trust bundle.
                session.trust_env = False
                with session.get(
                    query.url, timeout=(5, 20), stream=True, allow_redirects=False,
                    headers={"Accept": "application/json", "User-Agent": "MacroAtlas/0.1"},
                    proxies=proxies, verify=verify,
                ) as response:
                    length = response.headers.get("Content-Length")
                    if length is not None and length.isdecimal() and int(length) > MAX_BYTES:
                        raise schema_failure("Response exceeds the one MiB collection budget.")
                    chunks = []
                    size = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if time.monotonic() > deadline:
                            raise ConnectorFailure(StageStatus.FAILED_RETRYABLE,
                                                   ErrorCode.TRANSIENT,
                                                   "Response exceeded the collection time budget.")
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise schema_failure("Response exceeds the one MiB collection budget.")
                        chunks.append(chunk)
                    return Download(
                        query.url, b"".join(chunks), response.status_code, datetime.now(UTC),
                        response.headers.get("Content-Type", ""), EvidenceKind.LIVE_API,
                    )
        except requests.exceptions.SSLError:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                   "TLS verification failed; access stopped.") from None
        except requests.RequestException:
            raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                   "World Bank transport failed; no complete response saved.") from None


def check_http(download: Download) -> None:
    status = download.status_code
    if status == 200:
        return
    if status in {401, 403}:
        raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                               "World Bank access was denied; no authentication bypass attempted.")
    if status == 429 or 500 <= status < 600:
        raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                               "World Bank returned a temporary HTTP failure; retry manually later.")
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
        if (row["indicator"].get("id") != INDICATOR
                or row["indicator"].get("value") != INDICATOR_LABEL
                or row.get("countryiso3code") != "USA"):
            raise schema_failure("Observation country or indicator definition differs from the request.")
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
