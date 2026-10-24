"""Additive Gate A catalogue. Historical task JSON and SQLite user_version stay unchanged."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from macro_data_platform.contracts import StageStatus, required, utc
from macro_data_platform.storage.history import HistoryStore


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


class AuditStore:
    def __init__(self, history: HistoryStore, *, clock=lambda: datetime.now(UTC)):
        self.history, self.settings, self.clock = history, history.settings, clock
        with history.transaction() as connection:
            # Additive tables, no rewrite of any previous task, event, raw file or schema version.
            statements = (
                ("CREATE TABLE IF NOT EXISTS gate_a_records ("
                "record_id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                "task_id TEXT NOT NULL REFERENCES tasks(task_id), stage_run_id TEXT, "
                "idempotency_key TEXT UNIQUE, document TEXT NOT NULL)"),
                "CREATE INDEX IF NOT EXISTS gate_a_by_task ON gate_a_records(task_id, kind)",
                ("CREATE UNIQUE INDEX IF NOT EXISTS gate_a_by_stage "
                "ON gate_a_records(kind, stage_run_id) WHERE kind != 'feedback'"),
                ("CREATE TABLE IF NOT EXISTS gate_a_observations ("
                "validation_id TEXT NOT NULL REFERENCES gate_a_records(record_id), "
                "position INTEGER NOT NULL, document TEXT NOT NULL, "
                "PRIMARY KEY(validation_id, position))"),
            )
            for statement in statements:
                connection.execute(statement)

    def now(self):
        at = self.clock()
        utc(at)
        return at.isoformat()

    def active(self, request):
        doc = self.history.get(request.task_id)
        if not doc["active_token"] or not doc["stages"]:
            raise ValueError("audit writes require an active stage")
        row = doc["stages"][-1]
        if row["stage_id"] != request.stage_id or row["status"] != StageStatus.RUNNING:
            raise ValueError("audit stage ownership mismatch")
        return doc["active_token"], row["stage_run_id"]

    def _insert(self, connection, kind, task_id, stage_run_id, payload, key=None):
        record = {**payload, "schema_version": 1, "record_id": str(uuid4()), "kind": kind,
                  "task_id": task_id, "stage_run_id": stage_run_id,
                  "recorded_at": self.now()}
        connection.execute(
            "INSERT INTO gate_a_records VALUES (?, ?, ?, ?, ?, ?)",
            (record["record_id"], kind, task_id, stage_run_id, key,
             json.dumps(record, ensure_ascii=False, allow_nan=False)),
        )
        self.history.event(connection, task_id, {
            "kind": "AUDIT_" + kind.upper(), "at": record["recorded_at"],
            "record_id": record["record_id"], "stage_run_id": stage_run_id,
        })
        return record

    def record_stage(self, kind, request, owner, payload, *, observations=()):
        if kind not in {"artifact", "validation", "incident"}:
            raise ValueError("unknown audit record kind")
        observations = list(observations)
        if len(observations) > 10 or (observations and kind != "validation"):
            raise ValueError("invalid normalized observation batch")
        token, stage_run_id = owner
        with self.history.transaction() as connection:
            doc = self.history.load(connection, request.task_id)
            if (doc["active_token"] != token or not doc["stages"]
                    or doc["stages"][-1]["stage_run_id"] != stage_run_id
                    or doc["stages"][-1]["status"] != StageStatus.RUNNING):
                raise ValueError("stale worker cannot write audit records")
            if kind == "validation":
                artifact = self._load(connection, payload["artifact_id"], "artifact")
                if artifact["task_id"] != request.task_id:
                    raise ValueError("artifact belongs to another task")
                if payload["status"] != "passed" and observations:
                    raise ValueError("failed validation cannot publish observations")
                payload = {**payload, "normalized_sha256": digest(observations)}
            record = self._insert(connection, kind, request.task_id, stage_run_id, payload)
            for position, item in enumerate(observations):
                connection.execute("INSERT INTO gate_a_observations VALUES (?, ?, ?)", (
                    record["record_id"], position,
                    json.dumps(item, ensure_ascii=False, allow_nan=False),
                ))
            return record

    @staticmethod
    def _load(connection, record_id, kind=None):
        row = connection.execute(
            "SELECT kind, document FROM gate_a_records WHERE record_id=?", (record_id,),
        ).fetchone()
        if row is None or (kind is not None and row[0] != kind):
            raise ValueError("unknown audit record")
        return json.loads(row[1])

    def get(self, record_id, *, kind=None):
        with self.history._connect() as connection:
            return self._load(connection, record_id, kind)

    def for_task(self, task_id, *, kind=None):
        with self.history._connect() as connection:
            self.history.load(connection, task_id)
            rows = connection.execute(
                "SELECT document FROM gate_a_records WHERE task_id=? "
                "AND (? IS NULL OR kind=?) ORDER BY rowid", (task_id, kind, kind),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def observations(self, validation_id):
        with self.history._connect() as connection:
            report = self._load(connection, validation_id, "validation")
            rows = connection.execute(
                "SELECT document FROM gate_a_observations WHERE validation_id=? ORDER BY position",
                (validation_id,),
            ).fetchall()
            result = [json.loads(row[0]) for row in rows]
            if digest(result) != report["normalized_sha256"]:
                raise ValueError("normalized observation integrity check failed")
            return result

    def add_feedback(self, task_id, *, text, category="note", origin="user",
                     stage_run_id=None, record_id=None, idempotency_key=None):
        required(text, "feedback text")
        if len(text) > 2000 or category not in {"note", "correction", "problem"}:
            raise ValueError("invalid feedback text or category")
        if origin not in {"user", "verification"}:
            raise ValueError("unknown feedback origin")
        if idempotency_key is not None:
            required(idempotency_key, "feedback idempotency key")
            if len(idempotency_key) > 128:
                raise ValueError("feedback key too long")
        payload = {"text": text, "category": category, "origin": origin,
                   "related_record_id": record_id, "status": "recorded_unreviewed"}
        with self.history.transaction() as connection:
            doc = self.history.load(connection, task_id)
            if stage_run_id is not None and stage_run_id not in {
                item["stage_run_id"] for item in doc["stages"]
            }:
                raise ValueError("feedback stage belongs to another task")
            if record_id is not None:
                related = self._load(connection, record_id)
                if related["task_id"] != task_id or (stage_run_id is not None
                        and related["stage_run_id"] != stage_run_id):
                    raise ValueError("feedback record belongs to another scope")
            if idempotency_key is not None:
                row = connection.execute(
                    "SELECT document FROM gate_a_records WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    prior = json.loads(row[0])
                    if (prior["kind"] != "feedback" or prior["task_id"] != task_id
                            or prior["stage_run_id"] != stage_run_id
                            or any(prior[key] != value for key, value in payload.items())):
                        raise ValueError("feedback idempotency key conflict")
                    return prior
            return self._insert(connection, "feedback", task_id, stage_run_id, payload,
                                idempotency_key)
