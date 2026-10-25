"""Bounded, deterministic analysis of recorded errors, feedback, and inference candidates."""
from __future__ import annotations

import hashlib
import json
import time
import unicodedata
from collections import defaultdict

from macro_data_platform.storage.audit import AuditStore
from macro_data_platform.storage.history import HistoryStore

MAX_RECORDS_PER_STREAM = 2_000
MAX_PATTERN_COUNT = 500
MAX_SCAN_BYTES = 16_777_216
MAX_SCAN_TIME_MS = 5_000
MAX_REFS_PER_PATTERN = 100
_SEVERITY_POLICY_VERSION = "structured-error-severity-v1"
_SCOPE_FIELDS = ("institution_id", "dataset_id", "concept_id", "classification_axis")
_ERROR_POLICY = {
    "LICENSE_SECURITY": ("critical", "Do not retry or bypass; review source terms and access."),
    "INTERNAL_BUG": ("high", "Reproduce the failing stage with a minimal fixture before code changes."),
    "AUTH_ACCESS": ("high", "Review the configured access path; do not bypass authentication."),
    "QUALITY_FAILURE": ("high", "Add a scoped quality regression while preserving the raw source."),
    "SCHEMA_CHANGED": ("medium", "Compare a versioned source fixture and update parsing only with evidence."),
    "SEMANTIC_AMBIGUITY": ("medium", "Improve clarification or evidence capture; do not guess a statistical meaning."),
    "SITE_CHANGED": ("medium", "Review the official source strategy and retain the previous snapshot."),
    "TRANSIENT": ("low", "Review bounded retry and due-time evidence; do not add unbounded retries."),
}
_CORRECTION_POLICY = {
    "source_fact": ("high", "Recheck cited source evidence and add a versioned provenance regression."),
    "concept_mapping": ("high", "Review definitions, dimensions, and counterexamples before changing mappings."),
    "candidate_grouping": ("medium", "Add a scoped candidate-grouping regression and retain user choice."),
    "question_order": ("medium", "Add a question-order regression without changing source facts."),
    "output_preference": ("low", "Keep this as a confirmation-required presentation suggestion."),
    "general": ("low", "Classify the feedback manually before proposing a code or policy change."),
}


def _json_digest(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_fingerprint(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _scope(document: dict) -> dict:
    return {name: document.get(name) for name in _SCOPE_FIELDS}


def _priority(severity: str, distinct_tasks: int) -> str:
    if severity == "critical":
        return "P0"
    if severity == "high" or distinct_tasks >= 3:
        return "P1"
    if severity == "medium" or distinct_tasks >= 2:
        return "P2"
    return "P3"


class ImprovementAnalyzer:
    """Create proposals from explicit structured evidence without changing project state."""

    def __init__(self, history: HistoryStore):
        self.history = history

    def analyze(self, *, max_records: int = 500, max_patterns: int = 100,
                max_bytes: int = 4_194_304, max_time_ms: int = 1_000) -> dict:
        if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS_PER_STREAM:
            raise ValueError("improvement scan record budget is outside the supported range")
        if type(max_patterns) is not int or not 1 <= max_patterns <= MAX_PATTERN_COUNT:
            raise ValueError("improvement pattern budget is outside the supported range")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_SCAN_BYTES:
            raise ValueError("improvement scan byte budget is outside the supported range")
        if type(max_time_ms) is not int or not 1 <= max_time_ms <= MAX_SCAN_TIME_MS:
            raise ValueError("improvement scan time budget is outside the supported range")

        started = time.perf_counter()
        deadline = started + max_time_ms / 1000
        byte_count = 0
        scanned = defaultdict(int)
        truncated_streams = set()
        timed_out = False
        byte_limited = False
        groups = {}
        task_stage_cache = {}

        with self.history._connect() as connection:
            connection.execute("BEGIN")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "gate_a_records" in tables:
                for kind in ("incident", "feedback"):
                    cursor = connection.execute(
                        "SELECT record_id, task_id, stage_run_id, document FROM gate_a_records "
                        "WHERE kind=? ORDER BY rowid DESC LIMIT ?", (kind, max_records + 1),
                    )
                    for position in range(max_records + 1):
                        if time.perf_counter() >= deadline:
                            timed_out = True
                            break
                        row = cursor.fetchone()
                        if row is None:
                            break
                        if position == max_records:
                            truncated_streams.add("audit_" + kind)
                            break
                        record_id, task_id, stage_run_id, encoded = row
                        size = len(encoded.encode("utf-8"))
                        if byte_count + size > max_bytes:
                            byte_limited = True
                            break
                        byte_count += size
                        scanned["audit_" + kind] += 1
                        record = json.loads(encoded)
                        if record.get("record_id") != record_id or record.get("task_id") != task_id:
                            raise ValueError("audit record identity integrity check failed")
                        if kind == "incident":
                            self._add_incident(groups, connection, record, stage_run_id,
                                               task_stage_cache)
                        else:
                            if "gate_a_feedback_events" in tables:
                                feedback = AuditStore._feedback_view(connection, record_id)
                            else:
                                feedback = {**record, "cancelled": False,
                                            "review_status": record.get("review_status", "recorded_unreviewed")}
                            self._add_feedback(groups, feedback)
                    if timed_out or byte_limited:
                        break

            if (not timed_out and not byte_limited and "knowledge_current" in tables
                    and "knowledge_records" in tables):
                cursor = connection.execute(
                    "SELECT c.record_id, c.source_rowid, c.review_status, r.document, r.digest "
                    "FROM knowledge_current c JOIN knowledge_records r USING(record_id) "
                    "WHERE c.provenance='inference' AND c.active=1 "
                    "AND c.review_status IN ('pending', 'deferred') "
                    "ORDER BY c.source_rowid DESC LIMIT ?", (max_records + 1,),
                )
                for position in range(max_records + 1):
                    if time.perf_counter() >= deadline:
                        timed_out = True
                        break
                    row = cursor.fetchone()
                    if row is None:
                        break
                    if position == max_records:
                        truncated_streams.add("knowledge_inference")
                        break
                    record_id, _, review_status, encoded, expected_digest = row
                    size = len(encoded.encode("utf-8"))
                    if byte_count + size > max_bytes:
                        byte_limited = True
                        break
                    byte_count += size
                    scanned["knowledge_inference"] += 1
                    record = json.loads(encoded)
                    if (_json_digest(record) != expected_digest
                            or record.get("record_id") != record_id
                            or record.get("provenance") != "inference"):
                        raise ValueError("inference record integrity check failed")
                    self._add_inference(groups, record, review_status)

        candidates = [self._candidate(key, group) for key, group in groups.items()]
        candidates.sort(key=lambda item: (item["priority"],
                                          -item["distinct_task_count"],
                                          -item["observation_count"], item["pattern_id"]))
        patterns_truncated = len(candidates) > max_patterns
        candidates = candidates[:max_patterns]
        partial = bool(truncated_streams or timed_out or byte_limited or patterns_truncated)
        uncertainties = []
        if truncated_streams:
            uncertainties.extend("record_budget_exhausted:" + name
                                 for name in sorted(truncated_streams))
        if timed_out:
            uncertainties.append("time_budget_exhausted")
        if byte_limited:
            uncertainties.append("byte_budget_exhausted")
        if patterns_truncated:
            uncertainties.append("pattern_budget_exhausted")
        if partial:
            for candidate in candidates:
                candidate["apply_allowed"] = False
                candidate["proposal_status"] = "incomplete_scan_requires_review"
        return {
            "status": "partial" if partial else "complete",
            "read_only": True,
            "approval_required": True,
            "severity_policy_version": _SEVERITY_POLICY_VERSION,
            "scan_limits": {"records_per_stream": max_records,
                            "patterns": max_patterns, "bytes": max_bytes,
                            "time_ms": max_time_ms},
            "records_scanned": dict(scanned),
            "patterns": candidates,
            "uncertainties": uncertainties,
            "metrics": {"bytes_read": byte_count,
                        "patterns_generated": len(candidates),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)},
        }

    def _stage_id(self, connection, task_id, stage_run_id, cache):
        if not stage_run_id:
            return None
        key = (task_id, stage_run_id)
        if key not in cache:
            row = connection.execute("SELECT document FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            task = json.loads(row[0]) if row is not None else {}
            cache[key] = next((stage.get("stage_id") for stage in task.get("stages", ())
                               if stage.get("stage_run_id") == stage_run_id), None)
        return cache[key]

    def _add_incident(self, groups, connection, record, stage_run_id, stage_cache):
        error_code = record.get("error_code")
        if not isinstance(error_code, str) or not error_code:
            error_code = "UNCLASSIFIED"
        stage_id = self._stage_id(connection, record["task_id"], stage_run_id, stage_cache)
        key = ("error", error_code, stage_id)
        group = groups.setdefault(key, {"kind": "error", "error_code": error_code,
                                        "stage_id": stage_id, "records": [], "tasks": set(),
                                        "severity": _ERROR_POLICY.get(error_code, ("unknown", ""))[0]})
        group["records"].append(record["record_id"])
        group["tasks"].add(record["task_id"])

    @staticmethod
    def _add_feedback(groups, feedback):
        if (feedback.get("cancelled") or feedback.get("origin") != "user"
                or feedback.get("category") not in {"problem", "correction"}):
            return
        text = feedback.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        scope = _scope(feedback.get("scope", {}))
        correction_type = feedback.get("scope", {}).get("correction_type", "general")
        fingerprint = _normalized_fingerprint(text)
        key = ("feedback", feedback["category"], correction_type,
               *(scope[name] for name in _SCOPE_FIELDS), fingerprint)
        severity = _CORRECTION_POLICY.get(correction_type, ("unknown", ""))[0]
        group = groups.setdefault(key, {"kind": "feedback", "category": feedback["category"],
                                        "correction_type": correction_type, "scope": scope,
                                        "statement_fingerprint": fingerprint, "records": [],
                                        "tasks": set(), "review_states": set(),
                                        "severity": severity})
        group["records"].append(feedback["record_id"])
        group["tasks"].add(feedback["task_id"])
        group["review_states"].add(feedback.get("review_status", "recorded_unreviewed"))

    @staticmethod
    def _add_inference(groups, record, review_status):
        fingerprint = _normalized_fingerprint(record["statement"])
        scope = _scope(record)
        key = ("inference", *(scope[name] for name in _SCOPE_FIELDS), fingerprint)
        group = groups.setdefault(key, {"kind": "inference", "scope": scope,
                                        "statement_fingerprint": fingerprint,
                                        "records": [], "tasks": set(),
                                        "premise_evidence_refs": set(),
                                        "review_states": set(), "severity": "high"})
        group["records"].append(record["record_id"])
        if record.get("task_id"):
            group["tasks"].add(record["task_id"])
        group["premise_evidence_refs"].update(record.get("evidence_refs", ()))
        group["review_states"].add(review_status)

    @staticmethod
    def _candidate(key, group):
        distinct_tasks = len(group["tasks"])
        observations = len(group["records"])
        severity = group["severity"]
        priority = _priority(severity, distinct_tasks)
        pattern_id = _json_digest({"policy": _SEVERITY_POLICY_VERSION, "key": list(key)})[:24]
        classification = ("recurring_across_multiple_tasks" if distinct_tasks >= 3 else
                          "repeated_across_tasks" if distinct_tasks >= 2 else
                          "single_observation")
        refs = sorted(set(group["records"]))
        source_refs = refs[:MAX_REFS_PER_PATTERN]
        common = {
            "pattern_id": pattern_id, "pattern_type": group["kind"],
            "priority": priority, "severity": severity,
            "observation_count": observations, "distinct_task_count": distinct_tasks,
            "classification": classification,
            "record_refs": source_refs,
            "record_refs_omitted": max(0, len(refs) - len(source_refs)),
            "scope": group.get("scope", {"institution_id": None, "dataset_id": None,
                                           "concept_id": None, "classification_axis": None}),
            "proposal_status": "candidate_requires_human_review",
            "review_status": "requires_human_review", "apply_allowed": False,
            "generalization_status": "not_established",
        }
        if group["kind"] == "error":
            _, action = _ERROR_POLICY.get(group["error_code"],
                                          ("unknown", "Classify this error with a reviewer."))
            recommendation = (action if distinct_tasks >= 2 else
                              "Collect another independent reproduction before proposing a systemic change.")
            return {**common, "error_code": group["error_code"], "stage_id": group["stage_id"],
                    "recommendation": recommendation,
                    "expected_impact": (f"If reproduced, a scoped regression may reduce recurrence of "
                                        f"{group['error_code']} at this stage while preserving source evidence."),
                    "test_plan": ["Reproduce the exact structured error in a deterministic fixture.",
                                  "Assert raw/source evidence remains unchanged.",
                                  "Assert the expected safe status and recovery boundary."],
                    "risk": "Changing retry, access, source meaning, or parsing without a reproduced fixture can hide a source or data-integrity failure."}
        if group["kind"] == "feedback":
            _, action = _CORRECTION_POLICY.get(group["correction_type"],
                                               ("unknown", "Classify feedback with a reviewer."))
            return {**common, "category": group["category"],
                    "correction_type": group["correction_type"],
                    "statement_fingerprint": group["statement_fingerprint"],
                    "input_review_states": sorted(group["review_states"]),
                    "recommendation": (action if distinct_tasks >= 2 else
                                       "Treat as a task-local observation until independently reproduced."),
                    "expected_impact": (f"A scoped behavior regression may reduce repeated "
                                        f"{group['correction_type']} corrections within this declared scope."),
                    "test_plan": ["Use a fixture for the exact institution/concept scope.",
                                  "Assert explicit current-task instructions still take precedence.",
                                  "Assert no other institution receives the preference or claimed fact."],
                    "risk": "Feedback repetition is not official-source verification and cannot establish a cross-institution rule."}
        return {**common, "pattern_type": "inference_review",
                "statement_fingerprint": group["statement_fingerprint"],
                "premise_record_refs": source_refs,
                "premise_record_refs_omitted": max(0, len(refs) - len(source_refs)),
                "evidence_refs": sorted(group["premise_evidence_refs"])[:MAX_REFS_PER_PATTERN],
                "counterexample_refs": [], "counterexample_search_required": True,
                "input_review_states": sorted(group["review_states"]),
                "recommendation": "Review this quarantined inference with source evidence and explicit counterexamples before proposing any relation or generalization.",
                "expected_impact": "A reviewed relation candidate may improve scoped discovery; this proposal changes no mapping or fact.",
                "test_plan": ["Record explicit premises and source-versioned evidence.",
                              "Search and record counterexamples in the same declared scope.",
                              "Keep the hypothesis quarantined; assert no fact or code is changed."],
                "risk": "A recurring label or inference record does not prove conceptual equivalence."}
