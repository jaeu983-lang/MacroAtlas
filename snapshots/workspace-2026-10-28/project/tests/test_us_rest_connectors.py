"""Synthetic HTTP-to-file contracts; no credentials or external network are used."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bls import BLSClient
from macro_data_platform.connectors.census import CensusClient
from macro_data_platform.connectors.fred import FREDClient
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    ConnectorFailureReason,
    JsonApiTransport,
)
from macro_data_platform.contracts import ErrorCode
from macro_data_platform.storage.api_responses import read_api_response, save_api_response

FIXTURES = Path(__file__).parent / "fixtures" / "rest_api"
SECRET = "synthetic-test-only-fred-census-secret"
BLS_SECRET = "synthetic-test-only-unused-bls-secret"


def fixture(name, section=None):
    value = json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))
    return value if section is None else value[section]


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.status_code = status
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = {"Content-Type": "application/json", **(headers or {})}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        assert chunk_size == 8192
        yield self.body


class FakeSession:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.trust_env = True
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def _request(self, verb, endpoint, **kwargs):
        self.calls.append((verb, endpoint, kwargs))
        if self.error:
            raise self.error
        return self.response

    def get(self, endpoint, **kwargs):
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self._request("POST", endpoint, **kwargs)


def make(tmp_path, source, payload=None, *, status=200, enabled=True, error=None, headers=None):
    settings = Settings(tmp_path, network_enabled=enabled, fred_api_key=SECRET,
                        census_api_key=SECRET, bls_api_key=BLS_SECRET)
    session = FakeSession(FakeResponse(payload, status, headers), error)
    transport = JsonApiTransport(settings, session_factory=lambda: session)
    client = {"FRED": FREDClient, "Census": CensusClient, "BLS": BLSClient}[source](settings, transport)
    return settings, client, session


def data_call(source, client):
    if source == "FRED":
        return client.get_observations_page("GDP", "2023-01-01", "2023-12-31",
                                            realtime_start="2024-01-01", realtime_end="2024-01-01")
    if source == "Census":
        return client.get_data("2023/acs/acs5", ["NAME", "B01001_001E"], {"for": "state:*"})
    return client.get_data(["LNS14000000", "CUUR0000SA0"], 2023, 2023)


@pytest.mark.parametrize("source,fixture_name,section,institution_id", [
    ("FRED", "fred", "observations", "US-02"),
    ("Census", "census", "data", "US-06"),
    ("BLS", "bls_v1", None, "US-05"),
])
def test_each_client_preserves_values_and_saves_verified_files(
    tmp_path, source, fixture_name, section, institution_id,
):
    payload = fixture(fixture_name, section)
    settings, client, session = make(tmp_path, source, payload)
    response = data_call(source, client)
    saved = save_api_response(settings, response, dataset_id="synthetic-fixture")
    loaded = read_api_response(settings, saved)
    assert json.loads(loaded.body) == payload
    assert loaded.manifest["institution_id"] == institution_id
    assert loaded.manifest["source_agency"] == source
    assert loaded.manifest["http_method"] == ("POST" if source == "BLS" else "GET")
    assert loaded.manifest["representation_code"] == "sanitized_json_payload_canonical_utf8"
    assert str(institution_id) in saved.raw_path
    request_metadata = {row["name"]: row["value"] for row in loaded.manifest["request_parameters"]}
    assert not {"api_key", "key", "registrationkey"} & request_metadata.keys()
    for relative in (saved.raw_path, saved.manifest_path):
        stored = (tmp_path / relative).read_text(encoding="utf-8")
        assert SECRET not in stored and BLS_SECRET not in stored
    assert session.trust_env is False
    assert len(session.calls) == 1
    verb, endpoint, request = session.calls[0]
    assert request["allow_redirects"] is False and request["stream"] is True
    assert request["timeout"] == (5, 20) and request.get("verify", True) is True
    if source == "BLS":
        assert verb == "POST" and "/v1/" in endpoint and "/v2/" not in endpoint
        body = json.loads(request["data"])
        assert set(body) == {"seriesid", "startyear", "endyear"}
        assert BLS_SECRET not in str(request) and "registrationkey" not in str(request).lower()
        assert request["headers"]["Content-Type"] == "application/json"
    else:
        assert request["params"]["api_key" if source == "FRED" else "key"] == SECRET
    if source == "FRED":
        assert loaded.manifest["original_source_agency"] is None
        assert "St. Louis" in loaded.manifest["api_provider"]
        assert request_metadata["realtime_start"] == "2024-01-01"
    (tmp_path / saved.raw_path).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        read_api_response(settings, saved)


@pytest.mark.parametrize("section,method,args,route", [
    ("series", "get_series", ("GDP",), "/fred/series"),
    ("search", "search_series_page", ("GDP",), "/fred/series/search"),
    ("release", "get_series_release", ("GDP",), "/fred/series/release"),
    ("sources", "get_release_sources", (53,), "/fred/release/sources"),
])
def test_fred_discovery_and_original_source_metadata_are_archivable(tmp_path, section, method, args, route):
    payload = fixture("fred", section)
    settings, client, session = make(tmp_path, "FRED", payload)
    response = getattr(client, method)(*args)
    assert session.calls[0][1] == "https://api.stlouisfed.org" + route
    assert json.loads(read_api_response(settings, save_api_response(settings, response)).body) == payload


def test_fred_pages_are_explicit_and_never_automatically_combined(tmp_path):
    payload = fixture("fred", "observations")
    payload.update(count=4, limit=1, offset=1)
    payload["observations"] = payload["observations"][1:2]
    _, client, session = make(tmp_path, "FRED", payload)
    response = client.get_observations_page("GDP", "2023-01-01", "2023-12-31", limit=1, offset=1)
    assert response.payload["count"] == 4 and response.payload["observations"][0]["value"] == "."
    assert len(session.calls) == 1
    assert session.calls[0][2]["params"]["offset"] == "1"
    assert not {"frequency", "units", "aggregation_method"} & session.calls[0][2]["params"].keys()


@pytest.mark.parametrize("section,method,args,suffix", [
    ("catalogue", "list_datasets", (), "/data.json"),
    ("variables", "get_variables", ("2023/acs/acs5",), "/data/2023/acs/acs5/variables.json"),
    ("geographies", "get_geographies", ("2023/acs/acs5",), "/data/2023/acs/acs5/geography.json"),
])
def test_census_metadata_is_keyless_and_saved(tmp_path, section, method, args, suffix):
    payload = fixture("census", section)
    settings, client, session = make(tmp_path, "Census", payload)
    response = getattr(client, method)(*args)
    assert session.calls[0][1] == "https://api.census.gov" + suffix
    assert session.calls[0][2]["params"] == {}
    assert json.loads(read_api_response(settings, save_api_response(settings, response)).body) == payload


def test_census_supports_non_geographic_timeseries_dataset_predicates(tmp_path):
    _, client, session = make(tmp_path, "Census", fixture("census", "trade"))
    response = client.get_data("timeseries/intltrade/exports/enduse", ["E_COMMODITY", "ALL_VAL_MO"],
                               {"time": "2023-01", "E_COMMODITY": "00"})
    assert response.payload[1][0] == "00"
    assert "/timeseries/intltrade/exports/enduse" in session.calls[0][1]


def test_bls_preserves_the_alternative_documented_results_list(tmp_path):
    payload = fixture("bls_v1")
    payload["Results"] = [payload["Results"]]
    settings, client, _ = make(tmp_path, "BLS", payload)
    result = data_call("BLS", client)
    assert json.loads(read_api_response(settings, save_api_response(settings, result)).body) == payload


@pytest.mark.parametrize("source", ["FRED", "Census", "BLS"])
@pytest.mark.parametrize("status,code", [(401, ErrorCode.AUTH_ACCESS), (429, ErrorCode.TRANSIENT),
                                        (302, ErrorCode.LICENSE_SECURITY)])
def test_each_source_stops_on_http_failure_without_files_or_retries(tmp_path, source, status, code):
    _, client, session = make(tmp_path, source, b"private error details", status=status)
    with pytest.raises(ConnectorFailure) as error:
        data_call(source, client)
    assert error.value.code == code
    assert "private error details" not in str(error.value)
    assert len(session.calls) == 1 and not (tmp_path / "data").exists()


@pytest.mark.parametrize("source", ["FRED", "Census", "BLS"])
def test_source_network_opt_in_is_required(tmp_path, source):
    _, client, session = make(tmp_path, source, {}, enabled=False)
    with pytest.raises(ConnectorFailure) as error:
        data_call(source, client)
    assert error.value.code == ErrorCode.LICENSE_SECURITY and not session.calls


@pytest.mark.parametrize("source", ["FRED", "Census"])
def test_required_credentials_are_checked_without_network(tmp_path, source):
    settings = Settings(tmp_path, network_enabled=True)
    session = FakeSession(FakeResponse({}))
    client = {"FRED": FREDClient, "Census": CensusClient}[source](
        settings, JsonApiTransport(settings, session_factory=lambda: session))
    with pytest.raises(ConnectorFailure) as error:
        data_call(source, client)
    assert error.value.code == ErrorCode.AUTH_ACCESS and not session.calls
    if source == "Census":
        assert error.value.reason == ConnectorFailureReason.MISSING_API_KEY


@pytest.mark.parametrize("target,reason", [
    ("https://api.census.gov/data/invalid_key.html?key=" + SECRET, "invalid_api_key"),
    ("/data/invalid_key.html", "invalid_api_key"),
    ("https://api.census.gov/data/missing_key.html", "missing_api_key"),
])
def test_census_official_key_redirect_is_auth_failure_without_following_or_leaking(
    tmp_path, target, reason,
):
    _, client, session = make(tmp_path, "Census", b"must remain unread", status=302,
                              headers={"Location": target})
    session.response.iter_content = lambda **_kwargs: pytest.fail("redirect body was read")
    with pytest.raises(ConnectorFailure) as error:
        data_call("Census", client)
    assert error.value.reason.value == reason
    assert error.value.code == ErrorCode.AUTH_ACCESS
    assert error.value.http_status == 302
    assert len(session.calls) == 1
    assert session.calls[0][2]["allow_redirects"] is False
    assert SECRET not in str(error.value) and target not in str(error.value)
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("target", [
    "https://api.census.gov.evil.example/data/invalid_key.html",
    "https://api.census.gov@evil.example/data/invalid_key.html",
    "https://user@api.census.gov/data/invalid_key.html",
    "http://api.census.gov/data/invalid_key.html",
    "https://api.census.gov:443/data/invalid_key.html",
    "https://api.census.gov/data/invalid_key.html#fragment",
    "https://api.census.gov/data/unknown.html",
    "https://[invalid", "\n/data/invalid_key.html", "x" * 8193, None,
])
def test_unrecognized_census_redirect_stays_refused(tmp_path, target):
    _, client, session = make(tmp_path, "Census", {}, status=302, headers={"Location": target})
    with pytest.raises(ConnectorFailure) as error:
        data_call("Census", client)
    assert error.value.reason == ConnectorFailureReason.REDIRECT_REFUSED
    assert error.value.code == ErrorCode.LICENSE_SECURITY
    assert len(session.calls) == 1


def test_census_keyless_metadata_redirect_does_not_claim_supplied_key_invalid(tmp_path):
    _, client, session = make(tmp_path, "Census", {}, status=302,
                              headers={"Location": "/data/invalid_key.html"})
    with pytest.raises(ConnectorFailure) as error:
        client.list_datasets()
    assert error.value.reason == ConnectorFailureReason.REDIRECT_REFUSED
    assert len(session.calls) == 1


def test_bls_html_503_is_reported_safely_without_retry_or_api_fallback(tmp_path):
    _, client, session = make(tmp_path, "BLS", b"private error details " + SECRET.encode(),
                              status=503, headers={"Content-Type": "text/html; charset=utf-8"})
    session.response.iter_content = lambda **_kwargs: pytest.fail("503 body was read")
    with pytest.raises(ConnectorFailure) as error:
        data_call("BLS", client)
    assert error.value.reason == ConnectorFailureReason.HTTP_TRANSIENT_STATUS
    assert error.value.response_kind == "html"
    assert error.value.http_status == 503
    assert SECRET not in str(error.value)
    assert len(session.calls) == 1
    assert session.calls[0][1] == "https://api.bls.gov/publicAPI/v1/timeseries/data/"
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("source", ["FRED", "Census", "BLS"])
@pytest.mark.parametrize("failure", [requests.Timeout(SECRET), requests.exceptions.SSLError(SECRET)])
def test_each_source_transport_failures_hide_details_and_leave_no_artifact(tmp_path, source, failure):
    _, client, session = make(tmp_path, source, {}, error=failure)
    with pytest.raises(ConnectorFailure) as error:
        data_call(source, client)
    assert SECRET not in str(error.value) and len(session.calls) == 1
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("args", [([], 2023, 2023), (["A"] * 26, 2023, 2023),
                                  (["A", "A"], 2023, 2023), (["lowercase"], 2023, 2023),
                                  (["../v2"], 2023, 2023), (["A"], 2000, 2010),
                                  (["A"], 2024, 2023), (["A"], True, 2023)])
def test_bls_v1_rejects_inputs_exceeding_its_own_limits(tmp_path, args):
    _, client, session = make(tmp_path, "BLS", {})
    with pytest.raises(ValueError):
        client.get_data(*args)
    assert not session.calls


@pytest.mark.parametrize("mode", ["warning", "failed", "partial", "duplicate", "wrong_year", "empty"])
def test_bls_http_200_does_not_hide_api_errors_or_partial_selections(tmp_path, mode):
    payload = fixture("bls_v1")
    if mode == "warning":
        payload["message"] = ["synthetic warning"]
    elif mode == "failed":
        payload["status"] = "REQUEST_FAILED"
    elif mode == "partial":
        payload["Results"]["series"].pop()
    elif mode == "duplicate":
        payload["Results"]["series"][1] = deepcopy(payload["Results"]["series"][0])
    elif mode == "wrong_year":
        payload["Results"]["series"][0]["data"][0]["year"] = "2022"
    else:
        payload["Results"]["series"][0]["data"] = []
    _, client, _ = make(tmp_path, "BLS", payload)
    with pytest.raises(ConnectorFailure):
        data_call("BLS", client)


@pytest.mark.parametrize("dataset,variables,predicates", [
    ("../private", ["NAME"], {"for": "state:*"}),
    ("https://example.com", ["NAME"], {"for": "state:*"}),
    ("2023/acs/acs5?key=oops", ["NAME"], {"for": "state:*"}),
    ("2023/acs/acs5", ["NAME"], {"KEY": "override"}),
    ("2023/acs/acs5", ["NAME"], {"get": "override"}),
    ("2023/acs/acs5", ["NAME"], {}),
    ("2023/acs/acs5", ["NAME"] * 51, {"for": "state:*"}),
])
def test_census_rejects_route_injection_and_reserved_fields(tmp_path, dataset, variables, predicates):
    _, client, session = make(tmp_path, "Census", {})
    with pytest.raises(ValueError):
        client.get_data(dataset, variables, predicates)
    assert not session.calls


@pytest.mark.parametrize("mode", ["error", "ragged", "missing_column", "numeric_cell"])
def test_census_changed_table_contract_is_not_accepted(tmp_path, mode):
    payload = fixture("census", "data")
    if mode == "error":
        payload = {"error": "synthetic error"}
    elif mode == "ragged":
        payload[1].pop()
    elif mode == "missing_column":
        payload[0][1] = "OTHER"
    else:
        payload[1][1] = 0
    _, client, _ = make(tmp_path, "Census", payload)
    with pytest.raises(ConnectorFailure):
        data_call("Census", client)


@pytest.mark.parametrize("mode", ["error", "wrong_page", "truncated", "wrong_date", "wrong_vintage"])
def test_fred_response_identity_and_page_integrity_are_checked(tmp_path, mode):
    payload = fixture("fred", "observations")
    if mode == "error":
        payload = {"error_code": 400, "error_message": SECRET}
    elif mode == "wrong_page":
        payload["offset"] = 1
    elif mode == "truncated":
        payload["observations"].pop()
    elif mode == "wrong_vintage":
        payload["realtime_start"] = "2025-01-01"
    else:
        payload["observations"][0]["date"] = "2022-01-01"
    _, client, _ = make(tmp_path, "FRED", payload)
    with pytest.raises(ConnectorFailure) as error:
        data_call("FRED", client)
    assert SECRET not in str(error.value)


def test_new_secrets_are_redacted_in_response_and_archive(tmp_path):
    payload = fixture("fred", "series")
    payload["echo"] = {"api_key": SECRET, "note": SECRET}
    settings, client, _ = make(tmp_path, "FRED", payload)
    response = client.get_series("GDP")
    assert SECRET not in str(response)
    saved = save_api_response(settings, response)
    assert SECRET not in str(read_api_response(settings, saved))


def test_bls_v2_route_and_registration_fields_are_blocked_even_in_json_transport(tmp_path):
    settings = Settings(tmp_path, network_enabled=True)
    session = FakeSession(FakeResponse({}))
    transport = JsonApiTransport(settings, session_factory=lambda: session)
    with pytest.raises(ConnectorFailure):
        transport.post_json("BLS", "https://api.bls.gov/publicAPI/v2/timeseries/data/", "data",
                            {"seriesid": ["A"], "startyear": "2023", "endyear": "2023"})
    with pytest.raises(ValueError):
        transport.post_json("BLS", "https://api.bls.gov/publicAPI/v1/timeseries/data/", "data",
                            {"seriesid": ["A"], "registrationkey": BLS_SECRET})
    assert not session.calls


@pytest.mark.parametrize("call", [
    lambda client: client.get_series("../private"),
    lambda client: client.search_series_page("GDP", limit=1001),
    lambda client: client.get_observations_page("GDP", "2023-02-30", "2023-12-31"),
    lambda client: client.get_observations_page("GDP", "2024-01-01", "2023-01-01"),
    lambda client: client.get_observations_page("GDP", "2023-01-01", "2023-12-31",
                                               realtime_start="2024-01-01"),
])
def test_fred_bad_inputs_do_not_start_requests(tmp_path, call):
    _, client, session = make(tmp_path, "FRED", {})
    with pytest.raises(ValueError):
        call(client)
    assert not session.calls


def test_census_accidental_credential_in_dataset_path_is_not_echoed_or_saved(tmp_path):
    settings, client, _ = make(tmp_path, "Census", fixture("census", "data"))
    response = client.get_data(SECRET, ["NAME", "B01001_001E"], {"for": "state:*"})
    assert SECRET not in str(response)
    artifact = save_api_response(settings, response)
    assert SECRET not in str(read_api_response(settings, artifact))
