"""Bounded institution-scoped feedback index and conditional reuse suggestions."""
import json
from collections import OrderedDict
from datetime import UTC, datetime
from itertools import product

from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore

MAX_REFRESH_CHANGES = 500
MAX_QUERY_SCAN = 500
MAX_QUERY_RESULTS = 50
MAX_CACHE_ENTRIES = 64
MAX_CACHE_BYTES = 1_000_000


class KnowledgeStore:
    """Maintain an explicit SQLite projection; requests never rebuild or read task histories."""

    def __init__(self, history: HistoryStore, *, feedback: FeedbackStore | None = None,
                 clock=lambda: datetime.now(UTC)):
        self.history = history
        self.feedback = feedback or FeedbackStore(history, clock=clock)
        self.clock = clock
        self._cache: OrderedDict[tuple, dict] = OrderedDict()
        self._cache_sizes: dict[tuple, int] = {}
        self._cache_bytes = 0
        self._last_index_revision = None
        with history.transaction() as connection:
            had_meta = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_meta'"
            ).fetchone() is not None
            connection.execute("""CREATE TABLE IF NOT EXISTS knowledge_current (
                feedback_id TEXT PRIMARY KEY REFERENCES feedback_current(feedback_id),
                task_id TEXT NOT NULL,
                institution_id TEXT,
                dataset_id TEXT,
                concept TEXT,
                classification_axis TEXT,
                version TEXT,
                valid_from TEXT,
                valid_until TEXT,
                category TEXT NOT NULL,
                knowledge_kind TEXT NOT NULL,
                review_status TEXT NOT NULL,
                text TEXT NOT NULL,
                evidence_refs TEXT NOT NULL,
                source_revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL)""")
            connection.execute("""CREATE INDEX IF NOT EXISTS knowledge_scope_lookup
                ON knowledge_current(institution_id, review_status, knowledge_kind,
                                     concept, dataset_id, classification_axis)""")
            connection.execute("""CREATE INDEX IF NOT EXISTS knowledge_scope_lookup_v2
                ON knowledge_current(institution_id, review_status, knowledge_kind,
                                     dataset_id, concept, classification_axis, version, category)""")
            connection.execute("""CREATE INDEX IF NOT EXISTS knowledge_category_lookup
                ON knowledge_current(institution_id, category, review_status, knowledge_kind)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS knowledge_change_queue (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_id TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS knowledge_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                index_revision INTEGER NOT NULL)""")
            connection.execute("INSERT OR IGNORE INTO knowledge_meta VALUES (1, 0)")
            if not had_meta:
                connection.execute("""INSERT INTO knowledge_change_queue(feedback_id)
                    SELECT feedback_id FROM feedback_current ORDER BY rowid""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS feedback_index_insert
                AFTER INSERT ON feedback_current
                BEGIN INSERT INTO knowledge_change_queue(feedback_id)
                    VALUES (NEW.feedback_id); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS feedback_index_update
                AFTER UPDATE OF revision, document ON feedback_current
                BEGIN INSERT INTO knowledge_change_queue(feedback_id)
                    VALUES (NEW.feedback_id); END""")

    def _now(self):
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("knowledge clock must return UTC")
        return value.astimezone(UTC)

    @staticmethod
    def _scope_columns(document):
        scope = document.get("scope", {})
        return tuple(scope.get(key) for key in (
            "institution_id", "dataset_id", "concept", "classification_axis", "version",
            "valid_from", "valid_until",
        ))

    def refresh(self, *, max_changes=100):
        """Apply up to max_changes queued feedback revisions; never run implicitly on query."""
        if type(max_changes) is not int or not 1 <= max_changes <= MAX_REFRESH_CHANGES:
            raise ValueError(f"max_changes must be between 1 and {MAX_REFRESH_CHANGES}")
        processed = 0
        with self.history.transaction() as connection:
            rows = connection.execute(
                "SELECT sequence, feedback_id FROM knowledge_change_queue ORDER BY sequence LIMIT ?",
                (max_changes,),
            ).fetchall()
            if rows:
                cutoff = rows[-1][0]
                latest = {}
                for sequence, feedback_id in rows:
                    latest[feedback_id] = sequence
                for feedback_id, sequence in latest.items():
                    row = connection.execute(
                        "SELECT document, revision FROM feedback_current WHERE feedback_id=?",
                        (feedback_id,),
                    ).fetchone()
                    if row is None:
                        connection.execute("DELETE FROM knowledge_current WHERE feedback_id=?",
                                           (feedback_id,))
                        continue
                    document = json.loads(row[0])
                    scope = self._scope_columns(document)
                    connection.execute("""INSERT INTO knowledge_current VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(feedback_id) DO UPDATE SET
                        task_id=excluded.task_id, institution_id=excluded.institution_id,
                        dataset_id=excluded.dataset_id, concept=excluded.concept,
                        classification_axis=excluded.classification_axis, version=excluded.version,
                        valid_from=excluded.valid_from, valid_until=excluded.valid_until,
                        category=excluded.category, knowledge_kind=excluded.knowledge_kind,
                        review_status=excluded.review_status, text=excluded.text,
                        evidence_refs=excluded.evidence_refs, source_revision=excluded.source_revision,
                        updated_at=excluded.updated_at""",
                        (feedback_id, document["task_id"], *scope, document["category"],
                         document["knowledge_kind"], document["review_status"], document["text"],
                         json.dumps(document["evidence_refs"], ensure_ascii=False, allow_nan=False),
                         row[1], document["updated_at"]))
                connection.execute("DELETE FROM knowledge_change_queue WHERE sequence<=?", (cutoff,))
                connection.execute("UPDATE knowledge_meta SET index_revision=? WHERE singleton=1",
                                   (cutoff,))
                processed = len(rows)
            pending_rows = connection.execute(
                "SELECT sequence FROM knowledge_change_queue ORDER BY sequence LIMIT ?",
                (MAX_REFRESH_CHANGES + 1,),
            ).fetchall()
            pending = len(pending_rows)
            revision = connection.execute(
                "SELECT index_revision FROM knowledge_meta WHERE singleton=1",
            ).fetchone()[0]
        if processed:
            self._clear_cache()
        self._last_index_revision = revision
        return {"status": "refreshed" if pending == 0 else "partial",
                "processed_changes": processed, "pending_changes": pending,
                "pending_count_capped": pending > MAX_REFRESH_CHANGES,
                "index_revision": revision}

    @staticmethod
    def _utc_value(value, name):
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError(f"invalid {name}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid {name}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{name} must include UTC timezone")
        return parsed.astimezone(UTC)

    def _clear_cache(self):
        self._cache.clear()
        self._cache_sizes.clear()
        self._cache_bytes = 0

    def query(self, *, institution_id, category=None, dataset_id=None, concept=None,
              classification_axis=None, version=None, as_of=None, limit=20,
              include_unreviewed=False, include_inference=False):
        """Return scoped suggestions and evidence; never applies preferences automatically."""
        if not isinstance(institution_id, str) or not institution_id:
            raise ValueError("institution_id is required for scoped knowledge lookup")
        if type(limit) is not int or not 1 <= limit <= MAX_QUERY_RESULTS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_RESULTS}")
        if category is not None and not isinstance(category, str):
            raise ValueError("category must be text")
        if type(include_unreviewed) is not bool or type(include_inference) is not bool:
            raise ValueError("knowledge lookup flags must be booleans")
        for name, value in (("dataset_id", dataset_id), ("concept", concept),
                            ("classification_axis", classification_axis), ("version", version)):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 256):
                raise ValueError(f"invalid {name}")
        at = self._utc_value(as_of, "as_of") if as_of is not None else self._now()
        statuses = ("accepted", "unreviewed") if include_unreviewed else ("accepted",)
        kinds = ("user_instruction", "official_evidence", "inference") if include_inference else (
            "user_instruction", "official_evidence")
        dimensions = (("dataset_id", dataset_id), ("concept", concept),
                      ("classification_axis", classification_axis), ("version", version))
        provided = tuple((name, value) for name, value in dimensions if value is not None)
        scope_variants = []
        for selected in product((False, True), repeat=len(provided)):
            values = dict(dimensions)
            for (name, value), use_exact in zip(provided, selected, strict=True):
                values[name] = value if use_exact else None
            scope_variants.append(values)
        scope_variants.sort(key=lambda values: (
            -sum(value is not None for value in values.values()),
            tuple("" if values[name] is None else values[name] for name, _ in dimensions),
        ))
        with self.history._connect() as connection:
            # Read pending state, revision, and candidates from one SQLite snapshot.
            connection.execute("BEGIN")
            meta = connection.execute(
                "SELECT index_revision FROM knowledge_meta WHERE singleton=1",
            ).fetchone()
            pending_rows = connection.execute(
                "SELECT sequence FROM knowledge_change_queue ORDER BY sequence LIMIT ?",
                (MAX_REFRESH_CHANGES + 1,),
            ).fetchall()
            pending = len(pending_rows)
            revision = meta[0]
            if pending:
                return {"status": "NEEDS_REFRESH", "items": [], "pending_changes": pending,
                        "pending_count_capped": pending > MAX_REFRESH_CHANGES,
                        "index_revision": revision,
                        "warnings": ["Feedback changed; run the explicit bounded refresh before lookup."]}
            if self._last_index_revision is not None and revision != self._last_index_revision:
                self._clear_cache()
            self._last_index_revision = revision
            cache_key = (revision, institution_id, category, dataset_id, concept,
                         classification_axis, version, at.isoformat(), limit,
                         include_unreviewed, include_inference)
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                cached = json.loads(json.dumps(self._cache[cache_key], ensure_ascii=False))
                cached["cache"] = "hit"
                cached["candidate_rows_read"] = 0
                cached["candidate_logical_bytes_read"] = 0
                return cached
            rows = []
            candidate_rows_read = 0
            candidate_bytes_read = 0
            truncated = False
            for scope in scope_variants:
                remaining = MAX_QUERY_SCAN - len(rows)
                clauses = ["institution_id=?",
                           "review_status IN (" + ",".join("?" for _ in statuses) + ")",
                           "knowledge_kind IN (" + ",".join("?" for _ in kinds) + ")"]
                params = [institution_id, *statuses, *kinds]
                if category is not None:
                    clauses.append("category=?")
                    params.append(category)
                for name, _value in dimensions:
                    value = scope[name]
                    if value is None:
                        clauses.append(f"{name} IS NULL")
                    else:
                        clauses.append(f"{name}=?")
                        params.append(value)
                sql = ("SELECT feedback_id, task_id, dataset_id, concept, classification_axis, "
                       "version, valid_from, valid_until, category, knowledge_kind, review_status, "
                       "text, evidence_refs, source_revision FROM knowledge_current WHERE "
                       + " AND ".join(clauses) + " LIMIT ?")
                params.append(remaining + 1)
                batch = connection.execute(sql, params).fetchall()
                candidate_rows_read += len(batch)
                candidate_bytes_read += sum(
                    len(value.encode("utf-8")) if isinstance(value, str) else len(value)
                    if isinstance(value, bytes) else 8
                    for row in batch for value in row
                )
                if len(batch) > remaining:
                    rows.extend(batch[:remaining])
                    truncated = True
                    break
                rows.extend(batch)
        candidates = []
        for row in rows:
            (feedback_id, task_id, row_dataset, row_concept, row_axis, row_version,
             valid_from, valid_until, row_category, knowledge_kind, review_status,
             text, evidence_refs, source_revision) = row
            start = self._utc_value(valid_from, "valid_from")
            end = self._utc_value(valid_until, "valid_until")
            if (start is not None and at < start) or (end is not None and at > end):
                continue
            broader = any(supplied is not None and stored is None for supplied, stored in (
                (dataset_id, row_dataset), (concept, row_concept),
                (classification_axis, row_axis), (version, row_version)))
            candidates.append({
                "feedback_id": feedback_id, "task_id": task_id,
                "scope": {"institution_id": institution_id, "dataset_id": row_dataset,
                          "concept": row_concept, "classification_axis": row_axis,
                          "version": row_version, "valid_from": valid_from,
                          "valid_until": valid_until},
                "category": row_category, "knowledge_kind": knowledge_kind,
                "review_status": review_status, "text": text,
                "evidence_refs": json.loads(evidence_refs),
                "source_revision": source_revision,
                "scope_match": ("broader_than_request" if broader else
                                "institution_only" if all(value is None for value in
                                    (dataset_id, concept, classification_axis, version)) else "exact"),
                "applicability": ("review_required" if review_status != "accepted" or
                                  knowledge_kind == "inference" else
                                  "reference_only" if knowledge_kind == "official_evidence" else
                                  "suggestion"),
                "requires_confirmation": knowledge_kind == "user_instruction",
                "fact_status": "not_promoted" if knowledge_kind == "inference" else "reference_only",
            })
        conflicts = {}
        for item in candidates:
            key = (item["knowledge_kind"], item["category"], item["scope"]["dataset_id"],
                   item["scope"]["concept"], item["scope"]["classification_axis"],
                   item["scope"]["version"])
            if item["review_status"] == "accepted":
                conflicts.setdefault(key, set()).add(item["text"])
        conflict_keys = {key for key, texts in conflicts.items() if len(texts) > 1}
        for item in candidates:
            key = (item["knowledge_kind"], item["category"], item["scope"]["dataset_id"],
                   item["scope"]["concept"], item["scope"]["classification_axis"],
                   item["scope"]["version"])
            if key in conflict_keys:
                item["applicability"] = "review_required"
                item["possible_conflict"] = True
        scan_truncated = truncated
        result_truncated = len(candidates) > limit
        truncated = scan_truncated or result_truncated
        candidates = candidates[:limit]
        warnings = []
        if scan_truncated:
            warnings.append(f"Candidate scan reached the {MAX_QUERY_SCAN}-row limit; results are incomplete.")
        if result_truncated:
            warnings.append(f"Result limit reached at {limit} items; results are incomplete.")
        if conflict_keys:
            warnings.append("Multiple accepted entries share an exact scope; inspect them before reuse.")
        result = {"status": "partial" if truncated else "ready", "items": candidates,
                  "pending_changes": 0, "index_revision": revision,
                  "candidate_scan_cap": MAX_QUERY_SCAN,
                  "result_limit": limit,
                  "candidate_rows_read": candidate_rows_read,
                  "candidate_logical_bytes_read": candidate_bytes_read,
                  "truncated": truncated,
                  "candidate_scan_truncated": scan_truncated,
                  "result_truncated": result_truncated,
                  "conflict_groups": len(conflict_keys), "warnings": warnings,
                  "cache": "miss"}
        cached = json.loads(json.dumps(result, ensure_ascii=False))
        cached["cache"] = "miss"
        cache_size = len(json.dumps(cached, ensure_ascii=False).encode("utf-8"))
        if cache_size <= MAX_CACHE_BYTES:
            self._cache[cache_key] = cached
            self._cache_sizes[cache_key] = cache_size
            self._cache_bytes += cache_size
            self._cache.move_to_end(cache_key)
            while (len(self._cache) > MAX_CACHE_ENTRIES or
                   self._cache_bytes > MAX_CACHE_BYTES):
                removed_key, _removed = self._cache.popitem(last=False)
                self._cache_bytes -= self._cache_sizes.pop(removed_key)
        return result

    @staticmethod
    def decide_reuse(lookup, *, category, current_instruction=None):
        """Describe a safe next step; prior experience is never applied automatically."""
        if current_instruction is not None:
            if not isinstance(current_instruction, str) or not current_instruction.strip():
                raise ValueError("current_instruction must be nonempty text")
            return {"status": "current_instruction", "value": current_instruction,
                    "feedback_ids": []}
        if not isinstance(lookup, dict) or lookup.get("status") not in {"ready", "partial"}:
            return {"status": "lookup_unavailable", "value": None, "feedback_ids": []}
        if lookup["status"] == "partial":
            return {"status": "lookup_incomplete_requires_review", "value": None,
                    "feedback_ids": []}
        options = [item for item in lookup["items"]
                   if item["category"] == category and
                   item["knowledge_kind"] == "user_instruction" and
                   item["review_status"] == "accepted" and
                   item["applicability"] == "suggestion"]
        conflicts = [item for item in lookup["items"]
                     if item["category"] == category and
                     item["knowledge_kind"] == "user_instruction" and
                     item["review_status"] == "accepted" and
                     item.get("possible_conflict")]
        if conflicts:
            return {"status": "ask_to_resolve_conflict", "value": None,
                    "feedback_ids": [item["feedback_id"] for item in conflicts]}
        if category == "output_preference":
            if options:
                return {"status": "ask_to_confirm_prior_preference", "value": None,
                        "feedback_ids": [item["feedback_id"] for item in options]}
            return {"status": "ask_for_output_choice", "value": None, "feedback_ids": []}
        if options:
            return {"status": "suggestions_require_confirmation", "value": None,
                    "feedback_ids": [item["feedback_id"] for item in options]}
        return {"status": "no_accepted_prior_instruction", "value": None, "feedback_ids": []}

    def confirm_reuse(self, *, institution_id, category, feedback_id, dataset_id=None,
                      concept=None, classification_axis=None, version=None,
                      current_instruction=None):
        """Return one explicitly selected, accepted instruction for a bounded task plan."""
        if current_instruction is not None:
            if (not isinstance(current_instruction, str) or not current_instruction.strip()
                    or len(current_instruction) > 4000):
                raise ValueError("current_instruction must be nonempty text")
            return {
                "status": "current_instruction",
                "index_revision": None,
                "knowledge_context": {
                    "status": "current_instruction",
                    "text": current_instruction,
                    "feedback_ids": [],
                },
            }
        if not isinstance(category, str) or not category:
            raise ValueError("knowledge category is required")
        if not isinstance(feedback_id, str) or not feedback_id:
            raise ValueError("explicit feedback_id selection is required")
        lookup = self.query(
            institution_id=institution_id, category=category, dataset_id=dataset_id,
            concept=concept, classification_axis=classification_axis, version=version,
            limit=MAX_QUERY_RESULTS,
        )
        metrics = {name: lookup[name] for name in (
            "candidate_rows_read", "candidate_logical_bytes_read", "candidate_scan_cap",
            "result_limit", "cache",
        ) if name in lookup}
        if lookup["status"] != "ready":
            status = ("lookup_incomplete" if lookup["status"] == "partial" else
                      "lookup_needs_refresh" if lookup["status"] == "NEEDS_REFRESH" else
                      "lookup_unavailable")
            return {"status": status, "index_revision": lookup.get("index_revision"),
                    "feedback_ids": [], "lookup_metrics": metrics}
        item = next((candidate for candidate in lookup["items"]
                     if candidate["feedback_id"] == feedback_id), None)
        if item is None:
            return {"status": "feedback_not_in_scope", "index_revision": lookup["index_revision"],
                    "feedback_ids": [], "lookup_metrics": metrics}
        decision = self.decide_reuse(lookup, category=category)
        if item.get("possible_conflict") or decision["status"] == "ask_to_resolve_conflict":
            return {"status": "conflict_requires_review",
                    "index_revision": lookup["index_revision"], "feedback_ids": [],
                    "lookup_metrics": metrics}
        if (item["knowledge_kind"] != "user_instruction" or item["review_status"] != "accepted"
                or item["applicability"] != "suggestion"):
            return {"status": "feedback_not_reusable",
                    "index_revision": lookup["index_revision"], "feedback_ids": [],
                    "lookup_metrics": metrics}
        if item["scope_match"] == "broader_than_request":
            return {"status": "feedback_scope_too_broad",
                    "index_revision": lookup["index_revision"], "feedback_ids": [],
                    "lookup_metrics": metrics}
        return {
            "status": "confirmed",
            "index_revision": lookup["index_revision"],
            "feedback_ids": [feedback_id],
            "lookup_metrics": metrics,
            "knowledge_context": {
                "status": "confirmed",
                "feedback_id": feedback_id,
                "confirmed_by": "explicit_feedback_id_selection",
                "source_revision": item["source_revision"],
                "institution_id": institution_id,
                "category": category,
                "knowledge_kind": item["knowledge_kind"],
                "scope": item["scope"],
                "text": item["text"],
                "evidence_refs": item["evidence_refs"],
                "index_revision": lookup["index_revision"],
            },
        }
