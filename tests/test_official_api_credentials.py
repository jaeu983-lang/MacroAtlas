"""Mocked credential loading and official BEA/e-Stat API request safety."""
import json
import os
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import MAX_ENV_FILE_BYTES, Settings
from macro_data_platform.connectors.bea import API_URL as BEA_URL
from macro_data_platform.connectors.bea import BEAClient
from macro_data_platform.connectors.estat import API_ROOT as ESTAT_ROOT
from macro_data_platform.connectors.estat import EStatClient
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    ConnectorFailureReason,
    JsonApiTransport,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

_TEST_CREDENTIAL = "macroatlas-test-only-credential-sentinel"


class FakeResponse:
    def __init__(self, body: bytes | dict, status: int = 200,
                 content_type: str = "application/json", headers: dict | None = None):
        self.status_code = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self._body = json.dumps(body).encode() if isinstance(body, dict) else body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size: int):
        assert chunk_size == 8192
        yield self._body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.trust_env = True
        self.call = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **kwargs):
        self.call = (url, kwargs)
        if self.error:
            raise self.error
        return self.response


def _settings(tmp_path: Path, **env) -> Settings:
    return Settings.from_env(tmp_path, env)


def _transport(settings: Settings, response=None, error=None):
    session = FakeSession(response=response, error=error)
    return JsonApiTransport(settings, session_factory=lambda: session), session


def test_project_env_file_load_and_process_environment_precedence(tmp_path):
    (tmp_path / ".env").write_text(
        "# local only\nBEA_API_KEY=file-value\nESTAT_APP_ID=   \n"
        "MACROATLAS_NETWORK_ENABLED=true\n",
        encoding="utf-8",
    )
    settings = Settings.from_project_env(
        tmp_path,
        {"BEA_API_KEY": "process-value", "ESTAT_APP_ID": "process-estat"},
    )

    assert settings.bea_api_key == "process-value"
    assert settings.estat_app_id == "process-estat"
    assert settings.network_enabled is True
    assert "process-value" not in repr(settings)
    assert "process-estat" not in repr(settings)


def test_env_loader_missing_file_and_blank_credentials_are_offline_defaults(tmp_path):
    settings = Settings.from_project_env(tmp_path, {})

    assert settings.bea_api_key is None
    assert settings.estat_app_id is None
    assert settings.network_enabled is False

    (tmp_path / ".env").write_text("BEA_API_KEY= \nESTAT_APP_ID=\"\"\n", encoding="utf-8")
    settings = Settings.from_project_env(tmp_path, {})
    assert settings.bea_api_key is None
    assert settings.estat_app_id is None


@pytest.mark.parametrize(("name", "attribute"), [
    ("FRED_API_KEY", "fred_api_key"),
    ("CENSUS_API_KEY", "census_api_key"),
    ("BLS_API_KEY", "bls_api_key"),
])
def test_future_source_credentials_can_be_saved_safely_before_client_implementation(
    tmp_path, name, attribute,
):
    path = tmp_path / ".env"
    path.write_text(f"{name}=\n", encoding="utf-8")
    assert getattr(Settings.from_project_env(tmp_path, {}), attribute) is None

    path.write_text(f"{name}=file-only-test-sentinel\n", encoding="utf-8")
    loaded = Settings.from_project_env(tmp_path, {})
    assert getattr(loaded, attribute) == "file-only-test-sentinel"
    assert "file-only-test-sentinel" not in repr(loaded)
    assert loaded.network_enabled is False

    overridden = Settings.from_project_env(tmp_path, {name: "process-only-test-sentinel"})
    assert getattr(overridden, attribute) == "process-only-test-sentinel"
    assert "process-only-test-sentinel" not in repr(overridden)

    with pytest.raises(ValueError) as error:
        Settings.from_env(tmp_path, {name: "private-test-sentinel\ninvalid"})
    assert "private-test-sentinel" not in str(error.value)


@pytest.mark.parametrize("contents", [
    f"BEA_API_KEY={_TEST_CREDENTIAL}\nBEA_API_KEY=second\n",
    f"UNSUPPORTED_KEY={_TEST_CREDENTIAL}\n",
    f"BEA_API_KEY=\"{_TEST_CREDENTIAL}\n",
    f"malformed {_TEST_CREDENTIAL}\n",
])
def test_env_loader_rejects_bad_file_without_echoing_values(tmp_path, contents):
    (tmp_path / ".env").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError) as error:
        Settings.from_project_env(tmp_path, {})

    assert _TEST_CREDENTIAL not in str(error.value)


def test_env_loader_enforces_size_and_rejects_symlink(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"#" + b"x" * MAX_ENV_FILE_BYTES)
    with pytest.raises(ValueError, match="size limit"):
        Settings.from_project_env(tmp_path, {})

    path.unlink()
    target = tmp_path / "target"
    target.write_text("BEA_API_KEY=local\n", encoding="utf-8")
    try:
        os.symlink(target, path)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this Windows environment")
    with pytest.raises(ValueError, match="symbolic link"):
        Settings.from_project_env(tmp_path, {})


def test_bea_client_uses_documented_fixed_json_endpoint_and_redacts_key():
    settings = _settings(Path.cwd(), BEA_API_KEY=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, session = _transport(settings, FakeResponse({
        "BEAAPI": {"Request": {"UserID": _TEST_CREDENTIAL},
                   "Results": {"note": f"echo {_TEST_CREDENTIAL}"}},
    }))

    result = BEAClient(settings, transport).get_dataset_list()

    url, request = session.call
    assert url == BEA_URL == "https://apps.bea.gov/api/data"
    assert request["params"] == {
        "UserID": _TEST_CREDENTIAL, "method": "GetDataSetList", "ResultFormat": "JSON",
    }
    assert request["allow_redirects"] is False
    assert request["timeout"] == (5, 20)
    assert session.trust_env is False
    assert result.source_url == BEA_URL
    assert result.payload["BEAAPI"]["Request"]["UserID"] == "[REDACTED]"
    assert result.payload["BEAAPI"]["Results"]["note"] == "echo [REDACTED]"
    assert _TEST_CREDENTIAL not in repr(result)


def test_bea_methods_and_reserved_parameters_are_bounded():
    settings = _settings(Path.cwd(), BEA_API_KEY=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, session = _transport(settings, FakeResponse({"ok": True}))

    BEAClient(settings, transport).get_data("NIPA", {"TableName": "T10101", "Year": 2025})
    assert session.call[1]["params"]["method"] == "GetData"
    assert session.call[1]["params"]["DatasetName"] == "NIPA"
    assert session.call[1]["params"]["Year"] == "2025"

    with pytest.raises(ValueError, match="Unsupported BEA"):
        BEAClient(settings, transport).request("FetchAll")
    with pytest.raises(ValueError, match="reserved"):
        BEAClient(settings, transport).request("GetData", {"userid": "override"})


def test_estat_client_uses_v30_json_routes_and_redacts_application_id():
    settings = _settings(Path.cwd(), ESTAT_APP_ID=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, session = _transport(settings, FakeResponse({
        "GET_STATS_DATA": {"PARAMETER": {"appId": _TEST_CREDENTIAL},
                           "VALUE": f"echo {_TEST_CREDENTIAL}"},
    }))

    result = EStatClient(settings, transport).get_stats_data("TBL001", {"lang": "E"})

    url, request = session.call
    assert url == f"{ESTAT_ROOT}/getStatsData"
    assert request["params"] == {
        "appId": _TEST_CREDENTIAL, "statsDataId": "TBL001", "lang": "E",
    }
    assert request["allow_redirects"] is False
    assert result.method == "getStatsData"
    assert result.payload["GET_STATS_DATA"]["PARAMETER"]["appId"] == "[REDACTED]"
    assert result.payload["GET_STATS_DATA"]["VALUE"] == "echo [REDACTED]"
    assert _TEST_CREDENTIAL not in repr(result)


@pytest.mark.parametrize("client, credential_name", [
    (BEAClient, "BEA_API_KEY"), (EStatClient, "ESTAT_APP_ID"),
])
def test_clients_fail_closed_when_credentials_are_missing(client, credential_name, tmp_path):
    transport, session = _transport(_settings(tmp_path))
    with pytest.raises(ConnectorFailure) as error:
        client(_settings(tmp_path), transport).request("unavailable", {})
    assert error.value.status == StageStatus.NEEDS_REVIEW
    assert error.value.code == ErrorCode.AUTH_ACCESS
    assert credential_name in str(error.value)
    assert session.call is None


def test_network_disabled_stops_before_session_creation(tmp_path):
    settings = _settings(tmp_path, BEA_API_KEY=_TEST_CREDENTIAL)
    transport = JsonApiTransport(settings, session_factory=lambda: pytest.fail("transport ran"))

    with pytest.raises(ConnectorFailure) as error:
        BEAClient(settings, transport).get_dataset_list()

    assert error.value.code == ErrorCode.LICENSE_SECURITY


@pytest.mark.parametrize(("status", "expected_status", "expected_code", "expected_reason"), [
    (403, StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS, ConnectorFailureReason.AUTH_DENIED),
    (429, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
     ConnectorFailureReason.HTTP_TRANSIENT_STATUS),
    (503, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
     ConnectorFailureReason.HTTP_TRANSIENT_STATUS),
    (302, StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY, ConnectorFailureReason.REDIRECT_REFUSED),
    (404, StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED, ConnectorFailureReason.ENDPOINT_NOT_FOUND),
])
def test_http_failures_are_classified_without_echoing_request_values(
    tmp_path, status, expected_status, expected_code, expected_reason,
):
    settings = _settings(tmp_path, BEA_API_KEY=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, FakeResponse(b"ignored", status=status))

    with pytest.raises(ConnectorFailure) as error:
        BEAClient(settings, transport).get_dataset_list()

    assert error.value.status == expected_status
    assert error.value.code == expected_code
    assert error.value.reason == expected_reason
    assert error.value.http_status == status
    assert _TEST_CREDENTIAL not in str(error.value)


@pytest.mark.parametrize(("body", "content_type"), [
    (b"not-json", "application/json"),
    (b"{}", "text/html"),
    (b'{"n":NaN}', "application/json"),
])
def test_invalid_json_or_media_type_fails_closed(tmp_path, body, content_type):
    settings = _settings(tmp_path, ESTAT_APP_ID=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, FakeResponse(body, content_type=content_type))

    with pytest.raises(ConnectorFailure) as error:
        EStatClient(settings, transport).get_stats_list()

    assert error.value.code == ErrorCode.SCHEMA_CHANGED
    assert error.value.reason in {
        ConnectorFailureReason.UNEXPECTED_MEDIA_TYPE, ConnectorFailureReason.INVALID_JSON,
    }
    assert error.value.http_status == 200
    assert _TEST_CREDENTIAL not in str(error.value)


def test_transport_errors_hide_request_library_details(tmp_path):
    settings = _settings(tmp_path, ESTAT_APP_ID=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, error=requests.RequestException(_TEST_CREDENTIAL))

    with pytest.raises(ConnectorFailure) as error:
        EStatClient(settings, transport).get_stats_list()

    assert error.value.code == ErrorCode.TRANSIENT
    assert error.value.reason == ConnectorFailureReason.TRANSPORT_FAILURE
    assert _TEST_CREDENTIAL not in str(error.value)


def test_unexpected_transport_errors_are_suppressed(tmp_path):
    settings = _settings(tmp_path, BEA_API_KEY=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, error=RuntimeError(_TEST_CREDENTIAL))

    with pytest.raises(ConnectorFailure) as error:
        BEAClient(settings, transport).get_dataset_list()

    assert error.value.code == ErrorCode.INTERNAL_BUG
    assert error.value.reason == ConnectorFailureReason.UNEXPECTED_TRANSPORT_FAILURE
    assert _TEST_CREDENTIAL not in str(error.value)


def test_tls_failure_has_safe_reason_without_transport_details(tmp_path):
    settings = _settings(tmp_path, CENSUS_API_KEY=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, error=requests.exceptions.SSLError(_TEST_CREDENTIAL))

    with pytest.raises(ConnectorFailure) as error:
        from macro_data_platform.connectors.census import CensusClient
        CensusClient(settings, transport).get_data("2023/acs/acs5", ["NAME"], {"for": "state:06"})

    assert error.value.code == ErrorCode.LICENSE_SECURITY
    assert error.value.reason == ConnectorFailureReason.TLS_VERIFICATION_FAILED
    assert error.value.http_status is None
    assert _TEST_CREDENTIAL not in str(error.value)


def test_response_size_limit_is_enforced(tmp_path):
    settings = _settings(tmp_path, ESTAT_APP_ID=_TEST_CREDENTIAL,
                         MACROATLAS_NETWORK_ENABLED="true")
    transport, _ = _transport(settings, FakeResponse(
        b"{}", headers={"Content-Length": str(MAX_ENV_FILE_BYTES * 100)},
    ))

    with pytest.raises(ConnectorFailure) as error:
        EStatClient(settings, transport).get_stats_list()

    assert error.value.code == ErrorCode.SCHEMA_CHANGED
    assert error.value.reason == ConnectorFailureReason.RESPONSE_TOO_LARGE
    assert error.value.http_status is None
