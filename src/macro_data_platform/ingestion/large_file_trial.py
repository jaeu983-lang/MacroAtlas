"""Persisted resource-bounded trials; a passed trial is never production approval."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan
from macro_data_platform.storage.history import HistoryStore


@dataclass(frozen=True)
class TrialBudget:
    input_bytes: int = 128 * 1024 * 1024
    output_bytes: int = 192 * 1024 * 1024
    memory_bytes: int = 384 * 1024 * 1024
    cpu_seconds: int = 15
    wall_seconds: int = 20

    def __post_init__(self):
        for key, maximum in {
            "input_bytes": 128 * 1024 * 1024,
            "output_bytes": 192 * 1024 * 1024,
            "memory_bytes": 384 * 1024 * 1024,
            "cpu_seconds": 15,
            "wall_seconds": 20,
        }.items():
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(
                    "trial budget must be positive and within the qualification ceiling"
                )


DEFAULT_BUDGET = TrialBudget()
SCRATCH_MARKER = ".macroatlas-trial-scratch"


def not_executed(reason, *, attempted=False):
    return StageResult(
        StageStatus.NEEDS_REVIEW,
        {
            "execution_state": "NOT_EXECUTED",
            "production_execution": "NOT_EXECUTED",
            "trial_state": "REJECTED" if attempted else "NOT_RUN",
            "trial_attempted": attempted,
            "reason": reason,
            "message": f"미실행: {reason}",
            "original_modified": False,
        },
        warnings=("Qualification stopped; no production output was published.",),
        error_code=ErrorCode.SCHEMA_CHANGED,
    )


@contextmanager
def worker_slot(root):
    import fcntl

    descriptor = os.open(root / "worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield descriptor
    finally:
        os.close(descriptor)


def cleanup_orphaned_scratch(root):
    """Remove only marked trial directories after the workspace lock is held."""
    removed = 0
    for candidate in root.iterdir():
        if (not candidate.name.startswith("trial-") or candidate.is_symlink()
                or not candidate.is_dir()):
            continue
        marker = candidate / SCRATCH_MARKER
        if marker.is_symlink() or not marker.is_file():
            continue
        shutil.rmtree(candidate)
        removed += 1
    return removed


def _trial_root(settings):
    requested = settings.project_root / settings.data_dir / "large_trials"
    current = requested
    while current != settings.project_root:
        if current.is_symlink():
            raise ValueError("trial storage path contains a symbolic link")
        current = current.parent
    return settings._inside(f"{settings.data_dir}/large_trials")


def interrupted_trial_result(cleaned_scratch: int = 0):
    return StageResult(
        StageStatus.NEEDS_REVIEW,
        {
            "execution_state": "NOT_EXECUTED",
            "production_execution": "NOT_EXECUTED",
            "trial_state": "UNKNOWN",
            "trial_attempted": None,
            "reason": "interrupted_result_unavailable",
            "message": "시험 worker가 결과를 저장하기 전에 중단되어 판정을 복구할 수 없습니다. 원본은 보존되었고 정식 출력은 미실행입니다.",
            "original_modified": False,
            "trial_outputs_published": False,
            "orphan_scratch_removed": cleaned_scratch,
        },
        warnings=("Interrupted qualification result is unknown; production output was not published.",),
        error_code=ErrorCode.INTERNAL_BUG,
    )


def source_stat(path):
    value = path.stat()
    return {name: getattr(value, name) for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns")}


def code_fingerprint():
    return hashlib.sha256(
        Path(__file__).read_bytes() + Path(__file__).with_name("large_file_worker.py").read_bytes()
    ).hexdigest()


class LargeFileTrialEngine:
    def __init__(self, settings):
        self.settings = settings
        self._worker_slot = threading.local()

    @property
    def worker_lock_fd(self):
        return getattr(self._worker_slot, "descriptor", None)

    @worker_lock_fd.setter
    def worker_lock_fd(self, value):
        self._worker_slot.descriptor = value

    def run(self, request):
        data = request.input_data
        attempted = False
        try:
            budget = TrialBudget(**data["budget"])
            scope = data["scope"]
            relative = scope.get("relative_path")
            if not relative:
                return not_executed("no_local_artifact")
            path = self.settings._inside(relative)
            original = self.settings.project_root / relative
            if any(p.is_symlink() for p in (original, *original.parents)):
                return not_executed("symbolic_link")
            allowed = [
                self.settings._inside(f"{self.settings.data_dir}/{name}")
                for name in ("inbox", "raw")
            ]
            if not any(path.is_relative_to(root) for root in allowed) or not path.is_file():
                return not_executed("invalid_source_path")
            if data.get("source_stat") is not None and source_stat(path) != data["source_stat"]:
                return not_executed("source_changed_since_binding")
            if path.stat().st_size >= budget.input_bytes:
                return not_executed("input_budget")
            if path.suffix.lower() not in {".csv", ".tsv", ".txt", ".zip"}:
                return not_executed("unsupported_trial_format")
            if data.get("deferral_status") == "security_review":
                return not_executed("security_review_required")
            if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
                return not_executed("resource_isolation_unavailable")
            if data.get("engine_fingerprint") != code_fingerprint():
                return not_executed("engine_version_changed")
            trial_root = _trial_root(self.settings)
            trial_root.mkdir(parents=True, exist_ok=True)
            slot = (worker_slot(trial_root) if self.worker_lock_fd is None
                    else nullcontext(self.worker_lock_fd))
            with (
                slot as worker_lock_fd,
            ):
                orphan_scratch_removed = cleanup_orphaned_scratch(trial_root)
                if shutil.disk_usage(trial_root).free < budget.output_bytes + 64 * 1024 * 1024:
                    return not_executed("disk_budget")
                with tempfile.TemporaryDirectory(prefix="trial-", dir=trial_root) as scratch:
                    (Path(scratch) / SCRATCH_MARKER).write_text("MacroAtlas trial scratch\n",
                                                               encoding="utf-8")
                    job = {
                        "path": str(path),
                        "scope": scope,
                        "limits": asdict(budget),
                        "scratch": scratch,
                        "source_stat": data.get("source_stat"),
                    }
                    config = Path(scratch) / "job.json"
                    config.write_text(json.dumps(job), encoding="utf-8")
                    worker = Path(__file__).with_name("large_file_worker.py")
                    try:
                        attempted = True
                        process = subprocess.run(
                            [sys.executable, "-I", str(worker), str(config)],
                            capture_output=True,
                            text=True,
                            timeout=budget.wall_seconds,
                            check=False,
                            pass_fds=(worker_lock_fd,),
                        )
                    except subprocess.TimeoutExpired:
                        return not_executed("wall_time_budget", attempted=True)
                    if process.returncode != 0:
                        return not_executed("worker_resource_or_process_failure", attempted=True)
                    result = json.loads(process.stdout)
            if result.get("trial_state") != "PASSED":
                return not_executed(result.get("reason", "trial_rejected"), attempted=True)
            return StageResult(
                StageStatus.SUCCEEDED,
                {
                    **result,
                    "execution_state": "TRIAL_PASSED",
                    "production_execution": "NOT_EXECUTED",
                    "eligible_for_production": False,
                    "message": "용량 시험 통과. 본 실행은 미실행이며 별도 검토가 필요합니다.",
                    "trial_outputs_discarded": True,
                    "original_preserved": True,
                    "budget": asdict(budget),
                    "deferral_event_seq": data["deferral_event_seq"],
                    "quality_scope": "rectangular UTF-8 string rows only; no economic normalization",
                    "orphan_scratch_removed": orphan_scratch_removed,
                },
            )
        except BlockingIOError:
            return not_executed("engine_busy")
        except (OSError, ValueError, TypeError, KeyError):
            return not_executed("invalid_input_or_trial_storage", attempted=attempted)


def create_trial(store, settings, record_id, *, event_seq=None, budget=DEFAULT_BUDGET):
    """Bind an immutable existing event to an idempotent child trial in one transaction."""
    if store.settings.database_path != settings.database_path:
        raise ValueError("trial/history storage must match")
    with store.transaction() as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='deferred_non_api_events'"
        ).fetchone():
            raise ValueError("no deferred catalog")
        if event_seq is None:
            row = db.execute(
                "SELECT seq,document FROM deferred_non_api_events WHERE id=? "
                "ORDER BY seq DESC LIMIT 1",
                (record_id,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT seq,document FROM deferred_non_api_events WHERE id=? AND seq=?",
                (record_id, event_seq),
            ).fetchone()
        if not row:
            raise ValueError("unknown deferred event")
        seq, encoded = row
        record = json.loads(encoded)
        inputs = {
            "deferral_event_seq": seq,
            "deferral_id": record_id,
            "scope": record["scope"],
            "deferral_status": record["status"],
            "origin_task_id": record["task_id"],
            "origin_stage_id": record["stage_id"],
            "budget": asdict(budget),
            "engine_fingerprint": code_fingerprint(),
        }
        key = (
            "large-trial-v1:"
            + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        )
        existing = HistoryStore.by_key(db, key)
        if existing:
            bound = existing["plan"][0]["input_data"]
            if bound.get("source_stat") is not None:
                try:
                    current = source_stat(settings._inside(bound["scope"]["relative_path"]))
                except (OSError, ValueError):
                    raise ValueError("source_changed_since_binding") from None
                if current != bound["source_stat"]:
                    raise ValueError("source_changed_since_binding")
            return existing["task_id"]
        relative = record["scope"].get("relative_path")
        try:
            inputs["source_stat"] = source_stat(settings._inside(relative)) if relative else None
        except (OSError, ValueError):
            inputs["source_stat"] = None
        doc = HistoryStore.document(
            "Explicit local non-API qualification trial", datetime.now(UTC).isoformat()
        )
        doc.update(
            status="PLANNED",
            parent_task_id=record["task_id"],
            deferral_event_seq=seq,
            trial_only=True,
            plan=TaskPlan(
                (StageSpec("qualify", "large_file_trial", inputs, max_attempts=1),)
            ).snapshot(),
        )
        HistoryStore.insert(db, doc, key)
        HistoryStore.event(
            db,
            doc["task_id"],
            {"kind": "TRIAL_BOUND", "deferral_event_seq": seq, "parent_task_id": record["task_id"]},
        )
        return doc["task_id"]


def make_trial_orchestrator(store, settings):
    engine = LargeFileTrialEngine(settings)
    return LargeFileTrialOrchestrator(store, engine, settings)


class LargeFileTrialOrchestrator(Orchestrator):
    """Hold one workspace lock from task claim until the worker and stage finish."""

    def __init__(self, store, engine, settings):
        super().__init__(store, {("large_file_trial", "1"): engine})
        self.settings = settings
        self.trial_engine = engine

    def _with_trial_lock(self, operation, *args, **kwargs):
        if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
            return operation(*args, **kwargs)
        trial_root = _trial_root(self.settings)
        trial_root.mkdir(parents=True, exist_ok=True)
        try:
            with worker_slot(trial_root) as descriptor:
                if operation.__name__ in {"run", "resume"}:
                    self.trial_engine.worker_lock_fd = descriptor
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        self.trial_engine.worker_lock_fd = None
                return operation(*args, **kwargs)
        except BlockingIOError:
            if operation.__name__ in {"run", "resume"}:
                # The engine records a visible NOT_EXECUTED:engine_busy result.
                return operation(*args, **kwargs)
            raise

    def run(self, task_id):
        return self._with_trial_lock(super().run, task_id)

    def resume(self, task_id, *, approved=False):
        return self._with_trial_lock(super().resume, task_id, approved=approved)

    def recover_interrupted(self, task_id, *, recovery_result=None):
        if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
            return super().recover_interrupted(task_id, recovery_result=recovery_result)
        trial_root = _trial_root(self.settings)
        trial_root.mkdir(parents=True, exist_ok=True)
        with worker_slot(trial_root):
            cleaned = cleanup_orphaned_scratch(trial_root)
            result = recovery_result or interrupted_trial_result(cleaned)
            if recovery_result is not None:
                result = StageResult(
                    result.status,
                    {**(result.payload or {}), "orphan_scratch_removed": cleaned},
                    result.evidence_refs,
                    result.warnings,
                    result.error_code,
                    result.retry_hint,
                    result.retry_after_seconds,
                )
            super().recover_interrupted(task_id, recovery_result=result)
        return self.store.get(task_id)
