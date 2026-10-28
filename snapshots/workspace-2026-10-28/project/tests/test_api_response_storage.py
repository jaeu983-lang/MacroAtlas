"""Offline client-to-file round trips for the currently implemented API sources."""
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bea import BEAClient
from macro_data_platform.connectors.estat import EStatClient
from macro_data_platform.connectors.official_api import JsonApiTransport
from macro_data_platform.connectors.sdmx import (
    BISClient,
    BundesbankClient,
    ECBClient,
    EurostatClient,
    INSEEClient,
    OECDClient,
    SdmxApiTransport,
)
from macro_data_platform.connectors.worldbank import Download, GDPQuery
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.storage.api_responses import read_api_response, save_api_response

_SECRET = "macroatlas-archive-test-secret"
_RETRIEVED = datetime(2026, 10, 25, 3, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self.status_code = 200
        self.headers = {"Content-Type": content_type}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        assert chunk_size == 8192
        yield self.body


class FakeSession:
    def __init__(self, body: bytes, content_type: str):
        self.response = FakeResponse(body, content_type)
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url, **_kwargs):
        return self.response


def _settings(root: Path) -> Settings:
    return Settings.from_env(root, {
        "MACROATLAS_NETWORK_ENABLED": "true",
        "BEA_API_KEY": _SECRET,
        "ESTAT_APP_ID": _SECRET,
    })


def _client_response(source: str, settings: Settings):
    if source == "World Bank":
        body = b'[{"page":1},{"indicator":{"id":"NY.GDP.MKTP.CD"}}]'
        return Download(
            GDPQuery().url, body, 200, _RETRIEVED, "application/json", EvidenceKind.FIXTURE,
        ), body, "http_entity_bytes_after_requests_content_decoding"
    if source in {"BEA", "e-Stat"}:
        body = json.dumps({
            "echo": _SECRET,
            "request": {"UserID": _SECRET, "appId": _SECRET},
            "value": 123,
        }).encode()
        session_factory = lambda: FakeSession(body, "application/json")
        transport = JsonApiTransport(settings, session_factory=session_factory)
        if source == "BEA":
            response = BEAClient(settings, transport).get_dataset_list()
        else:
            response = EStatClient(settings, transport).get_stats_data("TBL001", {"lang": "E"})
        return response, None, "sanitized_json_payload_canonical_utf8"

    body = b"<fixture>source-payload</fixture>"
    session_factory = lambda: FakeSession(body, "application/vnd.sdmx.data+xml;version=2.1")
    transport = SdmxApiTransport(settings, session_factory=session_factory)
    clients = {
        "BIS": (BISClient, lambda client: client.get_data(
            "dataflow", "BIS", "WS_TC", "2.0", "Q.ID.N.A.M.USD.A")),
        "OECD": (OECDClient, lambda client: client.get_data(
            "OECD.SDD.TPS,DF_TABLE1", "AUS+USA..", "OECD")),
        "ECB": (ECBClient, lambda client: client.get_data(
            "EXR", "M.NOK.EUR.SP00.A", {"startPeriod": "2020"})),
        "Eurostat": (EurostatClient, lambda client: client.get_data(
            "NAMA_10_GDP", parameters={"geo": "DE"})),
        "Deutsche Bundesbank": (BundesbankClient, lambda client: client.get_data(
            "BBEX3", "D.USD.EUR.BB.AC.000")),
        "INSEE": (INSEEClient, lambda client: client.get_data_by_idbanks(
            ["001565137"], {"startPeriod": "2020"})),
    }
    client_type, call = clients[source]
    response = call(client_type(settings, transport))
    return response, body, "http_entity_bytes_after_requests_content_decoding"


@pytest.mark.parametrize("source,institution_id", [
    ("World Bank", "INT-04"),
    ("BEA", "US-04"),
    ("e-Stat", "JP-03"),
    ("BIS", "INT-02"),
    ("OECD", "INT-03"),
    ("ECB", "EU-01"),
    ("Eurostat", "EU-02"),
    ("Deutsche Bundesbank", "EU-03"),
    ("INSEE", "EU-05"),
])
def test_each_current_api_response_is_saved_and_verified_from_file(tmp_path, source, institution_id):
    settings = _settings(tmp_path)
    response, expected_body, representation = _client_response(source, settings)

    saved = save_api_response(settings, response, dataset_id="fixture-dataset")
    loaded = read_api_response(settings, saved)

    assert saved.institution_id == institution_id
    assert loaded.manifest["institution_id"] == institution_id
    assert loaded.manifest["source_agency"] == source
    assert loaded.manifest["dataset_id"] == "fixture-dataset"
    assert loaded.manifest["http_status"] == 200
    assert loaded.manifest["representation_code"] == representation
    assert loaded.manifest["byte_count"] == len(loaded.body)
    assert loaded.manifest["raw_sha256"] == hashlib.sha256(loaded.body).hexdigest()
    assert (tmp_path / saved.raw_path).read_bytes() == loaded.body
    assert (tmp_path / saved.manifest_path).exists()
    if expected_body is not None:
        assert loaded.body == expected_body
    else:
        parsed = json.loads(loaded.body)
        assert parsed["echo"] == "[REDACTED]"
        assert "macroatlas-archive-test-secret" not in loaded.body.decode()
    assert _SECRET not in repr(saved)
    assert _SECRET.encode() not in loaded.body
    assert _SECRET not in (tmp_path / saved.manifest_path).read_text(encoding="utf-8")


def test_json_manifest_keeps_safe_parameters_but_never_credentials(tmp_path):
    settings = _settings(tmp_path)
    response, _, _ = _client_response("e-Stat", settings)

    loaded = read_api_response(settings, save_api_response(settings, response))

    assert {item["name"] for item in loaded.manifest["request_parameters"]} == {
        "statsDataId", "lang",
    }
    assert all(item["name"].casefold() not in {"appid", "userid"}
               for item in loaded.manifest["request_parameters"])
    assert loaded.manifest["mode"] == "api_response"


def test_api_artifacts_are_write_once_and_raw_tampering_is_detected(tmp_path):
    settings = _settings(tmp_path)
    response, _, _ = _client_response("BIS", settings)
    first = save_api_response(settings, response)
    second = save_api_response(settings, response)
    assert first.raw_path != second.raw_path

    (tmp_path / first.raw_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        read_api_response(settings, first)


def test_manifest_tampering_is_detected_from_saved_reference(tmp_path):
    settings = _settings(tmp_path)
    response, _, _ = _client_response("BIS", settings)
    saved = save_api_response(settings, response)
    manifest_path = tmp_path / saved.manifest_path
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest hash"):
        read_api_response(settings, saved)


def test_read_rejects_manifest_paths_outside_raw_archive(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(ValueError, match="raw archive"):
        read_api_response(settings, "README.md")


def test_only_registered_institution_and_official_host_are_archived(tmp_path):
    settings = _settings(tmp_path)
    response, _, _ = _client_response("BIS", settings)

    with pytest.raises(ValueError, match="official provider"):
        save_api_response(settings, replace(response, source_url="https://example.org/data"))


def test_url_query_secret_is_redacted_and_world_bank_error_body_is_marked_unaccepted(tmp_path):
    settings = _settings(tmp_path)
    response, _, _ = _client_response("BIS", settings)
    response = replace(
        response,
        source_url="https://stats.bis.org/api/v2/data/fixture?token=" + _SECRET,
    )
    saved = save_api_response(settings, response)
    loaded = read_api_response(settings, saved)
    assert _SECRET not in loaded.manifest["source_url"]

    failed_download, _, _ = _client_response("World Bank", settings)
    failed_download = replace(failed_download, status_code=503)
    failed = read_api_response(settings, save_api_response(settings, failed_download))
    assert failed.manifest["http_status"] == 503
    assert failed.manifest["response_accepted"] is False
    assert failed.body == failed_download.body
