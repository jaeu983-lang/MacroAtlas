"""Versioned, evidence-linked evaluation case contract."""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlsplit

from macro_data_platform.workflow_contracts import DataRequest

_CASE_TYPES = {"rankable", "near_match", "insufficient_evidence", "unrelated"}
_SPLITS = {"development", "validation", "holdout"}
_STATES = {"candidate_found", "review_required", "unmatched"}
_MATCH_STATUSES = {"exact", "comparable", "related", "review_required"}
_FIELD_STATES = {"known", "unknown", "conflict"}
_EVIDENCE_KINDS = {
    "official_docs", "live_api", "live_ingestion", "fixture", "synthetic_fixture",
    "catalog_snapshot",
}
_ID = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}")
_CANDIDATE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_CREDENTIAL_QUERY_NAMES = {
    "key", "apikey", "token", "accesstoken", "password", "secret", "authorization",
    "appid", "applicationid", "userid", "clientsecret", "subscriptionkey",
}
_MAX_VARIANTS = 32
_MAX_EVIDENCE = 32


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _identifier(value: Any, name: str) -> str:
    _check(isinstance(value, str) and _ID.fullmatch(value) is not None,
           f"Invalid {name}")
    return value


def _candidate_identifier(value: Any, name: str) -> str:
    _check(isinstance(value, str) and _CANDIDATE_ID.fullmatch(value) is not None,
           f"Invalid {name}")
    return value


def _text(value: Any, name: str, *, max_length: int = 4000) -> str:
    _check(isinstance(value, str) and bool(value.strip()) and len(value) <= max_length,
           f"Invalid {name}")
    return value


def _json_value(value: Any, *, depth: int = 0) -> Any:
    _check(depth <= 12, "JSON value nesting is too deep")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        _check(math.isfinite(value),
               "Non-finite JSON numbers are not allowed")
        return value
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            _check(isinstance(key, str) and bool(key), "Expected JSON object keys")
            result[key] = _json_value(item, depth=depth + 1)
        return MappingProxyType(result)
    if isinstance(value, (tuple, list)):
        return tuple(_json_value(item, depth=depth + 1) for item in value)
    raise ValueError("Expected JSON-compatible value")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _sequence(value: Any, name: str, *, maximum: int = 256) -> tuple[str, ...]:
    _check(isinstance(value, (tuple, list)) and len(value) <= maximum,
           f"Invalid {name}")
    result = tuple(_text(item, name) for item in value)
    _check(len(result) == len(set(result)), f"Duplicate {name}")
    return result


def _utc_timestamp(value: Any) -> str:
    _text(value, "evidence timestamp", max_length=64)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid evidence timestamp") from None
    _check(parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(parsed),
           "Evidence timestamp must be UTC")
    return value


def _safe_uri(value: Any) -> str:
    _text(value, "official URI", max_length=2048)
    try:
        parsed = urlsplit(value)
        names = [re.sub(r"[^a-z0-9]", "", name.casefold())
                 for name, _ in parse_qsl(parsed.query, keep_blank_values=True)]
        safe = (parsed.scheme == "https" and parsed.hostname and parsed.username is None
                and parsed.password is None and not parsed.fragment
                and not any(name in _CREDENTIAL_QUERY_NAMES for name in names))
    except ValueError:
        safe = False
    _check(bool(safe), "Evidence URI must be credential-free HTTPS")
    return value


def _local_ref(value: Any) -> str:
    _text(value, "local evidence reference", max_length=512)
    path = PurePosixPath(value)
    _check(not path.is_absolute() and ".." not in path.parts and "\\" not in value,
           "Evidence reference must be a safe repository-relative path")
    return value


def _evidence(value: Any) -> Mapping[str, Any]:
    _check(isinstance(value, Mapping), "Expected required evidence object")
    base = {"evidence_id", "evidence_kind", "official_uri", "local_ref",
            "retrieved_at", "sha256", "claim"}
    kind = value.get("evidence_kind")
    if kind == "synthetic_fixture":
        required = base | {"purpose", "candidate_id"}
    elif kind == "catalog_snapshot":
        required = base | {"purpose"}
    else:
        required = base
    _check(set(value) == required, "Invalid required evidence fields")
    _identifier(value["evidence_id"], "evidence identifier")
    _check(isinstance(kind, str) and kind in _EVIDENCE_KINDS, "Unknown evidence kind")
    _local_ref(value["local_ref"])
    _check(isinstance(value["sha256"], str) and _SHA256.fullmatch(value["sha256"]),
           "Invalid evidence SHA-256")
    _text(value["claim"], "evidence claim")
    if kind in {"synthetic_fixture", "catalog_snapshot"}:
        _check(value["official_uri"] is None and value["retrieved_at"] is None,
               "Local evaluation evidence cannot claim an official URI or retrieval time")
        _text(value["purpose"], "evaluation evidence purpose")
        if kind == "synthetic_fixture":
            _candidate_identifier(value["candidate_id"], "synthetic evidence candidate identifier")
            _check("synthetic" in value["claim"].casefold()
                   and "not official" in value["claim"].casefold(),
                   "Synthetic fixture claims must explicitly deny official-source status")
        else:
            _check("fixed evaluation catalog" in value["claim"].casefold(),
                   "Catalog-snapshot evidence must scope its claim to the fixed catalog")
    else:
        _safe_uri(value["official_uri"])
        _utc_timestamp(value["retrieved_at"])
    return _json_value(value)


def _authorship(value: Any) -> Mapping[str, Any]:
    _check(isinstance(value, Mapping), "Expected case authorship provenance")
    required = {"origin", "run_id", "generator_agents", "reviewer_agents",
                "prompt_sha256", "review_status", "human_observed"}
    _check(set(value) == required, "Invalid case authorship fields")
    _check(value["origin"] == "agent_simulated", "Unsupported case authorship origin")
    _identifier(value["run_id"], "case generation run identifier")
    generators = _sequence(value["generator_agents"], "generator agent", maximum=8)
    reviewers = _sequence(value["reviewer_agents"], "reviewer agent", maximum=8)
    _check(bool(generators) and bool(reviewers),
           "Agent-simulated cases need recorded authors and reviewers")
    _check(all(_ID.fullmatch(item) is not None for item in (*generators, *reviewers)),
           "Invalid case provenance agent identifier")
    _check(isinstance(value["prompt_sha256"], str)
           and _SHA256.fullmatch(value["prompt_sha256"]),
           "Invalid generation prompt SHA-256")
    _check(value["review_status"] == "multi_agent_reviewed",
           "Agent-simulated cases require multi-agent review")
    _check(value["human_observed"] is False,
           "AI-simulated cases cannot be marked as human observed")
    return _json_value(value)


def _field_expectation(value: Any) -> Mapping[str, Any]:
    _check(isinstance(value, Mapping), "Expected field expectation object")
    state = value.get("state")
    _check(isinstance(state, str) and state in _FIELD_STATES,
           "Unknown expected field state")
    if state == "known":
        _check(set(value) == {"state", "value"}, "Known field needs exactly one value")
        _json_value(value["value"])
    elif state == "unknown":
        _check(set(value) == {"state"}, "Unknown field cannot carry an inferred value")
    else:
        _check(set(value) == {"state", "values"}, "Conflict field needs source values")
        vals = value["values"]
        _check(isinstance(vals, (list, tuple)) and len(vals) >= 2,
               "Conflict field needs at least two values")
        _json_value(vals)
    return _json_value(value)


def _expected_fields(value: Any) -> Mapping[str, Mapping[str, Any]]:
    _check(isinstance(value, Mapping) and len(value) <= 64,
           "Expected candidate-specific fields")
    result = {}
    for candidate_id, fields in value.items():
        _candidate_identifier(candidate_id, "expected-field candidate identifier")
        _check(isinstance(fields, Mapping) and bool(fields),
               "Expected at least one candidate field")
        cleaned = {}
        for name, expectation in fields.items():
            _check(isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_.]{0,63}", name),
                   "Invalid expected field name")
            cleaned[name] = _field_expectation(expectation)
        result[candidate_id] = MappingProxyType(cleaned)
    return MappingProxyType(result)


def _excel_policy(value: Any) -> Mapping[str, Any]:
    required = {"grouping", "incompatible_series", "overlap_conflict", "date_basis",
                "aggregation", "transformation", "missing_values", "interpolation",
                "forward_fill"}
    _check(isinstance(value, Mapping) and set(value) == required,
           "Invalid Excel policy fields")
    expected = {
        "grouping": "one_series_per_sheet",
        "incompatible_series": "separate_sheets",
        "overlap_conflict": "preserve_separately_or_review",
        "date_basis": "source_period",
        "aggregation": "none",
        "transformation": "none",
        "missing_values": "blank",
        "interpolation": "none",
        "forward_fill": "none",
    }
    _check(dict(value) == expected, "Excel policy must preserve source series and missing values")
    return MappingProxyType(dict(expected))


@dataclass(frozen=True, repr=False)
class EvaluationCase:
    case_id: str
    case_version: int
    case_family_id: str
    split: str
    case_type: str
    request: Mapping[str, Any]
    query_variants: tuple[str, ...]
    expected_state: str
    relevant_candidate_ids: tuple[str, ...]
    forbidden_candidate_ids: tuple[str, ...]
    expected_match_status: Mapping[str, str]
    expected_fields: Mapping[str, Mapping[str, Any]]
    required_evidence: tuple[Mapping[str, Any], ...]
    prohibited_actions: tuple[str, ...]
    excel_policy: Mapping[str, Any]
    feedback_ref: Mapping[str, Any] | None = None
    authorship: Mapping[str, Any] | None = None

    _BASE_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "case_id", "case_version", "case_family_id", "split", "case_type", "request",
        "query_variants", "expected_state", "relevant_candidate_ids",
        "forbidden_candidate_ids", "expected_match_status", "expected_fields",
        "required_evidence", "prohibited_actions", "excel_policy", "feedback_ref",
    })
    _FIELDS: ClassVar[frozenset[str]] = _BASE_FIELDS | {"authorship"}

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case identifier")
        _check(type(self.case_version) is int and self.case_version >= 1,
               "Invalid case version")
        _identifier(self.case_family_id, "case family identifier")
        _check(isinstance(self.split, str) and self.split in _SPLITS, "Unknown case split")
        _check(isinstance(self.case_type, str) and self.case_type in _CASE_TYPES,
               "Unknown case type")
        _check(isinstance(self.expected_state, str) and self.expected_state in _STATES,
               "Unknown expected state")

        _check(isinstance(self.request, Mapping), "Expected DataRequest snapshot")
        request = DataRequest.from_dict(dict(self.request))
        _check(request.request_id == self.case_id,
               "DataRequest identifier must match its evaluation case")
        object.__setattr__(self, "request", _json_value(request.to_dict()))

        variants = _sequence(self.query_variants, "query variant", maximum=_MAX_VARIANTS)
        _check(bool(variants), "At least one query variant is required")
        _check(request.text in variants,
               "Query variants must include the DataRequest text")
        object.__setattr__(self, "query_variants", variants)

        relevant = tuple(_candidate_identifier(item, "relevant candidate identifier")
                         for item in self.relevant_candidate_ids)
        forbidden = tuple(_candidate_identifier(item, "forbidden candidate identifier")
                          for item in self.forbidden_candidate_ids)
        _check(len(relevant) == len(set(relevant)), "Duplicate relevant candidate identifiers")
        _check(len(forbidden) == len(set(forbidden)), "Duplicate forbidden candidate identifiers")
        _check(not set(relevant).intersection(forbidden), "Relevant and forbidden candidates overlap")
        object.__setattr__(self, "relevant_candidate_ids", relevant)
        object.__setattr__(self, "forbidden_candidate_ids", forbidden)

        _check(isinstance(self.expected_match_status, Mapping),
               "Expected candidate match statuses")
        statuses = {}
        for candidate_id, status in self.expected_match_status.items():
            _candidate_identifier(candidate_id, "match-status candidate identifier")
            _check(isinstance(status, str) and status in _MATCH_STATUSES,
                   "Unknown expected match status")
            statuses[candidate_id] = status
        _check(set(statuses).issubset(set(relevant) | set(forbidden)),
               "Match status references an unclassified candidate")
        object.__setattr__(self, "expected_match_status", MappingProxyType(statuses))

        fields = _expected_fields(self.expected_fields)
        _check(set(fields).issubset(set(relevant) | set(forbidden)),
               "Expected fields reference an unclassified candidate")
        object.__setattr__(self, "expected_fields", fields)

        evidence = tuple(_evidence(item) for item in self.required_evidence)
        _check(bool(evidence) and len(evidence) <= _MAX_EVIDENCE,
               "At least one bounded evidence record is required")
        evidence_ids = [item["evidence_id"] for item in evidence]
        _check(len(evidence_ids) == len(set(evidence_ids)), "Duplicate evidence identifiers")
        object.__setattr__(self, "required_evidence", evidence)

        actions = _sequence(self.prohibited_actions, "prohibited action", maximum=64)
        _check(bool(actions), "Prohibited actions must be explicit")
        object.__setattr__(self, "prohibited_actions", actions)
        object.__setattr__(self, "excel_policy", _excel_policy(self.excel_policy))

        feedback = self.feedback_ref
        if feedback is not None:
            _check(isinstance(feedback, Mapping)
                   and set(feedback) == {"feedback_id", "revision"},
                   "Invalid feedback reference")
            _identifier(feedback["feedback_id"], "feedback identifier")
            _check(type(feedback["revision"]) is int and feedback["revision"] >= 1,
                   "Invalid feedback revision")
            object.__setattr__(self, "feedback_ref", MappingProxyType(dict(feedback)))

        if self.authorship is not None:
            object.__setattr__(self, "authorship", _authorship(self.authorship))

        if self.case_type == "rankable":
            _check(bool(relevant) and self.expected_state == "candidate_found",
                   "Rankable cases need relevant candidates and candidate_found state")
        elif self.case_type == "near_match":
            _check(bool(relevant) and bool(forbidden)
                   and self.expected_state in {"candidate_found", "review_required"},
                   "Near-match cases need relevant and forbidden candidates")
            _check(set(relevant).union(forbidden).issubset(statuses),
                   "Near-match candidates need explicit expected match statuses")
        elif self.case_type == "insufficient_evidence":
            _check(self.expected_state == "review_required" and not relevant,
                   "Insufficient-evidence cases need review_required and no relevant candidate")
        else:
            _check(self.expected_state == "unmatched" and not relevant,
                   "Unrelated cases need unmatched and no relevant candidate")

        for candidate_id, candidate_fields in fields.items():
            has_uncertainty = any(item["state"] in {"unknown", "conflict"}
                                  for item in candidate_fields.values())
            if has_uncertainty:
                _check(bool(evidence) and statuses.get(candidate_id) == "review_required",
                       "Unknown/conflict fields need evidence and review_required status")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "case_id": self.case_id,
            "case_version": self.case_version,
            "case_family_id": self.case_family_id,
            "split": self.split,
            "case_type": self.case_type,
            "request": _thaw(self.request),
            "query_variants": list(self.query_variants),
            "expected_state": self.expected_state,
            "relevant_candidate_ids": list(self.relevant_candidate_ids),
            "forbidden_candidate_ids": list(self.forbidden_candidate_ids),
            "expected_match_status": dict(self.expected_match_status),
            "expected_fields": _thaw(self.expected_fields),
            "required_evidence": [_thaw(item) for item in self.required_evidence],
            "prohibited_actions": list(self.prohibited_actions),
            "excel_policy": dict(self.excel_policy),
            "feedback_ref": _thaw(self.feedback_ref) if self.feedback_ref is not None else None,
        }
        if self.authorship is not None:
            result["authorship"] = _thaw(self.authorship)
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "EvaluationCase":
        keys = frozenset(value) if isinstance(value, Mapping) else frozenset()
        _check(isinstance(value, Mapping) and keys in {cls._BASE_FIELDS, cls._FIELDS},
               "Invalid EvaluationCase fields")
        data = dict(value)
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> "EvaluationCase":
        try:
            value = json.loads(text, object_pairs_hook=_unique_object,
                               parse_constant=_reject_json_constant)
            return cls.from_dict(value)
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ValueError("Invalid EvaluationCase JSON") from None

    def __repr__(self) -> str:
        return "EvaluationCase(<values omitted>)"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        _check(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Nonstandard JSON numeric constant: {value}")
