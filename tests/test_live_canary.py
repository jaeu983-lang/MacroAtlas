"""The live helper honors network opt-in before constructing a source collector."""
import json
import runpy
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import ConnectorFailure, ConnectorFailureReason
from macro_data_platform.contracts import ErrorCode, StageStatus

HELPERS = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "verify_dataset_paths.py"))


def test_network_off_records_all_seven_as_not_run_without_http(tmp_path, monkeypatch, capsys):
    settings = Settings(tmp_path, network_enabled=False, fred_api_key="test-secret-fred",
                        census_api_key="test-secret-census")
    (tmp_path / "reports").mkdir()

    def blocked(*_args, **_kwargs):
        raise AssertionError("Network-off preflight must not issue a request")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    HELPERS["run_live"](root=tmp_path, settings=settings)
    report_path = Path(capsys.readouterr().out.splitlines()[0])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "not_run_network_disabled"
    assert len(report["results"]) == 7
    assert {row["status"] for row in report["results"]} == {"not_run_network_disabled"}
    assert "test-secret" not in report_path.read_text(encoding="utf-8")
    assert not (tmp_path / "data").exists()
    assert report["gate_u_assessment"] == "not_passed"


def test_live_failure_report_records_safe_reason_and_http_status_only(tmp_path, monkeypatch, capsys):
    import macro_data_platform.ingestion.datasets as dataset_module

    class FailingCollector:
        def __init__(self, _settings):
            pass

        def collect(self, _profile_id, _parameters):
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                "Safe fixed message containing no request or response details.",
                reason=ConnectorFailureReason.TLS_VERIFICATION_FAILED,
            )

    monkeypatch.setattr(dataset_module, "DatasetCollector", FailingCollector)
    (tmp_path / "reports").mkdir()
    settings = Settings(tmp_path, network_enabled=True, fred_api_key="test-secret-fred",
                        census_api_key="test-secret-census")

    HELPERS["run_live"](root=tmp_path, settings=settings)

    report_path = Path(capsys.readouterr().out.splitlines()[0])
    report_text = report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert len(report["results"]) == 7
    assert {row["failure_reason"] for row in report["results"]} == {"tls_verification_failed"}
    assert {row["failure_http_status"] for row in report["results"]} == {None}
    assert "Safe fixed message" not in report_text
    assert "test-secret" not in report_text
    assert report["gate_u_assessment"] == "not_passed"


@pytest.mark.parametrize("profiles", [[], ["unknown"], ["bls.cpi", "bls.cpi"], [None], "bls.cpi"])
def test_invalid_live_selection_fails_before_network_or_output(tmp_path, profiles, monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "request",
                        lambda *_a, **_kw: pytest.fail("HTTP must not start"))
    with pytest.raises(ValueError):
        HELPERS["run_live"](root=tmp_path, settings=Settings(tmp_path), profile_ids=profiles)
    assert not (tmp_path / "reports").exists()
    assert not (tmp_path / "data").exists()


def test_selected_census_failure_report_omits_raw_redirect_and_credentials(tmp_path, monkeypatch, capsys):
    import macro_data_platform.ingestion.datasets as dataset_module

    calls = []

    class FailingCollector:
        def __init__(self, _settings):
            pass

        def collect(self, profile_id, _parameters):
            calls.append(profile_id)
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS, "private message",
                reason=ConnectorFailureReason.INVALID_API_KEY, http_status=302, response_kind="html",
            )

    monkeypatch.setattr(dataset_module, "DatasetCollector", FailingCollector)
    (tmp_path / "reports").mkdir()
    HELPERS["run_live"](root=tmp_path,
                        settings=Settings(tmp_path, network_enabled=True, census_api_key="test-secret"),
                        profile_ids=["census.acs2023.population"])
    path = Path(capsys.readouterr().out.splitlines()[0])
    text = path.read_text(encoding="utf-8")
    report = json.loads(text)
    assert calls == ["census.acs2023.population"]
    assert report["gate_u_assessment"] == "not_assessed_partial_scope"
    assert report["request_budget"]["planned_maximum"] == 1
    assert report["request_budget"]["bls_v1_maximum"] == 0
    assert report["results"][0]["failure_reason"] == "invalid_api_key"
    assert report["results"][0]["failure_response_kind"] == "html"
    assert "private message" not in text and "test-secret" not in text


@pytest.mark.parametrize("profiles,gate,maximum,bls_maximum", [
    (["bls.cpi"], "not_assessed_partial_scope", 1, 1),
    (None, "passed", 7, 2),
])
def test_gate_requires_complete_scope_even_when_selected_results_all_succeed(
    tmp_path, monkeypatch, capsys, profiles, gate, maximum, bls_maximum,
):
    from types import SimpleNamespace

    import macro_data_platform.ingestion.datasets as dataset_module
    import macro_data_platform.storage.datasets as storage_module

    calls = []
    saved = SimpleNamespace(raw=SimpleNamespace(raw_path="synthetic", raw_sha256="synthetic"))

    class SuccessfulCollector:
        def __init__(self, _settings):
            pass

        def collect(self, profile_id, _parameters):
            calls.append(profile_id)
            return saved

    monkeypatch.setattr(dataset_module, "DatasetCollector", SuccessfulCollector)
    monkeypatch.setattr(storage_module, "read_dataset_artifact", lambda *_args: (
        {"validation": {"status": "contract_validated"}, "raw": {}}, b"{}"))
    monkeypatch.setitem(HELPERS["run_live"].__globals__, "read_api_response",
                        lambda *_args: SimpleNamespace(manifest={"http_status": 200}))
    (tmp_path / "reports").mkdir()
    HELPERS["run_live"](root=tmp_path,
                        settings=Settings(tmp_path, network_enabled=True,
                                          fred_api_key="test-fred", census_api_key="test-census"),
                        profile_ids=profiles)
    path = Path(capsys.readouterr().out.splitlines()[0])
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["gate_u_assessment"] == gate
    assert len(calls) == maximum
    assert report["request_budget"]["planned_maximum"] == maximum
    assert report["request_budget"]["bls_v1_maximum"] == bls_maximum
