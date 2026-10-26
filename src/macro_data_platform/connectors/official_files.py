"""Bounded retrieval for the two official files used by the Gate C source watch."""
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from macro_data_platform.connectors.statistical_http import SourceFailure, parse_retry_after
from macro_data_platform.contracts import ErrorCode, StageStatus, utc

MAX_FILE_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 20
PROFILES = {
    "tic": {
        "url": "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt",
        "format": "txt", "delimiter": "\t", "header_row": 6,
        "source_agency": "U.S. Department of the Treasury, TIC",
        "source_table_name": "Table 5: Major Foreign Holders of Treasury Securities",
    },
    "bis": {
        "url": "https://data.bis.org/static/bulk/WS_GLI_csv_col.zip",
        "format": "zip", "source_agency": "BIS",
    },
}


@dataclass(frozen=True)
class OfficialFileDownload:
    source_id: str
    source_url: str
    body: bytes
    status_code: int
    retrieved_at: datetime
    content_type: str
    last_modified: str | None

    def __post_init__(self):
        profile = PROFILES.get(self.source_id)
        if profile is None or self.source_url != profile["url"] or self.status_code != 200:
            raise ValueError("official file identity or status is invalid")
        if not isinstance(self.body, bytes) or not 1 <= len(self.body) <= MAX_FILE_BYTES:
            raise ValueError("official file body exceeds the bounded response size")
        utc(self.retrieved_at)
        for value in (self.content_type, self.last_modified):
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                raise ValueError("official file provenance value is invalid")


def _configured_proxy() -> dict[str, str]:
    proxies = {}
    for scheme in ("http", "https"):
        value = (os.environ.get(f"{scheme.upper()}_PROXY")
                 or os.environ.get(f"{scheme}_proxy"))
        if value:
            proxies[scheme] = value
    return proxies


class OfficialFileTransport:
    """GET one allowlisted public file; no redirect, credential, or retry behavior."""

    def fetch(self, source_id: str) -> OfficialFileDownload:
        profile = PROFILES.get(source_id)
        if profile is None:
            raise ValueError("unsupported Gate C source identifier")
        url = profile["url"]
        verify = (os.environ.get("REQUESTS_CA_BUNDLE")
                  or os.environ.get("CURL_CA_BUNDLE") or True)
        deadline = time.monotonic() + TIMEOUT_SECONDS + 10
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.get(url, timeout=(5, TIMEOUT_SECONDS), stream=True,
                                 allow_redirects=False, proxies=_configured_proxy(),
                                 verify=verify,
                                 headers={"Accept": "application/octet-stream,text/plain,*/*",
                                          "User-Agent": "MacroAtlas/0.1"}) as response:
                    status = response.status_code
                    if status in {401, 403}:
                        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                            "Official source denied the file request.", status)
                    if status == 429 or 500 <= status < 600:
                        delay = parse_retry_after(response.headers.get("Retry-After"))
                        raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                            "Official source returned a temporary HTTP failure.",
                                            status, delay)
                    if 300 <= status < 400:
                        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                            "Official source redirect requires review.", status)
                    if status != 200:
                        raise SourceFailure(StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                                            "Official source returned an unexpected HTTP status.", status)
                    length = response.headers.get("Content-Length")
                    if length and length.isdecimal() and int(length) > MAX_FILE_BYTES:
                        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                            "Official file exceeded the sixteen MiB limit.")
                    chunks = []
                    size = 0
                    for chunk in response.iter_content(chunk_size=65536):
                        if time.monotonic() > deadline:
                            raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                                "Official file exceeded the time limit.")
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                                "Official file exceeded the sixteen MiB limit.")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if not body:
                        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                            "Official source returned an empty file.")
                    return OfficialFileDownload(
                        source_id, url, body, status, datetime.now(UTC),
                        response.headers.get("Content-Type", ""),
                        response.headers.get("Last-Modified"),
                    )
        except SourceFailure:
            raise
        except requests.exceptions.SSLError:
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                "TLS verification failed; access stopped.") from None
        except requests.RequestException:
            raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                "Official source transport failed; no complete file was saved.") from None
