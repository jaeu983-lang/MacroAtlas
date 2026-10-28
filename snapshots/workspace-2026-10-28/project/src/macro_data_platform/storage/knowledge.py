"""Append-only, provenance-aware inputs for the institution and concept knowledge engine."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from macro_data_platform.contracts import required, utc
from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore

MAX_KNOWLEDGE_BYTES = 65_536
_PROVENANCE = {"user_statement", "official_evidence", "inference"}
_VALIDATION = {"unverified", "verified", "rejected", "inferred", "needs_review"}
_REVIEW = {"accepted", "rejected", "deferred"}
_CORRECTION_TYPES = {
    "general", "candidate_grouping", "question_order", "output_preference",
    "source_fact", "concept_mapping",
}
_SCOPE_FIELDS = ("institution_id", "dataset_id", "concept_id", "classification_axis")
DEFAULT_QUERY_ROWS = 100
MAX_QUERY_ROWS = 1000
DEFAULT_QUERY_BYTES = 262_144
MAX_QUERY_BYTES = 1_048_576
DEFAULT_QUERY_TIME_MS = 250
MAX_QUERY_TIME_MS = 5_000
MAX_CACHE_ENTRIES = 128
MAX_CACHE_BYTES = 1_048_576


def _digest(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_text(name: str, value: str | None, maximum: int = 256) -> str | None:
    if value is None:
        return None
    required(value, name)
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the configured limit")
    return value


def _utc_timestamp(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    required(value, name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{name} must use UTC")
    return parsed.isoformat()


class KnowledgeStore:
    """Store scoped claims separately from raw task history and source observations."""

    def __init__(self, settings, *, clock=lambda: datetime.now(UTC)):
        self.settings, self.clock = settings, clock
        self._cache: OrderedDict[str, tuple[float, str, int]] = OrderedDict()
        self._cache_bytes = 0
        self._cache_lock = threading.RLock()
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.history = HistoryStore(settings)
        self.audit = AuditStore(self.history, clock=clock)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 2}:
                raise ValueError("unsupported history schema version")
            has_records = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_records'"
            ).fetchone() is not None
            has_current = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_current'"
            ).fetchone() is not None
            legacy_records = has_records and connection.execute(
                "SELECT 1 FROM knowledge_records LIMIT 1"
            ).fetchone() is not None
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_records (
                    record_id TEXT PRIMARY KEY,
                    task_id TEXT REFERENCES tasks(task_id),
                    feedback_id TEXT REFERENCES gate_a_records(record_id),
                    institution_id TEXT, dataset_id TEXT, concept_id TEXT,
                    classification_axis TEXT, record_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL, document TEXT NOT NULL, digest TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE
                );
                CREATE INDEX IF NOT EXISTS knowledge_by_scope ON knowledge_records(
                    institution_id, dataset_id, concept_id, classification_axis,
                    record_version, record_id);
                CREATE INDEX IF NOT EXISTS knowledge_by_task ON knowledge_records(
                    task_id, record_id);
                CREATE INDEX IF NOT EXISTS knowledge_by_feedback ON knowledge_records(
                    feedback_id, record_id);
                CREATE TABLE IF NOT EXISTS knowledge_events (
                    event_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL REFERENCES knowledge_records(record_id),
                    task_id TEXT REFERENCES tasks(task_id),
                    action TEXT NOT NULL, document TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS knowledge_events_by_record ON knowledge_events(
                    record_id, event_no);
                CREATE TABLE IF NOT EXISTS knowledge_current (
                    record_id TEXT PRIMARY KEY,
                    source_rowid INTEGER NOT NULL,
                    task_id TEXT, institution_id TEXT, dataset_id TEXT, concept_id TEXT,
                    classification_axis TEXT, provenance TEXT NOT NULL,
                    validation_status TEXT NOT NULL, review_status TEXT NOT NULL,
                    correction_type TEXT NOT NULL, source_version TEXT,
                    effective_from TEXT, effective_to TEXT,
                    record_version INTEGER NOT NULL, active INTEGER NOT NULL,
                    document_bytes INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS knowledge_current_scope ON knowledge_current(
                    institution_id, dataset_id, concept_id, classification_axis,
                    active, effective_from, effective_to, record_version, record_id);
                CREATE INDEX IF NOT EXISTS knowledge_current_task ON knowledge_current(
                    task_id, active, record_version, record_id);
                CREATE INDEX IF NOT EXISTS knowledge_current_by_provenance ON knowledge_current(
                    provenance, active, source_rowid DESC);
                CREATE TABLE IF NOT EXISTS knowledge_index_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    generation INTEGER NOT NULL, refresh_pending INTEGER NOT NULL,
                    refresh_cursor INTEGER NOT NULL, refreshed_at TEXT
                );
                INSERT OR IGNORE INTO knowledge_index_state(
                    singleton, generation, refresh_pending, refresh_cursor, refreshed_at
                ) VALUES (1, 0, 0, 0, NULL);
                CREATE TRIGGER IF NOT EXISTS knowledge_records_no_update
                BEFORE UPDATE ON knowledge_records BEGIN
                    SELECT RAISE(ABORT, 'knowledge records are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS knowledge_records_no_delete
                BEFORE DELETE ON knowledge_records BEGIN
                    SELECT RAISE(ABORT, 'knowledge records are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS knowledge_events_no_update
                BEFORE UPDATE ON knowledge_events BEGIN
                    SELECT RAISE(ABORT, 'knowledge events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS knowledge_events_no_delete
                BEFORE DELETE ON knowledge_events BEGIN
                    SELECT RAISE(ABORT, 'knowledge events are append-only'); END;
            """)
            if legacy_records and not has_current:
                connection.execute(
                    "UPDATE knowledge_index_state SET refresh_pending=1, refresh_cursor=0 "
                    "WHERE singleton=1"
                )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.settings.database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _now(self) -> str:
        value = self.clock()
        utc(value)
        return value.isoformat()

    def _clear_cache(self):
        with self._cache_lock:
            self._cache.clear()
            self._cache_bytes = 0

    def cache_info(self) -> dict:
        with self._cache_lock:
            return {"entries": len(self._cache), "bytes": self._cache_bytes,
                    "max_entries": MAX_CACHE_ENTRIES, "max_bytes": MAX_CACHE_BYTES}

    def clear_cache(self):
        """Explicitly discard only the in-memory query cache."""
        self._clear_cache()

    @staticmethod
    def _current_index_state(connection):
        row = connection.execute(
            "SELECT generation, refresh_pending, refresh_cursor, refreshed_at "
            "FROM knowledge_index_state WHERE singleton=1"
        ).fetchone()
        return {"generation": row[0], "refresh_pending": bool(row[1]),
                "refresh_cursor": row[2], "refreshed_at": row[3]}

    @staticmethod
    def _scope_tuple(document: dict):
        return tuple(document.get(name) for name in _SCOPE_FIELDS)

    @staticmethod
    def _concept_candidates(concept_id, concept_policy, max_depth):
        if concept_id is None:
            return {}
        if max_depth == 0 and concept_policy is None:
            return {concept_id: {"depth": 0, "path": [concept_id],
                                 "references": [], "relation": "exact_concept"}}
        if concept_policy is None:
            raise ValueError("concept expansion requires a versioned ConceptSearchPolicy")
        from macro_data_platform.mapping.concepts import ConceptSearchPolicy

        if not isinstance(concept_policy, ConceptSearchPolicy):
            raise TypeError("concept_policy must be a versioned ConceptSearchPolicy")
        canonical = concept_policy.canonical(concept_id)
        family = concept_policy.family(canonical)
        candidates = {canonical: {"depth": 0, "path": [canonical],
                                  "references": [], "relation": "exact_concept"}}
        if max_depth == 0 or canonical != family:
            return candidates
        queue = deque([(canonical, 0, (canonical,), ())])
        visited = {canonical}
        while queue:
            current, depth, path, references = queue.popleft()
            if depth >= max_depth:
                continue
            for link in concept_policy.links:
                if link.relation != "subtype" or link.parent != current:
                    continue
                child = concept_policy.canonical(link.child)
                if child in visited or concept_policy.family(child) != family:
                    continue
                visited.add(child)
                child_path = (*path, child)
                child_references = (*references, link.reference)
                candidates[child] = {
                    "depth": depth + 1, "path": list(child_path),
                    "references": list(child_references), "relation": "search_subtype",
                }
                if len(candidates) >= 16:
                    raise ValueError("concept expansion candidate budget exceeded")
                queue.append((child, depth + 1, child_path, child_references))
        return candidates

    def _project_record(self, connection, record_id: str):
        row = connection.execute(
            "SELECT rowid, document, digest FROM knowledge_records WHERE record_id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError("unknown knowledge record")
        source_rowid, encoded, expected_digest = row
        document = json.loads(encoded)
        if _digest(document) != expected_digest or document.get("record_id") != record_id:
            raise ValueError("knowledge record integrity check failed")
        latest = connection.execute(
            "SELECT action, document FROM knowledge_events WHERE record_id=? "
            "ORDER BY event_no DESC LIMIT 1", (record_id,),
        ).fetchone()
        review_status, active = "pending", 1
        if latest is not None:
            action, event_text = latest
            event = json.loads(event_text)
            if action == "review":
                review_status = event["status"]
            elif action == "cancel":
                review_status, active = "cancelled", 0
            elif action == "supersede":
                review_status, active = "superseded", 0
        correction_type = document.get("correction_type", "general")
        if document.get("correction_type") is None and document.get("feedback_id") is not None:
            feedback_scope = connection.execute(
                "SELECT correction_type FROM gate_a_feedback_index WHERE record_id=?",
                (document["feedback_id"],),
            ).fetchone()
            if feedback_scope is not None:
                correction_type = feedback_scope[0]
        connection.execute(
            "INSERT INTO knowledge_current(record_id, source_rowid, task_id, institution_id, "
            "dataset_id, concept_id, classification_axis, provenance, validation_status, "
            "review_status, correction_type, source_version, effective_from, effective_to, "
            "record_version, active, document_bytes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(record_id) DO UPDATE SET source_rowid=excluded.source_rowid, "
            "task_id=excluded.task_id, institution_id=excluded.institution_id, "
            "dataset_id=excluded.dataset_id, concept_id=excluded.concept_id, "
            "classification_axis=excluded.classification_axis, provenance=excluded.provenance, "
            "validation_status=excluded.validation_status, review_status=excluded.review_status, "
            "correction_type=excluded.correction_type, source_version=excluded.source_version, "
            "effective_from=excluded.effective_from, effective_to=excluded.effective_to, "
            "record_version=excluded.record_version, active=excluded.active, "
            "document_bytes=excluded.document_bytes",
            (record_id, source_rowid, document.get("task_id"), document.get("institution_id"),
             document.get("dataset_id"), document.get("concept_id"),
             document.get("classification_axis"), document["provenance"],
             document["validation_status"], review_status, correction_type,
             document.get("source_version"), document.get("effective_from"),
             document.get("effective_to"), document["record_version"], active,
             len(encoded.encode("utf-8"))),
        )
        connection.execute(
            "UPDATE knowledge_index_state SET generation=generation+1 WHERE singleton=1"
        )

    def refresh_index(self, *, batch_size: int = 250, restart: bool = False) -> dict:
        """Explicitly backfill/refresh a bounded page of the current knowledge projection."""
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("invalid knowledge refresh batch size")
        with self.history.transaction() as connection:
            state = self._current_index_state(connection)
            cursor = 0 if restart else state["refresh_cursor"]
            if not state["refresh_pending"] or restart:
                connection.execute(
                    "UPDATE knowledge_index_state SET refresh_pending=1, refresh_cursor=? "
                    "WHERE singleton=1", (cursor,),
                )
            rows = connection.execute(
                "SELECT rowid, record_id FROM knowledge_records WHERE rowid>? "
                "ORDER BY rowid LIMIT ?", (cursor, batch_size),
            ).fetchall()
            for _, record_id in rows:
                self._project_record(connection, record_id)
            if rows:
                cursor = rows[-1][0]
            more = connection.execute(
                "SELECT 1 FROM knowledge_records WHERE rowid>? LIMIT 1", (cursor,),
            ).fetchone() is not None
            refreshed_at = None
            if not more:
                refreshed_at = self._now()
                connection.execute(
                    "UPDATE knowledge_index_state SET refresh_pending=0, refresh_cursor=?, "
                    "refreshed_at=?, generation=generation+1 WHERE singleton=1",
                    (cursor, refreshed_at),
                )
            else:
                connection.execute(
                    "UPDATE knowledge_index_state SET refresh_pending=1, refresh_cursor=? "
                    "WHERE singleton=1", (cursor,),
                )
            state = self._current_index_state(connection)
            result = {"processed": len(rows), "cursor": cursor,
                      "refresh_pending": state["refresh_pending"],
                      "generation": state["generation"], "refreshed_at": refreshed_at}
        self._clear_cache()
        return result

    def _read_record(self, connection, record_id: str) -> dict:
        row = connection.execute(
            "SELECT document, digest FROM knowledge_records WHERE record_id=?", (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError("unknown knowledge record")
        document = json.loads(row[0])
        if _digest(document) != row[1] or document["record_id"] != record_id:
            raise ValueError("knowledge record integrity check failed")
        rows = connection.execute(
            "SELECT action, document FROM knowledge_events WHERE record_id=? ORDER BY event_no",
            (record_id,),
        ).fetchall()
        current = {**document, "review_status": "pending", "cancelled": False,
                   "superseded_by": None}
        for action, encoded in rows:
            event = json.loads(encoded)
            if action == "review":
                current["review_status"] = event["status"]
                current["review_note"] = event.get("note")
            elif action == "cancel":
                current["cancelled"] = True
                current["review_status"] = "cancelled"
                current["cancel_reason"] = event["reason"]
            elif action == "supersede":
                current["superseded_by"] = event["replacement_record_id"]
        current["revision"] = len(rows) + 1
        return current

    def register(self, statement: str | None = None, *, provenance: str,
                 validation_status: str | None = None,
                 task_id: str | None = None, feedback_id: str | None = None,
                 institution_id: str | None = None, dataset_id: str | None = None,
                 concept_id: str | None = None, classification_axis: str | None = None,
                 correction_type: str = "general",
                 source_version: str | None = None, effective_from: str | None = None,
                 effective_to: str | None = None, evidence_refs=(), supersedes_id: str | None = None,
                 idempotency_key: str | None = None) -> dict:
        if statement is not None:
            required(statement, "knowledge statement")
        if statement is not None and len(statement) > 16_000:
            raise ValueError("knowledge statement exceeds the configured limit")
        if provenance not in _PROVENANCE:
            raise ValueError("unknown knowledge provenance")
        if correction_type not in _CORRECTION_TYPES:
            raise ValueError("unknown knowledge correction type")
        if validation_status is None:
            validation_status = "inferred" if provenance == "inference" else "unverified"
        if validation_status not in _VALIDATION:
            raise ValueError("invalid knowledge validation status")
        if provenance == "inference" and validation_status == "verified":
            raise ValueError("inference cannot be marked as a verified source fact")
        if not isinstance(evidence_refs, (tuple, list)) or len(evidence_refs) > 32:
            raise ValueError("knowledge evidence references exceed the limit")
        refs = []
        for ref in evidence_refs:
            required(ref, "evidence reference")
            if len(ref) > 512:
                raise ValueError("knowledge evidence reference exceeds the limit")
            refs.append(ref)
        if provenance == "official_evidence" and not refs:
            raise ValueError("official evidence requires at least one evidence reference")
        if idempotency_key is not None:
            required(idempotency_key, "idempotency_key")
            if len(idempotency_key) > 128:
                raise ValueError("idempotency key exceeds the configured limit")
        scope = {name: _optional_text(name, value) for name, value in (
            ("institution_id", institution_id), ("dataset_id", dataset_id),
            ("concept_id", concept_id), ("classification_axis", classification_axis),
        )}
        source_version = _optional_text("source_version", source_version)
        effective_from = _utc_timestamp("effective_from", effective_from)
        effective_to = _utc_timestamp("effective_to", effective_to)
        if effective_from and effective_to and effective_from >= effective_to:
            raise ValueError("knowledge effective range must be increasing")
        if not any(scope.values()) and task_id is None and feedback_id is None:
            raise ValueError("knowledge input requires a task, feedback, or explicit scope")

        with self.history.transaction() as connection:
            feedback = None
            if feedback_id is not None:
                feedback = self.audit._feedback_view(connection, feedback_id)
                if feedback["cancelled"]:
                    raise ValueError("cancelled feedback cannot be registered as knowledge")
                expected_provenance = ("user_statement" if feedback["origin"] == "user"
                                       else "official_evidence")
                if provenance != expected_provenance:
                    raise ValueError("knowledge provenance cannot upgrade or relabel its feedback origin")
                if task_id is not None and task_id != feedback["task_id"]:
                    raise ValueError("knowledge feedback belongs to another task")
                task_id = feedback["task_id"]
                feedback_scope = feedback.get("scope", {})
                linked_correction_type = feedback_scope.get("correction_type", "general")
                if correction_type not in {"general", linked_correction_type}:
                    raise ValueError("knowledge correction type conflicts with linked feedback")
                correction_type = linked_correction_type
                for name in _SCOPE_FIELDS:
                    if scope[name] is None:
                        scope[name] = feedback_scope.get(name)
                    elif feedback_scope.get(name) not in {None, scope[name]}:
                        raise ValueError("knowledge scope conflicts with linked feedback")
                if source_version is None:
                    source_version = feedback_scope.get("source_version")
                if effective_from is None:
                    effective_from = feedback_scope.get("effective_from")
                if effective_to is None:
                    effective_to = feedback_scope.get("effective_to")
                if not refs:
                    refs = list(feedback_scope.get("evidence_refs", ()))
                effective_from = _utc_timestamp("effective_from", effective_from)
                effective_to = _utc_timestamp("effective_to", effective_to)
                if effective_from and effective_to and effective_from >= effective_to:
                    raise ValueError("knowledge effective range must be increasing")
                if statement is None:
                    statement = feedback.get("text", "")
                    required(statement, "linked feedback text")
            required(statement, "knowledge statement")
            if len(statement) > 16_000:
                raise ValueError("knowledge statement exceeds the configured limit")
            if task_id is not None:
                self.history.load(connection, task_id)
            if not any(scope.values()) and task_id is None:
                raise ValueError("knowledge input has no bounded scope")
            if idempotency_key is not None:
                existing = connection.execute(
                    "SELECT document, digest FROM knowledge_records WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    prior = json.loads(existing[0])
                    proposed = {
                        "task_id": task_id, "feedback_id": feedback_id, **scope,
                        "correction_type": correction_type,
                        "statement": statement, "provenance": provenance,
                        "validation_status": validation_status, "source_version": source_version,
                        "effective_from": effective_from, "effective_to": effective_to,
                        "evidence_refs": refs, "supersedes_id": supersedes_id,
                    }
                    if _digest(prior) != existing[1] or any(
                            prior.get(key) != value for key, value in proposed.items()):
                        raise ValueError("knowledge idempotency key conflict")
                    return self._read_record(connection, prior["record_id"])

            version_query = (
                "SELECT COALESCE(MAX(record_version), 0) FROM knowledge_records WHERE "
                "institution_id IS ? AND dataset_id IS ? AND concept_id IS ? "
                "AND classification_axis IS ?"
            )
            version_values = tuple(scope[name] for name in _SCOPE_FIELDS)
            version = connection.execute(version_query, version_values).fetchone()[0] + 1
            prior = None
            if supersedes_id is not None:
                prior = self._read_record(connection, supersedes_id)
                if self._scope_tuple(prior) != version_values:
                    raise ValueError("superseded knowledge record has a different scope")
                if not any(version_values) and prior.get("task_id") != task_id:
                    raise ValueError("task-only knowledge cannot cross task scope")
                if prior["cancelled"] or prior["superseded_by"]:
                    raise ValueError("knowledge record is no longer current")
                if version != prior["record_version"] + 1:
                    raise ValueError("knowledge replacement must supersede the latest scoped version")

            record_id = str(uuid4())
            document = {
                "record_id": record_id, "task_id": task_id, "feedback_id": feedback_id,
                **scope, "correction_type": correction_type,
                "statement": statement, "provenance": provenance,
                "validation_status": validation_status, "source_version": source_version,
                "effective_from": effective_from, "effective_to": effective_to,
                "evidence_refs": refs, "record_version": version,
                "supersedes_id": supersedes_id, "created_at": self._now(),
                "schema_version": 1,
            }
            encoded = json.dumps(document, ensure_ascii=False, allow_nan=False,
                                 sort_keys=True, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > MAX_KNOWLEDGE_BYTES:
                raise ValueError("knowledge record exceeds the configured size limit")
            connection.execute(
                "INSERT INTO knowledge_records(record_id, task_id, feedback_id, institution_id, "
                "dataset_id, concept_id, classification_axis, record_version, created_at, "
                "document, digest, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, task_id, feedback_id, scope["institution_id"], scope["dataset_id"],
                 scope["concept_id"], scope["classification_axis"], version,
                 document["created_at"], encoded, _digest(document), idempotency_key),
            )
            self._project_record(connection, record_id)
            if prior is not None:
                self._append_event(connection, supersedes_id, "supersede", task_id,
                                   {"replacement_record_id": record_id})
                self._project_record(connection, supersedes_id)
            if task_id is not None:
                self.history.event(connection, task_id, {
                    "kind": "KNOWLEDGE_INPUT_REGISTERED", "at": document["created_at"],
                    "record_id": record_id, "provenance": provenance,
                })
            self._clear_cache()
            return self._read_record(connection, record_id)

    def _append_event(self, connection, record_id, action, task_id, payload):
        document = {"event_id": str(uuid4()), "record_id": record_id, "action": action,
                    "task_id": task_id, "at": self._now(), **payload}
        connection.execute(
            "INSERT INTO knowledge_events(record_id, task_id, action, document) VALUES (?, ?, ?, ?)",
            (record_id, task_id, action,
             json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True)),
        )
        if task_id is not None:
            self.history.event(connection, task_id, {
                "kind": "KNOWLEDGE_" + action.upper(), "at": document["at"],
                "record_id": record_id,
            })
        return document

    def review(self, record_id: str, *, status: str, reviewer: str, note: str | None = None):
        if status not in _REVIEW:
            raise ValueError("invalid knowledge review status")
        required(reviewer, "reviewer")
        if len(reviewer) > 128 or (note is not None and (not isinstance(note, str) or len(note) > 1000)):
            raise ValueError("knowledge review metadata exceeds the limit")
        with self.history.transaction() as connection:
            current = self._read_record(connection, record_id)
            if current["cancelled"] or current["superseded_by"]:
                raise ValueError("inactive knowledge record cannot be reviewed")
            if current["provenance"] == "inference" and status == "accepted":
                raise ValueError("inference cannot be approved as a verified knowledge fact")
            event = self._append_event(connection, record_id, "review", current["task_id"], {
                "status": status, "reviewer": reviewer, "note": note,
            })
            self._project_record(connection, record_id)
            self._clear_cache()
            return event

    def cancel(self, record_id: str, *, reason: str, actor: str):
        required(reason, "cancellation reason")
        required(actor, "actor")
        if len(reason) > 1000 or len(actor) > 128:
            raise ValueError("knowledge cancellation metadata exceeds the limit")
        with self.history.transaction() as connection:
            current = self._read_record(connection, record_id)
            if current["cancelled"] or current["superseded_by"]:
                raise ValueError("inactive knowledge record cannot be cancelled")
            event = self._append_event(connection, record_id, "cancel", current["task_id"], {
                "reason": reason, "actor": actor,
            })
            self._project_record(connection, record_id)
            self._clear_cache()
            return event

    def get(self, record_id: str) -> dict:
        with self._connect() as connection:
            return self._read_record(connection, record_id)

    def history_for(self, record_id: str) -> list[dict]:
        with self._connect() as connection:
            self._read_record(connection, record_id)
            rows = connection.execute(
                "SELECT document FROM knowledge_events WHERE record_id=? ORDER BY event_no",
                (record_id,),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def for_task(self, task_id: str, *, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid knowledge query limit")
        with self._connect() as connection:
            self.history.load(connection, task_id)
            rows = connection.execute(
                "SELECT record_id FROM knowledge_records WHERE task_id=? "
                "ORDER BY record_id LIMIT ?", (task_id, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise ValueError("knowledge query budget exceeded")
            return [self._read_record(connection, row[0]) for row in rows]

    def query(self, *, institution_id: str | None = None, dataset_id: str | None = None,
              concept_id: str | None = None, classification_axis: str | None = None,
              task_id: str | None = None, source_version: str | None = None,
              as_of: str | None = None, max_rows: int = DEFAULT_QUERY_ROWS,
              max_bytes: int = DEFAULT_QUERY_BYTES, max_time_ms: int = DEFAULT_QUERY_TIME_MS,
              max_depth: int = 0, explicit_correction_types=(), policy_version: str = "1",
              concept_policy=None) -> dict:
        """Search a bounded current projection using only an optional reviewed subtype policy."""
        scope_values = {name: _optional_text(name, value) for name, value in (
            ("institution_id", institution_id), ("dataset_id", dataset_id),
            ("concept_id", concept_id), ("classification_axis", classification_axis),
        )}
        task_id = _optional_text("task_id", task_id)
        source_version = _optional_text("source_version", source_version)
        if not any(scope_values.values()) and task_id is None:
            raise ValueError("knowledge query requires a bounded task, institution, dataset, concept, or axis")
        if type(max_rows) is not int or not 1 <= max_rows <= MAX_QUERY_ROWS:
            raise ValueError("knowledge row budget is outside the supported range")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_QUERY_BYTES:
            raise ValueError("knowledge byte budget is outside the supported range")
        if type(max_time_ms) is not int or not 1 <= max_time_ms <= MAX_QUERY_TIME_MS:
            raise ValueError("knowledge time budget is outside the supported range")
        if type(max_depth) is not int or not 0 <= max_depth <= 4:
            raise ValueError("concept search depth must be between 0 and 4")
        if max_depth and concept_id is None:
            raise ValueError("concept expansion requires a concept_id")
        if max_depth and concept_policy is None:
            raise ValueError("concept expansion requires a versioned ConceptSearchPolicy")
        concept_candidates = self._concept_candidates(concept_id, concept_policy, max_depth)
        if len(concept_candidates) > 16:
            raise ValueError("concept expansion candidate budget exceeded")
        if concept_policy is None:
            concept_policy_version = None
            concept_policy_fingerprint = None
        else:
            from macro_data_platform.mapping.concepts import ConceptSearchPolicy
            if not isinstance(concept_policy, ConceptSearchPolicy):
                raise TypeError("concept_policy must be a versioned ConceptSearchPolicy")
            concept_policy_version = concept_policy.version
            concept_policy_fingerprint = concept_policy.fingerprint
        if not isinstance(explicit_correction_types, (tuple, list, set)):
            raise TypeError("explicit correction types must be a collection")
        if any(not isinstance(value, str) for value in explicit_correction_types):
            raise TypeError("explicit correction types must be strings")
        explicit_types = tuple(sorted(set(explicit_correction_types)))
        if any(value not in {"general", "candidate_grouping", "question_order",
                             "output_preference", "source_fact", "concept_mapping"}
               for value in explicit_types):
            raise ValueError("unknown explicit correction type")
        if not isinstance(policy_version, str) or not policy_version.strip() or len(policy_version) > 128:
            raise ValueError("invalid query policy version")
        if as_of is None:
            now = self.clock()
            utc(now)
            as_of_value = now.replace(microsecond=0).isoformat()
        else:
            as_of_value = _utc_timestamp("as_of", as_of)

        started = time.perf_counter()
        with self._connect() as connection:
            state = self._current_index_state(connection)
        cache_request = {
            **scope_values, "task_id": task_id, "source_version": source_version,
            "as_of": as_of_value, "max_rows": max_rows, "max_bytes": max_bytes,
            "max_time_ms": max_time_ms, "max_depth": max_depth,
            "explicit_correction_types": explicit_types, "policy_version": policy_version,
            "concept_policy_fingerprint": concept_policy_fingerprint,
            "index_generation": state["generation"],
        }
        cache_key = _digest(cache_request)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_key = cache_key
                expires, encoded, size = cached
                if expires > time.monotonic():
                    with self._connect() as connection:
                        current_state = self._current_index_state(connection)
                    if current_state["generation"] == state["generation"]:
                        self._cache.move_to_end(cache_key)
                        result = json.loads(encoded)
                        cache_state = self.cache_info()
                        result["metrics"].update({
                            "cache_hit": True, "cache_bytes": cache_state["bytes"],
                            "cache_entries": cache_state["entries"],
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                            "index_rows_read": 0, "evidence_bytes_read": 0,
                        })
                        return result
                    del self._cache[cached_key]
                    self._cache_bytes -= size
                    state = current_state
                    cache_request["index_generation"] = state["generation"]
                    cache_key = _digest(cache_request)
                else:
                    del self._cache[cached_key]
                    self._cache_bytes -= size

        conditions = ["active=1", "(effective_from IS NULL OR effective_from<=?)",
                      "(effective_to IS NULL OR effective_to>?)"]
        parameters: list[object] = [as_of_value, as_of_value]
        for name, value in scope_values.items():
            if name == "concept_id":
                continue
            if value is not None:
                conditions.append(f"({name} IS NULL OR {name}=?)")
                parameters.append(value)
        if concept_id is not None:
            concept_ids = tuple(concept_candidates)
            placeholders = ",".join("?" for _ in concept_ids)
            conditions.append(f"(concept_id IS NULL OR concept_id IN ({placeholders}))")
            parameters.extend(concept_ids)
        if source_version is not None:
            conditions.append("source_version=?")
            parameters.append(source_version)
        if task_id is not None:
            if institution_id is not None:
                conditions.append("(task_id=? OR institution_id=?)")
                parameters.extend((task_id, institution_id))
            else:
                conditions.append("(task_id=? OR (task_id IS NULL AND institution_id IS NULL))")
                parameters.append(task_id)
        sql = (
            "SELECT record_id, source_rowid, task_id, institution_id, dataset_id, concept_id, "
            "classification_axis, provenance, validation_status, review_status, correction_type, "
            "source_version, effective_from, effective_to, record_version, document_bytes "
            "FROM knowledge_current WHERE " + " AND ".join(conditions) +
            " ORDER BY institution_id, dataset_id, concept_id, classification_axis, "
            "record_version DESC, record_id LIMIT ?"
        )
        parameters.append(max_rows + 1)
        deadline = time.perf_counter() + max_time_ms / 1000
        timed_out = False
        rows = []
        try:
            with self._connect() as connection:
                connection.execute("BEGIN")
                connection.set_progress_handler(lambda: int(time.perf_counter() >= deadline), 500)
                try:
                    rows = connection.execute(sql, parameters).fetchall()
                except sqlite3.OperationalError as exc:
                    if "interrupted" not in str(exc).lower():
                        raise
                    timed_out = True
                finally:
                    connection.set_progress_handler(None, 0)
                if time.perf_counter() >= deadline:
                    timed_out = True
                state = self._current_index_state(connection)
                truncated = len(rows) > max_rows
                groups = {}
                for row in rows:
                    scope_key = tuple(row[index] for index in (3, 4, 5, 6))
                    if not any(scope_key):
                        scope_key = (*scope_key, row[2])
                    groups[scope_key] = groups.get(scope_key, 0) + 1
                conflicting_groups = {key for key, count in groups.items() if count > 1}
                rows = rows[:max_rows]
                records = []
                evidence_bytes_read = 0
                byte_limited = False
                for row in rows:
                    if time.perf_counter() >= deadline:
                        timed_out = True
                        break
                    (record_id, _, row_task_id, row_institution, row_dataset, row_concept,
                     row_axis, provenance, validation_status, review_status, correction_type,
                     _row_source_version, _effective_from, _effective_to, _record_version,
                     document_bytes) = row
                    if evidence_bytes_read + document_bytes > max_bytes:
                        byte_limited = True
                        break
                    stored = connection.execute(
                        "SELECT document, digest FROM knowledge_records WHERE record_id=?",
                        (record_id,),
                    ).fetchone()
                    if stored is None:
                        state["refresh_pending"] = True
                        timed_out = True
                        break
                    document = json.loads(stored[0])
                    if _digest(document) != stored[1] or document.get("record_id") != record_id:
                        raise ValueError("knowledge record integrity check failed")
                    evidence_bytes_read += document_bytes
                    fields = (row_institution, row_dataset, row_concept, row_axis)
                    scope_key = fields if any(fields) else (*fields, row_task_id)
                    conflict = scope_key in conflicting_groups
                    same_institution = (institution_id is not None
                                        and row_institution == institution_id)
                    requested_scope_matches = all(
                        requested is None or stored_value == requested
                        for requested, stored_value in zip(
                            scope_values.values(),
                            (row_institution, row_dataset, row_concept, row_axis),
                        )
                    )
                    exact_task = task_id is not None and row_task_id == task_id
                    current_explicit_override = correction_type in explicit_types
                    reusable = False
                    requires_confirmation = False
                    reason = "record is a candidate only until validation and review complete"
                    if provenance == "inference":
                        reason = "inference is quarantined from experience reuse"
                    elif provenance == "official_evidence":
                        reusable = (validation_status == "verified" and review_status == "accepted"
                                    and bool(document.get("evidence_refs"))
                                    and same_institution
                                    and requested_scope_matches
                                    and not state["refresh_pending"])
                        reason = ("verified official evidence is eligible in this scope"
                                  if reusable else "official evidence needs verification, review, or scope match")
                    elif provenance == "user_statement":
                        reusable = (review_status == "accepted" and same_institution
                                    and correction_type in {"candidate_grouping", "question_order",
                                                           "output_preference"}
                                    and not state["refresh_pending"])
                        requires_confirmation = reusable
                        reason = ("reviewed user guidance is a suggestion and needs current-task confirmation"
                                  if reusable else "user statement is not an official source fact")
                    if exact_task and provenance == "user_statement" and review_status == "accepted":
                        reusable = correction_type in {"candidate_grouping", "question_order",
                                                       "output_preference"}
                        requires_confirmation = reusable
                        reason = ("task-scoped user guidance requires current-task confirmation"
                                  if reusable else "task-scoped correction is not an official source fact")
                    if current_explicit_override:
                        reusable = False
                        requires_confirmation = False
                        reason = "current explicit instruction overrides this stored preference"
                    if conflict:
                        reusable = False
                        requires_confirmation = False
                        reason = "multiple active claims share this exact scope; review all before reuse"
                    if truncated or timed_out or byte_limited or state["refresh_pending"]:
                        reusable = False
                        requires_confirmation = False
                        if state["refresh_pending"]:
                            reason = "knowledge index refresh is incomplete; reuse is withheld"
                        elif truncated:
                            reason = "row budget exhausted; results are incomplete and reuse is withheld"
                        elif byte_limited:
                            reason = "evidence byte budget exhausted; results are incomplete and reuse is withheld"
                        elif timed_out:
                            reason = "time budget exhausted; results are incomplete and reuse is withheld"
                    concept_match = None
                    if concept_id is not None:
                        if row_concept is None:
                            concept_match = {"relation": "scope_only", "path": [],
                                             "references": [], "depth": None}
                        else:
                            concept_match = concept_candidates[row_concept]
                            if concept_match["relation"] == "search_subtype":
                                reusable = False
                                requires_confirmation = not current_explicit_override and not conflict
                                subtype_reason = (
                                    "included through a reviewed search subtype relation; this is not "
                                    "statistical equivalence or an automatic substitution"
                                )
                                reason = (reason + "; " + subtype_reason
                                          if current_explicit_override or conflict or truncated
                                          or timed_out or byte_limited or state["refresh_pending"]
                                          else subtype_reason)
                    records.append({
                        **document, "review_status": review_status,
                        "cancelled": False, "superseded_by": None,
                        "reusable": reusable, "requires_confirmation": requires_confirmation,
                        "conflict": conflict, "reason": reason,
                        "quarantined": provenance == "inference",
                        "search_concept_match": (concept_match["relation"]
                                                  if concept_match else None),
                        "search_concept_path": (concept_match["path"] if concept_match else []),
                        "search_concept_evidence_refs": (concept_match["references"]
                                                         if concept_match else []),
                        "search_concept_depth": (concept_match["depth"]
                                                 if concept_match else None),
                    })
                partial = bool(truncated or timed_out or byte_limited or state["refresh_pending"])
                if partial:
                    for item in records:
                        item["reusable"] = False
                        item["requires_confirmation"] = False
                uncertainties = []
                if state["refresh_pending"]:
                    uncertainties.append("knowledge_index_refresh_pending")
                if truncated:
                    uncertainties.append("row_budget_exhausted")
                    uncertainties.append("potential_conflicts_unchecked_due_to_row_budget")
                if byte_limited:
                    uncertainties.append("evidence_byte_budget_exhausted")
                if timed_out:
                    uncertainties.append("time_budget_exhausted")
                if conflicting_groups:
                    uncertainties.append("conflicting_active_claims")
                if any(item.get("search_concept_match") == "search_subtype" for item in records):
                    uncertainties.append("subtype_search_candidates_require_semantic_choice")
                if any(not item["reusable"] for item in records):
                    uncertainties.append("some_records_are_not_reusable")
                result = {
                    "status": "partial" if partial else "complete",
                    "scope": {**scope_values, "task_id": task_id,
                              "source_version": source_version, "as_of": as_of_value,
                              "concept_search": {"max_depth": max_depth,
                                                 "policy_version": concept_policy_version,
                                                 "policy_fingerprint": concept_policy_fingerprint}},
                    "records": records, "needs_review": bool(uncertainties),
                    "conflict_groups": len(conflicting_groups),
                    "refresh_pending": state["refresh_pending"],
                    "uncertainties": uncertainties,
                    "metrics": {
                        "index_generation": state["generation"],
                        "index_rows_read": min(len(rows) + int(truncated), max_rows + 1),
                        "records_returned": len(records),
                        "evidence_bytes_read": evidence_bytes_read,
                        "expansion_depth": max((item["depth"] for item in concept_candidates.values()),
                                               default=0),
                        "expansion_candidates": max(0, len(concept_candidates) - 1),
                        "cache_hit": False,
                        "cache_entries": self.cache_info()["entries"],
                        "cache_bytes": self.cache_info()["bytes"],
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                }
        except sqlite3.OperationalError as exc:
            if "interrupted" not in str(exc).lower():
                raise
            partial = True
            result = {
                "status": "partial", "scope": {**scope_values, "task_id": task_id,
                                                   "source_version": source_version,
                                                   "as_of": as_of_value,
                                                   "concept_search": {"max_depth": max_depth,
                                                                      "policy_version": concept_policy_version,
                                                                      "policy_fingerprint": concept_policy_fingerprint}},
                "records": [], "needs_review": True, "conflict_groups": 0,
                "refresh_pending": state["refresh_pending"],
                "uncertainties": ["time_budget_exhausted"],
                "metrics": {"index_generation": state["generation"],
                            "index_rows_read": 0, "records_returned": 0,
                            "evidence_bytes_read": 0,
                            "expansion_depth": max((item["depth"] for item in concept_candidates.values()),
                                                   default=0),
                            "expansion_candidates": max(0, len(concept_candidates) - 1),
                            "cache_hit": False, "cache_entries": self.cache_info()["entries"],
                            "cache_bytes": self.cache_info()["bytes"],
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)},
            }
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        if not partial and size <= MAX_CACHE_BYTES:
            now = time.monotonic()
            with self._cache_lock:
                cache_request["index_generation"] = state["generation"]
                cache_key = _digest(cache_request)
                self._cache[cache_key] = (now + 1.0, encoded, size)
                self._cache.move_to_end(cache_key)
                self._cache_bytes += size
                while (len(self._cache) > MAX_CACHE_ENTRIES
                       or self._cache_bytes > MAX_CACHE_BYTES):
                    _, (_, _, removed_size) = self._cache.popitem(last=False)
                    self._cache_bytes -= removed_size
                result["metrics"]["cache_entries"] = len(self._cache)
                result["metrics"]["cache_bytes"] = self._cache_bytes
        return result

    def explain_query_plan(self, *, institution_id: str | None = None,
                           dataset_id: str | None = None, concept_id: str | None = None,
                           classification_axis: str | None = None) -> tuple[str, ...]:
        """Return SQLite's plan for the indexed scope lookup, for diagnostics and Gate D."""
        values = {"institution_id": institution_id, "dataset_id": dataset_id,
                  "concept_id": concept_id, "classification_axis": classification_axis}
        if not any(values.values()):
            raise ValueError("query plan requires a bounded scope")
        where = ["active=1"]
        params = []
        for name, value in values.items():
            if value is not None:
                where.append(f"({name} IS NULL OR {name}=?)")
                params.append(value)
        sql = "SELECT record_id FROM knowledge_current WHERE " + " AND ".join(where)
        with self._connect() as connection:
            rows = connection.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        return tuple(row[3] for row in rows)
