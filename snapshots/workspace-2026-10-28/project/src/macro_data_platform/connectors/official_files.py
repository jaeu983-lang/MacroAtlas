"""Reviewed TIC and Bank of England file downloads; no inferred API availability."""
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from macro_data_platform.config import Settings
from macro_data_platform.connectors.http_transport import (
    BoundedHttpTransport,
    HttpEndpointPolicy,
    HttpTransportError,
)
from macro_data_platform.connectors.official_api import ConnectorFailure
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus, utc

_TIC_ROOT = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/"
_TIC_FILES = {"mfhhis01": _TIC_ROOT + "mfhhis01.csv", "slt3d": _TIC_ROOT + "slt3d.csv"}
_BOE_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _boe_dates(query: Mapping[str, str]) -> None:
    dates = []
    for key in ("Datefrom", "Dateto"):
        value = query.get(key)
        match = re.fullmatch(r"([0-9]{2})/([A-Za-z]{3})/([0-9]{4})", value) if isinstance(value, str) else None
        if match is None or match[2] not in _MONTHS:
            raise ValueError("BoE file dates must use the reviewed native date syntax")
        try:
            dates.append(date(int(match[3]), _MONTHS.index(match[2]) + 1, int(match[1])))
        except ValueError:
            raise ValueError("BoE file date is invalid") from None
    if not 0 <= (dates[1] - dates[0]).days < 366:
        raise ValueError("BoE file date range exceeds the reviewed budget")


def validate_official_file_identity(institution_id: str, dataset_id: str, source_url: str) -> None:
    parts = urlsplit(source_url)
    if parts.scheme != "https" or parts.username or parts.password or parts.fragment or parts.port is not None:
        raise ValueError("Official file URL violates its HTTPS policy")
    endpoint = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = dict(pairs)
    if len(pairs) != len(query):
        raise ValueError("Official file query contains duplicate fields")
    if institution_id == "US-03" and dataset_id in _TIC_FILES and endpoint == _TIC_FILES[dataset_id] and not query:
        return
    if institution_id == "EU-04" and dataset_id == "IUDBEDR" and endpoint == _BOE_URL and (
        set(query) == {"csv.x", "Datefrom", "Dateto", "SeriesCodes", "CSVF", "UsingCodes", "VPD", "VFD"}
        and query["csv.x"] == "yes" and query["SeriesCodes"] == "IUDBEDR" and query["CSVF"] == "TN"
        and query["UsingCodes"] == "Y" and query["VPD"] == "Y" and query["VFD"] == "N"
    ):
        _boe_dates(query)
        return
    raise ValueError("Official file URL and dataset do not match a reviewed route")


@dataclass(frozen=True)
class OfficialFileResponse:
    institution_id: str
    source_agency: str
    dataset_id: str
    source_url: str
    body: bytes
    http_status: int
    retrieved_at: datetime
    content_type: str
    kind: EvidenceKind
    request_parameters: tuple[tuple[str, str], ...] = ()
    format: str = "csv"
    etag: str | None = None
    last_modified: str | None = None

    def __post_init__(self):
        validate_official_file_identity(self.institution_id, self.dataset_id, self.source_url)
        expected = {"US-03": "U.S. Treasury TIC", "EU-04": "Bank of England"}
        if (self.source_agency != expected.get(self.institution_id) or self.format != "csv"
                or not isinstance(self.kind, EvidenceKind)
                or self.kind not in {EvidenceKind.FIXTURE, EvidenceKind.LIVE_INGESTION}
                or not isinstance(self.body, bytes) or not 0 < len(self.body) <= 8 * 1024 * 1024
                or type(self.http_status) is not int or self.http_status != 200):
            raise ValueError("Official file response identity, evidence or body is invalid")
        utc(self.retrieved_at)
        if sorted(parse_qsl(urlsplit(self.source_url).query)) != sorted(self.request_parameters):
            raise ValueError("Official file request metadata differs from its URL")
        if any(value is not None and (not isinstance(value, str) or len(value) > 512)
               for value in (self.etag, self.last_modified)):
            raise ValueError("Official file revision headers exceed the supported format")


class OfficialFileTransport:
    """Only the registered, exact file paths; every request has a strict 8 MiB cap."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Any] | None = None,
                 *, evidence_kind: EvidenceKind = EvidenceKind.LIVE_INGESTION):
        if not isinstance(evidence_kind, EvidenceKind) or evidence_kind not in {EvidenceKind.FIXTURE, EvidenceKind.LIVE_INGESTION}:
            raise ValueError("Official file response requires explicit valid evidence")
        if evidence_kind == EvidenceKind.FIXTURE and session_factory is None:
            raise ValueError("Fixture file transport requires an injected session")
        self.http = BoundedHttpTransport(settings, session_factory)
        self.kind = evidence_kind

    def get(self, institution_id: str, dataset_id: str,
            parameters: Mapping[str, str] | None = None) -> OfficialFileResponse:
        query = dict(parameters or {})
        if institution_id == "US-03" and dataset_id in _TIC_FILES and not query:
            endpoint, agency = _TIC_FILES[dataset_id], "U.S. Treasury TIC"
        elif institution_id == "EU-04" and dataset_id == "IUDBEDR" and (
            set(query) == {"csv.x", "Datefrom", "Dateto", "SeriesCodes", "CSVF", "UsingCodes", "VPD", "VFD"}
            and query["csv.x"] == "yes" and query["SeriesCodes"] == "IUDBEDR"
            and query["CSVF"] == "TN" and query["UsingCodes"] == "Y"
            and query["VPD"] == "Y" and query["VFD"] == "N"
        ):
            endpoint, agency = _BOE_URL, "Bank of England"
        else:
            raise ValueError("Official file route or parameters are not registered")
        parts = urlsplit(endpoint)
        validate_official_file_identity(institution_id, dataset_id,
                                        endpoint + ("?" + urlencode(query) if query else ""))
        try:
            response = self.http.get(
                endpoint, policy=HttpEndpointPolicy(parts.hostname, parts.path, exact_path=parts.path),
                parameters=query, headers={"Accept": "text/csv,text/plain,application/octet-stream",
                                           "Accept-Encoding": "identity", "User-Agent": "MacroAtlas/0.1"},
                max_response_bytes=8 * 1024 * 1024, max_elapsed_seconds=30, body_statuses=frozenset({200}),
            )
        except HttpTransportError as error:
            security = error.reason in {"network_disabled", "unsafe_endpoint", "tls_failure"}
            transient = error.reason in {"request_failure", "elapsed_timeout"}
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE if transient else StageStatus.NEEDS_REVIEW,
                ErrorCode.LICENSE_SECURITY if security else ErrorCode.TRANSIENT if transient else ErrorCode.SCHEMA_CHANGED,
                "Official file transfer failed its bounded network policy; no complete file was accepted.",
            ) from None
        status = response.status_code
        if status != 200:
            code = (ErrorCode.AUTH_ACCESS if status in {401, 403} else ErrorCode.LICENSE_SECURITY
                    if 300 <= status < 400 else ErrorCode.TRANSIENT
                    if status in {408, 429} or status >= 500 else ErrorCode.SITE_CHANGED)
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE if code == ErrorCode.TRANSIENT else StageStatus.NEEDS_REVIEW,
                code, "Official file download returned a non-success HTTP status; access was not bypassed.",
            )
        if response.content_type.split(";", 1)[0].strip().lower() not in {
            "text/csv", "text/plain", "application/csv", "application/octet-stream", "application/vnd.ms-excel",
        }:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                   "Official CSV download returned an unexpected media type.")
        source_url = endpoint + ("?" + urlencode(query) if query else "")
        return OfficialFileResponse(
            institution_id, agency, dataset_id, source_url, response.body, status, response.retrieved_at,
            response.content_type, self.kind, tuple(query.items()), etag=response.etag,
            last_modified=response.last_modified,
        )


class TICFileClient:
    def __init__(self, settings: Settings, transport: OfficialFileTransport | None = None):
        self.transport = transport or OfficialFileTransport(settings)

    def get_file(self, file_id: str) -> OfficialFileResponse:
        if file_id not in _TIC_FILES:
            raise ValueError("TIC file identifier is not registered")
        return self.transport.get("US-03", file_id)


class BankOfEnglandFileClient:
    def __init__(self, settings: Settings, transport: OfficialFileTransport | None = None):
        self.transport = transport or OfficialFileTransport(settings)

    def get_bank_rate(self, start: str, end: str) -> OfficialFileResponse:
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if first.isoformat() != start or last.isoformat() != end or not 0 <= (last - first).days < 366:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("BoE CSV requires an ordered ISO date range of at most 366 inclusive days") from None
        def native(value: date) -> str:
            return f"{value.day:02}/{_MONTHS[value.month - 1]}/{value.year:04}"
        return self.transport.get("EU-04", "IUDBEDR", {
            "csv.x": "yes", "Datefrom": native(first), "Dateto": native(last), "SeriesCodes": "IUDBEDR",
            "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N",
        })
