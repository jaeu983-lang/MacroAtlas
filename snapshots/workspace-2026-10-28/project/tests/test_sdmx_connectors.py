"""Deterministic, mocked contracts for documented SDMX API clients."""
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import ConnectorFailure
from macro_data_platform.connectors.sdmx import (
    MAX_SDMX_RESPONSE_BYTES,
    BISClient,
    BundesbankClient,
    ECBClient,
    EurostatClient,
    IMFClient,
    INSEEClient,
    OECDClient,
    SdmxApiTransport,
)
from macro_data_platform.contracts import ErrorCode, StageStatus


class FakeResponse:
    def __init__(self, body=b"<message/>", status=200, headers=None):
        self.status_code = status
        self.headers = {"Content-Type": "application/vnd.sdmx.data+xml;version=2.1", **(headers or {})}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        assert chunk_size == 8192
        yield self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.trust_env = True
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def _make_client(client_type, response=None):
    settings = Settings.from_env(
        Path.cwd(), {"MACROATLAS_NETWORK_ENABLED": "true"},
    )
    session = FakeSession(response or FakeResponse())
    transport = SdmxApiTransport(settings, session_factory=lambda: session)
    return client_type(settings, transport), session


@pytest.mark.parametrize(("client_type", "call", "expected"), [
    (
        BISClient,
        lambda client: client.get_data("dataflow", "BIS", "WS_TC", "2.0",
                                       "Q.ID.N.A.M.USD.A"),
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_TC/2.0/Q.ID.N.A.M.USD.A",
    ),
    (
        OECDClient,
        lambda client: client.get_data("OECD.SDD.TPS,DF_TABLE1", "AUS+USA..", "OECD"),
        "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.TPS,DF_TABLE1/AUS+USA../OECD",
    ),
    (
        ECBClient,
        lambda client: client.get_data("EXR", "M.NOK.EUR.SP00.A", {"startPeriod": "2020"}),
        "https://data-api.ecb.europa.eu/service/data/EXR/M.NOK.EUR.SP00.A",
    ),
    (
        EurostatClient,
        lambda client: client.get_data("NAMA_10_GDP", parameters={"geo": "DE", "format": "TSV"}),
        "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NAMA_10_GDP",
    ),
    (
        BundesbankClient,
        lambda client: client.get_data("BBEX3", "D.USD.EUR.BB.AC.000"),
        "https://api.statistiken.bundesbank.de/rest/data/BBEX3/D.USD.EUR.BB.AC.000",
    ),
    (
        INSEEClient,
        lambda client: client.get_data_by_idbanks(["001565137", "001585934"],
                                                  {"startPeriod": "2020"}),
        "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/001565137+001585934",
    ),
])
def test_documented_sdmx_data_routes_are_provider_specific_and_raw(
    client_type, call, expected,
):
    client, session = _make_client(client_type, FakeResponse(b"<source-payload/>"))

    result = call(client)

    url, request = session.calls[0]
    assert url == expected
    assert request["allow_redirects"] is False
    assert request["timeout"] == (5, 20)
    assert request["stream"] is True
    assert request["headers"]["Accept-Encoding"] == "identity"
    assert session.trust_env is False
    assert result.source_url.startswith(expected)
    assert result.body == b"<source-payload/>"
    assert result.content_type.startswith("application/vnd.sdmx.data+xml")
    assert result.http_status == 200


def test_structure_routes_preserve_each_provider_contract():
    bis, bis_session = _make_client(BISClient)
    oecd, oecd_session = _make_client(OECDClient)
    eurostat, eurostat_session = _make_client(EurostatClient)
    bundesbank, bundesbank_session = _make_client(BundesbankClient)

    bis.get_structure("dataflow", "BIS", "WS_TC", "2.0")
    oecd.get_structure("datastructure", "OECD.SDD.TPS", "DSD_NAMAIN10", "1.0")
    eurostat.get_dataflow("NAMA_10_GDP")
    bundesbank.get_datastructure("BBEX3")

    assert bis_session.calls[0][0] == "https://stats.bis.org/api/v2/structure/dataflow/BIS/WS_TC/2.0"
    assert oecd_session.calls[0][0] == "https://sdmx.oecd.org/public/rest/v1/datastructure/OECD.SDD.TPS/DSD_NAMAIN10/1.0"
    assert eurostat_session.calls[0][0] == "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/NAMA_10_GDP/latest"
    assert bundesbank_session.calls[0][0] == "https://api.statistiken.bundesbank.de/rest/metadata/datastructure/BBK/BBEX3"


def test_eurostat_lists_dataflows_using_documented_all_route():
    client, session = _make_client(EurostatClient)

    client.get_dataflows()

    assert session.calls[0][0] == "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/all"


def test_eurostat_rejects_unfiltered_full_dataset_requests():
    client, session = _make_client(EurostatClient)

    with pytest.raises(ValueError, match="explicit filter"):
        client.get_data("NAMA_10_GDP")

    assert session.calls == []


@pytest.mark.parametrize("bad_value", ["../other", "a/b", "?x=1", "with space", ""])
def test_path_segments_reject_unbounded_or_structural_values(bad_value):
    client, session = _make_client(ECBClient)

    with pytest.raises(ValueError, match="path segment"):
        client.get_data("EXR", bad_value)

    assert session.calls == []


def test_insee_idbank_request_is_bounded_and_numeric():
    client, session = _make_client(INSEEClient)

    with pytest.raises(ValueError, match="numeric IDBANK"):
        client.get_data_by_idbanks(["00123", "not-an-id"])
    with pytest.raises(ValueError, match="1 to 100"):
        client.get_data_by_idbanks(["00123"] * 101)

    assert session.calls == []


def test_imf_public_metadata_route_negotiates_structure_without_authentication():
    client, session = _make_client(IMFClient)
    result = client.get_dataflow("IMF.STA", "CPI")
    url, options = session.calls[0]
    assert url == "https://api.imf.org/external/sdmx/2.1/dataflow/IMF.STA/CPI/latest"
    assert result.institution_id == "INT-01" and result.operation == "dataflow"
    assert options["headers"]["Accept"] == "application/vnd.sdmx.structure+xml;version=2.1"
    assert "Authorization" not in options["headers"]
    assert options.get("params", {}) == {}
    assert options["allow_redirects"] is False
    assert not hasattr(client, "get_data")


def test_transport_rejects_unreviewed_hosts_and_credential_parameters():
    client, session = _make_client(ECBClient)

    with pytest.raises(ConnectorFailure) as bad_host:
        client.transport.get("EU-01", "https://example.com/service/data/EXR/A", "data")
    with pytest.raises(ValueError, match="credential parameters"):
        client.get_data("EXR", "M.NOK.EUR.SP00.A", {"api_key": "must-not-be-sent"})

    assert bad_host.value.code == ErrorCode.LICENSE_SECURITY
    assert session.calls == []


def test_transport_rejects_dot_segments_even_on_an_allowed_provider_host():
    client, session = _make_client(ECBClient)

    with pytest.raises(ConnectorFailure) as error:
        client.transport.get(
            "EU-01", "https://data-api.ecb.europa.eu/service/data/../other", "data",
        )

    assert error.value.code == ErrorCode.LICENSE_SECURITY
    assert session.calls == []


def test_network_access_is_off_by_default_for_sdmx_transport():
    settings = Settings.from_env(Path.cwd(), {})
    transport = SdmxApiTransport(settings, session_factory=lambda: pytest.fail("transport ran"))

    with pytest.raises(ConnectorFailure) as error:
        transport.get("EU-01", "https://data-api.ecb.europa.eu/service/data/EXR/A", "data")

    assert error.value.code == ErrorCode.LICENSE_SECURITY
    assert error.value.status == StageStatus.NEEDS_REVIEW


@pytest.mark.parametrize(("status", "expected_status", "expected_code"), [
    (302, StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY),
    (401, StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS),
    (429, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (503, StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT),
    (404, StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED),
])
def test_http_failures_are_classified_without_following_redirects(
    status, expected_status, expected_code,
):
    client, session = _make_client(ECBClient, FakeResponse(b"", status=status))

    with pytest.raises(ConnectorFailure) as error:
        client.get_data("EXR", "M.NOK.EUR.SP00.A")

    assert error.value.status == expected_status
    assert error.value.code == expected_code
    assert session.calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize("oversize_by_header", [True, False])
def test_response_limit_refuses_partial_sdmx_payload(oversize_by_header):
    if oversize_by_header:
        response = FakeResponse(b"<x/>", headers={"Content-Length": str(MAX_SDMX_RESPONSE_BYTES + 1)})
    else:
        response = FakeResponse(b"x" * (MAX_SDMX_RESPONSE_BYTES + 1))
    client, _ = _make_client(ECBClient, response)

    with pytest.raises(ConnectorFailure) as error:
        client.get_data("EXR", "M.NOK.EUR.SP00.A")

    assert error.value.code == ErrorCode.SCHEMA_CHANGED
    assert "partial data were refused" in str(error.value)
