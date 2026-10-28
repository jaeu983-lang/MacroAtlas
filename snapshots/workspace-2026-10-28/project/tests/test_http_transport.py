"""Deterministic tests for the shared bounded HTTP GET primitive."""
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.http_transport import (
    MAX_JSON_REQUEST_BYTES,
    BoundedHttpTransport,
    HttpEndpointPolicy,
    HttpTransportError,
)


class FakeResponse:
    def __init__(self, body=b"payload", status=200, headers=None):
        self.status_code = status
        self.headers = {"Content-Type": "application/octet-stream", **(headers or {})}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        assert chunk_size == 8192
        yield self.body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.trust_env = True
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, endpoint, **kwargs):
        self.request = (endpoint, kwargs)
        if self.error:
            raise self.error
        return self.response


def _policy() -> HttpEndpointPolicy:
    return HttpEndpointPolicy("api.example.gov", "/v1/")


def _transport(tmp_path: Path, session: FakeSession, *, enabled=True):
    return BoundedHttpTransport(
        Settings(tmp_path, network_enabled=enabled), session_factory=lambda: session,
    )


def _get(transport, endpoint="https://api.example.gov/v1/data", **overrides):
    options = {
        "policy": _policy(),
        "parameters": {"limit": "2"},
        "headers": {"Accept": "application/json"},
        "max_response_bytes": 1024,
        "max_elapsed_seconds": 30,
        "body_statuses": frozenset({200}),
    }
    options.update(overrides)
    return transport.get(endpoint, **options)


def test_shared_get_keeps_safe_session_bounds_and_raw_response(tmp_path):
    session = FakeSession(FakeResponse(b"{\"raw\":true}", headers={
        "Content-Type": "application/json", "Retry-After": "12",
    }))

    result = _get(_transport(tmp_path, session))

    assert result.body == b'{"raw":true}'
    assert result.status_code == 200
    assert result.content_type == "application/json"
    assert result.retry_after == "12"
    assert result.retrieved_at.tzinfo is not None
    assert session.trust_env is False
    endpoint, request = session.request
    assert endpoint == "https://api.example.gov/v1/data"
    assert request["params"] == {"limit": "2"}
    assert request["timeout"] == (5, 20)
    assert request["stream"] is True
    assert request["allow_redirects"] is False
    assert request.get("verify", True) is True
    assert "auth" not in request


@pytest.mark.parametrize("endpoint", [
    "http://api.example.gov/v1/data",
    "https://other.example.gov/v1/data",
    "https://api.example.gov:443/v1/data",
    "https://user@api.example.gov/v1/data",
    "https://api.example.gov/v1/../private",
    "https://api.example.gov/v1/%2e%2e/private",
    "https://api.example.gov/v1/data?token=value",
    "https://api.example.gov/v1/data#fragment",
])
def test_endpoint_policy_rejects_unreviewed_url_forms(tmp_path, endpoint):
    session = FakeSession(FakeResponse())
    transport = _transport(tmp_path, session)

    with pytest.raises(HttpTransportError) as error:
        _get(transport, endpoint)

    assert error.value.reason == "unsafe_endpoint"
    assert session.request is None


def test_network_must_be_explicitly_enabled(tmp_path):
    session = FakeSession(FakeResponse())

    with pytest.raises(HttpTransportError) as error:
        _get(_transport(tmp_path, session, enabled=False))

    assert error.value.reason == "network_disabled"
    assert session.request is None


@pytest.mark.parametrize("headers", [
    {"Content-Length": "1025"},
    {},
])
def test_response_size_is_bounded_by_header_and_stream(tmp_path, headers):
    body = b"payload" if headers else b"x" * 1025
    session = FakeSession(FakeResponse(body, headers=headers))

    with pytest.raises(HttpTransportError) as error:
        _get(_transport(tmp_path, session), max_response_bytes=1024)

    assert error.value.reason == "response_too_large"


def test_non_success_status_body_can_be_left_unread_by_family_policy(tmp_path):
    location = "https://api.example.gov/key-error?key=synthetic-secret"
    response = FakeResponse(b"must not be read", status=302, headers={"Location": location})
    response.iter_content = lambda **_kwargs: pytest.fail("redirect body must not be read")
    session = FakeSession(response)

    result = _get(_transport(tmp_path, session))

    assert result.status_code == 302
    assert result.body == b""
    assert result.redirect_location == location
    assert location not in repr(result) and "synthetic-secret" not in repr(result)
    assert session.request[1]["allow_redirects"] is False


def test_elapsed_budget_and_invalid_chunks_are_rejected(tmp_path, monkeypatch):
    session = FakeSession(FakeResponse())
    ticks = iter([0, 31, 0, 0])
    monkeypatch.setattr("macro_data_platform.connectors.http_transport.time.monotonic",
                        lambda: next(ticks))

    with pytest.raises(HttpTransportError) as timeout_error:
        _get(_transport(tmp_path, session))
    assert timeout_error.value.reason == "elapsed_timeout"

    invalid = FakeSession(FakeResponse())
    invalid.response.iter_content = lambda **_kwargs: iter(["not-bytes"])
    with pytest.raises(HttpTransportError) as chunk_error:
        _get(_transport(tmp_path, invalid))
    assert chunk_error.value.reason == "invalid_chunk"


@pytest.mark.parametrize(("failure", "reason"), [
    (requests.exceptions.SSLError("private detail"), "tls_failure"),
    (requests.Timeout("private detail"), "request_failure"),
    (requests.ConnectionError("private detail"), "request_failure"),
    (OSError("private detail"), "request_failure"),
    (RuntimeError("private detail"), "unexpected_failure"),
])
def test_transport_errors_are_fixed_and_suppress_library_details(tmp_path, failure, reason):
    session = FakeSession(error=failure)

    with pytest.raises(HttpTransportError) as error:
        _get(_transport(tmp_path, session))

    assert error.value.reason == reason
    assert "private detail" not in str(error.value)


def test_json_post_keeps_get_safety_and_response_bounds(tmp_path):
    session = FakeSession(FakeResponse(b"oversize"))
    session.post = session.get
    with pytest.raises(HttpTransportError) as error:
        _transport(tmp_path, session).post_json(
            "https://api.example.gov/v1/data", policy=_policy(), payload={"seriesid": ["A"]},
            headers={}, max_response_bytes=2, max_elapsed_seconds=30, body_statuses=frozenset({200}),
        )
    assert error.value.reason == "response_too_large"
    request = session.request[1]
    assert request["allow_redirects"] is False and session.trust_env is False
    assert request["headers"]["Content-Type"] == "application/json"
    assert isinstance(request["data"], bytes) and "params" not in request


@pytest.mark.parametrize("payload", [{"text": "x" * MAX_JSON_REQUEST_BYTES}, {"value": float("nan")}])
def test_json_post_rejects_oversized_or_nonstandard_bodies_before_sending(tmp_path, payload):
    session = FakeSession(FakeResponse())
    with pytest.raises(ValueError):
        _transport(tmp_path, session).post_json(
            "https://api.example.gov/v1/data", policy=_policy(), payload=payload,
            headers={}, max_response_bytes=1024, max_elapsed_seconds=30, body_statuses=frozenset({200}),
        )
    assert session.request is None
