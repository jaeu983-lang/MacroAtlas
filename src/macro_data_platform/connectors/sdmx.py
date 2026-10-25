"""Bounded raw-response clients for documented SDMX institutional APIs.

The clients preserve the provider's response bytes. Parsing and metadata
normalization remain separate so source payloads are not silently rewritten.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from macro_data_platform.config import Settings
from macro_data_platform.connectors.http_transport import (
    BoundedHttpTransport,
    HttpEndpointPolicy,
    HttpTransportError,
)
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    validate_parameters,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

MAX_SDMX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SDMX_REQUEST_SECONDS = 30
MAX_URL_LENGTH = 8192

_ROOTS = {
    "INT-02": ("https://stats.bis.org/api/v2", "BIS"),
    "INT-03": ("https://sdmx.oecd.org/public/rest/v1", "OECD"),
    "EU-01": ("https://data-api.ecb.europa.eu/service", "ECB"),
    "EU-02": (
        "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1",
        "Eurostat",
    ),
    "EU-03": ("https://api.statistiken.bundesbank.de/rest", "Deutsche Bundesbank"),
    "EU-05": ("https://bdm.insee.fr/series/sdmx", "INSEE"),
}
_ROOT_RULES = {
    institution_id: (urlsplit(root).hostname, urlsplit(root).path.rstrip("/") + "/")
    for institution_id, (root, _) in _ROOTS.items()
}
_SEGMENT = re.compile(r"[A-Za-z0-9_.:@,+*~-]{1,2048}\Z", re.ASCII)
_SENSITIVE_NAMES = frozenset({
    "userid", "appid", "apikey", "api_key", "applicationid", "application_id",
    "bea_api_key", "estat_app_id", "fred_api_key", "census_api_key", "bls_api_key",
})


@dataclass(frozen=True)
class SdmxApiResponse:
    """One bounded, unmodified HTTP response from an official SDMX API."""

    institution_id: str
    source_agency: str
    source_url: str
    operation: str
    http_status: int
    retrieved_at: datetime
    content_type: str
    body: bytes


def _segment(value: str, name: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str) or not _SEGMENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{name} must be a bounded SDMX path segment")
    return quote(value, safe=":@,+*~-_")


def _path(root: str, *segments: str) -> str:
    encoded = [_segment(item, "path value") for item in segments]
    url = root.rstrip("/") + "/" + "/".join(encoded)
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("SDMX request URL exceeds the supported length")
    return url


class SdmxApiTransport:
    """HTTPS GET transport with exact provider roots and a strict byte/time bound."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.session_factory = session_factory
        self.http = BoundedHttpTransport(settings, session_factory)

    def get(
        self,
        institution_id: str,
        endpoint: str,
        operation: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> SdmxApiResponse:
        if self.settings.network_enabled is not True:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "Network access is not enabled for this API request.",
            )
        profile = _ROOTS.get(institution_id)
        if profile is None or not isinstance(endpoint, str):
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "Only a reviewed official SDMX endpoint is allowed.",
            )
        source_agency = profile[1]
        hostname, prefix = _ROOT_RULES[institution_id]
        endpoint_policy = HttpEndpointPolicy(hostname or "", prefix)
        if not endpoint_policy.allows(endpoint):
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "The SDMX endpoint failed its HTTPS and provider allowlist checks.",
            )
        if not isinstance(operation, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", operation):
            raise ValueError("operation must be a bounded lowercase identifier")
        safe_parameters = validate_parameters(parameters, frozenset())
        if any(name.casefold() in _SENSITIVE_NAMES for name in safe_parameters):
            raise ValueError("credential parameters are not supported by this SDMX client")
        if sum(len(name) + len(value) + 2 for name, value in safe_parameters.items()) > 8192:
            raise ValueError("SDMX query parameters exceed the supported length")

        try:
            response = self.http.get(
                endpoint,
                policy=endpoint_policy,
                parameters=safe_parameters,
                headers={
                    "Accept": ("application/vnd.sdmx.structure+xml;version=2.1"
                               if operation in {"structure", "dataflow", "datastructure"}
                               else "*/*"),
                    "Accept-Encoding": "identity",
                    "User-Agent": "MacroAtlas/0.1",
                },
                max_response_bytes=MAX_SDMX_RESPONSE_BYTES,
                max_elapsed_seconds=MAX_SDMX_REQUEST_SECONDS,
                body_statuses=frozenset({200}),
            )
        except HttpTransportError as exc:
            if exc.reason == "tls_failure":
                raise ConnectorFailure(
                    StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                    f"{source_agency} SDMX API TLS verification failed; access stopped.",
                ) from None
            if exc.reason == "elapsed_timeout":
                raise ConnectorFailure(
                    StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                    f"{source_agency} SDMX API response exceeded the time limit.",
                ) from None
            if exc.reason == "response_too_large":
                raise self._size_failure(source_agency) from None
            if exc.reason == "invalid_chunk":
                raise self._schema_failure(source_agency) from None
            if exc.reason == "unsafe_endpoint":
                raise ConnectorFailure(
                    StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                    "The SDMX endpoint failed its HTTPS and provider allowlist checks.",
                ) from None
            if exc.reason == "request_failure":
                raise ConnectorFailure(
                    StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                    f"{source_agency} SDMX API transport failed; no complete response was accepted.",
                ) from None
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.INTERNAL_BUG,
                f"{source_agency} SDMX API transport stopped unexpectedly; details were suppressed.",
            ) from None

        status = response.status_code
        response_kind = ("html" if "html" in response.content_type.lower() else
                         "json" if "json" in response.content_type.lower() else "other")
        if status in {401, 403}:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                f"{source_agency} denied SDMX API access; review its access conditions.",
                http_status=status, response_kind=response_kind,
            )
        if status in {408, 429} or 500 <= status < 600:
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                f"{source_agency} returned a temporary SDMX API failure.",
                http_status=status, response_kind=response_kind,
            )
        if 300 <= status < 400:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                f"{source_agency} redirected the SDMX API request; redirect was refused.",
                http_status=status, response_kind=response_kind,
            )
        if status in {404, 410}:
            raise ConnectorFailure(
                StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                f"{source_agency} SDMX API endpoint was not found.",
                http_status=status, response_kind=response_kind,
            )
        if status != 200:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                f"{source_agency} returned an unexpected SDMX API status.",
                http_status=status, response_kind=response_kind,
            )

        query = urlencode(safe_parameters)
        source_url = endpoint + ("?" + query if query else "")
        return SdmxApiResponse(
            institution_id=institution_id,
            source_agency=source_agency,
            source_url=source_url,
            operation=operation,
            http_status=status,
            retrieved_at=response.retrieved_at,
            content_type=response.content_type,
            body=response.body,
        )

    @staticmethod
    def _size_failure(source_agency: str) -> ConnectorFailure:
        return ConnectorFailure(
            StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
            f"{source_agency} SDMX API response exceeded the eight MiB limit; partial data were refused.",
        )

    @staticmethod
    def _schema_failure(source_agency: str) -> ConnectorFailure:
        return ConnectorFailure(
            StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
            f"{source_agency} SDMX API response failed bounded transport validation.",
        )


class _SdmxClient:
    institution_id: str
    root: str

    def __init__(self, settings: Settings, transport: SdmxApiTransport | None = None):
        self.settings = settings
        self.transport = transport or SdmxApiTransport(settings)

    def _get(self, operation: str, *segments: str,
             parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self.transport.get(
            self.institution_id, _path(self.root, *segments), operation, parameters,
        )


class BISClient(_SdmxClient):
    """BIS SDMX REST API v2; data responses are documented as SDMX 2.1."""

    institution_id = "INT-02"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://stats.bis.org/api-doc/v2/"

    def get_structure(self, structure_type: str, agency_id: str, resource_id: str,
                      version: str = "latest") -> SdmxApiResponse:
        return self._get("structure", "structure", structure_type, agency_id,
                         resource_id, version)

    def get_data(self, context: str, agency_id: str, resource_id: str, version: str,
                 key: str, parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self._get("data", "data", context, agency_id, resource_id, version,
                         key, parameters=parameters)


class OECDClient(_SdmxClient):
    """OECD public SDMX REST API v1 (SDMX 2.1 query family)."""

    institution_id = "INT-03"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1"

    def get_structure(self, structure_type: str, agency_id: str, resource_id: str,
                      version: str = "latest") -> SdmxApiResponse:
        return self._get("structure", structure_type, agency_id, resource_id, version)

    def get_data(self, flow_ref: str, key: str, provider_ref: str = "all",
                 parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self._get("data", "data", flow_ref, key, provider_ref,
                         parameters=parameters)


class ECBClient(_SdmxClient):
    """ECB Data Portal SDMX 2.1 REST client."""

    institution_id = "EU-01"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://data.ecb.europa.eu/help/api/overview"

    def get_dataflow(self, agency_id: str, resource_id: str,
                     version: str = "latest") -> SdmxApiResponse:
        return self._get("dataflow", "dataflow", agency_id, resource_id, version)

    def get_datastructure(self, agency_id: str, resource_id: str,
                          version: str = "latest") -> SdmxApiResponse:
        return self._get("datastructure", "datastructure", agency_id, resource_id, version)

    def get_data(self, flow_ref: str, key: str,
                 parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self._get("data", "data", flow_ref, key, parameters=parameters)


class EurostatClient(_SdmxClient):
    """Eurostat SDMX 2.1 dissemination API; dataset IDs remain source-defined."""

    institution_id = "EU-02"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction"

    def get_dataflows(self, agency_id: str = "ESTAT") -> SdmxApiResponse:
        return self._get("dataflow", "dataflow", agency_id, "all")

    def get_dataflow(self, dataset_id: str, agency_id: str = "ESTAT",
                     version: str = "latest") -> SdmxApiResponse:
        return self._get("dataflow", "dataflow", agency_id, dataset_id, version)

    def get_datastructure(self, dataset_id: str, agency_id: str = "ESTAT",
                          version: str = "latest") -> SdmxApiResponse:
        return self._get("datastructure", "datastructure", agency_id, dataset_id, version)

    def get_data(self, dataset_id: str, key: str | None = None,
                 parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        if key is None and not parameters:
            raise ValueError("Eurostat full-dataset requests require an explicit filter")
        segments = ("data", dataset_id) if key is None else ("data", dataset_id, key)
        return self._get("data", *segments, parameters=parameters)


class BundesbankClient(_SdmxClient):
    """Deutsche Bundesbank SDMX web service; raw formats are preserved."""

    institution_id = "EU-03"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448"

    def get_dataflow(self, resource_id: str) -> SdmxApiResponse:
        return self._get("dataflow", "metadata", "dataflow", "BBK", resource_id)

    def get_datastructure(self, resource_id: str) -> SdmxApiResponse:
        return self._get("datastructure", "metadata", "datastructure", "BBK", resource_id)

    def get_data(self, flow_ref: str, key: str,
                 parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self._get("data", "data", flow_ref, key, parameters=parameters)


class INSEEClient(_SdmxClient):
    """INSEE BDM SDMX service for series IDs and thematic-group dataflows."""

    institution_id = "EU-05"
    root = _ROOTS[institution_id][0]
    API_DOCS = "https://www.insee.fr/en/information/2868055"

    def get_datastructure(self, resource_id: str, version: str = "1.0") -> SdmxApiResponse:
        """Direct BDM metadata route, user guide section IV (not API portal auth)."""
        return self._get("datastructure", "datastructure", "FR1", resource_id, version)

    def get_data_by_idbanks(self, idbanks: tuple[str, ...] | list[str],
                            parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        if not isinstance(idbanks, (tuple, list)) or not 1 <= len(idbanks) <= 100:
            raise ValueError("INSEE IDBANK request must contain 1 to 100 series IDs")
        if any(not isinstance(item, str) or not re.fullmatch(r"[0-9]{1,20}", item)
               for item in idbanks):
            raise ValueError("INSEE series IDs must be numeric IDBANK values")
        return self._get("data", "data", "SERIES_BDM", "+".join(idbanks),
                         parameters=parameters)

    def get_data_by_dataflow(self, dataflow_id: str, key: str,
                             parameters: Mapping[str, str | int] | None = None) -> SdmxApiResponse:
        return self._get("data", "data", dataflow_id, key, parameters=parameters)
