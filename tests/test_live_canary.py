"""The live helper honors network opt-in before constructing a source collector."""
import json
import runpy
from pathlib import Path

import requests

from macro_data_platform.config import Settings

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
