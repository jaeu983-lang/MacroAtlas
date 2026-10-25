"""Source-separated contracts, safety failures and archive regression; no live HTTP."""
import hashlib
import json
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import ConnectorFailure
from macro_data_platform.connectors.sdmx import MAX_SDMX_RESPONSE_BYTES
from macro_data_platform.contracts import ErrorCode, StageStatus
from macro_data_platform.discovery.sdmx_metadata_validation import (
    SDMX_SELECTIONS,
    validate_sdmx_metadata,
)
from macro_data_platform.metadata.adapters import parse_sdmx_structure
from macro_data_platform.storage.api_responses import read_api_response, save_api_response

ROOT = Path(__file__).parents[1]
HELPERS = runpy.run_path(str(ROOT / "scripts" / "verify_api_metadata.py"))


def response(source, settings):
    return HELPERS["_fetch"](source, settings, True)


@pytest.mark.parametrize("source", SDMX_SELECTIONS)
def test_fixed_source_metadata_route_and_contract(source, tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    value = response(source, settings)
    assert value.source_url == SDMX_SELECTIONS[source].url
    check = validate_sdmx_metadata(source, value)
    assert check["status"] == "metadata_contract_validated"
    assert check["observations_accepted"] is False
    artifact = save_api_response(settings, value, expected_institution_id=value.institution_id)
    loaded = read_api_response(settings, artifact)
    assert loaded.body == value.body
    assert hashlib.sha256(loaded.body).hexdigest() == artifact.raw_sha256
    assert validate_sdmx_metadata(source, replace(value, body=loaded.body)) == check
    (tmp_path / artifact.raw_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        read_api_response(settings, artifact)


@pytest.mark.parametrize("source", SDMX_SELECTIONS)
@pytest.mark.parametrize("change", ["empty", "html", "json_error", "xml_error", "namespace",
    "wrong_id", "wrong_agency", "wrong_version", "source", "url", "operation", "status",
    "no_name", "no_message_id", "no_structures", "dtd", "large", "duplicate", "stub",
    "missing_reference"])
def test_invalid_payloads_never_pass(source, change, tmp_path):
    value = response(source, Settings(tmp_path, network_enabled=True))
    selection = SDMX_SELECTIONS[source]
    body = value.body
    if change == "empty":
        value = replace(value, body=b"")
    elif change == "html":
        value = replace(value, body=b"<html>Access denied</html>", content_type="text/html")
    elif change == "json_error":
        value = replace(value, body=b'{"error":"denied"}', content_type="application/json")
    elif change == "xml_error":
        value = replace(value, body=body.replace(b"<m:Structures>", b"<m:Error/><m:Structures>"))
    elif change == "namespace":
        value = replace(value, body=body.replace(b"schemas/v2_1", b"schemas/fake"))
    elif change in {"wrong_id", "wrong_agency", "wrong_version"}:
        attr, old = {"wrong_id": ("id", selection.resource_id),
                     "wrong_agency": ("agencyID", selection.agency),
                     "wrong_version": ("version", selection.version or "1.0")}[change]
        new = "" if change == "wrong_version" and source == "bundesbank" else "WRONG"
        value = replace(value, body=body.replace(f'{attr}="{old}"'.encode(),
                                                f'{attr}="{new}"'.encode()))
    elif change == "source":
        value = replace(value, institution_id="EU-99")
    elif change == "url":
        value = replace(value, source_url=value.source_url + "?unreviewed=true")
    elif change == "operation":
        value = replace(value, operation="data")
    elif change == "status":
        value = replace(value, http_status=503)
    elif change == "no_name":
        value = replace(value, body=body.replace(b"c:Name", b"c:Other"))
    elif change == "no_message_id":
        value = replace(value, body=body.replace(b"m:ID", b"m:OtherID"))
    elif change == "no_structures":
        value = replace(value, body=body.replace(b"m:Structures", b"m:Other"))
    elif change == "dtd":
        value = replace(value, body=body.replace(b"<m:Structure ", b'<!DOCTYPE x><m:Structure '))
    elif change == "large":
        value = replace(value, body=b"x" * (MAX_SDMX_RESPONSE_BYTES + 1))
    elif change == "duplicate":
        start = body.index(f"<s:{selection.kind} ".encode())
        end_tag = f"</s:{selection.kind}>".encode()
        end = body.index(end_tag) + len(end_tag)
        value = replace(value, body=body[:end] + body[start:end] + body[end:])
    elif change == "stub":
        value = replace(value, body=body.replace(f"<s:{selection.kind} ".encode(),
                            f'<s:{selection.kind} isExternalReference="true" '.encode()))
    else:
        value = replace(value, body=body.replace(b"<Ref ", b"<BadRef ")
                        .replace(b"s:DimensionList", b"s:OtherList"))
    assert validate_sdmx_metadata(source, value)["status"] == "needs_review"


def test_explicit_sdmx_fixture_runner_preserves_default(tmp_path, monkeypatch):
    monkeypatch.setattr("requests.sessions.Session.request", lambda *_a, **_k: pytest.fail("HTTP"))
    path, report = HELPERS["run_checks"](Settings(tmp_path, network_enabled=True),
                                         sources=list(SDMX_SELECTIONS), fixture=True)
    assert "iteration_32" in path.name and report["status"] == "completed"
    assert len(report["results"]) == 6
    assert sum(row["request_count"] for row in report["results"]) == 0
    assert all(row["read_back_verified"] for row in report["results"])
    assert json.loads(path.read_text(encoding="utf-8")) == report
    assert tuple(HELPERS["SOURCES"]) == ("bea", "estat")


@pytest.mark.parametrize("selection", [["bis", "bis"], ["census"], ["bis", "bea"], []])
def test_selection_rejects_mixed_budgets_duplicates_and_deferred_sources(selection, tmp_path):
    with pytest.raises(ValueError):
        HELPERS["run_checks"](Settings(tmp_path), sources=selection)


def test_no_network_and_not_ready_do_not_fetch(tmp_path, monkeypatch):
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch",
                        lambda *_a: pytest.fail("fetch"))
    _, report = HELPERS["run_checks"](Settings(tmp_path), sources=["bis"])
    assert report["results"][0]["status"] == "not_run_network_disabled"
    monkeypatch.setitem(SDMX_SELECTIONS, "bis", replace(SDMX_SELECTIONS["bis"], ready=False))
    _, report = HELPERS["run_checks"](Settings(tmp_path, network_enabled=True), sources=["bis"])
    assert report["results"][0]["status"].startswith("not_ready")
    assert report["results"][0]["request_count"] == 0


def test_failure_isolation_and_report_before_request(tmp_path, monkeypatch):
    fetch = HELPERS["_fetch"]
    calls = []

    def fake(source, settings, fixture):
        reports = list((tmp_path / "reports").glob("iteration_32*.json"))
        assert len(reports) == 1
        pending = json.loads(reports[0].read_text(encoding="utf-8"))["results"][-1]
        assert pending["request_count"] == 1 and pending["status"] == "request_started"
        calls.append(source)
        if source == "bis":
            raise ConnectorFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                   "safe error", http_status=503, response_kind="html")
        return fetch(source, settings, True)

    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch", fake)
    _, report = HELPERS["run_checks"](Settings(tmp_path, network_enabled=True),
                                     sources=["bis", "ecb"])
    assert calls == ["bis", "ecb"] and report["status"] == "completed_with_issues"
    assert report["results"][0]["failure_http_status"] == 503
    assert report["results"][1]["status"] == "live_metadata_validated"


def test_report_write_failure_prevents_request(tmp_path, monkeypatch):
    (tmp_path / "reports").write_text("not a directory")
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch",
                        lambda *_a: pytest.fail("fetch"))
    with pytest.raises(OSError):
        HELPERS["run_checks"](Settings(tmp_path, network_enabled=True), sources=["bis"])


@pytest.mark.parametrize("source", SDMX_SELECTIONS)
def test_configured_credentials_in_bytes_refused_before_storage(source, tmp_path):
    settings = Settings(tmp_path, network_enabled=True, bea_api_key="test-private-credential")
    value = replace(response(source, settings), body=b"test-private-credential")
    with pytest.raises(ValueError, match="credential"):
        save_api_response(settings, value)
    assert not list(tmp_path.rglob("response.bin"))


def test_attribute_relationship_dimension_references_are_not_definitions(tmp_path):
    value = response("ecb", Settings(tmp_path, network_enabled=True))
    body = value.body.replace(b"</s:DataStructureComponents>",
        b'<s:AttributeList><s:Attribute id="TEST"><s:AttributeRelationship>'
        b'<s:Dimension><Ref id="FREQ"/></s:Dimension>'
        b'<s:Dimension><Ref id="TIME_PERIOD"/></s:Dimension>'
        b'</s:AttributeRelationship></s:Attribute></s:AttributeList></s:DataStructureComponents>')
    structures, _ = parse_sdmx_structure(body)
    assert [d["id"] for d in structures["datastructures"][0]["dimensions"]] == [
        "FREQ", "TIME_PERIOD"]
    assert validate_sdmx_metadata("ecb", replace(value, body=body))["status"] == (
        "metadata_contract_validated")


def test_offline_revalidation_keeps_original_report_immutable_and_detects_tampering(
    tmp_path, monkeypatch,
):
    settings = Settings(tmp_path, network_enabled=True)
    path, original = HELPERS["run_checks"](settings, sources=["ecb"], fixture=True)
    before = path.read_bytes()
    monkeypatch.setattr("requests.sessions.Session.request", lambda *_a, **_k: pytest.fail("HTTP"))
    _, replay = HELPERS["revalidate_sdmx_archives"](settings, path)
    assert replay["new_http_requests"] == 0
    assert replay["results"][0]["status"] == "archived_metadata_validated"
    assert path.read_bytes() == before
    artifact = original["results"][0]["artifact"]
    (tmp_path / artifact["raw_path"]).write_bytes(b"tampered")
    _, replay = HELPERS["revalidate_sdmx_archives"](settings, path)
    assert replay["results"][0]["status"] == "archive_revalidation_failed"


def test_archived_http_200_error_is_not_promoted_by_revalidation(tmp_path, monkeypatch):
    settings = Settings(tmp_path, network_enabled=True)
    value = response("ecb", settings)
    monkeypatch.setitem(HELPERS["run_checks"].__globals__, "_fetch", lambda *_a:
                        replace(value, body=b"<html>Error</html>", content_type="text/html"))
    path, original = HELPERS["run_checks"](settings, sources=["ecb"], fixture=True)
    assert original["results"][0]["status"] == "source_metadata_needs_review"
    _, replay = HELPERS["revalidate_sdmx_archives"](settings, path)
    assert replay["results"][0]["status"] == "source_metadata_needs_review"


@pytest.mark.parametrize("source", ["bis", "oecd", "ecb", "eurostat", "bundesbank"])
def test_recorded_metadata_has_provenance_hash_and_passes_exact_source_contract(source, tmp_path):
    folder = ROOT / "tests" / "fixtures" / "sdmx_metadata"
    provenance = json.loads((folder / "recorded.provenance.json").read_text(encoding="utf-8"))
    record = next(row for row in provenance["sources"] if row["source"] == source)
    body = (folder / record["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == record["sha256"]
    value = replace(response(source, Settings(tmp_path, network_enabled=True)),
                    body=body, source_url=record["source_url"], content_type=record["content_type"])
    assert validate_sdmx_metadata(source, value)["status"] == "metadata_contract_validated"
    if source == "ecb":
        structures, _ = parse_sdmx_structure(body)
        assert len(structures["datastructures"][0]["dimensions"]) == 6
        assert record["initial_validation_status"] == "source_metadata_needs_review"
