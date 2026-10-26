"""Explicit, durable production handoff for the measured BIS GLI flat ZIP."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4

from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus, TaskStatus
from macro_data_platform.ingestion.large_file_duration import (
    estimate_duration,
    history_documents,
    profile_artifact,
)
from macro_data_platform.ingestion.large_file_trial import _trial_root, worker_slot
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan
from macro_data_platform.storage.history import HistoryStore

BIS_FLAT_URL = "https://data.bis.org/static/bulk/WS_GLI_csv_flat.zip"
ENGINE_VERSION = "1"
MAX_ARCHIVE_PACKAGES = 1000
MAX_MANIFEST_BYTES = 64 * 1024
ARTIFACT_DIR = "large_artifacts"


@dataclass(frozen=True)
class ProductionBudget:
    input_bytes: int = 128 * 1024 * 1024
    output_bytes: int = 192 * 1024 * 1024
    memory_bytes: int = 384 * 1024 * 1024
    cpu_seconds: int = 30
    wall_seconds: int = 60

    def __post_init__(self):
        maximums = {
            "input_bytes": 128 * 1024 * 1024,
            "output_bytes": 192 * 1024 * 1024,
            "memory_bytes": 384 * 1024 * 1024,
            "cpu_seconds": 30,
            "wall_seconds": 60,
        }
        for name, maximum in maximums.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("production budget exceeds the qualified ceiling")


DEFAULT_PRODUCTION_BUDGET = ProductionBudget()


def _inside(settings, relative):
    path = settings.project_root / relative
    current = path
    while current != settings.project_root:
        if current.is_symlink():
            raise ValueError("symbolic_link")
        current = current.parent
    resolved = settings._inside(relative)
    return resolved


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source_url(url):
    if not isinstance(url, str) or len(url) > 512 or any(c.isspace() for c in url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname is not None
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _find_bis_raw(settings, scope, budget):
    if (scope.get("format") != "zip" or scope.get("source_url") != BIS_FLAT_URL
            or scope.get("source_agency") != "Bank for International Settlements"
            or not _safe_source_url(scope.get("source_url"))):
        raise ValueError("unsupported_source_scope")
    relative_inbox = scope.get("relative_path")
    if not isinstance(relative_inbox, str):
        raise ValueError("source_artifact_missing")  # noqa: TRY004 - invalid deferral is a value error
    inbox_path = _inside(settings, relative_inbox)
    inbox_root = _inside(settings, f"{settings.data_dir}/inbox")
    if not inbox_path.is_relative_to(inbox_root) or not inbox_path.is_file():
        raise ValueError("source_artifact_missing")
    if inbox_path.stat().st_size > budget.input_bytes:
        raise ValueError("input_budget")
    inbox_hash = _sha256(inbox_path)

    root_relative = f"{settings.data_dir}/raw/tabular"
    raw_root = _inside(settings, root_relative)
    if not raw_root.is_dir():
        raise ValueError("archived_raw_missing")
    manifests = sorted(raw_root.glob("*/request.json"))
    if len(manifests) > MAX_ARCHIVE_PACKAGES:
        raise ValueError("archive_scan_limit")
    matches = []
    for manifest_path in manifests:
        if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
            raise ValueError("symbolic_link")
        if not manifest_path.parent.resolve().is_relative_to(raw_root.resolve()):
            raise ValueError("archive_path_escape")
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest_budget")
        try:
            manifest_bytes = manifest_path.read_bytes()
            document = json.loads(manifest_bytes)
        except (OSError, UnicodeError, ValueError):
            raise ValueError("request_manifest_invalid") from None
        context = document.get("request_context") if isinstance(document, dict) else None
        raw = document.get("raw") if isinstance(document, dict) else None
        if (not isinstance(context, dict) or context.get("source_url") != BIS_FLAT_URL
                or context.get("format") != "zip"
                or context.get("source_agency") != "Bank for International Settlements"):
            continue
        package_id = document.get("package_id")
        if not isinstance(package_id, str) or not re.fullmatch(r"[a-f0-9]{32}", package_id):
            raise ValueError("request_manifest_scope_invalid")
        expected_relative = (Path(root_relative) / package_id / "source.zip").as_posix()
        if (manifest_path.parent.name != package_id
                or not isinstance(raw, dict) or raw.get("path") != expected_relative):
            raise ValueError("request_manifest_scope_invalid")
        raw_path = _inside(settings, expected_relative)
        if not raw_path.is_file() or raw_path.stat().st_size > budget.input_bytes:
            continue
        raw_hash = _sha256(raw_path)
        if (raw_hash == inbox_hash and raw_hash == raw.get("sha256")
                and raw_path.stat().st_size == raw.get("bytes")):
            matches.append((raw_path, manifest_path, raw_hash,
                            hashlib.sha256(manifest_bytes).hexdigest(), expected_relative,
                            manifest_path.relative_to(settings.project_root).as_posix(), context))
    if len(matches) != 1:
        raise ValueError("archived_raw_not_unique")
    return matches[0]


def _zip_member(raw_path):
    import stat
    import zipfile

    try:
        with zipfile.ZipFile(raw_path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) >= 1000:
                raise ValueError("archive_entries")
            members, names = [], set()
            for item in infos:
                name = item.filename
                if (name in names or "\\" in name or name.startswith("/")
                        or ".." in PurePosixPath(name).parts or ":" in name
                        or item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16)):
                    raise ValueError("archive_security")
                names.add(name)
                if item.file_size / max(1, item.compress_size) >= 200:
                    raise ValueError("archive_ratio")
                if item.file_size > 256 * 1024 * 1024:
                    raise ValueError("archive_budget")
                if not item.is_dir() and PurePosixPath(name).suffix.lower() == ".csv":
                    members.append(item)
            if len(members) != 1:
                raise ValueError("archive_selection")
            if members[0].file_size >= DEFAULT_PRODUCTION_BUDGET.input_bytes:
                raise ValueError("member_budget")
            return members[0].filename
    except (OSError, zipfile.BadZipFile, RuntimeError):
        raise ValueError("archive_invalid") from None


def _qualification_passed(connection, origin_task_id, event_seq, raw_sha256):
    rows = connection.execute("SELECT document FROM tasks").fetchall()
    for (encoded,) in rows:
        try:
            doc = json.loads(encoded)
        except ValueError:
            continue
        if not isinstance(doc, dict):
            continue
        if (doc.get("parent_task_id") != origin_task_id or not doc.get("trial_only")
                or doc.get("deferral_event_seq") != event_seq
                or doc.get("status") != TaskStatus.COMPLETED):
            continue
        stages = doc.get("stages", [])
        if not isinstance(stages, list):
            continue
        result = stages[-1].get("result") if stages else None
        payload = result.get("payload") if isinstance(result, dict) else None
        if (isinstance(payload, dict) and payload.get("execution_state") == "TRIAL_PASSED"
                and payload.get("raw_sha256") == raw_sha256):
            return True
    return False


def _append_deferral_event(connection, record_id, document):
    encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
    connection.execute(
        "INSERT INTO deferred_non_api_events(id,document) VALUES (?,?)", (record_id, encoded),
    )
    connection.execute(
        "INSERT INTO deferred_non_api(id,document) VALUES (?,?) "
        "ON CONFLICT(id) DO UPDATE SET document=excluded.document", (record_id, encoded),
    )


def create_production_handoff(store, settings, record_id, *, event_seq=None, approved=False,
                              budget=DEFAULT_PRODUCTION_BUDGET):
    """Bind one passed qualification and exact immutable deferral event to a production child."""
    if approved is not True:
        raise ValueError("explicit_production_approval_required")
    if event_seq is not None and (type(event_seq) is not int or event_seq < 1):
        raise ValueError("unknown_deferred_event")
    if store.settings.database_path != settings.database_path:
        raise ValueError("handoff/history storage must match")
    with store.transaction() as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='deferred_non_api_events'"
        ).fetchone():
            raise ValueError("unknown_deferred_event")
        if event_seq is None:
            event = connection.execute(
                "SELECT seq,document FROM deferred_non_api_events WHERE id=? "
                "ORDER BY seq LIMIT 1", (record_id,),
            ).fetchone()
        else:
            event = connection.execute(
                "SELECT seq,document FROM deferred_non_api_events WHERE id=? AND seq=?",
                (record_id, event_seq),
            ).fetchone()
        if not event:
            raise ValueError("unknown_deferred_event")
        seq, encoded = event
        record = json.loads(encoded)
        if not isinstance(record, dict) or not isinstance(record.get("scope"), dict):
            raise ValueError("deferred_event_invalid")  # noqa: TRY004 - persisted event is malformed
        if record.get("status") not in {"deferred", "inspection_required", "handed_off", "resolved"}:
            raise ValueError("security_review_required")
        if record.get("reason") in {"unsafe_archive", "zip_ratio", "invalid_archive"}:
            raise ValueError("security_review_required")
        current_row = connection.execute(
            "SELECT document FROM deferred_non_api WHERE id=?", (record_id,),
        ).fetchone()
        if current_row is None:
            raise ValueError("unknown_deferred_event")
        current_state = json.loads(current_row[0])
        if current_state.get("status") not in {"deferred", "inspection_required", "handed_off", "resolved"}:
            raise ValueError("security_review_required")
        origin_task_id = record.get("task_id")
        try:
            origin = HistoryStore.load(connection, origin_task_id)
        except (KeyError, TypeError):
            raise ValueError("origin_task_missing") from None
        if origin.get("status") != TaskStatus.NEEDS_REVIEW:
            raise ValueError("origin_task_scope_mismatch")
        last_result = origin.get("stages", [])[-1].get("result") if origin.get("stages") else None
        payload = (last_result or {}).get("payload") if isinstance(last_result, dict) else None
        deferred = payload.get("non_api_deferral") if isinstance(payload, dict) else None
        if not isinstance(deferred, dict) or deferred.get("id") != record_id:
            raise ValueError("origin_task_scope_mismatch")

        raw_path, request_path, raw_hash, request_hash, raw_relative, request_relative, context = (
            _find_bis_raw(settings, record.get("scope", {}), budget)
        )
        member = _zip_member(raw_path)
        if not _qualification_passed(connection, origin_task_id, seq, raw_hash):
            raise ValueError("matching_qualification_required")
        source_stat = raw_path.stat()
        source_request_stat = request_path.stat()
        inputs = {
            "deferral_id": record_id, "deferral_event_seq": seq,
            "origin_task_id": origin_task_id, "origin_stage_id": record.get("stage_id"),
            "source_url": BIS_FLAT_URL,
            "source_agency": "Bank for International Settlements",
            "raw_path": raw_relative, "raw_sha256": raw_hash,
            "raw_size": source_stat.st_size, "raw_mtime_ns": source_stat.st_mtime_ns,
            "request_manifest_path": request_relative,
            "request_manifest_sha256": request_hash,
            "request_manifest_size": source_request_stat.st_size,
            "request_manifest_mtime_ns": source_request_stat.st_mtime_ns,
            "source_captured_at": context.get("source_captured_at"),
            "source_http_status": context.get("source_http_status"),
            "source_content_type": context.get("source_content_type"),
            "source_last_modified": context.get("source_last_modified"),
            "zip_member": member, "budget": asdict(budget),
            "engine_fingerprint": production_code_fingerprint(),
        }
        idempotency = "large-production-v1:" + hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = HistoryStore.by_key(connection, idempotency)
        if existing:
            return existing["task_id"]
        if current_state.get("status") in {"handed_off", "resolved"}:
            raise ValueError("event_already_handed_off")
        task_id = str(uuid4())
        inputs["task_id"] = task_id
        inputs["artifact_root"] = f"{settings.data_dir}/{ARTIFACT_DIR}/{task_id}"
        inputs["duration_profile"] = profile_artifact(settings, {
            "relative_path": raw_relative,
            "format": "zip",
            "zip_member": member,
            "delimiter": ",",
            "header_row": 1,
        })
        inputs["duration_estimate"] = estimate_duration(
            "production", inputs["duration_profile"], history_documents(connection),
            wall_seconds=budget.wall_seconds,
        )
        doc = HistoryStore.document(
            f"Explicit BIS flat production handoff from {record_id} event {seq}",
            datetime.now(UTC).isoformat(),
        )
        doc.update(
            status=TaskStatus.PLANNED,
            parent_task_id=origin_task_id,
            deferral_id=record_id,
            deferral_event_seq=seq,
            production_handoff=True,
            source_raw_sha256=raw_hash,
            plan=TaskPlan((StageSpec(
                "materialize", "large_file_production", inputs, max_attempts=3,
            ),)).snapshot(),
        )
        doc["task_id"] = task_id
        HistoryStore.insert(connection, doc, idempotency)
        HistoryStore.event(connection, task_id, {
            "kind": "PRODUCTION_HANDOFF_BOUND", "deferral_id": record_id,
            "deferral_event_seq": seq, "parent_task_id": origin_task_id,
            "raw_sha256": raw_hash, "request_manifest_sha256": request_hash,
            "source_ref": raw_relative,
        })
        state = {**record, "status": "handed_off", "handoff_task_id": task_id,
                 "handoff_event_seq": seq, "raw_sha256": raw_hash,
                 "updated_at": datetime.now(UTC).isoformat()}
        _append_deferral_event(connection, record_id, state)
        return task_id


def production_code_fingerprint():
    base = Path(__file__).parent
    return hashlib.sha256(
        Path(__file__).read_bytes()
        + (base / "large_file_production_worker.py").read_bytes()
    ).hexdigest()


class LargeFileProductionEngine:
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
            budget = ProductionBudget(**data["budget"])
            if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
                return _not_executed("resource_isolation_unavailable")
            if data.get("engine_fingerprint") != production_code_fingerprint():
                return _not_executed("engine_version_changed")
            raw_path = _inside(self.settings, data["raw_path"])
            request_path = _inside(self.settings, data["request_manifest_path"])
            artifact_root = _inside(self.settings, data["artifact_root"])
            if (not raw_path.is_file() or not request_path.is_file()
                    or raw_path.stat().st_size != data["raw_size"]
                    or raw_path.stat().st_mtime_ns != data["raw_mtime_ns"]
                    or request_path.stat().st_size != data["request_manifest_size"]
                    or request_path.stat().st_mtime_ns != data["request_manifest_mtime_ns"]):
                return _not_executed("source_changed_since_binding")
            if _sha256(raw_path) != data["raw_sha256"]:
                return _not_executed("source_changed_since_binding")
            if _sha256(request_path) != data["request_manifest_sha256"]:
                return _not_executed("request_manifest_changed")
            if shutil.disk_usage(self.settings.project_root).free < budget.output_bytes + 64 * 1024 * 1024:
                return _not_executed("disk_budget")
            artifact_root.mkdir(parents=True, exist_ok=True)
            if artifact_root.is_symlink() or not artifact_root.is_dir():
                return _not_executed("invalid_artifact_directory")
            if self.worker_lock_fd is None:
                return _not_executed("engine_busy")
            job = {
                "task_id": request.task_id, "deferral_id": data["deferral_id"],
                "deferral_event_seq": data["deferral_event_seq"],
                "source_url": data["source_url"], "source_agency": data["source_agency"],
                "raw_path": str(raw_path), "raw_relative_path": data["raw_path"],
                "raw_sha256": data["raw_sha256"],
                "request_manifest_path": str(request_path),
                "request_manifest_relative_path": data["request_manifest_path"],
                "request_manifest_sha256": data["request_manifest_sha256"],
                "source_captured_at": data.get("source_captured_at"),
                "source_http_status": data.get("source_http_status"),
                "source_content_type": data.get("source_content_type"),
                "source_last_modified": data.get("source_last_modified"),
                "zip_member": data["zip_member"], "artifact_root": str(artifact_root),
                "database_path": str(self.settings.database_path), "budget": asdict(budget),
                "engine_fingerprint": data["engine_fingerprint"],
            }
            job_root = _inside(self.settings, f"{self.settings.data_dir}/{ARTIFACT_DIR}/.jobs")
            job_root.mkdir(parents=True, exist_ok=True)
            if job_root.is_symlink() or not job_root.is_dir():
                return _not_executed("invalid_job_directory")
            config = job_root / f"{request.task_id}.json"
            if config.is_symlink():
                return _not_executed("job_manifest_symbolic_link")
            config.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            worker = Path(__file__).with_name("large_file_production_worker.py")
            try:
                attempted = True
                process = subprocess.run(
                    [sys.executable, "-I", str(worker), str(config)], capture_output=True,
                    text=True, timeout=budget.wall_seconds, check=False,
                    pass_fds=(self.worker_lock_fd,),
                )
            except subprocess.TimeoutExpired:
                return StageResult(
                    StageStatus.FAILED_RETRYABLE,
                    {"execution_state": "PAUSED", "reason": "wall_time_budget",
                     "checkpoint_path": f"{data['artifact_root']}/checkpoint.json"},
                    error_code=ErrorCode.TRANSIENT,
                    retry_hint="Resume this same child task after verifying its worker has stopped.",
                )
            if process.returncode != 0:
                return _not_executed("worker_resource_or_process_failure", attempted=True)
            result = json.loads(process.stdout)
            if result.get("worker_status") != "SUCCEEDED":
                reason = result.get("reason", "worker_stopped")
                status = (StageStatus.FAILED_RETRYABLE if result.get("retryable") else
                          StageStatus.NEEDS_REVIEW)
                error = ErrorCode.TRANSIENT if status == StageStatus.FAILED_RETRYABLE else ErrorCode.SCHEMA_CHANGED
                return StageResult(
                    status, {"execution_state": "PAUSED" if result.get("retryable") else "NOT_EXECUTED",
                             "reason": reason,
                             "checkpoint_path": f"{data['artifact_root']}/checkpoint.json"},
                    warnings=("No complete output manifest was published.",), error_code=error,
                )
            result.pop("worker_status", None)
            result.update({"artifact_root": data["artifact_root"],
                           "output_manifest_path": f"{data['artifact_root']}/output_manifest.json",
                           "checkpoint_path": f"{data['artifact_root']}/checkpoint.json",
                           "budget": asdict(budget), "production_execution": "COMPLETED"})
            manifest_path = artifact_root / "output_manifest.json"
            result["output_manifest_sha256"] = _sha256(manifest_path)
            return StageResult(
                StageStatus.SUCCEEDED, result,
                (data["raw_path"], data["request_manifest_path"],
                 f"{data['artifact_root']}/output_manifest.json"),
                warnings=("Structural CSV checks passed; economic meaning and units were not inferred.",),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return _not_executed("invalid_input_or_production_storage", attempted=attempted)


def _not_executed(reason, *, attempted=False):
    return StageResult(
        StageStatus.NEEDS_REVIEW,
        {"execution_state": "NOT_EXECUTED", "production_execution": "NOT_EXECUTED",
         "attempted": attempted, "reason": reason},
        warnings=("No new normalized output was published.",),
        error_code=ErrorCode.SCHEMA_CHANGED,
    )


class LargeFileProductionOrchestrator(Orchestrator):
    def __init__(self, store, engine, settings):
        super().__init__(store, {("large_file_production", ENGINE_VERSION): engine})
        self.settings = settings
        self.production_engine = engine

    def _under_worker_lock(self, operation, *args, **kwargs):
        if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
            return operation(*args, **kwargs)
        root = _trial_root(self.settings)
        root.mkdir(parents=True, exist_ok=True)
        try:
            with worker_slot(root) as descriptor:
                if operation.__name__ in {"run", "resume"}:
                    self.production_engine.worker_lock_fd = descriptor
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        self.production_engine.worker_lock_fd = None
                return operation(*args, **kwargs)
        except BlockingIOError:
            if operation.__name__ in {"run", "resume"}:
                return operation(*args, **kwargs)
            raise

    def run(self, task_id):
        return self._under_worker_lock(super().run, task_id)

    def resume(self, task_id, *, approved=False):
        return self._under_worker_lock(super().resume, task_id, approved=approved)

    def recover_interrupted(self, task_id):
        root = _trial_root(self.settings)
        root.mkdir(parents=True, exist_ok=True)
        with worker_slot(root):
            result = StageResult(
                StageStatus.FAILED_RETRYABLE,
                {"execution_state": "PAUSED", "reason": "worker_interrupted",
                 "checkpoint_preserved": True},
                warnings=("Worker stopped; resume will verify checkpoint and source hashes.",),
                error_code=ErrorCode.TRANSIENT,
            )
            super().recover_interrupted(task_id, recovery_result=result)
        return self.store.get(task_id)

    def _finish(self, connection, doc, status):
        super()._finish(connection, doc, status)
        if status != TaskStatus.COMPLETED or not doc.get("production_handoff"):
            return
        record_id = doc["deferral_id"]
        row = connection.execute(
            "SELECT document FROM deferred_non_api WHERE id=?", (record_id,),
        ).fetchone()
        if row is None:
            raise ValueError("handoff deferral record disappeared")
        record = json.loads(row[0])
        stage_result = doc.get("stages", [])[-1].get("result") if doc.get("stages") else None
        payload = stage_result.get("payload") if isinstance(stage_result, dict) else None
        if not isinstance(payload, dict) or not payload.get("output_manifest_sha256"):
            raise ValueError("completed handoff has no verified output manifest")
        resolved = {**record, "status": "resolved", "resolved_task_id": doc["task_id"],
                    "output_manifest_path": payload["output_manifest_path"],
                    "output_manifest_sha256": payload["output_manifest_sha256"],
                    "resolved_at": datetime.now(UTC).isoformat()}
        _append_deferral_event(connection, record_id, resolved)


def make_large_file_production_orchestrator(store, settings):
    return LargeFileProductionOrchestrator(store, LargeFileProductionEngine(settings), settings)
