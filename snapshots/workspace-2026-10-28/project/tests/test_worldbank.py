"""Synthetic fixtures/mocked HTTP only. No network is used by these tests."""
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import (
    MAX_BYTES,
    ConnectorFailure,
    Download,
    GDPQuery,
    WorldBankTransport,
    parse_gdp,
)
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus, TaskStatus
from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine
from macro_data_platform.orchestration import Orchestrator, StageInput, StageSpec, TaskPlan
from macro_data_platform.storage import HistoryStore
from macro_data_platform.storage.raw_downloads import save_worldbank_download

FIXTURE = Path(__file__).parent / "fixtures" / "worldbank_gdp.json"
FIXTURE_TIME = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.fixture(autouse=True)
def deny_real_http(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Unexpected real HTTP call in fixture test")
    monkeypatch.setattr(requests.sessions.Session, "request", fail)


def fixture_download(*, body=None, status=200, content_type="application/json; charset=utf-8"):
    return Download(GDPQuery().url, body if body is not None else FIXTURE.read_bytes(), status,
                    FIXTURE_TIME, content_type, EvidenceKind.FIXTURE)


class FixtureTransport:
    def __init__(self, *results):
        self.results = results
        self.calls = []

    def fetch(self, query):
        result = self.results[min(len(self.calls), len(self.results) - 1)]
        self.calls.append(query)
        if isinstance(result, Exception):
            raise result
        return result


def stage_input(data=None):
    if data is None:
        data = {"start_year": 2020, "end_year": 2022}
    return StageInput("fixture-task", "fixture request", "collect", data, None, ())


def test_query_is_fixed_to_one_documented_host_country_indicator_and_source():
    parsed = urlsplit(GDPQuery().url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.worldbank.org"
    assert parsed.path == "/v2/country/USA/indicator/NY.GDP.MKTP.CD"
    assert parse_qs(parsed.query) == {
        "source": ["2"], "date": ["2020:2022"], "format": ["json"],
        "per_page": ["100"], "page": ["1"],
    }


@pytest.mark.parametrize("start,end", [(1959, 2020), (2022, 2020), (2020, 2030),
                                       (2020, 2101), (True, 2020), (2020, "2022")])
def test_invalid_or_bulk_queries_are_rejected(start, end):
    with pytest.raises(ValueError):
        GDPQuery(start, end)


def test_pure_parser_preserves_source_rows_null_zero_units_status_and_vintage():
    result = parse_gdp(fixture_download(), GDPQuery())
    assert result["observations"] == json.loads(FIXTURE.read_bytes())[1]
    assert [row["value"] for row in result["observations"]] == [123.5, None, 0]
    assert result["observations"][0]["unit"] == ""
    assert result["observations"][0]["obs_status"] == "F"
    assert result["source_last_updated"] == "2026-01-01"
    assert result["source_version"] is None
    assert result["frequency"] is None
    assert result["unit"] is None
    assert result["series_id"] is None
    assert result["series_key"]["source"] == "2"
    assert result["retrieved_at"] == FIXTURE_TIME.isoformat()


def test_parser_preserves_large_integer_precision_and_explicit_unknown_metadata():
    content = json.loads(FIXTURE.read_bytes())
    content[1][0]["value"] = 10 ** 400
    del content[0]["lastupdated"]
    result = parse_gdp(fixture_download(body=json.dumps(content).encode()), GDPQuery())
    assert result["observations"][0]["value"] == 10 ** 400
    assert result["source_last_updated"] is None
    assert result["source_version"] is None


def test_parser_and_download_contract_reject_unrelated_identity_and_evidence_mode():
    changed = Download("https://example.org", FIXTURE.read_bytes(), 200, FIXTURE_TIME,
                       "application/json", EvidenceKind.FIXTURE)
    with pytest.raises(ConnectorFailure, match="request identity") as caught:
        parse_gdp(changed, GDPQuery())
    assert caught.value.code == ErrorCode.SCHEMA_CHANGED
    with pytest.raises(ValueError, match="distinguish fixture"):
        Download(GDPQuery().url, b"{}", 200, FIXTURE_TIME, "application/json",
                 EvidenceKind.OFFICIAL_DOCS)


@pytest.mark.parametrize("status,stage_status,code", [
    (401, StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS),
    (403, StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS),
    (429, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (500, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (503, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (301, StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY),
    (404, StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED),
    (410, StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED),
    (400, StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED),
])
def test_http_failures_retain_raw_and_do_not_claim_success(tmp_path, status, stage_status, code):
    download = fixture_download(status=status, body=b'{"fixture":"error"}')
    engine = WorldBankGDPEngine(Settings(tmp_path), FixtureTransport(download))
    result = engine.run(stage_input())
    assert result.status == stage_status
    assert result.error_code == code
    assert (tmp_path / result.payload["raw_path"]).read_bytes() == download.body
    assert "observations" not in result.payload


@pytest.mark.parametrize("change", ["envelope", "api_error", "empty", "pagination", "total",
                                    "country", "indicator", "date", "missing_value", "numeric",
                                    "source", "row", "boolean_page", "nonstandard_nan"])
def test_schema_and_request_mismatches_are_rejected_without_discarding_raw(tmp_path, change):
    content = json.loads(FIXTURE.read_bytes())
    if change == "envelope":
        content = {"data": []}
    elif change == "api_error":
        content = [{"message": [{"id": "120", "key": "Invalid value"}]}]
    elif change == "empty":
        content[1] = []
        content[0]["total"] = 0
    elif change == "pagination":
        content[0]["pages"] = 2
    elif change == "total":
        content[0]["total"] = 99
    elif change == "country":
        content[1][0]["countryiso3code"] = "JPN"
    elif change == "indicator":
        content[1][0]["indicator"]["id"] = "SP.POP.TOTL"
    elif change == "date":
        content[1][0]["date"] = "2019"
    elif change == "missing_value":
        del content[1][0]["value"]
    elif change == "numeric":
        content[1][0]["value"] = True
    elif change == "source":
        content[0]["sourceid"] = []
    elif change == "row":
        content[1][0] = None
    elif change == "boolean_page":
        content[0]["page"] = True
    elif change == "nonstandard_nan":
        content[0]["unexpected"] = float("nan")
    body = json.dumps(content).encode()
    result = WorldBankGDPEngine(Settings(tmp_path), FixtureTransport(
        fixture_download(body=body),
    )).run(stage_input())
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.error_code == ErrorCode.SCHEMA_CHANGED
    assert (tmp_path / result.payload["raw_path"]).read_bytes() == body


@pytest.mark.parametrize("body,content_type", [(b"not JSON", "application/json"),
                                              (b"<html>failure</html>", "text/html"),
                                              (b"\xff", "application/json")])
def test_malformed_json_or_html_is_retained_for_review(tmp_path, body, content_type):
    download = fixture_download(body=body, content_type=content_type)
    result = WorldBankGDPEngine(Settings(tmp_path), FixtureTransport(download)).run(stage_input())
    assert result.status == StageStatus.NEEDS_REVIEW
    assert (tmp_path / result.payload["raw_path"]).read_bytes() == body


def test_raw_saves_are_distinct_and_never_overwrite(tmp_path):
    settings = Settings(tmp_path)
    first = save_worldbank_download(settings, fixture_download())
    second = save_worldbank_download(settings, fixture_download(body=b"new response"))
    assert first.raw_path != second.raw_path
    assert (tmp_path / first.raw_path).read_bytes() == FIXTURE.read_bytes()
    manifest = json.loads((tmp_path / first.manifest_path).read_text(encoding="utf-8"))
    assert manifest["mode"] == "fixture"
    assert manifest["http_status"] == 200
    assert manifest["byte_count"] == len(FIXTURE.read_bytes())
    assert manifest["retrieved_at"] == FIXTURE_TIME.isoformat()
    assert manifest["source_url"] == GDPQuery().url


def test_uuid_collision_fails_instead_of_overwriting_raw(tmp_path, monkeypatch):
    monkeypatch.setattr("macro_data_platform.storage.raw_downloads.uuid4",
                        lambda: type("FixedID", (), {"hex": "0" * 32})())
    settings = Settings(tmp_path)
    first = save_worldbank_download(settings, fixture_download())
    with pytest.raises(FileExistsError):
        save_worldbank_download(settings, fixture_download(body=b"replacement"))
    assert (tmp_path / first.raw_path).read_bytes() == FIXTURE.read_bytes()


def test_network_disabled_never_constructs_session_or_writes_raw(tmp_path, monkeypatch):
    def unexpected_session():
        raise AssertionError("Disabled transport must not create a session")
    monkeypatch.setattr(requests, "Session", unexpected_session)
    result = WorldBankGDPEngine(Settings(tmp_path)).run(stage_input())
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.error_code == ErrorCode.LICENSE_SECURITY
    assert not (tmp_path / "data").exists()


def test_truthy_string_is_not_explicit_network_permission(tmp_path):
    result = WorldBankGDPEngine(Settings(tmp_path, network_enabled="false")).run(stage_input())
    assert result.error_code == ErrorCode.LICENSE_SECURITY
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("data", [{}, {"url": "https://example.org"},
                                  {"start_year": 2020, "end_year": 2022, "api_key": "placeholder"},
                                  {"start_year": 2020, "end_year": 2035}, [], "unexpected"])
def test_invalid_engine_inputs_do_not_start_transport(tmp_path, data):
    transport = FixtureTransport(fixture_download())
    result = WorldBankGDPEngine(Settings(tmp_path), transport).run(stage_input(data))
    assert result.status == StageStatus.FAILED_TERMINAL
    assert not transport.calls
    assert "placeholder" not in str(result)


def test_engine_rejects_transport_url_changes_without_saving(tmp_path):
    download = Download("https://example.org", b"{}", 200, FIXTURE_TIME,
                        "application/json", EvidenceKind.FIXTURE)
    result = WorldBankGDPEngine(Settings(tmp_path), FixtureTransport(download)).run(stage_input())
    assert result.error_code == ErrorCode.LICENSE_SECURITY
    assert not (tmp_path / "data").exists()


def mocked_session(monkeypatch, *, body=None, status=200, headers=None, error=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.headers = headers or {"Content-Type": "application/json"}
    response.iter_content.return_value = [FIXTURE.read_bytes() if body is None else body]
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = response
    if error is not None:
        session.get.side_effect = error
    monkeypatch.setattr(requests, "Session", lambda: session)
    return session, response


def test_live_transport_settings_with_mocked_session_use_tls_and_no_implicit_credentials(
    tmp_path, monkeypatch,
):
    session, _ = mocked_session(monkeypatch)
    download = WorldBankTransport(Settings(tmp_path, network_enabled=True)).fetch(GDPQuery())
    assert download.body == FIXTURE.read_bytes()
    assert session.trust_env is False
    assert session.get.call_args.args == (GDPQuery().url,)
    kwargs = session.get.call_args.kwargs
    assert kwargs["timeout"] == (5, 20)
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True
    assert kwargs.get("verify", True) is True
    assert "auth" not in kwargs
    assert session.get.call_count == 1


@pytest.mark.parametrize(("header", "status", "expected"), [
    ("25", StageStatus.FAILED_RETRYABLE, 25.0),
    ("90000", StageStatus.NEEDS_REVIEW, None),
])
def test_rate_limit_retry_after_is_recorded_and_bounded(tmp_path, monkeypatch,
                                                        header, status, expected):
    session, _ = mocked_session(monkeypatch, status=429, headers={
        "Content-Type": "text/plain", "Retry-After": header,
    })

    result = WorldBankGDPEngine(Settings(tmp_path, network_enabled=True)).run(stage_input())

    assert result.status == status
    assert result.error_code == ErrorCode.TRANSIENT
    assert result.retry_after_seconds == expected
    assert session.get.call_count == 1
    if expected is not None:
        assert result.retry_after_seconds <= 86_400


@pytest.mark.parametrize("error,status,code", [
    (requests.Timeout("private detail"), StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (requests.ConnectionError("private detail"), StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (requests.exceptions.SSLError("private detail"), StageStatus.NEEDS_REVIEW,
     ErrorCode.LICENSE_SECURITY),
])
def test_transport_errors_are_safe_and_make_no_automatic_retries(tmp_path, monkeypatch,
                                                              error, status, code):
    session, _ = mocked_session(monkeypatch, error=error)
    result = WorldBankGDPEngine(Settings(tmp_path, network_enabled=True)).run(stage_input())
    assert result.status == status
    assert result.error_code == code
    assert "private detail" not in str(result)
    assert session.get.call_count == 1
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("mode", ["content_length", "stream_size", "time_budget"])
def test_oversized_or_over_budget_download_is_not_saved_as_complete(tmp_path, monkeypatch, mode):
    headers = {"Content-Type": "application/json"}
    body = b"{}"
    if mode == "content_length":
        headers["Content-Length"] = str(MAX_BYTES + 1)
    elif mode == "stream_size":
        body = b"x" * (MAX_BYTES + 1)
    else:
        ticks = iter([0, 31])
        monkeypatch.setattr("macro_data_platform.connectors.http_transport.time.monotonic",
                            lambda: next(ticks))
    mocked_session(monkeypatch, body=body, headers=headers)
    result = WorldBankGDPEngine(Settings(tmp_path, network_enabled=True)).run(stage_input())
    assert result.status != StageStatus.SUCCEEDED
    assert not (tmp_path / "data").exists()


def test_local_storage_failure_keeps_existing_raw_untouched(tmp_path, monkeypatch):
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"original")

    def fail_save(*args, **kwargs):
        raise OSError("private filesystem detail")
    monkeypatch.setattr("macro_data_platform.ingestion.worldbank.save_worldbank_download", fail_save)
    result = WorldBankGDPEngine(Settings(tmp_path), FixtureTransport(
        fixture_download(),
    )).run(stage_input())
    assert result.status == StageStatus.FAILED_TERMINAL
    assert result.error_code == ErrorCode.INTERNAL_BUG
    assert "private filesystem detail" not in str(result)
    assert existing.read_bytes() == b"original"


def test_offline_vertical_slice_integrates_with_durable_orchestrator_and_manual_retry(tmp_path):
    settings = Settings(tmp_path)
    transport = FixtureTransport(fixture_download(status=503), fixture_download())
    engine = WorldBankGDPEngine(settings, transport)
    store = HistoryStore(settings)
    now = [FIXTURE_TIME]
    runner = Orchestrator(store, {("worldbank_gdp", "1"): engine},
                          clock=lambda: now[0])
    task = runner.create("fixture GDP query")
    runner.plan(task.task_id, TaskPlan((StageSpec("collect", "worldbank_gdp",
                                                {"start_year": 2020, "end_year": 2022}),)))
    initial = runner.run(task.task_id)
    assert initial["status"] == TaskStatus.FAILED
    now[0] = datetime.fromisoformat(initial["stages"][-1]["result"]["retry_not_before"])
    result = runner.resume(task.task_id)
    assert result["status"] == TaskStatus.COMPLETED
    assert result["stages"][-1]["result"]["payload"]["mode"] == "fixture"
    assert len(transport.calls) == 2
    assert len(result["stages"][-1]["result"]["payload"]["observations"]) == 3
    assert (tmp_path / initial["stages"][-1]["result"]["payload"]["raw_path"]).exists()
    assert HistoryStore(settings).get(task.task_id) == result


def test_live_verification_script_requires_explicit_opt_in():
    result = subprocess.run([sys.executable, "scripts/verify_worldbank.py"],
                            capture_output=True, timeout=30, check=False)
    assert result.returncode == 2
    assert b"--live is required" in result.stderr
