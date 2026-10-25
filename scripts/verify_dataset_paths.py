"""Seven synthetic dataset requests through actual clients, archive and receipt read-back."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bls import BLSClient
from macro_data_platform.connectors.census import CensusClient
from macro_data_platform.connectors.dataset_bindings import (
    BLSV1Binding,
    BoECSVBinding,
    CensusTableBinding,
    FREDObservationBinding,
    TICCSVBinding,
)
from macro_data_platform.connectors.fred import FREDClient
from macro_data_platform.connectors.official_api import JsonApiTransport
from macro_data_platform.connectors.official_files import (
    BankOfEnglandFileClient,
    OfficialFileTransport,
    TICFileClient,
)
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.datasets import get_dataset_profile
from macro_data_platform.ingestion.datasets import DatasetCollector
from macro_data_platform.storage.datasets import read_dataset_artifact

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "rest_api"
CASES = {
    "fred.gdp": {"start": "2023-01-01", "end": "2023-12-31",
                 "realtime_start": "2024-01-01", "realtime_end": "2024-01-01"},
    "census.acs2023.population": {"predicates": {"for": "state:*"}},
    "bls.unemployment": {"start_year": 2023, "end_year": 2023},
    "bls.cpi": {"start_year": 2023, "end_year": 2023},
    "tic.mfh.history": {}, "tic.treasury_holdings.2023_01": {},
    "boe.bank_rate": {"start": "2025-01-01", "end": "2025-01-10"},
}


class FixtureResponse:
    def __init__(self, body, *, status=200, content_type="text/csv", headers=None):
        self.body = body
        self.status_code = status
        self.headers = {"Content-Type": content_type, "ETag": '"synthetic-revision"',
                        "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT", **(headers or {})}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        yield self.body


class FixtureSession:
    def __init__(self, response, error=None):
        self.response, self.error, self.calls = response, error, []
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def request(self, method, endpoint, **kwargs):
        self.calls.append((method, endpoint, kwargs))
        if self.error:
            raise self.error
        return self.response

    def get(self, endpoint, **kwargs):
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self.request("POST", endpoint, **kwargs)


def fixture_collector(settings, profile_id, *, body=None, status=200, content_type=None, error=None, headers=None):
    """Inject a synthetic transport; never consult the environment or real credentials."""
    profile = get_dataset_profile(profile_id)
    if profile.access_method == "official_file":
        filename = {"tic_mfh_blocks": "tic_mfh.csv", "tic_table3d": "tic_table3d.csv",
                    "boe_tn": "boe_bank_rate.csv"}[profile.validator_id]
        payload = (FIXTURES / filename).read_bytes() if body is None else body
        session = FixtureSession(FixtureResponse(payload, status=status, content_type=content_type or "text/csv",
                                                 headers=headers), error)
        transport = OfficialFileTransport(settings, lambda: session, evidence_kind=EvidenceKind.FIXTURE)
        binding = (TICCSVBinding(TICFileClient(settings, transport)) if profile.adapter_id == "tic_csv"
                   else BoECSVBinding(BankOfEnglandFileClient(settings, transport)))
    else:
        filename, section = {"fred_page": ("fred.json", "observations"),
                             "census_table": ("census.json", "data"), "bls_v1": ("bls_v1.json", None)}[profile.validator_id]
        payload = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        if section:
            payload = payload[section]
        if profile.validator_id == "bls_v1":
            payload["Results"]["series"] = [row for row in payload["Results"]["series"]
                                              if row["seriesID"] == profile.dataset_id]
        encoded = json.dumps(payload).encode() if body is None else body
        session = FixtureSession(FixtureResponse(encoded, status=status, content_type=content_type or "application/json",
                                                 headers=headers), error)
        transport = JsonApiTransport(settings, lambda: session)
        binding = {"fred_page": lambda: FREDObservationBinding(FREDClient(settings, transport)),
                   "census_table": lambda: CensusTableBinding(CensusClient(settings, transport)),
                   "bls_v1": lambda: BLSV1Binding(BLSClient(settings, transport))}[profile.validator_id]()
    return DatasetCollector(settings, {profile.adapter_id: binding}, fixture_mode=True), session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", required=True)
    parser.parse_args()
    settings = Settings(ROOT, network_enabled=True, fred_api_key="synthetic-fred-only",
                        census_api_key="synthetic-census-only", bls_api_key="synthetic-unused-bls")
    results = []
    with patch("requests.sessions.Session.request", side_effect=AssertionError("External HTTP is disabled")):
        for profile_id, parameters in CASES.items():
            collector, session = fixture_collector(settings, profile_id)
            saved = collector.collect(profile_id, parameters)
            receipt, raw = read_dataset_artifact(settings, saved)
            if receipt["validation"]["status"] != "contract_validated":
                raise RuntimeError("Synthetic dataset contract did not pass")
            results.append({"profile_id": profile_id, "access_method": receipt["profile"]["access_method"],
                            "validation": receipt["validation"], "artifact": asdict(saved),
                            "read_back_bytes": len(raw), "mock_requests": len(session.calls)})
    report = ROOT / "reports" / f"iteration_29_offline_{uuid4().hex}.json"
    report.write_text(json.dumps({"evidence": "synthetic_fixture", "live_requests": 0,
                                  "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report)
    print(f"{len(results)} dataset contracts saved and hash-verified; live requests: 0")


if __name__ == "__main__":
    main()
