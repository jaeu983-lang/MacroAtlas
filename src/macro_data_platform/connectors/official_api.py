"""Bounded GET/JSON transport shared by documented official API clients."""
from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit

import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.http_transport import (
    BoundedHttpTransport,
    HttpEndpointPolicy,
    HttpTransportError,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REQUEST_SECONDS = 30
_SAFE_ENDPOINTS = frozenset({
    "https://apps.bea.gov/api/data",
    "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
    "https://api.e-stat.go.jp/rest/3.0/app/json/getMetaInfo",
    "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData",
})
_FRED_ENDPOINTS = frozenset(
    "https://api.stlouisfed.org/fred/" + path
    for path in ("series", "series/search", "series/observations", "series/release", "release/sources")
)
_BLS_V1_ENDPOINT = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
_CENSUS_PATH = re.compile(
    r"/data/(?:[A-Za-z0-9_-]{1,64}/){0,7}[A-Za-z0-9_-]{1,64}"
    r"(?:/(?:variables|geography)\.json)?\Z", re.ASCII,
)
_SENSITIVE_FIELD_NAMES = frozenset({
    "userid", "appid", "apikey", "api_key", "applicationid", "application_id",
    "bea_api_key", "estat_app_id",
    "fred_api_key", "census_api_key", "bls_api_key", "registrationkey",
})
_SENSITIVE_REQUEST_NAMES = _SENSITIVE_FIELD_NAMES | {"key"}


class ConnectorFailure(Exception):
    """Safe, fixed-text failure; transport/library details never cross this boundary."""

    def __init__(
        self, status: StageStatus, code: ErrorCode, message: str, *,
        reason: ConnectorFailureReason | None = None, http_status: int | None = None,
    ):
        if reason is not None and not isinstance(reason, ConnectorFailureReason):
            raise TypeError("reason must be a ConnectorFailureReason")
        if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
            raise ValueError("http_status must be a valid HTTP status")
        super().__init__(message)
        self.status = status
        self.code = code
        self.reason = reason or ConnectorFailureReason.UNSPECIFIED
        self.http_status = http_status


class ConnectorFailureReason(str, Enum):
    """Safe, stable diagnostic labels; never contains response or request text."""

    UNSPECIFIED = "unspecified"
    NETWORK_DISABLED = "network_disabled"
    UNREVIEWED_ENDPOINT = "unreviewed_endpoint"
    ENDPOINT_SAFETY_CHECK = "endpoint_safety_check"
    AUTH_DENIED = "auth_denied"
    HTTP_TRANSIENT_STATUS = "http_transient_status"
    REDIRECT_REFUSED = "redirect_refused"
    ENDPOINT_NOT_FOUND = "endpoint_not_found"
    HTTP_UNEXPECTED_STATUS = "http_unexpected_status"
    TLS_VERIFICATION_FAILED = "tls_verification_failed"
    ELAPSED_TIMEOUT = "elapsed_timeout"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_RESPONSE_CHUNK = "invalid_response_chunk"
    UNSAFE_ENDPOINT = "unsafe_endpoint"
    TRANSPORT_FAILURE = "transport_failure"
    UNEXPECTED_TRANSPORT_FAILURE = "unexpected_transport_failure"
    UNEXPECTED_MEDIA_TYPE = "unexpected_media_type"
    INVALID_JSON = "invalid_json"


@dataclass(frozen=True)
class JsonApiResponse:
    source_agency: str
    source_url: str
    method: str
    http_status: int
    retrieved_at: datetime
    payload: Any
    request_parameters: tuple[tuple[str, str], ...] = ()
    content_type: str = "application/json"
    http_method: str = "GET"


def validate_parameters(
    parameters: Mapping[str, str | int] | None,
    reserved: frozenset[str],
) -> dict[str, str]:
    if parameters is None:
        return {}
    if not isinstance(parameters, Mapping) or len(parameters) > 40:
        raise ValueError("API parameters must be a mapping with at most 40 entries")
    result: dict[str, str] = {}
    normalized_names: set[str] = set()
    for name, value in parameters.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
                or name.casefold() in reserved or name.casefold() in normalized_names):
            raise ValueError("API parameters contain an invalid or reserved name")
        if type(value) not in {str, int}:
            raise ValueError("API parameter values must be text or integers")
        text = str(value)
        if len(text) > 4096 or any(ord(char) < 32 for char in text):
            raise ValueError("API parameter values exceed the supported format")
        result[name] = text
        normalized_names.add(name.casefold())
    return result


def _redact_payload(value: Any, secrets: tuple[str, ...], depth: int = 0) -> Any:
    if depth > 64:
        raise ValueError("JSON nesting limit exceeded")
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe_key = _redact_text(key, secrets) if isinstance(key, str) else key
            if isinstance(safe_key, str) and safe_key.casefold() in _SENSITIVE_FIELD_NAMES:
                result[safe_key] = "[REDACTED]"
            else:
                result[safe_key] = _redact_payload(item, secrets, depth + 1)
        return result
    if isinstance(value, list):
        return [_redact_payload(item, secrets, depth + 1) for item in value]
    if isinstance(value, str):
        return _redact_text(value, secrets)
    return value


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    result = value
    for secret in secrets:
        for variant in {secret, quote(secret, safe=""), quote_plus(secret, safe="")}:
            if variant:
                result = result.replace(variant, "[REDACTED]")
    return result


class JsonApiTransport:
    """Reviewed JSON API requests; BLS v1 alone also supports bounded JSON POST."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.session_factory = session_factory or requests.Session
        self.http = BoundedHttpTransport(settings, self.session_factory)

    def get_json(
        self,
        source_agency: str,
        endpoint: str,
        method: str,
        parameters: Mapping[str, str],
        credential: str,
    ) -> JsonApiResponse:
        return self._request_json(source_agency, endpoint, method, parameters, credential)

    def post_json(
        self, source_agency: str, endpoint: str, method: str, payload: Mapping[str, Any],
    ) -> JsonApiResponse:
        if set(payload) != {"seriesid", "startyear", "endyear"}:
            raise ValueError("Only the documented BLS v1 request fields are supported")
        parameters = {
            name: json.dumps(value, separators=(",", ":")) if isinstance(value, list) else str(value)
            for name, value in payload.items()
        }
        return self._request_json(
            source_agency, endpoint, method, parameters, "", json_body=payload,
        )

    def _request_json(
        self, source_agency: str, endpoint: str, method: str, parameters: Mapping[str, str],
        credential: str, *, json_body: Mapping[str, Any] | None = None,
    ) -> JsonApiResponse:
        if self.settings.network_enabled is not True:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW,
                ErrorCode.LICENSE_SECURITY,
                "Network access is not enabled for this API request.",
                reason=ConnectorFailureReason.NETWORK_DISABLED,
            )
        http_method = "GET" if json_body is None else "POST"
        if not self._reviewed_endpoint(source_agency, endpoint, http_method):
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "Only a reviewed official HTTPS endpoint is allowed.",
                reason=ConnectorFailureReason.UNREVIEWED_ENDPOINT,
            )
        parts = urlsplit(endpoint)
        if (parts.scheme != "https" or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment):
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "The API endpoint failed its HTTPS safety check.",
                reason=ConnectorFailureReason.ENDPOINT_SAFETY_CHECK,
            )
        if sum(len(name) + len(str(value)) + 2 for name, value in parameters.items()) > 8192:
            raise ValueError("JSON API request parameters exceed the supported length")

        secrets = (credential,)
        try:
            options = {
                "policy": HttpEndpointPolicy(
                    hostname=parts.hostname or "", path_prefix=parts.path, exact_path=parts.path),
                "headers": {"Accept": "application/json", "Accept-Encoding": "identity",
                            "User-Agent": "MacroAtlas/0.1"},
                "max_response_bytes": MAX_RESPONSE_BYTES,
                "max_elapsed_seconds": MAX_REQUEST_SECONDS,
                "body_statuses": frozenset({200}),
            }
            if json_body is None:
                response = self.http.get(endpoint, parameters=parameters, **options)
            else:
                response = self.http.post_json(endpoint, payload=json_body, **options)
        except HttpTransportError as exc:
            self._raise_transport_failure(source_agency, exc)

        status = response.status_code
        if status in {401, 403}:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                ("BLS denied public v1 API access; review its access conditions."
                 if source_agency == "BLS"
                 else f"{source_agency} denied API access; check the local credential."),
                reason=ConnectorFailureReason.AUTH_DENIED, http_status=status,
            )
        if status == 429 or status == 408 or 500 <= status < 600:
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                f"{source_agency} returned a temporary API failure.",
                reason=ConnectorFailureReason.HTTP_TRANSIENT_STATUS, http_status=status,
            )
        if 300 <= status < 400:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                f"{source_agency} redirected the API request; redirect was refused.",
                reason=ConnectorFailureReason.REDIRECT_REFUSED, http_status=status,
            )
        if status in {404, 410}:
            raise ConnectorFailure(
                StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                f"{source_agency} API endpoint was not found.",
                reason=ConnectorFailureReason.ENDPOINT_NOT_FOUND, http_status=status,
            )
        if status != 200:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                f"{source_agency} returned an unexpected HTTP status.",
                reason=ConnectorFailureReason.HTTP_UNEXPECTED_STATUS, http_status=status,
            )

        content_type = response.content_type
        retrieved_at = response.retrieved_at

        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in {"application/json", "text/json"}:
            raise self._schema_failure(
                source_agency, "expected a JSON response",
                reason=ConnectorFailureReason.UNEXPECTED_MEDIA_TYPE, http_status=status,
            )
        try:
            def reject_constant(value: str) -> None:
                raise ValueError("nonstandard JSON constant")

            parsed = json.loads(response.body, parse_constant=reject_constant)
            safe_payload = _redact_payload(parsed, secrets)
            self._validate_finite_json(safe_payload)
        except (ValueError, UnicodeError, RecursionError):
            raise self._schema_failure(
                source_agency, "response was not valid bounded JSON",
                reason=ConnectorFailureReason.INVALID_JSON, http_status=status,
            ) from None
        safe_parameters = tuple(
            (_redact_text(name, secrets), _redact_text(str(value), secrets))
            for name, value in parameters.items()
            if name.casefold() not in _SENSITIVE_REQUEST_NAMES
        )
        return JsonApiResponse(
            source_agency, _redact_text(endpoint, secrets), method, status, retrieved_at, safe_payload,
            safe_parameters, content_type, http_method,
        )

    @staticmethod
    def _reviewed_endpoint(source_agency: str, endpoint: str, http_method: str) -> bool:
        if http_method == "POST":
            return source_agency == "BLS" and endpoint == _BLS_V1_ENDPOINT
        if endpoint in _SAFE_ENDPOINTS:
            return True
        if source_agency == "FRED" and endpoint in _FRED_ENDPOINTS:
            return True
        if source_agency == "Census" and isinstance(endpoint, str):
            try:
                parts = urlsplit(endpoint)
            except ValueError:
                return False
            return (parts.scheme == "https" and parts.netloc == "api.census.gov"
                    and not parts.query and not parts.fragment
                    and (parts.path == "/data.json" or bool(_CENSUS_PATH.fullmatch(parts.path))))
        return False

    @staticmethod
    def _raise_transport_failure(source_agency: str, error: HttpTransportError) -> None:
        if error.reason == "tls_failure":
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                f"{source_agency} API TLS verification failed; access stopped.",
                reason=ConnectorFailureReason.TLS_VERIFICATION_FAILED,
            ) from None
        if error.reason == "elapsed_timeout":
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                f"{source_agency} API response exceeded the time limit.",
                reason=ConnectorFailureReason.ELAPSED_TIMEOUT,
            ) from None
        if error.reason == "response_too_large":
            raise JsonApiTransport._schema_failure(
                source_agency, "response exceeds the size limit",
                reason=ConnectorFailureReason.RESPONSE_TOO_LARGE,
            ) from None
        if error.reason == "invalid_chunk":
            raise JsonApiTransport._schema_failure(
                source_agency, "response was not valid bounded JSON",
                reason=ConnectorFailureReason.INVALID_RESPONSE_CHUNK,
            ) from None
        if error.reason == "unsafe_endpoint":
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "The API endpoint failed its HTTPS safety check.",
                reason=ConnectorFailureReason.UNSAFE_ENDPOINT,
            ) from None
        if error.reason == "request_failure":
            raise ConnectorFailure(
                StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                f"{source_agency} API transport failed; no complete response was accepted.",
                reason=ConnectorFailureReason.TRANSPORT_FAILURE,
            ) from None
        raise ConnectorFailure(
            StageStatus.NEEDS_REVIEW, ErrorCode.INTERNAL_BUG,
            f"{source_agency} API transport stopped after an unexpected error; details were suppressed.",
            reason=ConnectorFailureReason.UNEXPECTED_TRANSPORT_FAILURE,
        ) from None

    @staticmethod
    def _validate_finite_json(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        if isinstance(value, dict):
            for item in value.values():
                JsonApiTransport._validate_finite_json(item)
        elif isinstance(value, list):
            for item in value:
                JsonApiTransport._validate_finite_json(item)

    @staticmethod
    def _schema_failure(
        source_agency: str, detail: str, *,
        reason: ConnectorFailureReason = ConnectorFailureReason.UNSPECIFIED,
        http_status: int | None = None,
    ) -> ConnectorFailure:
        labels = {
            "response exceeds the size limit": "response exceeded the one MiB limit",
            "expected a JSON response": "expected a documented JSON response",
            "response was not valid bounded JSON": "response was not valid bounded JSON",
        }
        return ConnectorFailure(
            StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
            f"{source_agency} API {labels.get(detail, 'response failed validation')}.",
            reason=reason, http_status=http_status,
        )
