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


_CORRECTION_TYPES = {
    "general", "candidate_grouping", "question_order", "output_preference",
    "source_fact", "concept_mapping",
}
_PROVENANCE = {"user_statement", "official_evidence", "inference"}
_VALIDATION = {"unverified", "verified", "rejected", "inferred", "needs_review"}
_REVIEW = {"accepted", "rejected", "deferred"}
_SCOPE_TEXT_FIELDS = {
    "institution_id", "dataset_id", "concept_id", "classification_axis", "source_version",
}


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
                "CREATE INDEX IF NOT EXISTS gate_a_by_kind ON gate_a_records(kind)",
                ("CREATE UNIQUE INDEX IF NOT EXISTS gate_a_by_stage "
                "ON gate_a_records(kind, stage_run_id) WHERE kind != 'feedback'"),
                ("CREATE TABLE IF NOT EXISTS gate_a_observations ("
                "validation_id TEXT NOT NULL REFERENCES gate_a_records(record_id), "
                "position INTEGER NOT NULL, document TEXT NOT NULL, "
                "PRIMARY KEY(validation_id, position))"),
                ("CREATE TABLE IF NOT EXISTS gate_a_feedback_events ("
                "event_no INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL "
                "REFERENCES gate_a_records(record_id), task_id TEXT NOT NULL "
                "REFERENCES tasks(task_id), revision INTEGER NOT NULL, action TEXT NOT NULL, "
                "document TEXT NOT NULL, UNIQUE(record_id, revision))"),
                ("CREATE INDEX IF NOT EXISTS feedback_events_by_record "
                "ON gate_a_feedback_events(record_id, revision)"),
                ("CREATE TABLE IF NOT EXISTS gate_a_feedback_index ("
                "record_id TEXT PRIMARY KEY REFERENCES gate_a_records(record_id), "
                "task_id TEXT NOT NULL REFERENCES tasks(task_id), stage_run_id TEXT, "
                "related_record_id TEXT, error_code TEXT, institution_id TEXT, "
                "dataset_id TEXT, concept_id TEXT, correction_type TEXT NOT NULL, "
                "provenance TEXT NOT NULL, validation_status TEXT NOT NULL, "
                "effective_from TEXT, effective_to TEXT)"),
                ("CREATE INDEX IF NOT EXISTS feedback_by_task "
                "ON gate_a_feedback_index(task_id, record_id)"),
                ("CREATE INDEX IF NOT EXISTS feedback_by_error "
                "ON gate_a_feedback_index(task_id, error_code, record_id)"),
                ("CREATE INDEX IF NOT EXISTS feedback_by_institution "
                "ON gate_a_feedback_index(institution_id, correction_type, record_id)"),
                ("CREATE TRIGGER IF NOT EXISTS gate_a_feedback_events_no_update "
                "BEFORE UPDATE ON gate_a_feedback_events BEGIN "
                "SELECT RAISE(ABORT, 'feedback events are append-only'); END"),
                ("CREATE TRIGGER IF NOT EXISTS gate_a_feedback_events_no_delete "
                "BEFORE DELETE ON gate_a_feedback_events BEGIN "
                "SELECT RAISE(ABORT, 'feedback events are append-only'); END"),
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

    @staticmethod
    def _scope_document(*, correction_type, provenance, validation_status, institution_id,
                        dataset_id, concept_id, classification_axis, source_version,
                        effective_from, effective_to, evidence_refs, version_no,
                        supersedes_feedback_id):
        if correction_type not in _CORRECTION_TYPES:
            raise ValueError("unknown feedback correction type")
        if provenance not in _PROVENANCE or validation_status not in _VALIDATION:
            raise ValueError("invalid feedback provenance or validation status")
        for name, value in (("institution_id", institution_id), ("dataset_id", dataset_id),
                            ("concept_id", concept_id), ("classification_axis", classification_axis),
                            ("source_version", source_version)):
            if value is not None:
                required(value, name)
                if len(value) > 256:
                    raise ValueError(f"{name} is too long")
        for name, value in (("effective_from", effective_from), ("effective_to", effective_to)):
            if value is not None:
                required(value, name)
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(f"{name} must be an ISO timestamp") from exc
                if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
                    raise ValueError(f"{name} must use UTC")
        if effective_from is not None and effective_to is not None:
            start = datetime.fromisoformat(effective_from)
            end = datetime.fromisoformat(effective_to)
            if start >= end:
                raise ValueError("feedback effective range must be increasing")
        if type(version_no) is not int or version_no < 1:
            raise ValueError("feedback version must be a positive integer")
        if not isinstance(evidence_refs, (tuple, list)) or len(evidence_refs) > 32:
            raise ValueError("feedback evidence references exceed the limit")
        if any(not isinstance(ref, str) or not ref.strip() or len(ref) > 512
               for ref in evidence_refs):
            raise ValueError("invalid feedback evidence reference")
        if provenance == "official_evidence" and not evidence_refs:
            raise ValueError("official evidence feedback requires an evidence reference")
        if supersedes_feedback_id is not None:
            required(supersedes_feedback_id, "supersedes_feedback_id")
        return {
            "correction_type": correction_type,
            "provenance": provenance,
            "validation_status": validation_status,
            "institution_id": institution_id,
            "dataset_id": dataset_id,
            "concept_id": concept_id,
            "classification_axis": classification_axis,
            "source_version": source_version,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "evidence_refs": list(evidence_refs),
            "version_no": version_no,
            "supersedes_feedback_id": supersedes_feedback_id,
        }

    @staticmethod
    def _scope_matches(left, right):
        return all(left.get(key) == right.get(key) for key in (
            "institution_id", "dataset_id", "concept_id", "classification_axis"))

    def add_feedback(self, task_id, *, text, category="note", origin="user",
                     stage_run_id=None, record_id=None, idempotency_key=None,
                     correction_type="general", institution_id=None, dataset_id=None,
                     concept_id=None, classification_axis=None, source_version=None,
                     effective_from=None, effective_to=None, evidence_refs=(), provenance=None,
                     validation_status=None, version_no=1, supersedes_feedback_id=None):
        required(text, "feedback text")
        if len(text) > 2000 or category not in {"note", "correction", "problem"}:
            raise ValueError("invalid feedback text or category")
        if origin not in {"user", "verification"}:
            raise ValueError("unknown feedback origin")
        if provenance is None:
            provenance = "user_statement" if origin == "user" else "official_evidence"
        if ((origin == "user" and provenance != "user_statement")
                or (origin == "verification" and provenance != "official_evidence")):
            raise ValueError("feedback provenance must match its explicit origin")
        if validation_status is None:
            validation_status = "inferred" if provenance == "inference" else "unverified"
        scope = self._scope_document(
            correction_type=correction_type, provenance=provenance,
            validation_status=validation_status, institution_id=institution_id,
            dataset_id=dataset_id, concept_id=concept_id, classification_axis=classification_axis,
            source_version=source_version, effective_from=effective_from, effective_to=effective_to,
            evidence_refs=evidence_refs, version_no=version_no,
            supersedes_feedback_id=supersedes_feedback_id,
        )
        if idempotency_key is not None:
            required(idempotency_key, "feedback idempotency key")
            if len(idempotency_key) > 128:
                raise ValueError("feedback key too long")
        payload = {"text": text, "category": category, "origin": origin,
                   "related_record_id": record_id, "status": "recorded_unreviewed",
                   "review_status": "recorded_unreviewed", "scope": scope}
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
            if supersedes_feedback_id is not None:
                superseded = self._load(connection, supersedes_feedback_id, "feedback")
                if superseded["task_id"] != task_id or not self._scope_matches(
                        superseded.get("scope", {}), scope):
                    raise ValueError("superseded feedback belongs to another scope")
            if idempotency_key is not None:
                row = connection.execute(
                    "SELECT document FROM gate_a_records WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    prior = json.loads(row[0])
                    legacy_scope = self._scope_document(
                        correction_type="general",
                        provenance="user_statement",
                        validation_status="unverified",
                        institution_id=None, dataset_id=None, concept_id=None,
                        classification_axis=None, source_version=None, effective_from=None,
                        effective_to=None, evidence_refs=(), version_no=1,
                        supersedes_feedback_id=None,
                    )
                    normalized = {**prior, "scope": prior.get("scope", legacy_scope),
                                  "review_status": prior.get("review_status", prior.get(
                                      "status", "recorded_unreviewed"))}
                    if (prior["kind"] != "feedback" or prior["task_id"] != task_id
                            or prior["stage_run_id"] != stage_run_id
                            or any(normalized.get(key) != value for key, value in payload.items())):
                        raise ValueError("feedback idempotency key conflict")
                    indexed = connection.execute(
                        "SELECT 1 FROM gate_a_feedback_index WHERE record_id=?",
                        (prior["record_id"],),
                    ).fetchone()
                    if indexed is None:
                        prior_scope = normalized["scope"]
                        related_error = None
                        related_id = prior.get("related_record_id")
                        if related_id is not None:
                            related = self._load(connection, related_id)
                            if related.get("kind") == "incident":
                                related_error = related.get("error_code")
                        connection.execute(
                            "INSERT INTO gate_a_feedback_index(record_id, task_id, stage_run_id, "
                            "related_record_id, error_code, institution_id, dataset_id, concept_id, "
                            "correction_type, provenance, validation_status, effective_from, effective_to) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (prior["record_id"], task_id, stage_run_id, related_id, related_error,
                             prior_scope.get("institution_id"), prior_scope.get("dataset_id"),
                             prior_scope.get("concept_id"), prior_scope["correction_type"],
                             prior_scope["provenance"], prior_scope["validation_status"],
                             prior_scope.get("effective_from"), prior_scope.get("effective_to")),
                        )
                    return prior
            saved = self._insert(connection, "feedback", task_id, stage_run_id, payload,
                                 idempotency_key)
            related_error = None
            if record_id is not None and related.get("kind") == "incident":
                related_error = related.get("error_code")
            connection.execute(
                "INSERT INTO gate_a_feedback_index(record_id, task_id, stage_run_id, "
                "related_record_id, error_code, institution_id, dataset_id, concept_id, "
                "correction_type, provenance, validation_status, effective_from, effective_to) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (saved["record_id"], task_id, stage_run_id, record_id, related_error,
                 institution_id, dataset_id, concept_id, correction_type, provenance,
                 validation_status, effective_from, effective_to),
            )
            return saved

    @staticmethod
    def _feedback_view(connection, record_id):
        original = AuditStore._load(connection, record_id, "feedback")
        current = dict(original)
        current.setdefault("scope", AuditStore._scope_document(
            correction_type="general", provenance="user_statement", validation_status="unverified",
            institution_id=None, dataset_id=None, concept_id=None, classification_axis=None,
            source_version=None, effective_from=None, effective_to=None, evidence_refs=(),
            version_no=1, supersedes_feedback_id=None,
        ))
        current.setdefault("review_status", current.get("status", "recorded_unreviewed"))
        current["original_text"] = original["text"]
        current["revision"] = 1
        current["cancelled"] = False
        rows = connection.execute(
            "SELECT revision, action, document FROM gate_a_feedback_events "
            "WHERE record_id=? ORDER BY revision", (record_id,),
        ).fetchall()
        for revision, action, encoded in rows:
            event = json.loads(encoded)
            if action == "edit":
                for key, value in event["changes"].items():
                    current[key] = value
                current["review_status"] = "recorded_unreviewed"
            elif action == "review":
                current["review_status"] = event["review_status"]
                current["review_note"] = event.get("note")
            elif action == "cancel":
                current["review_status"] = "cancelled"
                current["cancelled"] = True
                current["cancel_reason"] = event["reason"]
            current["revision"] = revision
        return current

    def _append_feedback_event(self, connection, feedback, action, document):
        revision = feedback["revision"] + 1
        at = self.now()
        event = {"event_id": str(uuid4()), "action": action, "revision": revision,
                 "at": at, **document}
        connection.execute(
            "INSERT INTO gate_a_feedback_events(record_id, task_id, revision, action, document) "
            "VALUES (?, ?, ?, ?, ?)",
            (feedback["record_id"], feedback["task_id"], revision, action,
             json.dumps(event, ensure_ascii=False, allow_nan=False, sort_keys=True)),
        )
        AuditStore._record_feedback_index(connection, feedback, action, document)
        self.history.event(connection, feedback["task_id"], {
            "kind": "AUDIT_FEEDBACK_" + action.upper(), "at": at,
            "record_id": feedback["record_id"], "revision": revision,
        })
        return event

    @staticmethod
    def _record_feedback_index(connection, feedback, action, document):
        if action == "edit" and "scope" in document["changes"]:
            scope = document["changes"]["scope"]
            connection.execute(
                "UPDATE gate_a_feedback_index SET institution_id=?, dataset_id=?, concept_id=?, "
                "correction_type=?, provenance=?, validation_status=?, effective_from=?, "
                "effective_to=? WHERE record_id=?",
                (scope.get("institution_id"), scope.get("dataset_id"), scope.get("concept_id"),
                 scope["correction_type"], scope["provenance"], scope["validation_status"],
                 scope.get("effective_from"), scope.get("effective_to"), feedback["record_id"]),
            )

    def get_feedback(self, record_id):
        with self.history._connect() as connection:
            return self._feedback_view(connection, record_id)

    def feedback_history(self, record_id):
        with self.history._connect() as connection:
            self._load(connection, record_id, "feedback")
            rows = connection.execute(
                "SELECT document FROM gate_a_feedback_events WHERE record_id=? ORDER BY revision",
                (record_id,),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def edit_feedback(self, record_id, *, expected_revision, changes):
        if not isinstance(changes, dict) or not changes or not set(changes) <= {
            "text", "category", "scope",
        }:
            raise ValueError("feedback edits may change text, category, or scope")
        with self.history.transaction() as connection:
            current = self._feedback_view(connection, record_id)
            if type(expected_revision) is not int or expected_revision != current["revision"]:
                raise ValueError("feedback revision conflict")
            if current["cancelled"]:
                raise ValueError("cancelled feedback cannot be edited")
            edited = dict(changes)
            if "text" in edited:
                required(edited["text"], "feedback text")
                if len(edited["text"]) > 2000:
                    raise ValueError("feedback text is too long")
            if "category" in edited and edited["category"] not in {"note", "correction", "problem"}:
                raise ValueError("invalid feedback category")
            if "scope" in edited:
                prior = current["scope"]
                supplied = edited["scope"]
                if not isinstance(supplied, dict):
                    raise ValueError("feedback scope must be an object")
                if not set(supplied) <= set(prior):
                    raise ValueError("feedback scope contains unsupported fields")
                merged = {**prior, **supplied}
                rebuilt = self._scope_document(
                    correction_type=merged["correction_type"], provenance=merged["provenance"],
                    validation_status=merged["validation_status"],
                    institution_id=merged.get("institution_id"), dataset_id=merged.get("dataset_id"),
                    concept_id=merged.get("concept_id"),
                    classification_axis=merged.get("classification_axis"),
                    source_version=merged.get("source_version"),
                    effective_from=merged.get("effective_from"), effective_to=merged.get("effective_to"),
                    evidence_refs=merged.get("evidence_refs", ()),
                    version_no=merged["version_no"],
                    supersedes_feedback_id=merged.get("supersedes_feedback_id"),
                )
                if rebuilt["supersedes_feedback_id"] is not None:
                    superseded = self._load(connection, rebuilt["supersedes_feedback_id"], "feedback")
                    if (superseded["task_id"] != current["task_id"]
                            or not self._scope_matches(superseded.get("scope", {}), rebuilt)):
                        raise ValueError("superseded feedback belongs to another scope")
                edited["scope"] = rebuilt
            return self._append_feedback_event(connection, current, "edit", {"changes": edited})

    def review_feedback(self, record_id, *, review_status, reviewer, note=None,
                        expected_revision):
        if review_status not in _REVIEW:
            raise ValueError("invalid feedback review status")
        required(reviewer, "reviewer")
        if len(reviewer) > 128 or (note is not None and (not isinstance(note, str) or len(note) > 1000)):
            raise ValueError("feedback review metadata exceeds the limit")
        with self.history.transaction() as connection:
            current = self._feedback_view(connection, record_id)
            if type(expected_revision) is not int or expected_revision != current["revision"]:
                raise ValueError("feedback revision conflict")
            if current["cancelled"]:
                raise ValueError("cancelled feedback cannot be reviewed")
            return self._append_feedback_event(connection, current, "review", {
                "review_status": review_status, "reviewer": reviewer, "note": note,
            })

    def cancel_feedback(self, record_id, *, reason, expected_revision):
        required(reason, "cancellation reason")
        if len(reason) > 1000:
            raise ValueError("feedback cancellation reason is too long")
        with self.history.transaction() as connection:
            current = self._feedback_view(connection, record_id)
            if type(expected_revision) is not int or expected_revision != current["revision"]:
                raise ValueError("feedback revision conflict")
            if current["cancelled"]:
                raise ValueError("feedback is already cancelled")
            return self._append_feedback_event(connection, current, "cancel", {"reason": reason})

    def feedback_for_task(self, task_id, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid feedback query limit")
        with self.history._connect() as connection:
            self.history.load(connection, task_id)
            ids = connection.execute(
                "SELECT record_id FROM gate_a_records WHERE task_id=? AND kind='feedback' "
                "ORDER BY rowid LIMIT ?", (task_id, limit + 1),
            ).fetchall()
            if len(ids) > limit:
                raise ValueError("feedback query budget exceeded")
            return [self._feedback_view(connection, row[0]) for row in ids]

    def feedback_for_error(self, task_id, error_code, *, limit=100):
        required(error_code, "error_code")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid feedback query limit")
        with self.history._connect() as connection:
            self.history.load(connection, task_id)
            rows = connection.execute(
                "SELECT record_id FROM gate_a_feedback_index WHERE task_id=? AND error_code=? "
                "ORDER BY record_id LIMIT ?", (task_id, error_code, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise ValueError("feedback query budget exceeded")
            found = {row[0] for row in rows}
            legacy_rows = connection.execute(
                "SELECT r.record_id, r.document FROM gate_a_records r "
                "LEFT JOIN gate_a_feedback_index i ON i.record_id=r.record_id "
                "WHERE r.task_id=? AND r.kind='feedback' AND i.record_id IS NULL "
                "ORDER BY r.rowid LIMIT ?", (task_id, 1001),
            ).fetchall()
            if len(legacy_rows) > 1000:
                raise ValueError("legacy feedback query budget exceeded")
            for feedback_id, encoded in legacy_rows:
                related_id = json.loads(encoded).get("related_record_id")
                if related_id is None:
                    continue
                try:
                    related = self._load(connection, related_id)
                except ValueError:
                    continue
                if related.get("kind") == "incident" and related.get("error_code") == error_code:
                    found.add(feedback_id)
                    if len(found) > limit:
                        raise ValueError("feedback query budget exceeded")
            return [self._feedback_view(connection, identifier)
                    for identifier in sorted(found)]
