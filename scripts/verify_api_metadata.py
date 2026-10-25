"""Iteration 31: BEA/e-Stat metadata only, one request per selected source, no retries."""
import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bea import BEAClient
from macro_data_platform.connectors.estat import EStatClient
from macro_data_platform.connectors.official_api import ConnectorFailure, JsonApiTransport
from macro_data_platform.discovery.api_catalogue_validation import validate_api_catalogue
from macro_data_platform.storage.api_responses import read_api_response, save_api_response

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"bea": ("US-04", "bea_api_key"), "estat": ("JP-03", "estat_app_id")}
FIXTURES = ROOT / "tests" / "fixtures" / "rest_api"


class _FixtureResponse:
    status_code = 200

    def __init__(self, payload):
        self.headers = {"Content-Type": "application/json"}
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        yield self.body


class _FixtureSession:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url, **_kwargs):
        return _FixtureResponse(self.payload)


def _fetch(source, settings, fixture):
    transport = None
    if fixture:
        payload = json.loads((FIXTURES / f"{source}_catalogue.json").read_text(encoding="utf-8"))
        transport = JsonApiTransport(settings, lambda: _FixtureSession(payload))
    if source == "bea":
        return BEAClient(settings, transport).get_dataset_list()
    return EStatClient(settings, transport).get_stats_list({"lang": "E", "limit": 1})


def _write(output, report):
    output.seek(0)
    json.dump(report, output, ensure_ascii=False, indent=2)
    output.write("\n")
    output.truncate()
    output.flush()


def run_checks(settings, *, sources=None, fixture=False):
    if sources is not None and (
        not isinstance(sources, (list, tuple)) or not sources
        or any(not isinstance(item, str) or item not in SOURCES for item in sources)
        or len(set(sources)) != len(sources)
    ):
        raise ValueError("Select distinct registered BEA/e-Stat sources")
    selected = list(SOURCES) if sources is None else list(sources)
    report_dir = settings.project_root / "reports"
    if report_dir.is_symlink() or not report_dir.resolve().is_relative_to(settings.project_root):
        raise ValueError("Reports must stay inside the project")
    report_dir.mkdir(exist_ok=True)
    path = report_dir / f"iteration_31_api_metadata_{uuid4().hex}.json"
    report = {"evidence": "synthetic_fixture" if fixture else "live_metadata_canary",
              "started_at": datetime.now(UTC).isoformat(), "status": "running",
              "scope": "metadata_envelope_and_archive_only", "observations_accepted": False,
              "source_scope": selected, "excluded_institution_ids": ["US-05", "US-06"],
              "request_budget": {"maximum_http_requests": 0 if fixture else len(selected),
                                 "automatic_retries": 0}, "results": []}
    # Prove report output can be opened before any HTTP request consumes its budget.
    with path.open("x+", encoding="utf-8") as output:
        _write(output, report)
        for source in selected:
            institution_id, credential_name = SOURCES[source]
            row = {"source": source, "institution_id": institution_id, "request_count": 0}
            if settings.network_enabled is not True:
                row["status"] = "not_run_network_disabled"
            elif not getattr(settings, credential_name):
                row["status"] = "not_run_missing_key"
            else:
                row["request_count"] = 0 if fixture else 1
                row["mock_requests"] = 1 if fixture else 0
                try:
                    response = _fetch(source, settings, fixture)
                    saved = save_api_response(settings, response, dataset_id="metadata_catalogue",
                                              expected_institution_id=institution_id)
                    loaded = read_api_response(settings, saved)
                    validation = validate_api_catalogue(source, json.loads(loaded.body))
                    row.update(http_status=response.http_status, artifact=asdict(saved),
                               stored_bytes=len(loaded.body), read_back_verified=True,
                               validation=validation)
                    row["status"] = (
                        ("fixture_metadata_validated" if fixture else "live_metadata_validated")
                        if validation["status"] == "metadata_contract_validated"
                        else "source_metadata_needs_review"
                    )
                except ConnectorFailure as error:
                    row.update(status="request_failed", failure_code=error.code.value,
                               failure_stage=error.status.value, failure_reason=error.reason.value,
                               failure_http_status=error.http_status,
                               failure_response_kind=error.response_kind)
                except (ValueError, TypeError, OSError, KeyError, AttributeError, RuntimeError) as error:
                    row.update(status="validation_or_storage_failed", failure_type=type(error).__name__)
            report["results"].append(row)
            _write(output, report)
        expected = "fixture_metadata_validated" if fixture else "live_metadata_validated"
        report["status"] = ("completed" if all(row["status"] == expected for row in report["results"])
                            else "completed_with_issues")
        report["finished_at"] = datetime.now(UTC).isoformat()
        _write(output, report)
    return path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--source", action="append", choices=tuple(SOURCES))
    args = parser.parse_args()
    if args.fixture:
        settings = Settings(ROOT, network_enabled=True, bea_api_key="fixture-bea-credential",
                            estat_app_id="fixture-estat-credential")
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No fixture HTTP")):
            path, report = run_checks(settings, sources=args.source, fixture=True)
    else:
        path, report = run_checks(Settings.from_project_env(ROOT), sources=args.source)
    print(path)
    for row in report["results"]:
        print(f"{row['source']}: {row['status']}; requests={row['request_count']}")


if __name__ == "__main__":
    main()
