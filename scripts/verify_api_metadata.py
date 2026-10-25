"""Bounded metadata checks; SDMX sources require explicit selection (Iteration 32)."""
import argparse
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.bea import BEAClient
from macro_data_platform.connectors.estat import EStatClient
from macro_data_platform.connectors.official_api import ConnectorFailure, JsonApiTransport
from macro_data_platform.connectors.sdmx import SdmxApiResponse, SdmxApiTransport
from macro_data_platform.discovery.api_catalogue_validation import validate_api_catalogue
from macro_data_platform.discovery.sdmx_metadata_validation import (
    SDMX_SELECTIONS,
    fetch_sdmx_metadata,
    validate_sdmx_metadata,
)
from macro_data_platform.storage.api_responses import (
    SavedApiArtifact,
    read_api_response,
    save_api_response,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"bea": ("US-04", "bea_api_key"), "estat": ("JP-03", "estat_app_id")}
ALL_SOURCES = {**SOURCES, **{key: (row.institution_id, None)
                          for key, row in SDMX_SELECTIONS.items()}}
FIXTURES = ROOT / "tests" / "fixtures" / "rest_api"


class _FixtureResponse:
    status_code = 200

    def __init__(self, payload):
        self.headers = {"Content-Type": "application/xml" if isinstance(payload, bytes)
                        else "application/json"}
        self.body = (payload if isinstance(payload, bytes) else
                     json.dumps(payload, ensure_ascii=False).encode("utf-8"))

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
    if source in SDMX_SELECTIONS:
        if fixture:
            body = (ROOT / "tests" / "fixtures" / "sdmx_metadata" / f"{source}.xml").read_bytes()
            transport = SdmxApiTransport(settings, lambda: _FixtureSession(body))
        return fetch_sdmx_metadata(source, settings, transport)
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
        or any(not isinstance(item, str) or item not in ALL_SOURCES for item in sources)
        or len(set(sources)) != len(sources)
    ):
        raise ValueError("Select distinct registered metadata sources")
    selected = list(SOURCES) if sources is None else list(sources)
    sdmx = any(source in SDMX_SELECTIONS for source in selected)
    if sdmx and any(source in SOURCES for source in selected):
        raise ValueError("Run SDMX and BEA/e-Stat metadata budgets separately")
    iterations = {SDMX_SELECTIONS[source].iteration for source in selected} if sdmx else {31}
    if len(iterations) != 1:
        raise ValueError("Run numbered iteration budgets separately")
    report_dir = settings.project_root / "reports"
    if report_dir.is_symlink() or not report_dir.resolve().is_relative_to(settings.project_root):
        raise ValueError("Reports must stay inside the project")
    report_dir.mkdir(exist_ok=True)
    iteration = iterations.pop()
    path = report_dir / f"iteration_{iteration}_api_metadata_{uuid4().hex}.json"
    report = {"evidence": "synthetic_fixture" if fixture else "live_metadata_canary",
              "started_at": datetime.now(UTC).isoformat(), "status": "running",
              "scope": "metadata_envelope_and_archive_only", "observations_accepted": False,
              "source_scope": selected, "excluded_institution_ids": ["US-05", "US-06"],
              "request_budget": {"maximum_http_requests": 0 if fixture else len(selected),
                                 "automatic_retries": 0, "concurrency": 1,
                                 "per_source_maximum": 1}, "results": []}
    # Prove report output can be opened before any HTTP request consumes its budget.
    with path.open("x+", encoding="utf-8") as output:
        _write(output, report)
        for source in selected:
            institution_id, credential_name = ALL_SOURCES[source]
            row = {"source": source, "institution_id": institution_id, "request_count": 0}
            report["results"].append(row)
            if settings.network_enabled is not True:
                row["status"] = "not_run_network_disabled"
            elif source in SDMX_SELECTIONS and not SDMX_SELECTIONS[source].ready:
                row["status"] = "not_ready_official_route_or_access"
            elif credential_name and not getattr(settings, credential_name):
                row["status"] = "not_run_missing_key"
            else:
                row["request_count"] = 0 if fixture else 1
                row["mock_requests"] = 1 if fixture else 0
                row["status"] = "request_started"
                _write(output, report)
                try:
                    response = _fetch(source, settings, fixture)
                    if source in SDMX_SELECTIONS and validate_sdmx_metadata(source, response).get(
                            "reason") == "source_or_request_mismatch":
                        raise ValueError("SDMX response differs from its selected source/request")
                    dataset_id = (SDMX_SELECTIONS[source].resource_id if source in SDMX_SELECTIONS
                                  else "metadata_catalogue")
                    saved = save_api_response(settings, response, dataset_id=dataset_id,
                                              expected_institution_id=institution_id)
                    row["artifact"] = asdict(saved)
                    loaded = read_api_response(settings, saved)
                    validation = (validate_sdmx_metadata(source, replace(response, body=loaded.body))
                                  if source in SDMX_SELECTIONS else
                                  validate_api_catalogue(source, json.loads(loaded.body)))
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
    mode.add_argument("--read-back-report", type=Path,
                      help="Revalidate existing SDMX archives only; zero HTTP requests")
    parser.add_argument("--source", action="append", choices=tuple(ALL_SOURCES),
                        help="Default remains BEA/e-Stat only; explicitly select each SDMX source")
    args = parser.parse_args()
    if args.read_back_report:
        if args.source:
            parser.error("Archive revalidation uses the original report selection")
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No replay HTTP")):
            path, report = revalidate_sdmx_archives(Settings.from_project_env(ROOT),
                                                      args.read_back_report)
    elif args.fixture:
        settings = Settings(ROOT, network_enabled=True, bea_api_key="fixture-bea-credential",
                            estat_app_id="fixture-estat-credential")
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No fixture HTTP")):
            path, report = run_checks(settings, sources=args.source, fixture=True)
    else:
        path, report = run_checks(Settings.from_project_env(ROOT), sources=args.source)
    print(path)
    for row in report["results"]:
        print(f"{row['source']}: {row['status']}; requests={row['request_count']}")


def revalidate_sdmx_archives(settings, original_path):
    """Keep the initial canary immutable and explicitly separate offline revalidation."""
    original_path = Path(original_path).resolve()
    report_dir = settings._inside("reports")
    if not original_path.is_relative_to(report_dir):
        raise ValueError("Original report must be inside project reports")
    with original_path.open("rb") as stream:
        original_bytes = stream.read(1024 * 1024 + 1)
    if len(original_bytes) > 1024 * 1024:
        raise ValueError("Original report exceeds limit")
    original = json.loads(original_bytes)
    rows = original["results"]
    sources = [row["source"] for row in rows]
    if (not sources or len(sources) != len(set(sources))
            or any(source not in SDMX_SELECTIONS for source in sources)):
        raise ValueError("Only distinct SDMX sources can be revalidated")
    report = {"evidence": "offline_archive_revalidation",
              "original_evidence": original["evidence"],
              "original_report": original_path.relative_to(settings.project_root).as_posix(),
              "original_report_sha256": hashlib.sha256(original_bytes).hexdigest(),
              "started_at": datetime.now(UTC).isoformat(), "status": "running",
              "observations_accepted": False, "new_http_requests": 0, "results": []}
    iterations = {SDMX_SELECTIONS[source].iteration for source in sources}
    if len(iterations) != 1:
        raise ValueError("Revalidate numbered iteration budgets separately")
    path = report_dir / f"iteration_{iterations.pop()}_archive_revalidation_{uuid4().hex}.json"
    with path.open("x+", encoding="utf-8") as output:
        _write(output, report)
        for old in rows:
            row = {"source": old["source"], "request_count": 0,
                   "original_status": old["status"], "status": "not_revalidated_no_archive"}
            if "artifact" in old:
                try:
                    artifact = SavedApiArtifact(**old["artifact"])
                    loaded = read_api_response(settings, artifact)
                    m = loaded.manifest
                    response = SdmxApiResponse(m["institution_id"], m["source_agency"],
                        m["source_url"], m["operation"], m["http_status"],
                        datetime.fromisoformat(m["retrieved_at"]), m["content_type"], loaded.body)
                    validation = validate_sdmx_metadata(old["source"], response)
                    row.update(artifact=asdict(artifact), read_back_verified=True,
                               validation=validation, http_status=m["http_status"])
                    row["status"] = ("archived_metadata_validated" if validation["status"] ==
                                     "metadata_contract_validated" else "source_metadata_needs_review")
                except (ValueError, TypeError, OSError, KeyError) as error:
                    row.update(status="archive_revalidation_failed", failure_type=type(error).__name__)
            report["results"].append(row)
            _write(output, report)
        report["status"] = ("completed" if all(row["status"] == "archived_metadata_validated"
                            for row in report["results"]) else "completed_with_issues")
        report["finished_at"] = datetime.now(UTC).isoformat()
        _write(output, report)
    return path, report


if __name__ == "__main__":
    main()
