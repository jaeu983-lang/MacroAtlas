"""The live helper honors network opt-in before constructing a source collector."""
import json
import runpy
from pathlib import Path

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
