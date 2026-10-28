"""Offline development-set measurements of lexical search policies."""

import hashlib
import json
from dataclasses import asdict, dataclass

from macro_data_platform.discovery.series_search import rank_candidates
from macro_data_platform.evaluation.cases import EvaluationCorpus
from macro_data_platform.workflow_contracts import DataRequest

_FIELDS = {
    "institution_id",
    "dataset_id",
    "series_id",
    "definition",
    "frequency",
    "unit",
    "available_start",
    "available_end",
}
_UNSUPPORTED = object()


@dataclass(frozen=True)
class SearchPolicy:
    """Evaluation-only ranker wrapper; it cannot confirm or collect a candidate."""

    version: str = "lexical-v1"
    limit: int = 50
    minimum_score: float = 0

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("policy version must be non-empty")
        if type(self.limit) is not int or not 1 <= self.limit <= 50:
            raise ValueError("policy limit must be between 1 and 50")
        if (
            isinstance(self.minimum_score, bool)
            or not isinstance(self.minimum_score, (int, float))
            or not 0 <= self.minimum_score <= 100
        ):
            raise ValueError("minimum score must be between 0 and 100")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def rank(self, request, candidates):
        ranked = rank_candidates(request, candidates, limit=self.limit)
        return [row for row in ranked if row["score"] >= self.minimum_score]


def _candidate_field(candidate, name):
    if name in _FIELDS:
        return getattr(candidate, name)
    if name == "geography":
        return candidate.countries[0] if len(candidate.countries) == 1 else _UNSUPPORTED
    if name.startswith("series_key."):
        return candidate.series_key.get(name.removeprefix("series_key."))
    return _UNSUPPORTED


def evaluate_development(corpus: EvaluationCorpus, policy: SearchPolicy | None = None) -> dict:
    """Measure rank and unmatched behavior without running collection or promotion."""
    policy = policy or SearchPolicy()
    groups = {}
    for case in corpus.cases:
        if case.split != "development":
            continue
        group = groups.setdefault(
            case.case_type,
            {
                "cases": 0,
                "queries": 0,
                "rankable_queries": 0,
                "top1_hits": 0,
                "reciprocal_rank_sum": 0.0,
                "unrelated_queries": 0,
                "unrelated_with_candidates": 0,
                "false_exact_candidates": 0,
                "status_expected": 0,
                "status_returned": 0,
                "status_matches": 0,
                "fields_expected": 0,
                "fields_returned": 0,
                "fields_matches": 0,
                "fields_unmeasured": 0,
            },
        )
        group["cases"] += 1
        for variant in case.query_variants:
            request = dict(case.request)
            request["text"] = variant
            ranked = policy.rank(DataRequest.from_dict(request), corpus.candidates)
            ids = [row["candidate"].candidate_id for row in ranked]
            by_id = {row["candidate"].candidate_id: row for row in ranked}
            group["queries"] += 1
            relevant = set(case.relevant_candidate_ids)
            if relevant:
                group["rankable_queries"] += 1
                group["top1_hits"] += bool(ids and ids[0] in relevant)
                ranks = [index for index, identifier in enumerate(ids, 1) if identifier in relevant]
                if ranks:
                    group["reciprocal_rank_sum"] += 1 / min(ranks)
            if case.case_type == "unrelated":
                group["unrelated_queries"] += 1
                group["unrelated_with_candidates"] += bool(ids)
            group["false_exact_candidates"] += sum(
                row["match_status"] == "exact"
                and (
                    row["candidate"].candidate_id not in relevant
                    or case.expected_match_status.get(row["candidate"].candidate_id) != "exact"
                )
                for row in ranked
            )
            for candidate_id, expected in case.expected_match_status.items():
                group["status_expected"] += 1
                if candidate_id in by_id:
                    group["status_returned"] += 1
                    group["status_matches"] += by_id[candidate_id]["match_status"] == expected
            for candidate_id, fields in case.expected_fields.items():
                for name, expectation in fields.items():
                    group["fields_expected"] += 1
                    if candidate_id not in by_id:
                        continue
                    group["fields_returned"] += 1
                    actual = _candidate_field(by_id[candidate_id]["candidate"], name)
                    state = expectation["state"]
                    if actual is _UNSUPPORTED or state == "conflict":
                        group["fields_unmeasured"] += 1
                    elif state == "unknown":
                        group["fields_matches"] += actual is None
                    elif state == "known":
                        group["fields_matches"] += actual == expectation["value"]
    for group in groups.values():
        denominator = group["rankable_queries"]
        group["mrr"] = round(group["reciprocal_rank_sum"] / denominator, 6) if denominator else None
        group["reciprocal_rank_sum"] = round(group["reciprocal_rank_sum"], 6)
    return {
        "status": "POLICY_MEASUREMENT_ONLY",
        "split": "development",
        "case_sha256": corpus.case_sha256,
        "catalog_sha256": corpus.catalog_sha256,
        "policy": asdict(policy),
        "policy_sha256": policy.sha256,
        "groups": groups,
        "field_measurement": "structural equality only; missing candidates and unsupported fields are reported separately",
        "not_measured": [
            "engine_confirmation",
            "prohibited_actions",
            "semantic_equivalence",
            "validation",
            "holdout",
            "prohibited_actions",
        ],
    }


def compare_development_policies(
    corpus: EvaluationCorpus,
    baseline: SearchPolicy,
    candidate: SearchPolicy,
) -> dict:
    """Compare two policies on the same development cases and catalog snapshot."""
    baseline_report = evaluate_development(corpus, baseline)
    candidate_report = evaluate_development(corpus, candidate)
    deltas = {}
    for case_type, before in baseline_report["groups"].items():
        after = candidate_report["groups"][case_type]
        deltas[case_type] = {
            metric: after[metric] - before[metric]
            for metric in (
                "top1_hits",
                "rankable_queries",
                "unrelated_with_candidates",
                "false_exact_candidates",
                "status_matches",
                "fields_matches",
            )
        }
        deltas[case_type]["mrr"] = (
            round(after["mrr"] - before["mrr"], 6)
            if before["mrr"] is not None and after["mrr"] is not None
            else None
        )
    return {
        "status": "DEVELOPMENT_COMPARISON_ONLY",
        "split": "development",
        "case_sha256": corpus.case_sha256,
        "catalog_sha256": corpus.catalog_sha256,
        "baseline": baseline_report,
        "candidate": candidate_report,
        "deltas": deltas,
        "not_measured": [
            "engine_confirmation",
            "prohibited_actions",
            "semantic_equivalence",
            "promotion_eligibility",
            "validation",
            "holdout",
        ],
    }
