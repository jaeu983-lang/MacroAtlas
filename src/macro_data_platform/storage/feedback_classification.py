"""Frozen feedback revision keys and explicitly imported classification batches."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from time import perf_counter_ns
from uuid import uuid4

from macro_data_platform.storage.feedback import FeedbackStore

LABELS = frozenset({"candidate_group", "question_order", "output_preference", "source_method",
                    "statistical_definition", "other", "unclassified"})
REASONS = frozenset({"privacy_excluded", "ambiguous", "unsupported", "model_error"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identifier(value, name):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


class FeedbackClassificationStore:
    """Keep derived labels separate from the immutable feedback revision ledger."""

    def __init__(self, feedback: FeedbackStore):
        self.feedback = feedback
        self.history = feedback.history
        with self.history.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_classification_snapshots (
                snapshot_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, row_count INTEGER NOT NULL,
                key_hash TEXT NOT NULL, source_hash TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_classification_snapshot_rows (
                snapshot_id TEXT NOT NULL REFERENCES feedback_classification_snapshots(snapshot_id),
                feedback_id TEXT NOT NULL, revision INTEGER NOT NULL, document_hash TEXT NOT NULL,
                PRIMARY KEY(snapshot_id, feedback_id, revision),
                FOREIGN KEY(feedback_id, revision) REFERENCES feedback_revisions(feedback_id, revision))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_classification_batches (
                batch_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES
                feedback_classification_snapshots(snapshot_id), created_at TEXT NOT NULL,
                prompt_version TEXT NOT NULL, model_version TEXT NOT NULL, reviewer_id TEXT NOT NULL,
                elapsed_ms INTEGER, cost_usd REAL, key_hash TEXT NOT NULL, result_hash TEXT NOT NULL,
                privacy_cleared INTEGER NOT NULL CHECK(privacy_cleared=1), validation_ns INTEGER NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS feedback_classification_rows (
                batch_id TEXT NOT NULL REFERENCES feedback_classification_batches(batch_id),
                feedback_id TEXT NOT NULL, revision INTEGER NOT NULL, label TEXT NOT NULL,
                reason TEXT, PRIMARY KEY(batch_id, feedback_id, revision),
                FOREIGN KEY(feedback_id, revision) REFERENCES feedback_revisions(feedback_id, revision))""")

    def snapshot(self):
        """Freeze all existing revisions; output contains identities and hashes, never feedback text."""
        with self.history.transaction() as connection:
            records = connection.execute(
                "SELECT feedback_id, revision, document FROM feedback_revisions "
                "ORDER BY feedback_id, revision").fetchall()
            rows = []
            for feedback_id, revision, document in records:
                parsed = json.loads(document)
                if parsed.get("feedback_id") != feedback_id or parsed.get("revision") != revision:
                    raise ValueError("feedback revision identity mismatch")
                rows.append({"feedback_id": feedback_id, "revision": revision,
                             "document_hash": _digest(parsed)})
            snapshot_id = str(uuid4())
            now = datetime.now(UTC).isoformat()
            key_hash = _digest([[r["feedback_id"], r["revision"]] for r in rows])
            source_hash = _digest(rows)
            connection.execute("INSERT INTO feedback_classification_snapshots VALUES (?, ?, ?, ?, ?)",
                               (snapshot_id, now, len(rows), key_hash, source_hash))
            connection.executemany("INSERT INTO feedback_classification_snapshot_rows VALUES (?, ?, ?, ?)",
                                   [(snapshot_id, r["feedback_id"], r["revision"],
                                     r["document_hash"]) for r in rows])
        return {"snapshot_id": snapshot_id, "created_at": now, "row_count": len(rows),
                "key_hash": key_hash, "source_hash": source_hash, "rows": rows}

    def import_batch(self, document):
        """Validate every frozen revision before storing an independently produced label batch."""
        started_ns = perf_counter_ns()
        required = {"snapshot_id", "key_hash", "source_hash", "prompt_version", "model_version",
                    "reviewer_id", "privacy_cleared", "elapsed_ms", "cost_usd", "rows"}
        if not isinstance(document, dict) or set(document) != required:
            raise ValueError("invalid classification batch fields")
        if document["privacy_cleared"] is not True:
            raise ValueError("explicit privacy clearance required")
        snapshot_id = _identifier(document["snapshot_id"], "snapshot_id")
        for name in ("prompt_version", "model_version", "reviewer_id"):
            _identifier(document[name], name)
        elapsed, cost = document["elapsed_ms"], document["cost_usd"]
        if elapsed is not None and (type(elapsed) is not int or elapsed < 0):
            raise ValueError("invalid elapsed_ms")
        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            raise ValueError("invalid cost_usd")
        if not isinstance(document["rows"], list):
            raise TypeError("classification rows must be a list")
        classified = {}
        for row in document["rows"]:
            if not isinstance(row, dict) or set(row) != {"feedback_id", "revision", "label", "reason"}:
                raise ValueError("invalid classification row")
            key = (_identifier(row["feedback_id"], "feedback_id"), row["revision"])
            if type(key[1]) is not int or key[1] < 1 or key in classified:
                raise ValueError("invalid or duplicate revision key")
            if not isinstance(row["label"], str) or row["label"] not in LABELS:
                raise ValueError("invalid classification label")
            if ((row["label"] == "unclassified" and
                 (not isinstance(row["reason"], str) or row["reason"] not in REASONS))
                    or (row["label"] != "unclassified" and row["reason"] is not None)):
                raise ValueError("invalid unclassified reason")
            classified[key] = (row["label"], row["reason"])
        with self.history.transaction() as connection:
            snapshot = connection.execute(
                "SELECT row_count, key_hash, source_hash FROM feedback_classification_snapshots "
                "WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            if snapshot is None:
                raise ValueError("unknown classification snapshot")
            source_rows = connection.execute(
                "SELECT s.feedback_id, s.revision, s.document_hash, r.document "
                "FROM feedback_classification_snapshot_rows s JOIN feedback_revisions r "
                "ON r.feedback_id=s.feedback_id AND r.revision=s.revision "
                "WHERE s.snapshot_id=? ORDER BY s.feedback_id, s.revision", (snapshot_id,)).fetchall()
            expected = {(row[0], row[1]) for row in source_rows}
            source_manifest = [{"feedback_id": row[0], "revision": row[1],
                                "document_hash": row[2]} for row in source_rows]
            if (len(source_rows) != snapshot[0] or len(classified) != snapshot[0]
                    or set(classified) != expected or document["key_hash"] != snapshot[1]
                    or document["source_hash"] != snapshot[2]
                    or _digest([[r["feedback_id"], r["revision"]] for r in source_manifest]) != snapshot[1]
                    or _digest(source_manifest) != snapshot[2]
                    or any(_digest(json.loads(row[3])) != row[2] for row in source_rows)):
                raise ValueError("snapshot count, key set, hash, or source revision mismatch")
            rows = [{"feedback_id": key[0], "revision": key[1], "label": classified[key][0],
                     "reason": classified[key][1]} for key in sorted(classified)]
            result_hash, batch_id = _digest(rows), str(uuid4())
            now = datetime.now(UTC).isoformat()
            validation_ns = perf_counter_ns() - started_ns
            connection.execute("INSERT INTO feedback_classification_batches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (batch_id, snapshot_id, now, document["prompt_version"],
                                document["model_version"], document["reviewer_id"], elapsed, cost,
                                snapshot[1], result_hash, 1, validation_ns))
            connection.executemany("INSERT INTO feedback_classification_rows VALUES (?, ?, ?, ?, ?)",
                                   [(batch_id, r["feedback_id"], r["revision"], r["label"],
                                     r["reason"]) for r in rows])
        return {"batch_id": batch_id, "snapshot_id": snapshot_id, "row_count": len(rows),
                "key_hash": snapshot[1], "source_hash": snapshot[2], "result_hash": result_hash}

    def batches(self):
        with self.history._connect() as connection:
            rows = connection.execute(
                "SELECT b.batch_id, b.snapshot_id, b.created_at, b.prompt_version, b.model_version, "
                "b.reviewer_id, b.elapsed_ms, b.cost_usd, b.key_hash, b.result_hash, "
                "b.privacy_cleared, b.validation_ns, s.row_count, s.source_hash "
                "FROM feedback_classification_batches b JOIN feedback_classification_snapshots s "
                "ON s.snapshot_id=b.snapshot_id ORDER BY b.rowid").fetchall()
        keys = ("batch_id", "snapshot_id", "created_at", "prompt_version", "model_version",
                "reviewer_id", "elapsed_ms", "cost_usd", "key_hash", "result_hash",
                "privacy_cleared", "validation_ns", "row_count", "source_hash")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def batch_rows(self, batch_id):
        _identifier(batch_id, "batch_id")
        with self.history._connect() as connection:
            if connection.execute("SELECT 1 FROM feedback_classification_batches WHERE batch_id=?",
                                  (batch_id,)).fetchone() is None:
                raise ValueError("unknown classification batch")
            rows = connection.execute(
                "SELECT feedback_id, revision, label, reason FROM feedback_classification_rows "
                "WHERE batch_id=? ORDER BY feedback_id, revision", (batch_id,)).fetchall()
        return [dict(zip(("feedback_id", "revision", "label", "reason"), row, strict=True))
                for row in rows]
