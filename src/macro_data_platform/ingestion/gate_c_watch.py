"""Persist-before-request exact-scope live checks for the TIC and BIS Gate C files."""
from datetime import UTC
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_files import (
    PROFILES,
    OfficialFileDownload,
    OfficialFileTransport,
)
from macro_data_platform.connectors.statistical_http import SourceFailure
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.ingestion.tabular_files import TabularFileEngine
from macro_data_platform.orchestration import Orchestrator, StageInput, StageSpec, TaskPlan
from macro_data_platform.storage.history import HistoryStore


class Transport(Protocol):
    def fetch(self, source_id: str) -> OfficialFileDownload: ...


class GateCFileEngine:
    def __init__(self, settings: Settings, transport: Transport | None = None):
        self.settings = settings
        self.transport = transport if transport is not None else OfficialFileTransport()
        self.parser = TabularFileEngine(settings)

    def run(self, request: StageInput) -> StageResult[dict]:
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network collection is disabled in settings.",))
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"source_id"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected one allowlisted Gate C source identifier.",))
        source_id = data["source_id"]
        profile = PROFILES.get(source_id)
        if profile is None:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Unsupported Gate C source identifier.",))
        try:
            download = self.transport.fetch(source_id)
            if download.source_id != source_id or download.source_url != profile["url"]:
                return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                                   warnings=("Downloaded file identity differed from the fixed source.",))
            relative_dir = Path(self.settings.data_dir) / "inbox" / "gate_c_watch"
            extension = "txt" if profile["format"] == "txt" else "zip"
            filename = f"{source_id}_{uuid4().hex}.{extension}"
            relative_path = relative_dir / filename
            target = self.settings._inside(relative_path.as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(download.body)
            parser_input = {
                "relative_path": relative_path.as_posix(),
                "source_url": profile["url"], "format": profile["format"],
                "source_agency": profile["source_agency"],
                "source_captured_at": download.retrieved_at.astimezone(UTC).isoformat(),
                "source_content_type": download.content_type or "application/octet-stream",
                "source_http_status": download.status_code,
                "source_last_modified": download.last_modified,
            }
            parser_input.update({key: profile[key] for key in (
                "delimiter", "header_row", "zip_member", "source_table_name",
            ) if key in profile})
            result = self.parser.run(StageInput(
                request.task_id, request.request, request.stage_id, parser_input, None, (),
            ))
            if result.status == StageStatus.NEEDS_REVIEW:
                return result
            payload = dict(result.payload or {})
            payload.update({"watch_source_id": source_id, "evidence_kind": "live_file"})
            return StageResult(result.status, payload, result.evidence_refs, result.warnings,
                               result.error_code, result.retry_hint, result.retry_after_seconds)
        except SourceFailure as failure:
            retry_hint = None
            retry_after = None
            if failure.status == StageStatus.FAILED_RETRYABLE:
                retry_after = failure.retry_after_seconds
                retry_hint = (f"Wait at least {retry_after} seconds before manual resume; "
                              "no automatic retry was sent." if retry_after is not None else
                              "Resume manually after the temporary source condition clears; "
                              "no retry was sent.")
            payload = ({"http_status": failure.status_code}
                       if failure.status_code is not None else None)
            return StageResult(failure.status, payload, warnings=(str(failure),),
                               error_code=failure.code, retry_hint=retry_hint,
                               retry_after_seconds=retry_after)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                               warnings=("Official file preservation failed; existing captures remain.",))


def build_gate_c_watch_plan(source_id: str) -> TaskPlan:
    if source_id not in PROFILES:
        raise ValueError("source_id must be tic or bis")
    return TaskPlan((StageSpec("source_watch", "gate_c_file_watch", {"source_id": source_id},
                               max_attempts=2),))


def make_gate_c_watch_orchestrator(store: HistoryStore, settings: Settings,
                                   transport: Transport | None = None) -> Orchestrator:
    if store.settings.database_path != settings.database_path:
        raise ValueError("Gate C watcher and history must use the same configured storage")
    return Orchestrator(store, {("gate_c_file_watch", "1"): GateCFileEngine(settings, transport)})


def create_gate_c_watch_task(store: HistoryStore, settings: Settings, source_id: str,
                             transport: Transport | None = None) -> dict:
    runner = make_gate_c_watch_orchestrator(store, settings, transport)
    task = runner.create(f"Gate C same-scope live source watch: {source_id}")
    runner.plan(task.task_id, build_gate_c_watch_plan(source_id))
    return store.get(task.task_id)
