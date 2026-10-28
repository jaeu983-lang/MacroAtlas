"""Explicit opt-in live verification for iteration 03; not a general product CLI."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.contracts import EvidenceKind, SourceEvidence, TaskStatus
from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine
from macro_data_platform.ingestion.worldbank_request import WorldBankRequestDispatcher
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan, WorkflowService
from macro_data_platform.storage import HistoryStore
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    DataRequest,
    OutputSpec,
)
from macro_data_platform.workflow_extensions import DeliverySpec, GroupedProposal


def confirmed_verification_task(store: HistoryStore) -> dict:
    """Explicit file request using the existing documented profile, not metadata discovery."""
    at = datetime.now(UTC)
    request = DataRequest(
        str(uuid4()), "World Bank USA GDP, source 2, 2020:2022, raw_json; live verification",
        concept="GDP (current US$)", countries=("USA",), dimensions={},
        period_start="2020", period_end="2022", frequency="source", unit_policy="preserve",
        vintage_requirement="latest_available",
    )
    evidence = SourceEvidence(
        "worldbank:documented-profile", "World Bank",
        "https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries",
        datetime(2026, 10, 24, tzinfo=UTC), EvidenceKind.OFFICIAL_DOCS,
        original_ref="docs/developer/connectors/WORLDBANK.md; prior documented profile, not fresh discovery",
    )
    candidate = Candidate(
        "usa-gdp", "worldbank", "GDP (current US$)",
        definition="Documented World Bank GDP (current US$) indicator; fixed verification profile.",
        dataset_id="2", series_key={"source": "2", "country": "USA", "indicator": "NY.GDP.MKTP.CD"},
        countries=("USA",), dimensions={}, available_start="2020", available_end="2022",
        evidence=(evidence,), verification_status="documented", availability_status="available",
        auth_requirement="none", support_status="supported", supported_outputs=("raw_json",),
    )
    service = WorkflowService(store)
    doc = service.begin(
        request, GroupedProposal(CandidateProposal(str(uuid4()), request.request_id, 1, at,
                                                  (candidate,))),
        candidate_id=candidate.candidate_id,
        delivery=DeliverySpec("file", OutputSpec("raw_json", f"{store.settings.data_dir}/raw")),
        confirmation_method="explicit_request",
    )
    return service.create_work(doc["task_id"], expected_revision=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one public World Bank GDP query.")
    parser.add_argument("--live", action="store_true", help="explicitly permit the fixed API request")
    parser.add_argument("--legacy", action="store_true", help="use the original unbound verification")
    parser.add_argument("--gate-a", action="store_true", help="hash, normalize and validate the new task")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this script never enables network access implicitly")
    if args.legacy and args.gate_a:
        parser.error("--legacy and --gate-a are separate execution contracts")
    root = Path(__file__).resolve().parents[1]
    settings = Settings(root, network_enabled=True)
    store = HistoryStore(settings)
    if args.legacy:
        engine = WorldBankGDPEngine(settings)
        runner = Orchestrator(store, {("worldbank_gdp", "1"): engine})
        task = runner.create("World Bank USA GDP (current US$), WDI source 2, 2020:2022; live verification")
        runner.plan(task.task_id, TaskPlan((StageSpec(
            "collect", "worldbank_gdp", {"start_year": 2020, "end_year": 2022}, max_attempts=1,
        ),)))
        result = runner.run(task.task_id)
    else:
        child = confirmed_verification_task(store)
        dispatcher = WorldBankRequestDispatcher(settings, store, gate_a=args.gate_a)
        result = dispatcher.run(child["task_id"])
    task_id = result["task_id"]
    report = {"mode": "live", "task": result, "events": store.events(task_id),
              "scope": "legacy_iteration_03" if args.legacy else "alignment_03_only; not Gate A"}
    if not args.legacy:
        report["workflow_events"] = store.events(result["workflow_context"]["source_workflow_id"])
    if args.gate_a:
        report["scope"] = "iteration_04_gate_a; fixed World Bank path only"
        audit = dispatcher.audit
        feedback = audit.add_feedback(task_id, category="note", origin="verification",
            text="Verification run recorded; this is not a user correction or statistical approval.",
            idempotency_key="verification:" + task_id)
        report["feedback_id"] = feedback["record_id"]
        report["audit_records"] = audit.for_task(task_id)
        validations = audit.for_task(task_id, kind="validation")
        report["normalized_observations"] = (audit.observations(validations[-1]["record_id"])
                                              if validations else [])
        report["events"] = store.events(task_id)
        report["live_path_passed"] = (result["status"] == TaskStatus.COMPLETED
            and bool(validations) and validations[-1]["status"] == "passed"
            and validations[-1]["mode"] == "live_api")
    report_dir = root / "reports"
    report_dir.mkdir(exist_ok=True)
    prefix = "iteration_04" if args.gate_a else "iteration_03" if args.legacy else "alignment_03"
    path = report_dir / f"{prefix}_live_{uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
    stage = result["stages"][-1]
    print(json.dumps({"task_id": task_id, "status": result["status"],
                      "report": path.relative_to(root).as_posix(),
                      "payload": stage["result"]["payload"],
                      "error_code": stage["result"]["error_code"]}, ensure_ascii=True))
    return 0 if result["status"] == TaskStatus.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
