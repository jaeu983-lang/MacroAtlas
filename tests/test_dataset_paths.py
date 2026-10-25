"""Source-specific dataset contracts, bounded official files and verifiable archives."""
import json
import runpy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import ConnectorFailure
from macro_data_platform.connectors.official_files import (
    OfficialFileTransport,
    validate_official_file_identity,
)
from macro_data_platform.discovery.datasets import (
    DatasetProfile,
    all_dataset_profiles,
    get_dataset_profile,
)
from macro_data_platform.discovery.source_registry import (
    AdapterStatus,
    FixtureScope,
    get_source_profile,
)
from macro_data_platform.ingestion.datasets import DatasetCollector
from macro_data_platform.storage.api_responses import read_api_response, save_api_response
from macro_data_platform.storage.datasets import read_dataset_artifact, save_dataset_receipt

HELPERS = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "verify_dataset_paths.py"))
CASES, fixture_collector = HELPERS["CASES"], HELPERS["fixture_collector"]
SECRET = "synthetic-credential-never-stored"


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("No external HTTP permitted in dataset tests")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


def settings(root, enabled=True):
    return Settings(root, network_enabled=enabled, fred_api_key=SECRET, census_api_key=SECRET,
                    bls_api_key=SECRET)


@pytest.mark.parametrize("profile_id", CASES)
def test_each_source_request_saved_and_pinned_read_back(tmp_path, profile_id):
    config = settings(tmp_path)
    collector, session = fixture_collector(config, profile_id)
    saved = collector.collect(profile_id, CASES[profile_id])
    receipt, body = read_dataset_artifact(config, saved)
    loaded = read_api_response(config, saved.raw)
    assert receipt["run_evidence"] == "synthetic_fixture"
    assert receipt["profile_sha256"] == get_dataset_profile(profile_id).fingerprint
    assert receipt["validation"]["status"] == "contract_validated"
    assert receipt["validation"]["observations_accepted"] is False
    assert receipt["validation"]["complete_dataset_assessed"] is False
    assert len(session.calls) == 1 and session.trust_env is False
    method, url, query = session.calls[0]
    assert query["timeout"] == (5, 20) and query["allow_redirects"] is False
    if profile_id.startswith("bls."):
        assert method == "POST" and "/v1/" in url
        assert SECRET not in str(query) and "registrationkey" not in str(query)
    if receipt["profile"]["access_method"] == "official_file":
        assert body == session.response.body
        assert loaded.manifest["api_provider"] is None
        assert loaded.manifest["etag"] == '"synthetic-revision"'
        assert saved.raw.raw_path.endswith(".csv")
    for relative in (saved.raw.raw_path, saved.raw.manifest_path, saved.receipt_path):
        assert SECRET not in (tmp_path / relative).read_text(encoding="utf-8")


def test_registry_is_immutable_versioned_and_explicit():
    profiles = all_dataset_profiles()
    assert len(profiles) == len({p.profile_id for p in profiles}) == 7
    profile = get_dataset_profile("tic.mfh.history")
    with pytest.raises(FrozenInstanceError):
        profile.version = 2
    assert replace(profile, version=2).fingerprint != profile.fingerprint
    mutable = [["file_id", "mfhhis01"]]
    clone = replace(profile, fixed_parameters=mutable)
    mutable[0][1] = "other"
    assert clone.fixed["file_id"] == "mfhhis01"
    clone.fixed["file_id"] = "other"
    assert clone.fixed == profile.fixed
    with pytest.raises(ValueError):
        replace(profile, fixed_parameters=(("api_key", "forbidden"),))
    with pytest.raises(ValueError):
        replace(profile, source_url="https://example.org/data?key=bad")
    assert isinstance(profile, DatasetProfile)


@pytest.mark.parametrize("profile_id", CASES)
def test_selection_cannot_be_overridden(tmp_path, profile_id):
    collector, session = fixture_collector(settings(tmp_path), profile_id)
    with pytest.raises(ValueError):
        collector.collect(profile_id, {**CASES[profile_id], "source_url": "https://example.com/"})
    assert session.calls == []


def test_unknown_profile_adapter_or_implicit_fixture_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        DatasetCollector(settings(tmp_path), fixture_mode=True)
    collector = DatasetCollector(settings(tmp_path), {})
    for name in ("unregistered.dataset", "fred.gdp"):
        with pytest.raises(ValueError):
            collector.collect(name, {})
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("profile_id", ["tic.mfh.history", "tic.treasury_holdings.2023_01", "boe.bank_rate"])
def test_changed_csv_is_preserved_but_not_accepted(tmp_path, profile_id):
    config = settings(tmp_path)
    collector, session = fixture_collector(config, profile_id, body=b"Unknown,Changed\n0,n.a.\n")
    saved = collector.collect(profile_id, CASES[profile_id])
    receipt, body = read_dataset_artifact(config, saved)
    assert body == session.response.body
    assert receipt["validation"] == {"status": "needs_review", "reason_code": "dataset_contract_changed",
                                      "observations_accepted": False}


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500])
def test_file_http_failures_never_fallback_or_write(tmp_path, status):
    collector, session = fixture_collector(settings(tmp_path), "tic.mfh.history", status=status)
    with pytest.raises(ConnectorFailure):
        collector.collect("tic.mfh.history", {})
    assert len(session.calls) == 1
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("error", [requests.exceptions.SSLError("hidden-detail"),
                                  requests.exceptions.Timeout("hidden-detail")])
def test_safe_file_transport_errors(tmp_path, error):
    collector, _ = fixture_collector(settings(tmp_path), "tic.mfh.history", error=error)
    with pytest.raises(ConnectorFailure) as caught:
        collector.collect("tic.mfh.history", {})
    assert "hidden-detail" not in str(caught.value)


@pytest.mark.parametrize("kwargs", [{"content_type": "text/html"},
                                   {"headers": {"Content-Length": str(8 * 1024 * 1024 + 1)}},
                                   {"body": b"x" * (8 * 1024 * 1024 + 1)}])
def test_file_media_and_size_limits(tmp_path, kwargs):
    collector, _ = fixture_collector(settings(tmp_path), "tic.mfh.history", **kwargs)
    with pytest.raises(ConnectorFailure):
        collector.collect("tic.mfh.history", {})
    assert not (tmp_path / "data").exists()


def test_network_off_and_unregistered_routes(tmp_path):
    collector, session = fixture_collector(settings(tmp_path, False), "tic.mfh.history")
    with pytest.raises(ConnectorFailure):
        collector.collect("tic.mfh.history", {})
    assert session.calls == []
    transport = OfficialFileTransport(settings(tmp_path))
    with pytest.raises(ValueError):
        transport.get("US-03", "unregistered")
    with pytest.raises(ValueError):
        validate_official_file_identity("US-03", "mfhhis01", "https://example.org/mfhhis01.csv")


@pytest.mark.parametrize("parameters", [{"start": "2024-01-01", "end": "2025-01-01"},
                                        {"start": "2025-02-01", "end": "2025-01-01"},
                                        {"start": "2025-02-30", "end": "2025-03-01"}])
def test_boe_range_limits_before_network(tmp_path, parameters):
    collector, session = fixture_collector(settings(tmp_path), "boe.bank_rate")
    with pytest.raises(ValueError):
        collector.collect("boe.bank_rate", parameters)
    assert session.calls == []


@pytest.mark.parametrize("body", [b"DATE,IUDBEDR\n02 Jan 25,1\n02 Jan 25,2\n",
                                  b"DATE,IUDBEDR\n31 Dec 24,1\n",
                                  b"DATE,OTHER\n02 Jan 25,1\n",
                                  b"DATE,IUDBEDR\n02 Jan 25,NaN\n"])
def test_boe_invalid_dates_headers_and_values_require_review(tmp_path, body):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "boe.bank_rate", body=body)
    saved = collector.collect("boe.bank_rate", CASES["boe.bank_rate"])
    assert read_dataset_artifact(config, saved)[0]["validation"]["status"] == "needs_review"


def test_source_specific_periods_missing_and_aggregates_stay_raw(tmp_path):
    config = settings(tmp_path)
    for name in ("tic.mfh.history", "tic.treasury_holdings.2023_01", "boe.bank_rate"):
        collector, _ = fixture_collector(config, name)
        receipt, body = read_dataset_artifact(config, collector.collect(name, CASES[name]))
        if name == "tic.mfh.history":
            assert receipt["validation"]["header_blocks"] == 2
            assert receipt["validation"]["data_row_count"] == 6
            assert b"Grand Total" in body and b"n.a." in body and b",0," in body
        elif name.startswith("tic."):
            assert receipt["validation"]["source_period"] == "2023-01"
            assert b"Memo:" in body and b"n.a." in body
        else:
            assert receipt["validation"]["data_row_count"] == 3
            assert b".." in body and b",0" in body


@pytest.mark.parametrize("target", ["receipt", "raw", "manifest"])
def test_archive_or_receipt_tampering_is_rejected(tmp_path, target):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history")
    saved = collector.collect("tic.mfh.history", {})
    relative = {"receipt": saved.receipt_path, "raw": saved.raw.raw_path,
                "manifest": saved.raw.manifest_path}[target]
    with (tmp_path / relative).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        read_dataset_artifact(config, saved)


def test_receipt_write_once_path_and_profile_checks(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history")
    saved = collector.collect("tic.mfh.history", {})
    receipt, _ = read_dataset_artifact(config, saved)
    with pytest.raises(FileExistsError):
        save_dataset_receipt(config, get_dataset_profile("tic.mfh.history"), saved.raw, receipt["validation"])
    for changed in (replace(saved, receipt_path="../outside.json"), replace(saved, profile_sha256="0" * 64),
                    replace(saved, profile_id="other"), replace(saved, validation_status="other")):
        with pytest.raises(ValueError):
            read_dataset_artifact(config, changed)
    with pytest.raises(ValueError):
        save_dataset_receipt(config, get_dataset_profile("boe.bank_rate"), saved.raw, receipt["validation"])


def test_wrong_response_provider_or_dataset_cannot_be_archived(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history")
    profile = get_dataset_profile("tic.mfh.history")
    response = collector.bindings[profile.adapter_id].fetch(profile, {})
    with pytest.raises(ValueError):
        save_api_response(config, response, expected_institution_id="EU-04")
    with pytest.raises(ValueError):
        save_api_response(config, response, dataset_id="slt3d")
    assert not (tmp_path / "data").exists()


def test_json_and_file_cannot_be_silently_interchanged(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history")
    profile = get_dataset_profile("tic.mfh.history")
    response = collector.bindings[profile.adapter_id].fetch(profile, {})
    class WrongBinding:
        def fetch(self, *_args):
            return response
    with pytest.raises(TypeError):
        DatasetCollector(config, {"fred_observations": WrongBinding()}).collect("fred.gdp", {})
    assert not (tmp_path / "data").exists()


def test_profile_snapshot_is_stored_without_reinterpreting_registry(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "bls.cpi")
    saved = collector.collect("bls.cpi", CASES["bls.cpi"])
    receipt, body = read_dataset_artifact(config, saved)
    assert receipt["profile"]["version"] == 1
    assert json.loads(body)["Results"]["series"][0]["data"][0]["period"] == "M13"


def test_file_registry_records_partial_fixture_not_live():
    for source_id in ("US-03", "EU-04"):
        source = get_source_profile(source_id)
        assert source.adapter_status == AdapterStatus.PARTIAL
        assert source.fixture_scope == FixtureScope.SOURCE_SPECIFIC
        assert source.to_dict()["api_availability"] == "unconfirmed"
        assert "no live ingestion" in source.status_note


def test_revision_headers_cannot_leak_known_credentials(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history", headers={"ETag": SECRET, "Last-Modified": SECRET})
    saved = collector.collect("tic.mfh.history", {})
    receipt, _ = read_dataset_artifact(config, saved)
    assert receipt["validation"]["status"] == "contract_validated"
    assert SECRET not in (tmp_path / saved.raw.manifest_path).read_text(encoding="utf-8")


def test_raw_credential_and_false_fixture_evidence_are_rejected(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "tic.mfh.history", body=SECRET.encode())
    with pytest.raises(ValueError):
        collector.collect("tic.mfh.history", {})
    collector, _ = fixture_collector(config, "tic.mfh.history")
    collector.fixture_mode = False
    with pytest.raises(ValueError):
        collector.collect("tic.mfh.history", {})
    assert not (tmp_path / "data").exists()


def test_boe_two_digit_leap_day_uses_requested_century(tmp_path):
    config = settings(tmp_path)
    collector, _ = fixture_collector(config, "boe.bank_rate", body=b"DATE,IUDBEDR\n29 Feb 00,0\n")
    saved = collector.collect("boe.bank_rate", {"start": "2000-02-28", "end": "2000-03-01"})
    assert read_dataset_artifact(config, saved)[0]["validation"]["status"] == "contract_validated"


def test_tic_replaced_snapshot_requires_review(tmp_path):
    config = settings(tmp_path)
    body = (HELPERS["FIXTURES"] / "tic_table3d.csv").read_bytes().replace(b"January 2023", b"January 2024")
    collector, _ = fixture_collector(config, "tic.treasury_holdings.2023_01", body=body)
    saved = collector.collect("tic.treasury_holdings.2023_01", {})
    assert read_dataset_artifact(config, saved)[0]["validation"]["status"] == "needs_review"
