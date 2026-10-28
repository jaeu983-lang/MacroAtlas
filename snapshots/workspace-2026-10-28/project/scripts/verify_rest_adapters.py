"""Write and read three synthetic API artifacts, with real HTTP explicitly blocked."""
import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bls import BLSClient
from macro_data_platform.connectors.census import CensusClient
from macro_data_platform.connectors.fred import FREDClient
from macro_data_platform.connectors.official_api import JsonApiTransport
from macro_data_platform.storage.api_responses import read_api_response, save_api_response

_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "rest_api"
_DUMMY = "fixture-only-never-a-real-credential"


def run_fixture_verification(root: Path) -> dict:
    """Explicit synthetic settings only: never load the project's .env or process keys."""
    settings = Settings(root, network_enabled=True, fred_api_key=_DUMMY, census_api_key=_DUMMY)
    fred = json.loads((_FIXTURES / "fred.json").read_text(encoding="utf-8"))["observations"]
    census = json.loads((_FIXTURES / "census.json").read_text(encoding="utf-8"))["data"]
    bls = json.loads((_FIXTURES / "bls_v1.json").read_text(encoding="utf-8"))
    cases = [
        ("FRED", fred, FREDClient, lambda client: client.get_observations_page(
            "GDP", "2023-01-01", "2023-12-31", realtime_start="2024-01-01", realtime_end="2024-01-01"),
         "FRED v1 synthetic page", "GDP"),
        ("Census", census, CensusClient, lambda client: client.get_data(
            "2023/acs/acs5", ["NAME", "B01001_001E"], {"for": "state:*"}),
         "2023/acs/acs5", None),
        ("BLS", bls, BLSClient, lambda client: client.get_data(
            ["LNS14000000", "CUUR0000SA0"], 2023, 2023), "BLS Public Data API v1", None),
    ]
    results = []
    with patch("requests.sessions.Session.request", side_effect=AssertionError("Real HTTP is blocked")):
        for name, payload, client_type, call, dataset, series in cases:
            reply = MagicMock()
            reply.__enter__.return_value = reply
            reply.status_code = 200
            reply.headers = {"Content-Type": "application/json"}
            reply.iter_content.return_value = [json.dumps(payload).encode("utf-8")]
            session = MagicMock()
            session.__enter__.return_value = session
            session.get.return_value = reply
            session.post.return_value = reply
            transport = JsonApiTransport(settings, session_factory=lambda session=session: session)
            response = call(client_type(settings, transport))
            saved = save_api_response(settings, response, dataset_id=dataset, series_id=series)
            loaded = read_api_response(settings, saved)
            assert json.loads(loaded.body) == payload
            assert _DUMMY not in loaded.body.decode("utf-8")
            assert _DUMMY not in (root / saved.manifest_path).read_text(encoding="utf-8")
            results.append({
                "source": name, "status": "fixture_file_roundtrip_pass",
                "evidence_kind": "synthetic_fixture", "artifact": asdict(saved),
                "http_method": loaded.manifest["http_method"],
                "mock_request_count": session.get.call_count + session.post.call_count,
                "request_parameters": loaded.manifest["request_parameters"],
                "representation": loaded.manifest["representation_code"],
            })
    return {"schema_version": 1, "evidence_kind": "synthetic_fixture",
            "warning": "Invented values; not live institution data or authentication validation.",
            "created_at": datetime.now(UTC).isoformat(), "live_requests": 0, "sources": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="required explicit offline fixture mode")
    args = parser.parse_args()
    if not args.fixture:
        parser.error("Specify --fixture; this script has no live mode")
    root = Path(__file__).resolve().parents[1]
    report = run_fixture_verification(root)
    relative = f"reports/iteration_28_offline_{uuid4().hex}.json"
    with (root / relative).open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"report": relative, "live_requests": 0,
                      "source_results": [{"source": row["source"], "status": row["status"],
                                          "raw_path": row["artifact"]["raw_path"]}
                                         for row in report["sources"]]}, indent=2))


if __name__ == "__main__":
    main()
