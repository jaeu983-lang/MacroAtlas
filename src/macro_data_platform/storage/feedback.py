"""Explicit, versioned user feedback linked to task and institution scope."""
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from macro_data_platform.storage.history import HistoryStore

_CATEGORIES = {"candidate_group", "question_order", "output_preference", "source_method",
              "statistical_definition", "other"}
_KINDS = {"user_instruction", "official_evidence", "inference"}
_TERMINAL = {"withdrawn", "superseded"}
_SCOPE_KEYS = {"institution_id", "dataset_id", "concept", "classification_axis", "version",
               "valid_from", "valid_until"}
_EDITABLE = _SCOPE_KEYS | {"text", "category", "knowledge_kind", "evidence_refs"}
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def _utc(value, field):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")
    return parsed


class FeedbackStore:
    """Append-only revisions with a small current snapshot; never promotes knowledge globally."""

    def __init__(self, history: HistoryStore, *, clock=lambda: datetime.now(UTC)):
        self.history, self.clock = history, clock
        with history.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_current (
                feedback_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                idempotency_key TEXT UNIQUE,
                revision INTEGER NOT NULL,
                document TEXT NOT NULL)""")
            connection.execute("""CREATE INDEX IF NOT EXISTS feedback_by_task
                ON feedback_current(task_id, feedback_id)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_revisions (
                feedback_id TEXT NOT NULL REFERENCES feedback_current(feedback_id),
                revision INTEGER NOT NULL,
                action TEXT NOT NULL,
                document TEXT NOT NULL,
                PRIMARY KEY(feedback_id, revision))""")

    def _now(self):
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("feedback clock must return UTC")
        return value.isoformat()

    @staticmethod
    def _text(value, field, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"invalid {field}")
        return value

    @classmethod
    def _payload(cls, *, text, category, knowledge_kind, scope, evidence_refs):
        cls._text(text, "feedback text", 4000)
        if (not isinstance(category, str) or category not in _CATEGORIES
                or not isinstance(knowledge_kind, str) or knowledge_kind not in _KINDS):
            raise ValueError("invalid feedback category or knowledge kind")
        if not isinstance(scope, dict) or set(scope) - _SCOPE_KEYS:
            raise ValueError("invalid feedback scope")
        scope = dict(scope)
        if "institution_id" in scope:
            value = scope["institution_id"]
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("invalid institution identifier")
        for key in _SCOPE_KEYS - {"institution_id", "valid_from", "valid_until"}:
            if key in scope:
                cls._text(scope[key], key, 256)
        start, end = _utc(scope.get("valid_from"), "valid_from"), _utc(scope.get("valid_until"), "valid_until")
        if start and end and start > end:
            raise ValueError("feedback validity range is reversed")
        if not isinstance(evidence_refs, (list, tuple)) or len(evidence_refs) > 10:
            raise ValueError("invalid feedback evidence references")
        refs = []
        for item in evidence_refs:
            if (not isinstance(item, dict) or set(item) - {"source_url", "source_version", "captured_at"}
                    or not isinstance(item.get("source_url"), str)):
                raise ValueError("invalid evidence reference")
            url = item["source_url"]
            try:
                parsed_url = urlsplit(url)
                valid_url = (parsed_url.scheme == "https" and parsed_url.hostname is not None
                             and parsed_url.username is None and parsed_url.password is None
                             and parsed_url.query == "" and parsed_url.fragment == "")
            except ValueError:
                valid_url = False
            if len(url) > 512 or not valid_url:
                raise ValueError("evidence URL must be HTTPS without credentials or query data")
            for key in ("source_version", "captured_at"):
                if key in item:
                    cls._text(item[key], key, 128)
            if "captured_at" in item:
                _utc(item["captured_at"], "evidence captured_at")
            refs.append(dict(item))
        if knowledge_kind == "official_evidence" and not refs:
            raise ValueError("official evidence requires a source reference")
        if knowledge_kind == "user_instruction" and refs:
            raise ValueError("user instructions cannot be labeled as official evidence")
        return {"text": text, "category": category, "knowledge_kind": knowledge_kind,
                "scope": scope, "evidence_refs": refs}

    def record(self, task_id, *, text, category="other", knowledge_kind="user_instruction",
               scope=None, evidence_refs=(), stage_run_id=None, related_record_id=None,
               idempotency_key=None, supersedes_feedback_id=None):
        payload = self._payload(text=text, category=category, knowledge_kind=knowledge_kind,
                                scope={} if scope is None else scope, evidence_refs=evidence_refs)
        if idempotency_key is not None:
            self._text(idempotency_key, "idempotency key", 128)
        with self.history.transaction() as connection:
            task = self.history.load(connection, task_id)
            if stage_run_id is not None and stage_run_id not in {
                    item["stage_run_id"] for item in task["stages"]}:
                raise ValueError("feedback stage belongs to another task")
            if related_record_id is not None:
                row = connection.execute(
                    "SELECT task_id, stage_run_id FROM gate_a_records WHERE record_id=?",
                    (related_record_id,),
                ).fetchone()
                if row is None or row[0] != task_id or (
                        stage_run_id is not None and row[1] != stage_run_id):
                    raise ValueError("feedback evidence belongs to another task or stage")
            if idempotency_key is not None:
                row = connection.execute("SELECT document FROM feedback_current WHERE idempotency_key=?",
                                         (idempotency_key,)).fetchone()
                if row:
                    prior = json.loads(row[0])
                    if (prior["task_id"] != task_id or prior["stage_run_id"] != stage_run_id
                            or prior["related_record_id"] != related_record_id
                            or prior["supersedes_feedback_id"] != supersedes_feedback_id
                            or any(prior[key] != payload[key] for key in payload)):
                        raise ValueError("feedback idempotency key conflict")
                    return prior
            superseded = None
            if supersedes_feedback_id is not None:
                superseded = self._current(connection, supersedes_feedback_id)
                if superseded["task_id"] != task_id:
                    raise ValueError("superseded feedback belongs to another task")
                if superseded["review_status"] in _TERMINAL:
                    raise ValueError("withdrawn or superseded feedback cannot be replaced")
            feedback_id, now = str(uuid4()), self._now()
            document = {**payload, "schema_version": 1, "feedback_id": feedback_id,
                        "task_id": task_id, "stage_run_id": stage_run_id,
                        "related_record_id": related_record_id,
                        "supersedes_feedback_id": supersedes_feedback_id,
                        "review_status": "unreviewed",
                        "review_note": None, "revision": 1, "recorded_at": now,
                        "updated_at": now}
            connection.execute("INSERT INTO feedback_current VALUES (?, ?, ?, ?, ?)",
                               (feedback_id, task_id, idempotency_key, 1,
                                json.dumps(document, ensure_ascii=False, allow_nan=False)))
            self._event(connection, feedback_id, 1, "created", document)
            self.history.event(connection, task_id, {"kind": "FEEDBACK_CREATED", "at": now,
                                                     "feedback_id": feedback_id, "revision": 1})
            if superseded is not None:
                updated = {**superseded, "revision": superseded["revision"] + 1,
                           "review_status": "superseded", "review_note": feedback_id,
                           "updated_at": now}
                self._save_revision(connection, updated, "superseded")
            return document

    def _event(self, connection, feedback_id, revision, action, document):
        connection.execute("INSERT INTO feedback_revisions VALUES (?, ?, ?, ?)",
                           (feedback_id, revision, action,
                            json.dumps(document, ensure_ascii=False, allow_nan=False)))

    def _current(self, connection, feedback_id):
        row = connection.execute("SELECT document FROM feedback_current WHERE feedback_id=?",
                                 (feedback_id,)).fetchone()
        if row is None:
            raise ValueError("unknown feedback identifier")
        return json.loads(row[0])

    def revise(self, feedback_id, *, expected_revision, changes):
        if (type(expected_revision) is not int or not isinstance(changes, dict)
                or not changes):
            raise ValueError("revision and nonempty changes are required")
        if set(changes) - _EDITABLE:
            raise ValueError("unsupported feedback change")
        with self.history.transaction() as connection:
            current = self._current(connection, feedback_id)
            if current["revision"] != expected_revision:
                raise ValueError("stale feedback revision")
            if current["review_status"] in _TERMINAL:
                raise ValueError("withdrawn or superseded feedback cannot be edited")
            merged = {key: current[key] for key in ("text", "category", "knowledge_kind", "scope",
                                                    "evidence_refs")}
            merged.update(changes)
            updated_payload = self._payload(text=merged["text"], category=merged["category"],
                                            knowledge_kind=merged["knowledge_kind"],
                                            scope=merged["scope"],
                                            evidence_refs=merged["evidence_refs"])
            now, revision = self._now(), expected_revision + 1
            document = {**current, **updated_payload, "revision": revision,
                        "review_status": "unreviewed", "review_note": None, "updated_at": now}
            self._save_revision(connection, document, "edited")
            return document

    def review(self, feedback_id, *, expected_revision, status, reviewer_note=None):
        if status not in {"accepted", "rejected", "unreviewed"}:
            raise ValueError("invalid feedback review status")
        if reviewer_note is not None:
            self._text(reviewer_note, "review note", 1000)
        return self._transition(feedback_id, expected_revision, status, reviewer_note, "reviewed")

    def withdraw(self, feedback_id, *, expected_revision, reason):
        self._text(reason, "withdrawal reason", 1000)
        return self._transition(feedback_id, expected_revision, "withdrawn", reason, "withdrawn")

    def _transition(self, feedback_id, expected_revision, status, note, action):
        if type(expected_revision) is not int:
            raise ValueError("feedback revision must be an integer")
        with self.history.transaction() as connection:
            current = self._current(connection, feedback_id)
            if current["revision"] != expected_revision:
                raise ValueError("stale feedback revision")
            if current["review_status"] in _TERMINAL and status != current["review_status"]:
                raise ValueError("withdrawn or superseded feedback is final")
            document = {**current, "revision": expected_revision + 1,
                        "review_status": status, "review_note": note, "updated_at": self._now()}
            self._save_revision(connection, document, action)
            return document

    def _save_revision(self, connection, document, action):
        revision = document["revision"]
        connection.execute("UPDATE feedback_current SET revision=?, document=? WHERE feedback_id=?",
                           (revision, json.dumps(document, ensure_ascii=False, allow_nan=False),
                            document["feedback_id"]))
        self._event(connection, document["feedback_id"], revision, action, document)
        self.history.event(connection, document["task_id"], {
            "kind": "FEEDBACK_" + action.upper(), "at": document["updated_at"],
            "feedback_id": document["feedback_id"], "revision": revision})

    def get(self, feedback_id):
        with self.history._connect() as connection:
            return self._current(connection, feedback_id)

    def history_for(self, feedback_id):
        with self.history._connect() as connection:
            self._current(connection, feedback_id)
            rows = connection.execute("SELECT revision, action, document FROM feedback_revisions "
                                      "WHERE feedback_id=? ORDER BY revision", (feedback_id,)).fetchall()
            return [{"revision": row[0], "action": row[1], "document": json.loads(row[2])}
                    for row in rows]

    def for_task(self, task_id, *, institution_id=None, category=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("feedback limit must be between 1 and 500")
        with self.history._connect() as connection:
            self.history.load(connection, task_id)
            rows = connection.execute(
                "SELECT document FROM feedback_current WHERE task_id=? "
                "AND (? IS NULL OR json_extract(document, '$.scope.institution_id')=?) "
                "AND (? IS NULL OR json_extract(document, '$.category')=?) "
                "ORDER BY rowid LIMIT ?",
                (task_id, institution_id, institution_id, category, category, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
