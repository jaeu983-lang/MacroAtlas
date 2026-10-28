"""Durable per-unit progress for bounded, explicitly confirmed collection plans."""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from requests.exceptions import RequestException

from macro_data_platform.contracts import ErrorCode, StageStatus, utc
from macro_data_platform.ingestion.bulk import CollectionPlan, CollectionUnit
from macro_data_platform.ingestion.retry import retry_delay
from macro_data_platform.orchestration.workflow import validate_workflow_task
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.workflow_extensions import ConfirmedDelivery

MAX_UNIT_ATTEMPTS = 3


@dataclass(frozen=True)
class UnitOutcome:
    status: StageStatus
    artifact_refs: tuple[str, ...] = ()
    observation_count: int = 0
    byte_count: int = 0
    elapsed_seconds: float = 0.0
    error_code: ErrorCode | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self):
        if not isinstance(self.status, StageStatus) or self.status not in {
            StageStatus.SUCCEEDED, StageStatus.FAILED_RETRYABLE,
            StageStatus.FAILED_TERMINAL, StageStatus.NEEDS_REVIEW,
        }:
            raise ValueError("invalid collection unit outcome")
        if (self.status in {StageStatus.FAILED_RETRYABLE, StageStatus.FAILED_TERMINAL}
                and self.error_code is None):
            raise ValueError("failed collection unit requires an error code")
        if self.status == StageStatus.FAILED_RETRYABLE and self.error_code in {
            ErrorCode.AUTH_ACCESS, ErrorCode.LICENSE_SECURITY,
        }:
            raise ValueError("access and security errors cannot be retried")
        if self.status == StageStatus.SUCCEEDED and self.error_code is not None:
            raise ValueError("successful collection unit cannot contain an error")
        if self.error_code is not None and not isinstance(self.error_code, ErrorCode):
            raise ValueError("invalid collection unit error code")
        if (type(self.observation_count) is not int or self.observation_count < 0
                or type(self.byte_count) is not int or self.byte_count < 0
                or type(self.elapsed_seconds) not in {int, float}
                or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError("invalid collection unit resource usage")
        if self.retry_after_seconds is not None and (
            self.status != StageStatus.FAILED_RETRYABLE
            or self.error_code != ErrorCode.TRANSIENT
            or type(self.retry_after_seconds) not in {int, float}
            or not math.isfinite(self.retry_after_seconds)
            or not 0 <= self.retry_after_seconds <= 86_400
        ):
            raise ValueError("invalid bounded retry delay")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.artifact_refs):
            raise ValueError("artifact references must be nonempty paths")


class CollectionProgressStore:
    """Store unit attempts in the owning workflow task and its append-only event history."""

    def __init__(self, history: HistoryStore, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 monotonic: Callable[[], float] = time.monotonic):
        self.history = history
        self.clock = clock
        self.monotonic = monotonic

    def _now(self) -> datetime:
        at = self.clock()
        utc(at)
        return at

    @staticmethod
    def _unit_id(unit: CollectionUnit) -> str:
        payload = json.dumps(asdict(unit), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _plan_fingerprint(plan: CollectionPlan) -> str:
        payload = json.dumps(asdict(plan), ensure_ascii=False, sort_keys=True,
                             allow_nan=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _matches_confirmation(confirmed, plan: CollectionPlan) -> None:
        request, candidate = confirmed.offer.request, confirmed.offer.candidate
        selected_series_id = candidate.series_id or candidate.candidate_id
        if plan.mode not in {"sample", "full"} or not plan.requires_confirmation:
            raise ValueError("collection plan requires an explicit sample/full confirmation")
        if not plan.units or plan.planned_requests != len(plan.units):
            raise ValueError("collection plan has no executable bounded units")
        if plan.series_ids != (selected_series_id,):
            raise ValueError("plan series must match the confirmed candidate")
        if not set(plan.countries).issubset(request.countries):
            raise ValueError("plan countries exceed the confirmed request")
        if candidate.frequency != plan.frequency:
            raise ValueError("plan frequency differs from the confirmed candidate")
        if (request.period_start is None or request.period_end is None
                or request.frequency not in {None, "source", plan.frequency}
                or request.period_start != plan.period_start
                or plan.mode == "full" and plan.period_end != request.period_end
                or plan.period_end is None or plan.period_end > request.period_end):
            raise ValueError("plan period or frequency exceeds the confirmed request")
        if confirmed.delivery.mode not in {"file", "both"}:
            raise ValueError("collection plans require confirmed file delivery")

    def initialize(self, task_id: str, plan: CollectionPlan,
                   confirmation_fingerprint: str) -> dict:
        if not isinstance(plan, CollectionPlan) or not isinstance(confirmation_fingerprint, str):
            raise TypeError("a bounded plan and confirmation fingerprint are required")
        fingerprint = self._plan_fingerprint(plan)
        at = self._now()
        with self.history.transaction() as db:
            doc = self.history.load(db, task_id)
            if "workflow_context" not in doc:
                raise ValueError("collection plan must belong to a confirmed workflow task")
            validate_workflow_task(self.history, db, doc, at)
            confirmed = ConfirmedDelivery.from_dict(doc["workflow_context"]["confirmation"])
            if confirmed.fingerprint != confirmation_fingerprint:
                raise ValueError("collection confirmation fingerprint differs")
            self._matches_confirmation(confirmed, plan)
            existing = doc.get("collection_progress")
            if existing is not None:
                if (existing["plan_fingerprint"] != fingerprint
                        or existing["confirmation_fingerprint"] != confirmation_fingerprint):
                    raise ValueError("collection plan is immutable after initialization")
                return existing
            units = []
            for unit in plan.units:
                units.append({
                    "unit_id": self._unit_id(unit), "unit": asdict(unit),
                    "status": "NOT_RUN", "attempt_count": 0, "artifact_refs": [],
                    "observation_count": 0, "byte_count": 0, "elapsed_seconds": 0.0,
                    "history": [], "retry_not_before": None, "error_code": None,
                    "message": None,
                })
            progress = {
                "schema_version": 1, "plan_fingerprint": fingerprint,
                "confirmation_fingerprint": confirmation_fingerprint,
                "plan": asdict(plan), "units": units,
                "request_attempts": 0, "observation_count": 0, "byte_count": 0,
                "elapsed_seconds": 0.0, "stop_reason": None, "pause_until": None,
            }
            doc["collection_progress"] = progress
            self.history.save(db, doc)
            self.history.event(db, task_id, {
                "kind": "COLLECTION_PLAN_RECORDED", "at": at.isoformat(),
                "plan_fingerprint": fingerprint, "unit_count": len(units),
            })
            return progress

    def snapshot(self, task_id: str) -> dict:
        doc = self.history.get(task_id)
        if "collection_progress" not in doc:
            raise ValueError("collection progress is not initialized")
        return doc["collection_progress"]

    def pending_units(self, task_id: str) -> tuple[CollectionUnit, ...]:
        progress = self.snapshot(task_id)
        now = self._now()
        if progress["stop_reason"]:
            return ()
        pause_until = progress["pause_until"]
        if pause_until and now < datetime.fromisoformat(pause_until):
            return ()
        return tuple(
            CollectionUnit(**row["unit"])
            for row in progress["units"]
            if row["status"] == "NOT_RUN"
            or (row["status"] == StageStatus.FAILED_RETRYABLE
                and row["attempt_count"] < MAX_UNIT_ATTEMPTS
                and (row["retry_not_before"] is None
                     or now >= datetime.fromisoformat(row["retry_not_before"])))
        )

    def start_unit(self, task_id: str, unit_id: str) -> dict | None:
        at = self._now()
        with self.history.transaction() as db:
            doc = self.history.load(db, task_id)
            validate_workflow_task(self.history, db, doc, at)
            progress = doc.get("collection_progress")
            if progress is None or progress["stop_reason"]:
                raise ValueError("collection run is stopped or uninitialized")
            if progress["pause_until"] and at < datetime.fromisoformat(progress["pause_until"]):
                raise ValueError("collection backoff has not elapsed")
            row = next((item for item in progress["units"] if item["unit_id"] == unit_id), None)
            if row is None:
                raise ValueError("unknown collection unit")
            if row["status"] not in {"NOT_RUN", StageStatus.FAILED_RETRYABLE}:
                raise ValueError("collection unit is not resumable")
            if row["attempt_count"] >= MAX_UNIT_ATTEMPTS:
                row["status"] = StageStatus.NEEDS_REVIEW
                progress["stop_reason"] = "unit_retry_limit_reached"
                self.history.save(db, doc)
                self.history.event(db, task_id, {
                    "kind": "COLLECTION_UNIT_RETRY_LIMIT", "at": at.isoformat(),
                    "unit_id": unit_id,
                })
                return None
            budget = progress["plan"]["budget"]
            if (progress["request_attempts"] >= budget["max_requests"]
                    or progress["observation_count"] >= budget["max_observations"]
                    or progress["byte_count"] >= budget["max_bytes"]
                    or progress["elapsed_seconds"] >= budget["max_seconds"]):
                progress["stop_reason"] = "collection_budget_exhausted"
                self.history.save(db, doc)
                self.history.event(db, task_id, {
                    "kind": "COLLECTION_BUDGET_STOPPED", "at": at.isoformat(),
                    "unit_id": unit_id,
                })
                return None
            row["attempt_count"] += 1
            progress["request_attempts"] += 1
            row["status"] = "RUNNING"
            row["started_at"] = at.isoformat()
            row["retry_not_before"] = None
            row["history"].append({"attempt": row["attempt_count"], "status": "RUNNING",
                                   "started_at": at.isoformat()})
            self.history.save(db, doc)
            self.history.event(db, task_id, {
                "kind": "COLLECTION_UNIT_STARTED", "at": at.isoformat(),
                "unit_id": unit_id, "attempt": row["attempt_count"],
            })
            return {"unit": row["unit"], "attempt_no": row["attempt_count"],
                    "remaining_bytes": budget["max_bytes"] - progress["byte_count"],
                    "remaining_seconds": budget["max_seconds"] - progress["elapsed_seconds"]}

    def finish_unit(self, task_id: str, unit_id: str, outcome: UnitOutcome) -> dict:
        if not isinstance(outcome, UnitOutcome):
            raise TypeError("collection executor must return UnitOutcome")
        for ref in outcome.artifact_refs:
            path = self.history.settings._inside(ref)
            if (not path.is_relative_to(self.history.settings.raw_dir) or not path.is_file()):
                raise ValueError("collection artifact must be an existing file under data/raw")
        at = self._now()
        with self.history.transaction() as db:
            doc = self.history.load(db, task_id)
            progress = doc.get("collection_progress")
            if progress is None:
                raise ValueError("collection progress is not initialized")
            row = next((item for item in progress["units"] if item["unit_id"] == unit_id), None)
            if row is None or row["status"] != "RUNNING":
                raise ValueError("collection unit has no active attempt")
            status = outcome.status
            message = {
                StageStatus.SUCCEEDED: "Collection unit completed; artifacts retained.",
                StageStatus.FAILED_RETRYABLE: "Transient unit failure; bounded retry scheduled.",
                StageStatus.FAILED_TERMINAL: "Unit failed terminally; a new task is required.",
                StageStatus.NEEDS_REVIEW: "Unit requires review; remaining units paused.",
            }[status]
            try:
                validate_workflow_task(self.history, db, doc, at)
            except ValueError:
                status = StageStatus.NEEDS_REVIEW
                message = "Confirmation or source metadata changed during collection."
            budget = progress["plan"]["budget"]
            next_observations = progress["observation_count"] + outcome.observation_count
            next_bytes = progress["byte_count"] + outcome.byte_count
            next_seconds = progress["elapsed_seconds"] + outcome.elapsed_seconds
            if (next_observations > budget["max_observations"]
                    or next_bytes > budget["max_bytes"]
                    or next_seconds > budget["max_seconds"]):
                status = StageStatus.NEEDS_REVIEW
                message = "Collection unit exceeded the confirmed run resource budget; raw retained."
            if outcome.observation_count > row["unit"]["period_count"] * len(row["unit"]["countries"]):
                status = StageStatus.NEEDS_REVIEW
                message = "Collection unit returned more observations than its confirmed scope."
            progress["observation_count"] = next_observations
            progress["byte_count"] = next_bytes
            progress["elapsed_seconds"] = next_seconds
            row.update(status=status, artifact_refs=list(outcome.artifact_refs),
                       observation_count=outcome.observation_count, byte_count=outcome.byte_count,
                       elapsed_seconds=outcome.elapsed_seconds,
                       error_code=outcome.error_code, message=message,
                       finished_at=at.isoformat())
            retry_not_before = None
            if status == StageStatus.FAILED_RETRYABLE:
                delay = retry_delay(row["attempt_count"], outcome.retry_after_seconds)
                retry_not_before = (at + timedelta(seconds=delay)).isoformat()
                row["retry_not_before"] = retry_not_before
                progress["pause_until"] = retry_not_before
            else:
                row["retry_not_before"] = None
                progress["pause_until"] = None
            row["history"][-1].update(status=status, finished_at=at.isoformat(),
                                      artifact_refs=list(outcome.artifact_refs),
                                      error_code=outcome.error_code, message=message,
                                      retry_not_before=retry_not_before)
            if status in {StageStatus.NEEDS_REVIEW, StageStatus.FAILED_TERMINAL}:
                progress["stop_reason"] = "unit_requires_review" if status == StageStatus.NEEDS_REVIEW else "unit_failed_terminal"
            self.history.save(db, doc)
            self.history.event(db, task_id, {
                "kind": "COLLECTION_UNIT_FINISHED", "at": at.isoformat(),
                "unit_id": unit_id, "attempt": row["attempt_count"],
                "unit_status": status, "error_code": outcome.error_code,
            })
            return progress

    def execute_pending(self, task_id: str,
                        execute: Callable[[CollectionUnit, int, float], UnitOutcome]) -> dict:
        """Run available units with per-unit limits; the callback owns transport timeouts."""
        for unit in self.pending_units(task_id):
            unit_id = self._unit_id(unit)
            lease = self.start_unit(task_id, unit_id)
            if lease is None:
                break
            attempt_unit = CollectionUnit(**lease["unit"])
            started = self.monotonic()
            try:
                outcome = execute(attempt_unit, lease["remaining_bytes"],
                                  lease["remaining_seconds"])
                if not isinstance(outcome, UnitOutcome):
                    raise TypeError("executor returned an invalid unit outcome")
                elapsed = max(outcome.elapsed_seconds, self.monotonic() - started)
                if elapsed != outcome.elapsed_seconds:
                    outcome = UnitOutcome(
                        outcome.status, outcome.artifact_refs, outcome.observation_count,
                        outcome.byte_count, elapsed, outcome.error_code,
                        outcome.retry_after_seconds,
                    )
            except (TimeoutError, ConnectionError, RequestException):
                elapsed = max(0.0, self.monotonic() - started)
                outcome = UnitOutcome(StageStatus.FAILED_RETRYABLE, elapsed_seconds=elapsed,
                                      error_code=ErrorCode.TRANSIENT)
            except Exception:  # noqa: BLE001 - persist a safe unit failure without exception detail
                elapsed = max(0.0, self.monotonic() - started)
                outcome = UnitOutcome(StageStatus.FAILED_TERMINAL, elapsed_seconds=elapsed,
                                      error_code=ErrorCode.INTERNAL_BUG)
            self.finish_unit(task_id, unit_id, outcome)
            progress = self.snapshot(task_id)
            if progress["stop_reason"] or progress["pause_until"]:
                break
        return self.snapshot(task_id)
