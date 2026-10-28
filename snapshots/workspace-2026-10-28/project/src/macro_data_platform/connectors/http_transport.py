"""Shared bounded HTTP GET and JSON POST for reviewed source-specific API transports."""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import requests

from macro_data_platform.config import Settings

CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
STREAM_CHUNK_BYTES = 8192
MAX_JSON_REQUEST_BYTES = 16 * 1024

HttpFailureReason = Literal[
    "network_disabled",
    "unsafe_endpoint",
    "tls_failure",
    "elapsed_timeout",
    "request_failure",
    "response_too_large",
    "invalid_chunk",
    "unexpected_failure",
]


class HttpTransportError(Exception):
    """Fixed-kind transport error that never carries request or library details."""

    def __init__(self, reason: HttpFailureReason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class HttpEndpointPolicy:
    """Host/path allowlist supplied by the API-family or source wrapper."""

    hostname: str
    path_prefix: str
    exact_path: str | None = None
    allow_query_in_url: bool = False

    def allows(self, endpoint: str) -> bool:
        if not isinstance(endpoint, str) or not self.hostname or not self.path_prefix:
            return False
        try:
            parts = urlsplit(endpoint)
            port = parts.port
        except ValueError:
            return False
        path_matches = (
            parts.path == self.exact_path
            if self.exact_path is not None
            else parts.path.startswith(self.path_prefix)
        )
        return bool(
            parts.scheme == "https"
            and parts.hostname is not None
            and parts.hostname.casefold() == self.hostname.casefold()
            and port is None
            and parts.username is None
            and parts.password is None
            and not parts.fragment
            and "#" not in endpoint
            and (self.allow_query_in_url or not parts.query)
            and path_matches
            and "%" not in parts.path
            and not parts.path.startswith("//")
            and all(segment not in {".", ".."} for segment in parts.path.split("/"))
        )


@dataclass(frozen=True)
class HttpResponse:
    """Bounded response entity and the minimal headers used by API wrappers."""

    status_code: int
    body: bytes
    retrieved_at: datetime
    content_type: str
    retry_after: str | None
    etag: str | None = None
    last_modified: str | None = None
    # Transient header only: may contain credentials, so exclude it from repr/logs.
    redirect_location: str | None = field(default=None, repr=False)


class BoundedHttpTransport:
    """Bounded network primitive; source-specific status and payload rules stay outside."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.session_factory = session_factory or requests.Session

    def get(
        self,
        endpoint: str,
        *,
        policy: HttpEndpointPolicy,
        parameters: Mapping[str, str | int] | None,
        headers: Mapping[str, str],
        max_response_bytes: int,
        max_elapsed_seconds: float,
        body_statuses: frozenset[int] | None,
    ) -> HttpResponse:
        return self._request(
            "GET", endpoint, policy=policy, parameters=parameters, headers=headers,
            max_response_bytes=max_response_bytes, max_elapsed_seconds=max_elapsed_seconds,
            body_statuses=body_statuses,
        )

    def post_json(
        self,
        endpoint: str,
        *,
        policy: HttpEndpointPolicy,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        max_response_bytes: int,
        max_elapsed_seconds: float,
        body_statuses: frozenset[int] | None,
    ) -> HttpResponse:
        try:
            if not isinstance(payload, Mapping):
                raise TypeError
            body = json.dumps(dict(payload), allow_nan=False, separators=(",", ":")).encode("utf-8")
            if len(body) > MAX_JSON_REQUEST_BYTES:
                raise ValueError
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ValueError("JSON request body exceeds the supported format or size") from None
        return self._request(
            "POST", endpoint, policy=policy, parameters=None,
            headers={**headers, "Content-Type": "application/json"}, request_body=body,
            max_response_bytes=max_response_bytes, max_elapsed_seconds=max_elapsed_seconds,
            body_statuses=body_statuses,
        )

    def _request(
        self,
        http_method: Literal["GET", "POST"],
        endpoint: str,
        *,
        policy: HttpEndpointPolicy,
        parameters: Mapping[str, str | int] | None,
        headers: Mapping[str, str],
        max_response_bytes: int,
        max_elapsed_seconds: float,
        body_statuses: frozenset[int] | None,
        request_body: bytes | None = None,
    ) -> HttpResponse:
        if self.settings.network_enabled is not True:
            raise HttpTransportError("network_disabled")
        if not policy.allows(endpoint):
            raise HttpTransportError("unsafe_endpoint")
        if (
            type(max_response_bytes) is not int or max_response_bytes < 1
            or type(max_elapsed_seconds) not in {int, float} or max_elapsed_seconds <= 0
            or not isinstance(headers, Mapping)
            or parameters is not None and not isinstance(parameters, Mapping)
        ):
            raise ValueError("bounded HTTP request policy is invalid")

        deadline = time.monotonic() + max_elapsed_seconds
        try:
            with self.session_factory() as session:
                # Do not inherit .netrc, implicit proxy, or environment credential settings.
                session.trust_env = False
                request_options: dict[str, Any] = {
                    "timeout": (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    "stream": True,
                    "allow_redirects": False,
                    "headers": dict(headers),
                }
                if parameters is not None:
                    request_options["params"] = dict(parameters)
                if request_body is not None:
                    request_options["data"] = request_body
                send = session.get if http_method == "GET" else session.post
                with send(endpoint, **request_options) as response:
                    status = response.status_code
                    chunks: list[bytes] = []
                    if body_statuses is None or status in body_statuses:
                        length = response.headers.get("Content-Length")
                        if (isinstance(length, str) and length.isdecimal()
                                and int(length) > max_response_bytes):
                            raise HttpTransportError("response_too_large")
                        size = 0
                        for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
                            if time.monotonic() > deadline:
                                raise HttpTransportError("elapsed_timeout")
                            if not isinstance(chunk, bytes):
                                raise HttpTransportError("invalid_chunk")
                            size += len(chunk)
                            if size > max_response_bytes:
                                raise HttpTransportError("response_too_large")
                            chunks.append(chunk)
                    return HttpResponse(
                        status_code=status,
                        body=b"".join(chunks),
                        retrieved_at=datetime.now(UTC),
                        content_type=response.headers.get("Content-Type", ""),
                        retry_after=response.headers.get("Retry-After"),
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                        redirect_location=response.headers.get("Location") if 300 <= status < 400 else None,
                    )
        except HttpTransportError:
            raise
        except requests.exceptions.SSLError:
            raise HttpTransportError("tls_failure") from None
        except (requests.Timeout, TimeoutError):
            raise HttpTransportError("request_failure") from None
        except (requests.RequestException, OSError):
            raise HttpTransportError("request_failure") from None
        except Exception:  # noqa: BLE001 - requests errors may contain query credentials
            raise HttpTransportError("unexpected_failure") from None
