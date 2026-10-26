"""Read-only, bounded analysis of recurring task outcomes and accepted feedback."""
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode
from macro_data_platform.storage.history import HistoryStore

MAX_TASKS = 500
MAX_RECORDS = 2_500
MAX_PROPOSALS = 20
MAX_EVIDENCE_PER_PROPOSAL = 10
_TERMINAL_TASKS = ("COMPLETED", "FAILED", "PARTIAL", "NEEDS_REVIEW")
_STAGE_OUTCOMES = (
    "SUCCEEDED", "SKIPPED_REUSED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "NEEDS_REVIEW",
)
_FAILURES = {"FAILED_RETRYABLE", "FAILED_TERMINAL", "NEEDS_REVIEW"}
_ERROR_CODES = {item.value for item in ErrorCode}
_FEEDBACK_CATEGORIES = {
    "candidate_group", "question_order", "output_preference", "source_method",
    "statistical_definition", "other",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|authorization)\b\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]{12,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b[A-Za-z0-9_+/-]{32,}={0,2}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)[?&](token|key|secret|password|credential)=[^&#\s]+"),
)
_INSTITUTION_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


def _has_secret(value):
    return isinstance(value, str) and any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _safe_scope(value, *, institution=False):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (not value or len(value) > 256 or _has_secret(value)
            or (institution and not _INSTITUTION_ID.fullmatch(value))):
        return None
    return value


def _size(value):
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return 8


def _json_key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _distinct_unknowns(fingerprint, task_id, required_fields=()):
    """Make each missing scope dimension task-local so unknowns never merge cases."""
    key = dict(fingerprint)
    unknown = []
    for field in ("institution_id", "engine", "engine_version", "stage_id",
                  "dataset_id", "concept", *required_fields):
        if key.get(field) is None:
            key[field] = {"unknown_for_task": task_id}
            unknown.append(field)
    return _json_key(key), unknown


def _stage_scope_sql(plan_field, knowledge_field, candidate_field, workflow_path=None):
    candidate_path = f"$.{candidate_field}"
    workflow_value = (
        f"json_extract(t.document, '{workflow_path}')" if workflow_path else f"""(
        SELECT json_extract(c.value, '{candidate_path}')
          FROM json_each(t.document,
            '$.workflow_context.confirmation.offer.proposal.proposal.candidates') AS c
         WHERE json_extract(c.value, '$.candidate_id') =
               json_extract(t.document, '$.workflow_context.confirmation.offer.candidate_id')
         LIMIT 1)"""
    )
    # Fixed, persisted source identities only. Never infer an economic concept.
    adapter = "NULL"
    engine = "json_extract(p.value, '$.engine')"
    source = "json_extract(p.value, '$.input_data.source_id')"
    if plan_field == "institution_id":
        adapter = f"""CASE
            WHEN {engine} = 'gate_c_file_watch' AND {source} IN ('tic', 'bis') THEN {source}
            WHEN {engine} IN ('boj_metadata', 'boj_observations')
             AND json_extract(p.value, '$.input_data.database') = 'FM08'
             AND json_extract(p.value, '$.input_data.series_code') = 'FXERD01' THEN 'boj'
            END"""
    elif plan_field == "dataset_id":
        adapter = f"""CASE
            WHEN {engine} = 'gate_c_file_watch' AND {source} = 'tic' THEN 'TIC_TABLE5'
            WHEN {engine} = 'gate_c_file_watch' AND {source} = 'bis' THEN 'WS_GLI_csv_col'
            WHEN {engine} IN ('boj_metadata', 'boj_observations')
             AND json_extract(p.value, '$.input_data.database') = 'FM08'
             AND json_extract(p.value, '$.input_data.series_code') = 'FXERD01' THEN 'FM08'
            END"""
    return f"""COALESCE(
        json_extract(p.value, '$.input_data.{plan_field}'),
        json_extract(t.document, '$.knowledge_context.{knowledge_field}'),
        {workflow_value},
        {adapter}
    )"""


class PatternAnalyzer:
    """Produce deterministic draft candidates without changing tasks or feedback."""

    def __init__(self, history: HistoryStore | Settings):
        if isinstance(history, HistoryStore):
            self.database_path = history.settings.database_path
        elif isinstance(history, Settings):
            self.database_path = history.database_path
        else:
            raise TypeError("expected HistoryStore or Settings")

    def _connect_read_only(self):
        uri = self.database_path.as_uri() + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=5)

    def analyze(self) -> dict:
        """Read only terminal metadata and accepted user instructions within fixed limits."""
        if not self.database_path.exists():
            return self._empty_result()
        with self._connect_read_only() as connection:
            connection.execute("BEGIN")
            task_rows = connection.execute(
                "SELECT task_id, json_extract(document, '$.created_at'), "
                "json_extract(document, '$.status') FROM tasks "
                "WHERE json_extract(document, '$.status') IN (?, ?, ?, ?) "
                "ORDER BY rowid DESC LIMIT ?",
                (*_TERMINAL_TASKS, MAX_TASKS),
            ).fetchall()
            task_truncated = connection.execute(
                "SELECT 1 FROM tasks WHERE json_extract(document, '$.status') IN (?, ?, ?, ?) "
                "ORDER BY rowid DESC LIMIT 1 OFFSET ?",
                (*_TERMINAL_TASKS, MAX_TASKS),
            ).fetchone() is not None
            task_ids = [row[0] for row in task_rows]
            task_meta = {row[0]: {"created_at": row[1], "status": row[2]} for row in task_rows}
            logical_bytes = sum(_size(value) for row in task_rows for value in row)

            stage_rows = []
            stage_truncated = False
            if task_ids:
                sql = f"""SELECT t.task_id,
                    json_extract(t.document, '$.created_at'),
                    json_extract(s.value, '$.stage_run_id'),
                    json_extract(s.value, '$.stage_id'),
                    COALESCE(json_extract(s.value, '$.engine'), json_extract(p.value, '$.engine')),
                    COALESCE(json_extract(s.value, '$.engine_version'),
                             json_extract(p.value, '$.engine_version')),
                    json_extract(s.value, '$.status'),
                    json_extract(s.value, '$.result.error_code'),
                    json_extract(s.value, '$.started_at'),
                    json_extract(s.value, '$.finished_at'),
                    {_stage_scope_sql('institution_id', 'institution_id', 'institution_id')},
                    {_stage_scope_sql('dataset_id', 'scope.dataset_id', 'dataset_id')},
                    {_stage_scope_sql(
                        'concept', 'scope.concept', 'concept',
                        '$.workflow_context.confirmation.offer.request.concept')}
                FROM tasks AS t
                JOIN json_each(t.document, '$.stages') AS s
                LEFT JOIN json_each(t.document, '$.plan') AS p
                  ON json_extract(p.value, '$.stage_id') = json_extract(s.value, '$.stage_id')
                WHERE t.task_id=?
                  AND json_extract(s.value, '$.status') IN ({','.join('?' for _ in _STAGE_OUTCOMES)})
                LIMIT ?"""
                for task_id in task_ids:
                    remaining = MAX_RECORDS - len(stage_rows)
                    if remaining == 0:
                        break
                    batch = connection.execute(
                        sql, (task_id, *_STAGE_OUTCOMES, remaining),
                    ).fetchall()
                    stage_rows.extend(batch)
                if len(stage_rows) == MAX_RECORDS:
                    placeholders = ",".join("?" for _ in task_ids)
                    stage_truncated = connection.execute(
                        f"""SELECT 1 FROM tasks AS t
                        JOIN json_each(t.document, '$.stages') AS s
                        WHERE t.task_id IN ({placeholders})
                          AND json_extract(s.value, '$.status') IN (
                              {','.join('?' for _ in _STAGE_OUTCOMES)})
                        LIMIT 1 OFFSET ?""",
                        (*task_ids, *_STAGE_OUTCOMES, MAX_RECORDS),
                    ).fetchone() is not None
            stage_count = len(stage_rows)
            logical_bytes += sum(_size(value) for row in stage_rows for value in row)

            remaining = max(0, MAX_RECORDS - stage_count)
            feedback_rows = []
            feedback_truncated = False
            has_feedback = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feedback_current'",
            ).fetchone() is not None
            if not stage_truncated and task_ids and has_feedback:
                feedback_limit = MAX_RECORDS - stage_count
                sql = """SELECT f.feedback_id, f.task_id,
                        json_extract(f.document, '$.category'),
                        json_extract(f.document, '$.text'),
                        json_extract(f.document, '$.scope.institution_id'),
                        json_extract(f.document, '$.scope.dataset_id'),
                        json_extract(f.document, '$.scope.concept'),
                        json_extract(f.document, '$.stage_run_id'),
                        json_extract(f.document, '$.recorded_at')
                    FROM feedback_current AS f JOIN tasks AS t ON t.task_id=f.task_id
                    WHERE f.task_id=?
                      AND json_extract(t.document, '$.status') IN (?, ?, ?, ?)
                      AND json_extract(f.document, '$.review_status')='accepted'
                      AND json_extract(f.document, '$.knowledge_kind')='user_instruction'
                    LIMIT ?"""
                for task_id in task_ids:
                    remaining = MAX_RECORDS - stage_count - len(feedback_rows)
                    if remaining == 0:
                        break
                    batch = connection.execute(sql, (task_id, *_TERMINAL_TASKS, remaining)).fetchall()
                    feedback_rows.extend(batch)
                if len(feedback_rows) == feedback_limit:
                    placeholders = ",".join("?" for _ in task_ids)
                    feedback_truncated = connection.execute(
                        f"""SELECT 1 FROM feedback_current AS f
                        JOIN tasks AS t ON t.task_id=f.task_id
                        WHERE f.task_id IN ({placeholders})
                          AND json_extract(t.document, '$.status') IN (?, ?, ?, ?)
                          AND json_extract(f.document, '$.review_status')='accepted'
                          AND json_extract(f.document, '$.knowledge_kind')='user_instruction'
                        LIMIT 1 OFFSET ?""",
                        (*task_ids, *_TERMINAL_TASKS, feedback_limit),
                    ).fetchone() is not None
            feedback_count = len(feedback_rows)
            logical_bytes += sum(_size(value) for row in feedback_rows for value in row)

        outcomes, stage_by_id = self._stage_observations(stage_rows, task_meta)
        (feedback, unsafe_feedback_count, invalid_feedback_count,
         missing_stage_feedback_count) = self._feedback_observations(
            feedback_rows, task_meta, stage_by_id,
        )
        candidates, one_offs, insufficient, possible_conflicts = self._aggregate(
            outcomes + feedback,
        )
        overflow = len(candidates) > MAX_PROPOSALS
        candidates = sorted(
            candidates,
            key=lambda item: (0 if item["priority"] == "high" else 1,
                              -item["distinct_task_count"], item["proposal_id"]),
        )
        proposals = candidates[:MAX_PROPOSALS]
        partial = task_truncated or stage_truncated or feedback_truncated or overflow
        return {
            "schema_version": 1,
            "status": "partial" if partial else "complete",
            "read_only": True,
            "limits": {"tasks": MAX_TASKS, "records": MAX_RECORDS,
                       "proposals": MAX_PROPOSALS,
                       "evidence_per_proposal": MAX_EVIDENCE_PER_PROPOSAL},
            "metrics": {
                "tasks_scanned": len(task_rows), "stage_records_scanned": stage_count,
                "feedback_records_scanned": feedback_count,
                "records_scanned": stage_count + feedback_count,
                "logical_bytes_read": logical_bytes,
                "candidate_count": len(candidates), "proposal_count": len(proposals),
                "scope_complete_candidate_count": sum(
                    not item["scope_unknown"] for item in candidates
                ),
            },
            "truncation": {
                "tasks": task_truncated, "records": stage_truncated or feedback_truncated,
                "proposals": overflow,
            },
            "summary": {
                "one_off_count": len(one_offs),
                "insufficient_evidence_count": (len(insufficient) + invalid_feedback_count
                                                 + missing_stage_feedback_count),
                "possible_conflict_count": len(possible_conflicts),
                "unsafe_feedback_excluded": unsafe_feedback_count,
                "invalid_feedback_excluded": invalid_feedback_count,
                "feedback_stage_link_missing": missing_stage_feedback_count,
                "one_off_sample": one_offs[:10],
                "insufficient_evidence_sample": insufficient[:10],
                "possible_conflicts": possible_conflicts[:10],
            },
            "proposals": proposals,
        }

    @staticmethod
    def _empty_result():
        return {
            "schema_version": 1, "status": "complete", "read_only": True,
            "limits": {"tasks": MAX_TASKS, "records": MAX_RECORDS,
                       "proposals": MAX_PROPOSALS,
                       "evidence_per_proposal": MAX_EVIDENCE_PER_PROPOSAL},
            "metrics": {"tasks_scanned": 0, "stage_records_scanned": 0,
                        "feedback_records_scanned": 0, "records_scanned": 0,
                        "logical_bytes_read": 0, "candidate_count": 0,
                        "proposal_count": 0, "scope_complete_candidate_count": 0},
            "truncation": {"tasks": False, "records": False, "proposals": False},
            "summary": {"one_off_count": 0, "insufficient_evidence_count": 0,
                        "possible_conflict_count": 0, "unsafe_feedback_excluded": 0,
                        "invalid_feedback_excluded": 0,
                        "feedback_stage_link_missing": 0,
                        "one_off_sample": [], "insufficient_evidence_sample": [],
                        "possible_conflicts": []},
            "proposals": [],
        }

    @staticmethod
    def _stage_observations(rows, task_meta):
        observations = []
        by_stage_id = {}
        for row in rows:
            (task_id, _created, stage_run_id, stage_id, engine, engine_version, status,
             error_code, started_at, finished_at, institution, dataset, concept) = row
            institution = _safe_scope(institution, institution=True)
            dataset = _safe_scope(dataset)
            concept = _safe_scope(concept)
            item = {
                "type": "stage_error" if status in _FAILURES else "stage_outcome",
                "task_id": task_id, "evidence_id": stage_run_id,
                "engine": _safe_scope(engine), "engine_version": _safe_scope(engine_version),
                "stage_id": _safe_scope(stage_id), "status": status,
                "error_category": (error_code if error_code in _ERROR_CODES else
                                   status if status == "NEEDS_REVIEW" and error_code is None else None),
                "institution_id": institution, "dataset_id": dataset, "concept": concept,
                "observed_at": finished_at or started_at or task_meta[task_id]["created_at"],
            }
            observations.append(item)
            if stage_run_id:
                by_stage_id[stage_run_id] = item
        return observations, by_stage_id

    @staticmethod
    def _feedback_observations(rows, task_meta, stage_by_id):
        observations = []
        unsafe_count = 0
        invalid_count = 0
        missing_stage_count = 0
        for row in rows:
            (feedback_id, task_id, category, text, institution, dataset, concept,
             stage_run_id, recorded_at) = row
            if category not in _FEEDBACK_CATEGORIES:
                invalid_count += 1
                continue
            if not isinstance(text, str) or len(text) > 4_000 or _has_secret(text):
                unsafe_count += 1
                continue
            normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
            if not normalized:
                unsafe_count += 1
                continue
            linked = stage_by_id.get(stage_run_id)
            if stage_run_id and linked is None:
                # A capped/missing stage reference cannot safely establish the fingerprint.
                missing_stage_count += 1
                continue
            institution = _safe_scope(institution, institution=True)
            dataset = _safe_scope(dataset)
            concept = _safe_scope(concept)
            if linked:
                engine, engine_version, stage_id = (
                    linked["engine"], linked["engine_version"], linked["stage_id"],
                )
            else:
                engine, engine_version, stage_id = "accepted_user_feedback", "1", "accepted_feedback"
            observations.append({
                "type": "accepted_feedback", "task_id": task_id,
                "evidence_id": feedback_id, "engine": engine,
                "engine_version": engine_version, "stage_id": stage_id,
                "error_category": "feedback:" + str(category), "status": "ACCEPTED",
                "institution_id": institution, "dataset_id": dataset, "concept": concept,
                "observed_at": recorded_at or task_meta[task_id]["created_at"],
                "content_fingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            })
        return observations, unsafe_count, invalid_count, missing_stage_count

    @staticmethod
    def _aggregate(observations):
        groups = defaultdict(list)
        stage_outcomes = defaultdict(list)
        feedback_scope_texts = defaultdict(lambda: defaultdict(list))
        one_offs, insufficient = [], []

        for item in observations:
            fields = [
                "type", "institution_id", "engine", "engine_version", "stage_id",
                "dataset_id", "concept", "content_fingerprint",
            ]
            if item["type"] != "stage_outcome":
                fields.append("error_category")
            fingerprint = {field: item.get(field) for field in fields if field in item}
            required = ("error_category",) if item["type"] != "stage_outcome" else ()
            key, unknown = _distinct_unknowns(fingerprint, item["task_id"], required)
            if item["type"] == "stage_outcome":
                base = {name: fingerprint.get(name) for name in (
                    "institution_id", "engine", "engine_version", "stage_id", "dataset_id", "concept",
                )}
                base_key, _base_unknown = _distinct_unknowns(base, item["task_id"])
                stage_outcomes[base_key].append(item)
                if item["status"] not in _FAILURES:
                    continue
            if item["type"] == "accepted_feedback":
                scope_key = _json_key({name: item.get(name) for name in (
                    "institution_id", "engine", "engine_version", "stage_id",
                    "dataset_id", "concept", "error_category",
                )})
                if not unknown:
                    feedback_scope_texts[scope_key][item["content_fingerprint"]].append(item)
            if unknown:
                insufficient.append({"evidence_id": item["evidence_id"],
                                     "task_id": item["task_id"],
                                     "unknown_dimensions": unknown})
            groups[key].append({**item, "fingerprint": fingerprint, "scope_unknown": unknown})

        conflicting_feedback_keys = set()
        possible_conflicts = []
        for scope_key, text_groups in feedback_scope_texts.items():
            if len(text_groups) > 1:
                conflicting_feedback_keys.add(scope_key)
                ids = sorted(item["evidence_id"] for group in text_groups.values() for item in group)
                possible_conflicts.append({"scope_fingerprint": hashlib.sha256(
                    scope_key.encode("utf-8")).hexdigest(), "evidence_ids": ids[:10],
                    "distinct_instruction_count": len(text_groups),
                    "review_status": "possible_conflict_requires_human_review"})

        proposals = []
        for key, items in groups.items():
            distinct_tasks = sorted({item["task_id"] for item in items})
            if len(distinct_tasks) < 3 or any(item["scope_unknown"] for item in items):
                continue
            exemplar = items[0]
            if exemplar["type"] == "accepted_feedback":
                scope_key = _json_key({name: exemplar.get(name) for name in (
                    "institution_id", "engine", "engine_version", "stage_id",
                    "dataset_id", "concept", "error_category",
                )})
                if scope_key in conflicting_feedback_keys:
                    continue
            status_by_task = {}
            for item in items:
                status_by_task[item["task_id"]] = item["status"]
            terminal_failures = sum(value == "FAILED_TERMINAL" for value in status_by_task.values())
            high_priority = exemplar["type"] == "stage_error" and terminal_failures > 0
            matching = items
            base_counterexamples = []
            if exemplar["type"] == "stage_error":
                base = {name: exemplar["fingerprint"].get(name) for name in (
                    "institution_id", "engine", "engine_version", "stage_id", "dataset_id", "concept",
                )}
                base_key, _ = _distinct_unknowns(base, exemplar["task_id"])
                base_counterexamples = [item for item in stage_outcomes.get(base_key, ())
                                        if item["error_category"] != exemplar["error_category"]]
            counterexamples = []
            if base_counterexamples:
                counterexamples = [{"evidence_id": item["evidence_id"],
                                    "task_id": item["task_id"],
                                    "status": item["status"],
                                    "error_category": item["error_category"]}
                                   for item in base_counterexamples[:10]]
            proposal_id = "pattern-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            unknown_names = sorted({name for item in items for name in item["scope_unknown"]})
            is_feedback = exemplar["type"] == "accepted_feedback"
            proposals.append({
                "proposal_id": proposal_id,
                "proposal_type": "recurring_accepted_feedback" if is_feedback
                                 else "recurring_stage_error",
                "review_status": "draft", "promotion_status": "not_promoted",
                "fingerprint": exemplar["fingerprint"],
                "scope": {name: exemplar.get(name) for name in (
                    "institution_id", "dataset_id", "concept")},
                "scope_unknown": unknown_names,
                "distinct_task_count": len(distinct_tasks),
                "observed_from": min((item["observed_at"] for item in items
                                       if item.get("observed_at")), default=None),
                "observed_through": max((item["observed_at"] for item in items
                                          if item.get("observed_at")), default=None),
                "evidence_ids": sorted({item["evidence_id"] for item in matching})[
                    :MAX_EVIDENCE_PER_PROPOSAL],
                "severity_basis": ({"distinct_tasks": len(distinct_tasks),
                                    "terminal_failure_tasks": terminal_failures,
                                    "status_counts_by_distinct_task": {
                                        status: sum(value == status for value in status_by_task.values())
                                        for status in sorted(set(status_by_task.values()))},
                                    "derived_from": "persisted stage status only"}
                                   if not is_feedback else {
                                       "distinct_tasks": len(distinct_tasks),
                                       "basis": "accepted explicit user feedback recurrence",
                                       "operational_severity": "not_inferred"}),
                "expected_impact": (
                    "The bounded stage may require repeated recovery or review in this scope; "
                    "no data or economic impact is inferred."
                    if not is_feedback else
                    "A repeated, accepted instruction may guide a scoped review; it is not applied automatically."
                ),
                "counterexamples": counterexamples,
                "uncertainty": ["Historical recurrence does not establish root cause or future behavior."],
                "regression_test_proposal": (
                    "Use fixtures from three distinct tasks with this fingerprint; assert one draft "
                    "proposal and preserve the input task and feedback records."
                ),
                "risk": "A repeated symptom may have different causes; human review is required.",
                "priority": "high" if high_priority else "review",
            })
        for key, items in groups.items():
            if len({item["task_id"] for item in items}) in (1, 2) and not any(
                    item["scope_unknown"] for item in items):
                one_offs.append({"evidence_id": items[0]["evidence_id"],
                                 "task_id": items[0]["task_id"],
                                 "pattern_type": items[0]["type"],
                                 "distinct_task_count": len({item["task_id"] for item in items})})
        return proposals, one_offs, insufficient, possible_conflicts
