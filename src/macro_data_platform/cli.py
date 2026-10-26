"""Structured, opt-in command line for the currently supported local workflows."""
import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import BOJQuery
from macro_data_platform.connectors.worldbank import API_DOCS, GDPQuery
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.ingestion.boj import (
    build_boj_plan,
    make_boj_orchestrator,
)
from macro_data_platform.ingestion.gate_c_watch import (
    build_gate_c_watch_plan,
    make_gate_c_watch_orchestrator,
)
from macro_data_platform.ingestion.worldbank_request import WorldBankRequestDispatcher
from macro_data_platform.orchestration import WorkflowService
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    DataRequest,
    OutputSpec,
    SourceEvidence,
)
from macro_data_platform.workflow_extensions import DeliverySpec, GroupedProposal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macroatlas",
        description="Run only fixed, documented MacroAtlas paths from a local project checkout.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd(),
                        help="MacroAtlas checkout (defaults to the current directory)")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="collect one explicitly selected series")
    sources = collect.add_subparsers(dest="source", required=True)
    worldbank = sources.add_parser("worldbank-gdp", help="World Bank USA GDP, WDI source 2")
    worldbank.add_argument("--start-year", type=int, required=True)
    worldbank.add_argument("--end-year", type=int, required=True)
    worldbank.add_argument("--live", action="store_true", required=True,
                            help="explicitly permit the fixed public API request")
    boj = sources.add_parser("boj-fxer", help="BOJ FM08 FXERD01 monthly observations")
    boj.add_argument("--month", required=True, help="one month as YYYYMM")
    boj.add_argument("--live", action="store_true", required=True,
                     help="explicitly permit the official API requests")

    watch = commands.add_parser("watch", help="check an exact-scope TIC or BIS source file")
    watch.add_argument("source", choices=("tic", "bis"))
    watch.add_argument("--live", action="store_true", required=True,
                       help="explicitly permit the official file request")

    deferred = commands.add_parser("deferred", help="list deferred non-API files or record history")
    deferred.add_argument("record_id", nargs="?")
    deferred.add_argument("--events", action="store_true",
                          help="include immutable event sequence numbers for one record")

    trial = commands.add_parser("large-check", help="run one bounded local qualification trial")
    trial.add_argument("deferral_id")
    trial.add_argument("--event-seq", type=int)

    large_run = commands.add_parser(
        "large-run", help="explicitly hand off one qualified BIS flat artifact to production",
    )
    large_run.add_argument("deferral_id")
    large_run.add_argument("--event-seq", type=int, required=True)
    large_run.add_argument("--approve-production", action="store_true", required=True,
                           help="explicitly authorize this local production processing run")

    large_resume = commands.add_parser(
        "large-resume", help="resume a saved large-file production child task",
    )
    large_resume.add_argument("task_id")
    large_resume.add_argument("--approve-review", action="store_true",
                              help="acknowledge a NEEDS_REVIEW result before resuming")

    status = commands.add_parser("status", help="inspect a saved task without network access")
    status.add_argument("task_id")

    export = commands.add_parser(
        "export", help="export one verified completed World Bank or BOJ task as CSV",
    )
    export.add_argument("task_id")
    export.add_argument("--format", choices=("csv",), default="csv")
    export.add_argument("--output", required=True,
                        help="new CSV path under data/exports/ (never overwrites)")

    resume = commands.add_parser("resume", help="resume one saved task under its persisted plan")
    resume.add_argument("task_id")
    resume.add_argument("--live", action="store_true", required=True,
                        help="explicitly permit the persisted request to run again")
    resume.add_argument("--approve-review", action="store_true",
                        help="acknowledge a NEEDS_REVIEW result before resuming")
    return parser


def _worldbank_task(store: HistoryStore, settings: Settings,
                    start_year: int, end_year: int) -> str:
    # GDPQuery performs the canonical range validation before a task is persisted.
    GDPQuery(start_year, end_year)
    now = datetime.now(UTC)
    request = DataRequest(
        str(uuid4()),
        f"World Bank USA GDP source 2, {start_year}:{end_year}, raw_json",
        concept="GDP (current US$)", countries=("USA",), dimensions={},
        period_start=str(start_year), period_end=str(end_year), frequency="source",
        unit_policy="preserve", vintage_requirement="latest_available",
    )
    evidence = SourceEvidence(
        "worldbank:documented-profile", "World Bank", API_DOCS,
        datetime(2026, 10, 24, tzinfo=UTC), EvidenceKind.OFFICIAL_DOCS,
        original_ref="docs/connectors/WORLDBANK.md; fixed supported profile",
    )
    candidate = Candidate(
        "usa-gdp", "worldbank", "GDP (current US$)",
        definition="Fixed documented WDI indicator; live response is validated during collection.",
        dataset_id="2", series_key={"source": "2", "country": "USA",
                                     "indicator": "NY.GDP.MKTP.CD"},
        countries=("USA",), dimensions={}, available_start=str(start_year),
        available_end=str(end_year),
        evidence=(evidence,), verification_status="documented", availability_status="available",
        auth_requirement="none", support_status="supported", supported_outputs=("raw_json",),
        uncertainties=("Availability bounds reflect the requested interval, not a catalogue lookup.",),
    )
    proposal = CandidateProposal(str(uuid4()), request.request_id, 1, now, (candidate,))
    service = WorkflowService(store)
    doc = service.begin(
        request, GroupedProposal(proposal), candidate_id=candidate.candidate_id,
        delivery=DeliverySpec("file", OutputSpec("raw_json", f"{settings.data_dir}/raw")),
        confirmation_method="explicit_request",
    )
    return service.create_work(doc["task_id"], expected_revision=1)["task_id"]


def _summary(doc: dict) -> dict:
    stages = doc.get("stages", [])
    last = stages[-1] if stages else None
    result = last.get("result") if isinstance(last, dict) else None
    payload = result.get("payload") if isinstance(result, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    summary = {
        "task_id": doc.get("task_id"), "status": _display_status(doc.get("status")),
        "task_attempts": len(doc.get("attempts", [])),
        "stages": [{
            "stage_id": row.get("stage_id"), "status": _display_status(row.get("status")),
            "error_code": (row.get("result") or {}).get("error_code"),
        } for row in stages],
    }
    for key in ("parent_task_id", "deferral_id", "deferral_event_seq", "production_handoff",
                "source_raw_sha256"):
        if key in doc:
            summary[key] = doc[key]
    if doc.get("trial_only"):
        summary.update({"trial_only": True, "parent_task_id": doc.get("parent_task_id"),
                        "deferral_event_seq": doc.get("deferral_event_seq")})
    for key in ("raw_path", "manifest_path", "normalized_path", "request_manifest_path",
                "source_change_status", "watch_source_id", "quality", "http_status", "non_api_deferral",
                "execution_state", "production_execution", "reason", "message", "trial_state",
                "trial_attempted", "trial_outputs_published", "orphan_scratch_removed",
                "rows", "columns", "elapsed_seconds", "peak_rss_bytes", "raw_sha256",
                "parent_task_id", "deferral_id", "deferral_event_seq", "production_handoff",
                "output_manifest_path", "output_manifest_sha256", "artifact_root", "budget",
                "cells", "empty_fields", "zero_fields", "quality_scope", "checkpoint_path"):
        if key in payload:
            summary[key] = payload[key]
    if isinstance(payload.get("observations"), list):
        summary["observation_count"] = len(payload["observations"])
    return summary


def _display_status(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _trial_not_executed(task_id: str, reason: str, *, status: str) -> dict:
    return {
        "task_id": task_id,
        "status": status,
        "trial_only": True,
        "execution_state": "NOT_EXECUTED",
        "production_execution": "NOT_EXECUTED",
        "trial_state": "UNKNOWN",
        "trial_attempted": None,
        "reason": reason,
        "message": f"미실행: {reason}",
    }


def _settings(root: Path, *, live: bool) -> Settings:
    data_dir = os.environ.get("MACROATLAS_DATA_DIR", "data")
    return Settings(root, data_dir=data_dir, network_enabled=live)


def dispatch(args, *, boj_transport=None, file_transport=None, worldbank_transport=None) -> tuple[int, dict]:
    root = args.project_root.resolve()
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ValueError("project root must contain the MacroAtlas pyproject.toml")
    live = bool(getattr(args, "live", False))
    settings = _settings(root, live=live)
    if args.command == "export":
        from macro_data_platform.ingestion.csv_export import export_task
        result = export_task(settings, args.task_id, args.output, format=args.format)
        return 0, result
    if args.command == "deferred":
        from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore
        if args.events:
            if not args.record_id:
                raise ValueError("--events requires a deferral record ID")
            return 0, {"events": DeferredNonAPIStore(settings, read_only=True).events(args.record_id)}
        return 0, {"records": DeferredNonAPIStore(settings, read_only=True).list(args.record_id)}

    store = HistoryStore(settings)

    if args.command == "large-run":
        from macro_data_platform.ingestion.large_file_production import (
            create_production_handoff,
            make_large_file_production_orchestrator,
        )
        try:
            task_id = create_production_handoff(
                store, settings, args.deferral_id, event_seq=args.event_seq,
                approved=args.approve_production,
            )
        except ValueError as failure:
            reason = str(failure)
            return 1, {
                "execution_state": "NOT_EXECUTED", "production_execution": "NOT_EXECUTED",
                "reason": reason, "message": f"미실행: {reason}",
            }
        doc = store.get(task_id)
        if _display_status(doc["status"]) == "PLANNED":
            try:
                doc = make_large_file_production_orchestrator(store, settings).run(task_id)
            except BlockingIOError:
                return 1, {"task_id": task_id, "status": "PLANNED",
                           "execution_state": "NOT_EXECUTED", "reason": "engine_busy"}
            except (OSError, ValueError):
                return 1, {"task_id": task_id, "status": "PLANNED",
                           "execution_state": "NOT_EXECUTED", "reason": "production_storage_unavailable"}
        return _exit_code(doc), _summary(doc)

    if args.command == "large-resume":
        from macro_data_platform.ingestion.large_file_production import (
            make_large_file_production_orchestrator,
        )
        doc = store.get(args.task_id)
        if not doc.get("production_handoff"):
            raise ValueError("task is not a large-file production handoff")
        runner = make_large_file_production_orchestrator(store, settings)
        if _display_status(doc["status"]) == "RUNNING":
            try:
                doc = runner.recover_interrupted(args.task_id)
            except BlockingIOError:
                return 1, {"task_id": args.task_id, "status": "RUNNING",
                           "execution_state": "NOT_EXECUTED", "reason": "worker_still_active"}
            except (OSError, ValueError):
                return 1, {"task_id": args.task_id, "status": "RUNNING",
                           "execution_state": "NOT_EXECUTED", "reason": "checkpoint_recovery_unavailable"}
        if _display_status(doc["status"]) == "COMPLETED":
            return 0, _summary(doc)
        doc = runner.resume(args.task_id, approved=args.approve_review)
        return _exit_code(doc), _summary(doc)

    if args.command == "large-check":
        from macro_data_platform.ingestion.large_file_trial import (
            create_trial,
            make_trial_orchestrator,
        )
        try:
            task_id = create_trial(store, settings, args.deferral_id, event_seq=args.event_seq)
        except ValueError as failure:
            reason = ("source_changed_since_binding" if str(failure) == "source_changed_since_binding"
                      else "unknown_candidate")
            return 1, {"execution_state": "NOT_EXECUTED", "production_execution": "NOT_EXECUTED",
                       "reason": reason, "message": f"미실행: {reason}"}
        doc = store.get(task_id)
        if _display_status(doc["status"]) == "PLANNED":
            try:
                doc = make_trial_orchestrator(store, settings).run(task_id)
            except BlockingIOError:
                return 1, _trial_not_executed(task_id, "engine_busy", status="PLANNED")
            except (OSError, ValueError):
                return 1, _trial_not_executed(
                    task_id, "trial_storage_unavailable", status="PLANNED",
                )
        elif _display_status(doc["status"]) == "RUNNING":
            return 1, _trial_not_executed(task_id, "trial_already_running", status="RUNNING")
        return _exit_code(doc), _summary(doc)

    if args.command == "status":
        return 0, _summary(store.get(args.task_id))

    if args.command == "collect" and args.source == "worldbank-gdp":
        task_id = _worldbank_task(store, settings, args.start_year, args.end_year)
        dispatcher = WorldBankRequestDispatcher(
            settings, store, transport=worldbank_transport, gate_a=True,
        )
        return _exit_code(doc := dispatcher.run(task_id)), _summary(doc)

    if args.command == "collect" and args.source == "boj-fxer":
        query = BOJQuery(args.month)
        runner = make_boj_orchestrator(store, settings, boj_transport)
        task = runner.create(f"BOJ {query.database}/{query.series_code} observations {query.month}")
        runner.plan(task.task_id, build_boj_plan(query))
        doc = runner.run(task.task_id)
        return _exit_code(doc), _summary(doc)

    if args.command == "watch":
        runner = make_gate_c_watch_orchestrator(store, settings, file_transport)
        task = runner.create(f"Gate C same-scope live source watch: {args.source}")
        runner.plan(task.task_id, build_gate_c_watch_plan(args.source))
        doc = runner.run(task.task_id)
        return _exit_code(doc), _summary(doc)

    if args.command == "resume":
        doc = store.get(args.task_id)
        if "workflow_context" in doc:
            dispatcher = WorldBankRequestDispatcher(
                settings, store, transport=worldbank_transport, gate_a=True,
            )
            resumed = dispatcher.resume(args.task_id, approved=args.approve_review)
        else:
            engines = {spec["engine"] for spec in doc.get("plan", [])}
            if doc.get("trial_only"):
                from macro_data_platform.ingestion.large_file_trial import (
                    interrupted_trial_result,
                    make_trial_orchestrator,
                )
                runner = make_trial_orchestrator(store, settings)
                if _display_status(doc["status"]) == "RUNNING":
                    try:
                        recovered = runner.recover_interrupted(
                            args.task_id,
                            recovery_result=interrupted_trial_result(),
                        )
                    except BlockingIOError:
                        return 1, _trial_not_executed(
                            args.task_id, "worker_still_active", status="RUNNING",
                        )
                    except (OSError, ValueError):
                        return 1, _trial_not_executed(
                            args.task_id, "trial_recovery_unavailable", status="RUNNING",
                        )
                    return _exit_code(recovered), _summary(recovered)
            elif doc.get("production_handoff"):
                from macro_data_platform.ingestion.large_file_production import (
                    make_large_file_production_orchestrator,
                )
                runner = make_large_file_production_orchestrator(store, settings)
                if _display_status(doc["status"]) == "RUNNING":
                    try:
                        doc = runner.recover_interrupted(args.task_id)
                    except BlockingIOError:
                        return 1, {"task_id": args.task_id, "status": "RUNNING",
                                   "execution_state": "NOT_EXECUTED", "reason": "worker_still_active"}
                    except (OSError, ValueError):
                        return 1, {"task_id": args.task_id, "status": "RUNNING",
                                   "execution_state": "NOT_EXECUTED",
                                   "reason": "checkpoint_recovery_unavailable"}
                elif _display_status(doc["status"]) == "COMPLETED":
                    return 0, _summary(doc)
                resumed = runner.resume(args.task_id, approved=args.approve_review)
                return _exit_code(resumed), _summary(resumed)
            elif engines <= {"boj_metadata", "boj_observations"}:
                runner = make_boj_orchestrator(store, settings, boj_transport)
            elif engines == {"gate_c_file_watch"}:
                runner = make_gate_c_watch_orchestrator(store, settings, file_transport)
            elif not doc.get("trial_only"):
                raise ValueError("task plan is not supported by this CLI")
            resumed = runner.resume(args.task_id, approved=args.approve_review)
        return _exit_code(resumed), _summary(resumed)
    raise ValueError("unsupported MacroAtlas CLI command")


def _exit_code(doc: dict) -> int:
    status = doc.get("status")
    return 0 if (status.value if hasattr(status, "value") else status) == "COMPLETED" else 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        status, output = dispatch(args)
    except sqlite3.Error:
        if args.command == "large-check":
            print(json.dumps({"execution_state": "NOT_EXECUTED",
                              "production_execution": "NOT_EXECUTED",
                              "reason": "trial_storage_unavailable", "trial_state": "UNKNOWN",
                              "message": "미실행: 시험 이력 저장소를 사용할 수 없습니다."},
                             ensure_ascii=False))
            return 1
        if args.command in {"large-run", "large-resume"}:
            print(json.dumps({
                "execution_state": "NOT_EXECUTED",
                "production_execution": "NOT_EXECUTED",
                "reason": "handoff_storage_unavailable",
                "message": "미실행: 대용량 인계 이력 저장소를 사용할 수 없습니다.",
            }, ensure_ascii=False))
            return 1
        print(json.dumps({"status": "ERROR", "message": "Local history storage is unavailable."}),
              file=sys.stderr)
        return 2
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
