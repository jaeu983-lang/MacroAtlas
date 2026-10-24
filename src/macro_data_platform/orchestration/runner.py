"""Synchronous sequential runner with durable attempts and explicit resumption."""
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from macro_data_platform.contracts import (
    Engine,
    ErrorCode,
    StageResult,
    StageStatus,
    Task,
    TaskStatus,
    required,
    utc,
)
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan, json_snapshot
from macro_data_platform.orchestration.workflow import validate_workflow_task
from macro_data_platform.storage.history import HistoryStore

SUCCESS = {StageStatus.SUCCEEDED, StageStatus.SKIPPED_REUSED}
OUTCOMES = {StageStatus.SUCCEEDED, StageStatus.FAILED_RETRYABLE,
            StageStatus.FAILED_TERMINAL, StageStatus.NEEDS_REVIEW}


class Orchestrator:
    def __init__(
        self,
        store: HistoryStore,
        engines: Mapping[tuple[str, str], Engine[StageInput, Any]],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        reuse_validator: Callable[[StageSpec, dict], bool] | None = None,
    ):
        self.store = store
        self.engines = dict(engines)
        self.clock = clock
        self.reuse_validator = reuse_validator

    def _now(self) -> str:
        value = self.clock()
        utc(value)
        return value.isoformat()

    def _event(self, connection, doc: dict, kind: str, **details) -> None:
        self.store.event(connection, doc["task_id"], {
            "kind": kind, "at": self._now(), "task_status": doc["status"], **details,
        })

    def _check_workflow(self, connection, doc: dict) -> None:
        if "workflow_request" in doc or "workflow_context" in doc:
            validate_workflow_task(self.store, connection, doc,
                                   datetime.fromisoformat(self._now()))

    def create(self, request: str, *, idempotency_key: str | None = None) -> Task:
        required(request, "request")
        if idempotency_key is not None:
            required(idempotency_key, "idempotency_key")
        with self.store.transaction() as connection:
            if idempotency_key is not None:
                row = connection.execute(
                    "SELECT document FROM tasks WHERE idempotency_key=?", (idempotency_key,),
                ).fetchone()
                if row is not None:
                    doc = json.loads(row[0])
                    if (doc["request"] != request or "workflow_request" in doc
                            or "workflow_context" in doc):
                        raise ValueError("idempotency key conflicts with another request")
                    return self._task(doc)
            doc = {
                "task_id": str(uuid4()), "request": request, "created_at": self._now(),
                "status": TaskStatus.CREATED, "plan": None, "attempts": [], "stages": [],
                "active_token": None, "cancel_requested": False,
            }
            connection.execute(
                "INSERT INTO tasks(task_id, idempotency_key, document) VALUES (?, ?, ?)",
                (doc["task_id"], idempotency_key, json.dumps(doc, ensure_ascii=False)),
            )
            self._event(connection, doc, "TASK_CREATED")
        return self._task(doc)

    @staticmethod
    def _task(doc: dict) -> Task:
        return Task(doc["task_id"], doc["request"], datetime.fromisoformat(doc["created_at"]),
                    TaskStatus(doc["status"]))

    def plan(self, task_id: str, plan: TaskPlan) -> None:
        snapshot = plan.snapshot()
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            self._check_workflow(connection, doc)
            if doc["plan"] is not None:
                if doc["plan"] == snapshot:
                    return
                raise ValueError("saved plan is immutable; create another task for changes")
            if doc["status"] != TaskStatus.CREATED:
                raise ValueError("only a created task can be planned")
            doc["plan"] = snapshot
            doc["status"] = TaskStatus.PLANNED
            self.store.save(connection, doc)
            self._event(connection, doc, "TASK_PLANNED")

    def cancel(self, task_id: str) -> None:
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            if doc["status"] in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
                return
            if doc["cancel_requested"]:
                return
            doc["cancel_requested"] = True
            if doc["active_token"] is None:
                doc["status"] = TaskStatus.CANCELLED
            self.store.save(connection, doc)
            self._event(connection, doc, "CANCEL_REQUESTED")

    def run(self, task_id: str) -> dict:
        return self._execute(task_id, resume=False, approved=False)

    def resume(self, task_id: str, *, approved: bool = False) -> dict:
        return self._execute(task_id, resume=True, approved=approved)

    def _claim(self, task_id: str, *, resume: bool, approved: bool) -> str | None:
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            self._check_workflow(connection, doc)
            if doc["status"] == TaskStatus.COMPLETED:
                return None
            if doc["active_token"] is not None or doc["status"] == TaskStatus.RUNNING:
                raise ValueError("task already running; recover only after its worker has stopped")
            if doc["plan"] is None:
                raise ValueError("task requires a plan")
            if not resume and doc["status"] != TaskStatus.PLANNED:
                raise ValueError("use resume for a previously attempted or cancelled task")
            if resume:
                self._check_resume(doc, approved=approved)
            for spec in doc["plan"]:
                if (spec["engine"], spec["engine_version"]) not in self.engines:
                    raise ValueError("plan requires an unregistered engine version")
            token = str(uuid4())
            doc["active_token"] = token
            doc["cancel_requested"] = False
            doc["status"] = TaskStatus.RUNNING
            doc["attempts"].append({
                "attempt_no": len(doc["attempts"]) + 1, "token": token,
                "started_at": self._now(), "finished_at": None, "status": TaskStatus.RUNNING,
            })
            self.store.save(connection, doc)
            self._event(connection, doc, "TASK_RESUMED" if resume else "TASK_STARTED")
            return token

    @staticmethod
    def _check_resume(doc: dict, *, approved: bool) -> None:
        if doc["status"] not in {
            TaskStatus.FAILED, TaskStatus.PARTIAL, TaskStatus.NEEDS_REVIEW, TaskStatus.CANCELLED,
        }:
            raise ValueError("task is not resumable in this state")
        if doc["status"] == TaskStatus.NEEDS_REVIEW and not approved:
            raise ValueError("review acknowledgement required before resume")
        # Cancellation cannot turn an existing terminal/review failure into a retry.
        latest = doc["stages"][-1] if doc["stages"] else None
        if latest is not None:
            if latest["status"] == StageStatus.FAILED_TERMINAL:
                raise ValueError("terminal failure requires a new task")
            if latest["status"] == StageStatus.NEEDS_REVIEW and not approved:
                raise ValueError("review acknowledgement required before resume")

    @staticmethod
    def _owned(doc: dict, token: str) -> None:
        if doc["active_token"] != token:
            raise ValueError("task ownership changed; stale worker cannot commit")

    def _finish(self, connection, doc: dict, status: TaskStatus) -> None:
        doc["status"] = status
        doc["active_token"] = None
        doc["attempts"][-1].update(status=status, finished_at=self._now())
        self.store.save(connection, doc)
        self._event(connection, doc, "TASK_FINISHED")

    def recover_interrupted(self, task_id: str) -> None:
        """Explicit operator action, only after the previous worker has stopped."""
        with self.store.transaction() as connection:
            doc = self.store.load(connection, task_id)
            if doc["active_token"] is None:
                raise ValueError("task has no interrupted active attempt")
            if doc["stages"] and doc["stages"][-1]["status"] == StageStatus.RUNNING:
                stage = doc["stages"][-1]
                stage.update(
                    status=StageStatus.FAILED_RETRYABLE, finished_at=self._now(),
                    result=asdict(StageResult(
                        StageStatus.FAILED_RETRYABLE, error_code=ErrorCode.INTERNAL_BUG,
                        warnings=("Interrupted worker; external side effects require checking.",),
                    )),
                )
                self._event(connection, doc, "STAGE_INTERRUPTED", stage_id=stage["stage_id"])
            status = TaskStatus.CANCELLED if doc["cancel_requested"] else TaskStatus.FAILED
            self._finish(connection, doc, status)

    @staticmethod
    def _fingerprint(doc: dict, spec: StageSpec, upstream: dict | None) -> str:
        value = {"request": doc["request"], "stage": asdict(spec), "upstream": upstream}
        if "workflow_context" in doc:
            value["workflow_context"] = doc["workflow_context"]
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _reusable(self, spec: StageSpec, candidate: dict | None, fingerprint: str) -> bool:
        if candidate is None or candidate["status"] not in SUCCESS:
            return False
        if candidate["fingerprint"] != fingerprint or self.reuse_validator is None:
            return False
        age = (datetime.fromisoformat(self._now())
               - datetime.fromisoformat(candidate["validated_at"])).total_seconds()
        if not 0 <= age < spec.reuse_ttl_seconds:
            return False
        try:
            detached_spec = StageSpec(**json_snapshot(asdict(spec)))
            return self.reuse_validator(detached_spec, json_snapshot(candidate)) is True
        except Exception:  # noqa: BLE001 - validator failure must deny reuse
            # Validation exceptions cannot authorize reuse or leak exception messages.
            return False

    def _execute(self, task_id: str, *, resume: bool, approved: bool) -> dict:
        token = self._claim(task_id, resume=resume, approved=approved)
        if token is None:
            return self.store.get(task_id)
        doc = self.store.get(task_id)
        upstream = None
        upstream_run_id = None
        reuse_prefix = resume
        for saved_spec in doc["plan"]:
            spec = StageSpec(**saved_spec)
            current = self.store.get(task_id)
            fingerprint = self._fingerprint(current, spec, upstream)
            previous = [row for row in current["stages"] if row["stage_id"] == spec.stage_id]
            candidate = previous[-1] if previous else None
            reuse = reuse_prefix and self._reusable(spec, candidate, fingerprint)
            # Claim a stage and persist RUNNING before executing external code.
            with self.store.transaction() as connection:
                current = self.store.load(connection, task_id)
                self._owned(current, token)
                if current["cancel_requested"]:
                    self._finish(connection, current, TaskStatus.CANCELLED)
                    return current
                try:
                    self._check_workflow(connection, current)
                except ValueError:
                    self._finish(connection, current, TaskStatus.NEEDS_REVIEW)
                    return current
                invocations = sum(row["status"] != StageStatus.SKIPPED_REUSED for row in previous)
                if not reuse and invocations >= spec.max_attempts:
                    self._event(connection, current, "RETRY_LIMIT_REACHED", stage_id=spec.stage_id)
                    self._finish(connection, current, TaskStatus.NEEDS_REVIEW)
                    return current
                row = {
                    "stage_run_id": str(uuid4()), "stage_id": spec.stage_id,
                    "engine": spec.engine, "engine_version": spec.engine_version,
                    "task_attempt_no": len(current["attempts"]),
                    "attempt_no": invocations if reuse else invocations + 1,
                    "input_refs": upstream["evidence_refs"] if upstream else [],
                    "input_stage_run_id": upstream_run_id,
                    "fingerprint": fingerprint, "started_at": self._now(),
                    "finished_at": None, "validated_at": None,
                    "status": StageStatus.RUNNING, "result": None, "reused_from": None,
                }
                if reuse:
                    row.update(
                        status=StageStatus.SKIPPED_REUSED, result=candidate["result"],
                        finished_at=self._now(), validated_at=candidate["validated_at"],
                        reused_from=candidate["stage_run_id"],
                    )
                current["stages"].append(row)
                self.store.save(connection, current)
                self._event(connection, current, "STAGE_REUSED" if reuse else "STAGE_STARTED",
                            stage_id=spec.stage_id, stage_run_id=row["stage_run_id"])
            if reuse:
                upstream = row["result"]
                upstream_run_id = row["stage_run_id"]
                continue
            reuse_prefix = False
            try:
                result = self.engines[(spec.engine, spec.engine_version)].run(StageInput(
                    task_id, current["request"], spec.stage_id, json_snapshot(spec.input_data),
                    json_snapshot(upstream["payload"]) if upstream else None,
                    tuple(row["input_refs"]),
                ))
                if not isinstance(result, StageResult) or result.status not in OUTCOMES:
                    raise ValueError("engine must return a terminal stage result")
                if (
                    result.status == StageStatus.FAILED_RETRYABLE
                    and result.error_code in {ErrorCode.AUTH_ACCESS, ErrorCode.LICENSE_SECURITY}
                ):
                    result = StageResult(
                        StageStatus.NEEDS_REVIEW, result.payload, result.evidence_refs,
                        result.warnings, result.error_code, result.retry_hint,
                    )
                serialized = json_snapshot(asdict(result))
            except Exception:  # noqa: BLE001 - isolate injected engines without logging secrets
                serialized = json_snapshot(asdict(StageResult(
                    StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                    warnings=("Engine exception or invalid result; details omitted.",),
                )))
            with self.store.transaction() as connection:
                current = self.store.load(connection, task_id)
                self._owned(current, token)
                row = current["stages"][-1]
                row.update(status=serialized["status"], result=serialized,
                           finished_at=self._now(), validated_at=self._now())
                self._event(connection, current, "STAGE_FINISHED", stage_id=spec.stage_id,
                            stage_run_id=row["stage_run_id"], stage_status=row["status"],
                            error_code=serialized["error_code"])
                if current["cancel_requested"]:
                    self._finish(connection, current, TaskStatus.CANCELLED)
                    return current
                if row["status"] != StageStatus.SUCCEEDED:
                    if row["status"] == StageStatus.NEEDS_REVIEW:
                        status = TaskStatus.NEEDS_REVIEW
                    elif upstream is not None:
                        status = TaskStatus.PARTIAL
                    else:
                        status = TaskStatus.FAILED
                    self._finish(connection, current, status)
                    return current
                self.store.save(connection, current)
                upstream = serialized
                upstream_run_id = row["stage_run_id"]
        with self.store.transaction() as connection:
            current = self.store.load(connection, task_id)
            self._owned(current, token)
            status = TaskStatus.CANCELLED if current["cancel_requested"] else TaskStatus.COMPLETED
            self._finish(connection, current, status)
        return current
