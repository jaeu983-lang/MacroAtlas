"""BEA/e-Stat catalogue envelopes and bounded, source-separated archive checks."""
import hashlib
import json
import runpy
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import ConnectorFailure, JsonApiResponse
from macro_data_platform.contracts import ErrorCode, StageStatus
from macro_data_platform.discovery.api_catalogue_validation import validate_api_catalogue
from macro_data_platform.storage.api_responses import SavedApiArtifact, read_api_response

ROOT = Path(__file__).parents[1]
HELPERS = runpy.run_path(str(ROOT / "scripts" / "verify_api_metadata.py"))


def payload(source):
    return json.loads((ROOT / "tests" / "fixtures" / "rest_api" /
                       f"{source}_catalogue.json").read_text(encoding="utf-8"))


def settings(root, *, enabled=True):
    return Settings(root, network_enabled=enabled, bea_api_key="fixture-bea-credential",
                    estat_app_id="fixture-estat-credential")


@pytest.mark.parametrize("source", ["bea", "estat"])
def test_valid_catalogues_are_metadata_only_and_do_not_mutate_payload(source):
    original = payload(source)
    before = deepcopy(original)
    result = validate_api_catalogue(source, original)
    assert result["status"] == "metadata_contract_validated"
    assert result["entry_count"] == 1
    assert result["observations_accepted"] is False
    assert result["complete_dataset_assessed"] is False
    assert original == before


@pytest.mark.parametrize("source", ["bea", "estat"])
def test_recorded_live_metadata_fixture_matches_provenance_and_source_contract(source):
    folder = ROOT / "tests" / "fixtures" / "rest_api"
    provenance = json.loads((folder / "recorded_api_catalogues.provenance.json").read_text(
        encoding="utf-8"))
    record = next(row for row in provenance["sources"] if row["source"] == source)
    body = (folder / record["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == record["sha256"]
    result = validate_api_catalogue(source, json.loads(body))
    assert result["status"] == "metadata_contract_validated"
    assert result["entry_count"] == record["entry_count"]
    assert result["observations_accepted"] is False
    assert provenance["evidence"] == "recorded_live_metadata_sanitized"


@pytest.mark.parametrize("code", [0, "1", "100", None, True, "private-error", -1])
def test_bea_error_envelope_never_becomes_success_or_exposes_description(code):
    result = validate_api_catalogue("bea", {"BEAAPI": {"Results": {
        "Error": {"APIErrorCode": code, "APIErrorDescription": "private-error-detail"},
        "Dataset": payload("bea")["BEAAPI"]["Results"]["Dataset"],
    }}})
    assert result["status"] == "needs_review"
    assert result["reason"] == "source_api_error"
    assert "private-error" not in json.dumps(result)


@pytest.mark.parametrize("rows", [[], {}, [{"DatasetName": "A"}],
                                  [{"DatasetName": "A", "DatasetDescription": ""}],
                                  [{"DatasetName": "A", "DatasetDescription": "x"}] * 2])
def test_empty_changed_and_duplicate_bea_catalogues_require_review(rows):
    assert validate_api_catalogue("bea", {"BEAAPI": {"Results": {"Dataset": rows}}})[
        "status"] == "needs_review"


@pytest.mark.parametrize("status,reason", [(1, "empty_catalogue"), (100, "source_api_error"),
                                         ("100", "source_api_error"), (False, "source_api_error")])
def test_estat_empty_and_error_statuses_are_not_metadata_success(status, reason):
    data = payload("estat")
    data["GET_STATS_LIST"]["RESULT"]["STATUS"] = status
    result = validate_api_catalogue("estat", data)
    assert result["status"] == "needs_review" and result["reason"] == reason


@pytest.mark.parametrize("change", ["language", "limit", "multiple_rows", "missing_title", "bad_id"])
def test_estat_english_one_row_selection_is_validated(change):
    data = payload("estat")
    root = data["GET_STATS_LIST"]
    if change == "language":
        root["PARAMETER"]["LANG"] = "J"
    elif change == "limit":
        root["PARAMETER"]["LIMIT"] = 2
    elif change == "multiple_rows":
        root["DATALIST_INF"]["TABLE_INF"] = [root["DATALIST_INF"]["TABLE_INF"]] * 2
    elif change == "missing_title":
        del root["DATALIST_INF"]["TABLE_INF"]["TITLE"]
    else:
        root["DATALIST_INF"]["TABLE_INF"]["@id"] = "not-an-id"
    assert validate_api_catalogue("estat", data)["status"] == "needs_review"


def test_estat_single_item_array_and_string_status_preserve_original_structure():
    data = payload("estat")
    root = data["GET_STATS_LIST"]
    root["RESULT"]["STATUS"] = "0"
    root["DATALIST_INF"]["TABLE_INF"] = [root["DATALIST_INF"]["TABLE_INF"]]
    assert validate_api_catalogue("estat", data)["status"] == "metadata_contract_validated"
    assert isinstance(root["DATALIST_INF"]["TABLE_INF"], list)


def test_fixture_runner_uses_real_clients_and_hash_checked_redacted_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "request",
                        lambda *_a, **_kw: pytest.fail("Fixture must not issue HTTP"))
    configured = settings(tmp_path)
    path, report = HELPERS["run_checks"](configured, fixture=True)
    assert report["evidence"] == "synthetic_fixture" and report["status"] == "completed"
    assert report["request_budget"]["maximum_http_requests"] == 0
    assert [row["institution_id"] for row in report["results"]] == ["US-04", "JP-03"]
    assert set(report["excluded_institution_ids"]) == {"US-05", "US-06"}
    for row in report["results"]:
        assert row["status"] == "fixture_metadata_validated"
        assert row["request_count"] == 0 and row["mock_requests"] == 1
        assert row["read_back_verified"] is True
        loaded = read_api_response(configured, SavedApiArtifact(**row["artifact"]))
        for relative in (row["artifact"]["raw_path"], row["artifact"]["manifest_path"]):
            text = (tmp_path / relative).read_text(encoding="utf-8")
            assert "fixture-bea-credential" not in text and "fixture-estat-credential" not in text
        assert loaded.manifest["institution_id"] == row["institution_id"]
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"


@pytest.mark.parametrize("enabled,expected", [(False, "not_run_network_disabled"),
                                              (True, "not_run_missing_key")])
def test_no_network_or_no_keys_never_calls_source(tmp_path, monkeypatch, enabled, expected):
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch",
                        lambda *_a: pytest.fail("Source must not run"))
    _, report = HELPERS["run_checks"](Settings(tmp_path, network_enabled=enabled))
    assert {row["status"] for row in report["results"]} == {expected}
    assert sum(row["request_count"] for row in report["results"]) == 0
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("sources", [[], ["census"], ["bls"], ["bea", "bea"], [None], "bea"])
def test_invalid_or_deferred_sources_fail_before_any_output(tmp_path, sources):
    with pytest.raises(ValueError):
        HELPERS["run_checks"](settings(tmp_path), sources=sources, fixture=True)
    assert not (tmp_path / "reports").exists()


def test_report_output_failure_stops_before_source_request(tmp_path, monkeypatch):
    (tmp_path / "reports").write_text("existing file", encoding="utf-8")
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch",
                        lambda *_a: pytest.fail("Report failure must precede HTTP"))
    with pytest.raises(OSError):
        HELPERS["run_checks"](settings(tmp_path))


def test_source_failure_does_not_hide_or_block_independent_source_result(tmp_path, monkeypatch):
    calls = []

    def fetch(source, _settings, _fixture):
        calls.append(source)
        if source == "bea":
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                   "private-credential-detail", http_status=403)
        return JsonApiResponse("e-Stat", "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
                               "getStatsList", 200, datetime.now(UTC), payload("estat"))

    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch", fetch)
    path, report = HELPERS["run_checks"](settings(tmp_path))
    assert calls == ["bea", "estat"]
    assert report["status"] == "completed_with_issues"
    assert [row["status"] for row in report["results"]] == ["request_failed", "live_metadata_validated"]
    assert sum(row["request_count"] for row in report["results"]) == 2
    assert "private-credential-detail" not in path.read_text(encoding="utf-8")


def test_http_200_source_api_error_is_archived_but_never_counted_as_success(tmp_path, monkeypatch):
    response = JsonApiResponse("BEA", "https://apps.bea.gov/api/data", "GetDataSetList", 200,
                               datetime.now(UTC), {"BEAAPI": {"Results": {"Error": {
                                   "APIErrorCode": "4", "APIErrorDescription": "fixture-bea-credential",
                               }}}})
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch", lambda *_a: response)
    path, report = HELPERS["run_checks"](settings(tmp_path), sources=["bea"])
    row = report["results"][0]
    assert row["status"] == "source_metadata_needs_review" and row["http_status"] == 200
    assert row["read_back_verified"] is True
    assert row["validation"]["reason"] == "source_api_error"
    assert "fixture-bea-credential" not in path.read_text(encoding="utf-8")
