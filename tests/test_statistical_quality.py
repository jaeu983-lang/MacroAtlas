"""Iteration 10 quality diagnostics and manual recovery coverage."""
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import (
    ApiDownload,
    SourceFailure,
    request_json,
)
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus
from macro_data_platform.ingestion.bls import BLSEngine
from macro_data_platform.ingestion.census import CensusEngine
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CENSUS_URL = "https://api.census.gov/data/2022/acs/acs1"
BLS_INPUT = {"series_ids": ["CUUR0000SA0"], "start_year": 2024, "end_year": 2024}
CENSUS_INPUT = {
    "year": 2022, "dataset": "acs/acs1", "variables": ["NAME", "B01001_001E"],
    "geography": "state:06",
}


def make_download(url, body):
    return ApiDownload(url, json.dumps(body).encode(), 200, NOW, "application/json",
                       EvidenceKind.FIXTURE)


def bls_body(*rows):
    return {
        "status": "REQUEST_SUCCEEDED", "messageCodes": [],
        "Results": {"series": [{"seriesID": "CUUR0000SA0", "data": list(rows)}]},
    }


def bls_row(year="2024", period="M01", value="308.417"):
    return {"year": year, "period": period, "periodName": "January", "value": value,
            "footnotes": []}


def census_download(value):
    return make_download(CENSUS_URL, [
        ["NAME", "B01001_001E", "state"], ["California", value, "06"],
    ])


class SequenceTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def fetch(self, query):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeHttpResponse:
    def __init__(self, body):
        self.body = body
        self.status = 200
        self.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size):
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk


class SequenceOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def stage_input(engine, payload):
    return StageInput("quality-task", "quality test", engine, payload, None, ())


@pytest.mark.parametrize(("status", "stage", "code"), [
    (403, StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS),
    (429, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (503, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (404, StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED),
])
def test_http_status_classification_is_safe_and_retains_status(status, stage, code):
    opener = Mock()
    opener.open.side_effect = HTTPError(
        BLS_URL, status, "fixture failure", {}, BytesIO(b"not persisted"),
    )
    with patch("macro_data_platform.connectors.statistical_http.urllib.request.build_opener",
               return_value=opener), pytest.raises(SourceFailure) as captured:
        request_json(BLS_URL, method="GET")

    assert captured.value.status is stage
    assert captured.value.code is code
    assert captured.value.status_code == status
    assert "fixture failure" not in str(captured.value)
    assert opener.open.call_count == 1


def test_retry_after_seconds_are_retained_without_an_automatic_request():
    opener = Mock()
    opener.open.side_effect = HTTPError(
        BLS_URL, 429, "fixture failure", {"Retry-After": "17"}, BytesIO(b"not persisted"),
    )
    with patch("macro_data_platform.connectors.statistical_http.urllib.request.build_opener",
               return_value=opener), pytest.raises(SourceFailure) as captured:
        request_json(BLS_URL, method="GET")

    assert captured.value.status is StageStatus.FAILED_RETRYABLE
    assert captured.value.retry_after_seconds == 17
    assert opener.open.call_count == 1


def test_retry_after_http_date_is_converted_to_a_minimum_delay():
    opener = Mock()
    retry_at = datetime.now(UTC) + timedelta(seconds=20)
    opener.open.side_effect = HTTPError(
        BLS_URL, 503, "fixture failure", {"Retry-After": format_datetime(retry_at, usegmt=True)},
        BytesIO(b"not persisted"),
    )
    with patch("macro_data_platform.connectors.statistical_http.urllib.request.build_opener",
               return_value=opener), pytest.raises(SourceFailure) as captured:
        request_json(BLS_URL, method="GET")

    assert 1 <= captured.value.retry_after_seconds <= 20
    assert opener.open.call_count == 1


def test_transport_timeout_is_transient_without_automatic_retry():
    opener = Mock()
    opener.open.side_effect = URLError(TimeoutError())
    with patch("macro_data_platform.connectors.statistical_http.urllib.request.build_opener",
               return_value=opener), pytest.raises(SourceFailure) as captured:
        request_json(BLS_URL, method="GET")

    assert captured.value.status is StageStatus.FAILED_RETRYABLE
    assert captured.value.code is ErrorCode.TRANSIENT
    assert opener.open.call_count == 1


@pytest.mark.parametrize(("source", "engine_cls", "input_data", "valid_download"), [
    ("bls", BLSEngine, BLS_INPUT, make_download(BLS_URL, bls_body(bls_row()))),
    ("census", CensusEngine, CENSUS_INPUT,
     make_download(CENSUS_URL, [["NAME", "B01001_001E", "state"],
                               ["California", "39029342", "06"]])),
])
def test_429_failure_remains_retryable_across_process_restart(
        tmp_path, source, engine_cls, input_data, valid_download):
    transient = SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                              "Official API returned a temporary HTTP failure.", 429)
    transport = SequenceTransport(transient, valid_download)
    settings = Settings(tmp_path, network_enabled=True)
    engines = {(source, "1"): engine_cls(settings, transport)}
    first_runner = Orchestrator(HistoryStore(settings), engines)
    task = first_runner.create("retry after rate limit")
    first_runner.plan(task.task_id, TaskPlan((StageSpec(source, source, input_data),)))

    first = first_runner.run(task.task_id)
    assert first["status"] == "FAILED"
    assert first["stages"][-1]["result"]["error_code"] == "TRANSIENT"
    assert first["stages"][-1]["result"]["retry_hint"]
    assert transport.calls == 1

    restarted = Orchestrator(HistoryStore(settings), engines)
    final = restarted.resume(task.task_id)
    assert final["status"] == "COMPLETED"
    assert transport.calls == 2
    assert final["stages"][-1]["result"]["payload"]["quality"]["status"] == "passed"


def test_orchestrator_persists_simulated_http_503_and_resumes_same_task_after_retry_after(
        tmp_path):
    body = json.dumps(bls_body(bls_row())).encode()
    opener = SequenceOpener(
        HTTPError(BLS_URL, 503, "fixture outage", {"Retry-After": "2"}, BytesIO(b"")),
        FakeHttpResponse(body),
    )

    class Clock:
        value = NOW

        def __call__(self):
            return self.value

    clock = Clock()
    settings = Settings(tmp_path, network_enabled=True)
    engines = {("bls", "1"): BLSEngine(settings)}
    first_runner = Orchestrator(HistoryStore(settings), engines, clock=clock)
    task = first_runner.create("persist provider retry through Orchestrator")
    first_runner.plan(task.task_id, TaskPlan((StageSpec("bls", "bls", BLS_INPUT),)))

    with patch("macro_data_platform.connectors.statistical_http.urllib.request.build_opener",
               return_value=opener):
        failed = first_runner.run(task.task_id)
        restarted = Orchestrator(HistoryStore(settings), engines, clock=clock)
        with pytest.raises(ValueError, match="Retry-After delay has not elapsed"):
            restarted.resume(task.task_id)
        assert len(opener.requests) == 1
        clock.value += timedelta(seconds=2)
        completed = restarted.resume(task.task_id)

    assert failed["status"] == "FAILED"
    assert failed["stages"][-1]["status"] == StageStatus.FAILED_RETRYABLE
    assert failed["stages"][-1]["result"]["payload"]["http_status"] == 503
    assert failed["stages"][-1]["result"]["retry_after_seconds"] == 2
    assert completed["task_id"] == task.task_id
    assert completed["status"] == "COMPLETED"
    assert [row["status"] for row in completed["attempts"]] == ["FAILED", "COMPLETED"]
    assert [row["status"] for row in completed["stages"]] == [
        StageStatus.FAILED_RETRYABLE, StageStatus.SUCCEEDED,
    ]
    assert completed["stages"][-1]["result"]["payload"]["quality"]["status"] == "passed"
    assert len(opener.requests) == 2
    assert all(request.full_url == BLS_URL and request.method == "POST"
               for request, _timeout in opener.requests)
    reopened = HistoryStore(settings)
    assert reopened.get(task.task_id) == completed
    event_kinds = [event["kind"] for event in reopened.events(task.task_id)]
    assert "TASK_RESUMED" in event_kinds
    assert event_kinds.count("STAGE_FINISHED") == 2


@pytest.mark.parametrize(("source", "engine_cls", "input_data"), [
    ("bls", BLSEngine, BLS_INPUT),
    ("census", CensusEngine, CENSUS_INPUT),
])
def test_403_requires_review_and_never_becomes_retryable(
        tmp_path, source, engine_cls, input_data):
    denied = SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                           "Official API denied access; credentials were not logged.", 403)
    engine = engine_cls(Settings(tmp_path, network_enabled=True), SequenceTransport(denied))

    result = engine.run(stage_input(source, input_data))

    assert result.status is StageStatus.NEEDS_REVIEW
    assert result.error_code is ErrorCode.AUTH_ACCESS
    assert result.payload == {"http_status": 403}
    assert result.retry_hint is None


@pytest.mark.parametrize(("engine_cls", "input_data", "source"), [
    (BLSEngine, BLS_INPUT, "bls"),
    (CensusEngine, CENSUS_INPUT, "census"),
])
def test_retry_after_survives_source_engine_failure(tmp_path, engine_cls, input_data, source):
    failure = SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                            "temporary API condition", 429, retry_after_seconds=45)
    result = engine_cls(
        Settings(tmp_path, network_enabled=True), SequenceTransport(failure),
    ).run(stage_input(source, input_data))

    assert result.status is StageStatus.FAILED_RETRYABLE
    assert result.retry_after_seconds == 45
    assert "45 seconds" in result.retry_hint


def test_bls_duplicate_period_is_quarantined_and_missing_value_is_reported(tmp_path):
    body = bls_body(bls_row(value=""), bls_row(value="309.1"))
    result = BLSEngine(
        Settings(tmp_path, network_enabled=True),
        SequenceTransport(make_download(BLS_URL, body)),
    ).run(stage_input("bls", BLS_INPUT))

    assert result.status is StageStatus.NEEDS_REVIEW
    assert result.error_code is ErrorCode.QUALITY_FAILURE
    assert result.payload["quality"]["issues"] == ["duplicate_series_periods"]
    assert result.payload["quality"]["duplicate_period_count"] == 1
    assert result.payload["quality"]["empty_value_count"] == 1
    assert "empty_values_preserved" in result.payload["quality"]["warnings"]
    assert Path(tmp_path, result.payload["raw_path"]).exists()


def test_census_geography_mismatch_is_quarantined_and_nulls_are_preserved(tmp_path):
    download = make_download(CENSUS_URL, [
        ["NAME", "B01001_001E", "state"], ["California", None, "36"],
    ])
    result = CensusEngine(
        Settings(tmp_path, network_enabled=True), SequenceTransport(download),
    ).run(stage_input("census", CENSUS_INPUT))

    assert result.status is StageStatus.NEEDS_REVIEW
    assert result.error_code is ErrorCode.QUALITY_FAILURE
    assert result.payload["quality"]["issues"] == ["requested_geography_mismatch"]
    assert result.payload["quality"]["missing_value_count"] == 1
    assert result.payload["observations"][0]["B01001_001E"] is None
    assert Path(tmp_path, result.payload["raw_path"]).exists()


@pytest.mark.parametrize(("source", "engine_cls", "input_data", "download"), [
    ("bls", BLSEngine, BLS_INPUT,
     make_download(BLS_URL, bls_body(bls_row()))),
    ("census", CensusEngine, CENSUS_INPUT,
     make_download(CENSUS_URL, [["NAME", "B01001_001E", "state"],
                               ["California", "39029342", "06"]])),
])
def test_unknown_unit_frequency_and_vintage_stay_unknown(
        tmp_path, source, engine_cls, input_data, download):
    result = engine_cls(
        Settings(tmp_path, network_enabled=True), SequenceTransport(download),
    ).run(stage_input(source, input_data))

    assert result.status is StageStatus.SUCCEEDED
    assert result.payload["unit"] is None
    assert result.payload["frequency"] is None
    assert "unit_unknown" in result.payload["quality"]["warnings"]
    assert "frequency_unknown" in result.payload["quality"]["warnings"]
    assert result.payload["quality"]["source_change_status"] == "first_observation"


@pytest.mark.parametrize(("source", "engine_cls", "input_data", "first", "changed"), [
    ("bls", BLSEngine, BLS_INPUT,
     make_download(BLS_URL, bls_body(bls_row(value="308.417"))),
     make_download(BLS_URL, bls_body(bls_row(value="309.1")))),
    ("census", CensusEngine, CENSUS_INPUT, census_download("39029342"),
     census_download("39029343")),
])
def test_changed_raw_for_same_request_is_preserved_and_needs_review(
        tmp_path, source, engine_cls, input_data, first, changed):
    settings = Settings(tmp_path, network_enabled=True)
    transport = SequenceTransport(first, changed)
    engine = engine_cls(settings, transport)

    first_result = engine.run(stage_input(source, input_data))
    second = engine.run(stage_input(source, input_data))

    assert first_result.status is StageStatus.SUCCEEDED
    assert first_result.payload["source_change_status"] == "first_observation"
    assert second.status is StageStatus.NEEDS_REVIEW
    assert second.error_code is ErrorCode.QUALITY_FAILURE
    assert second.payload["source_change_status"] == "changed"
    assert "source_payload_changed_since_prior_request" in second.payload["quality"]["issues"]
    first_raw = Path(tmp_path, first_result.payload["raw_path"])
    second_raw = Path(tmp_path, second.payload["raw_path"])
    assert first_raw.read_bytes() == first.body
    assert second_raw.read_bytes() == changed.body
    first_manifest = json.loads(Path(tmp_path, first_result.payload["manifest_path"]).read_text())
    second_manifest = json.loads(Path(tmp_path, second.payload["manifest_path"]).read_text())
    assert first_manifest["raw_sha256"] != second_manifest["raw_sha256"]
    assert second_manifest["source_change_status"] == "changed"


def test_bls_response_time_does_not_count_as_source_payload_change(tmp_path):
    first_body = bls_body(bls_row())
    first_body["responseTime"] = "0.012"
    second_body = bls_body(bls_row())
    second_body["responseTime"] = "0.021"
    settings = Settings(tmp_path, network_enabled=True)
    engine = BLSEngine(settings, SequenceTransport(
        make_download(BLS_URL, first_body), make_download(BLS_URL, second_body),
    ))

    first = engine.run(stage_input("bls", BLS_INPUT))
    second = engine.run(stage_input("bls", BLS_INPUT))

    assert first.status is StageStatus.SUCCEEDED
    assert second.status is StageStatus.SUCCEEDED
    assert first.payload["raw_sha256"] != second.payload["raw_sha256"]
    assert first.payload["quality"]["source_change_status"] == "first_observation"
    assert second.payload["quality"]["source_change_status"] == "unchanged"
    first_manifest = json.loads(Path(tmp_path, first.payload["manifest_path"]).read_text())
    second_manifest = json.loads(Path(tmp_path, second.payload["manifest_path"]).read_text())
    assert first_manifest["comparison_method"] == "bls_json_without_responseTime_v1"
    assert first_manifest["comparison_sha256"] == second_manifest["comparison_sha256"]


def test_unchanged_raw_is_confirmed_and_tampered_history_is_unknown(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    response = make_download(BLS_URL, bls_body(bls_row()))
    first = BLSEngine(settings, SequenceTransport(response)).run(stage_input("bls", BLS_INPUT))
    same = BLSEngine(settings, SequenceTransport(response)).run(stage_input("bls", BLS_INPUT))
    repeated = BLSEngine(
        settings, SequenceTransport(response),
    ).run(stage_input("bls", BLS_INPUT))
    Path(tmp_path, first.payload["raw_path"]).write_bytes(b"changed after capture")
    after_tamper = BLSEngine(
        settings, SequenceTransport(response),
    ).run(stage_input("bls", BLS_INPUT))

    assert same.status is StageStatus.SUCCEEDED
    assert same.payload["source_change_status"] == "unchanged"
    assert repeated.status is StageStatus.SUCCEEDED
    assert repeated.payload["source_change_status"] == "unchanged"
    assert after_tamper.status is StageStatus.SUCCEEDED
    assert after_tamper.payload["source_change_status"] == "unknown_history_integrity"
    assert "prior_response_comparison_unavailable" in after_tamper.payload["quality"]["warnings"]


def test_different_request_scope_starts_a_separate_change_baseline(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    response = make_download(BLS_URL, bls_body(bls_row()))
    first = BLSEngine(settings, SequenceTransport(response)).run(
        stage_input("bls", BLS_INPUT),
    )
    other_scope = {**BLS_INPUT, "start_year": 2023, "end_year": 2023}
    other_response = make_download(BLS_URL, bls_body(bls_row(year="2023")))
    second = BLSEngine(settings, SequenceTransport(other_response)).run(
        stage_input("bls", other_scope),
    )

    assert first.status is StageStatus.SUCCEEDED
    assert second.status is StageStatus.SUCCEEDED
    assert second.payload["source_change_status"] == "first_observation"


def test_schema_drift_retains_new_raw_response_for_diagnosis(tmp_path):
    drifted = make_download(BLS_URL, {
        "status": "REQUEST_SUCCEEDED", "Results": {"unexpected": []},
    })
    result = BLSEngine(
        Settings(tmp_path, network_enabled=True), SequenceTransport(drifted),
    ).run(stage_input("bls", BLS_INPUT))

    assert result.status is StageStatus.NEEDS_REVIEW
    assert result.error_code is ErrorCode.SCHEMA_CHANGED
    assert Path(tmp_path, result.payload["raw_path"]).read_bytes() == drifted.body
