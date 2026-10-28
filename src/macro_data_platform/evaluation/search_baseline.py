"""Offline development-set measurements of the existing lexical ranker."""

from macro_data_platform.discovery.series_search import rank_candidates
from macro_data_platform.evaluation.cases import EvaluationCorpus
from macro_data_platform.workflow_contracts import DataRequest


def evaluate_development(corpus: EvaluationCorpus) -> dict:
    """Measure rank and unmatched behavior without running collection or promotion."""
    groups = {}
    for case in corpus.cases:
        if case.split != "development":
            continue
        group = groups.setdefault(case.case_type, {
            "cases": 0, "queries": 0, "rankable_queries": 0, "top1_hits": 0,
            "reciprocal_rank_sum": 0.0, "unrelated_queries": 0,
            "unrelated_with_candidates": 0, "false_exact_candidates": 0,
        })
        group["cases"] += 1
        for variant in case.query_variants:
            request = dict(case.request)
            request["text"] = variant
            ranked = rank_candidates(DataRequest.from_dict(request), corpus.candidates)
            ids = [row["candidate"].candidate_id for row in ranked]
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
                and (row["candidate"].candidate_id not in relevant
                     or case.expected_match_status.get(row["candidate"].candidate_id) != "exact")
                for row in ranked
            )
    for group in groups.values():
        denominator = group["rankable_queries"]
        group["mrr"] = round(group["reciprocal_rank_sum"] / denominator, 6) if denominator else None
        group["reciprocal_rank_sum"] = round(group["reciprocal_rank_sum"], 6)
    return {
        "status": "BASELINE_ONLY", "split": "development",
        "case_sha256": corpus.case_sha256, "catalog_sha256": corpus.catalog_sha256,
        "groups": groups,
        "not_measured": ["engine_confirmation", "prohibited_actions", "field_exactness",
                         "policy_comparison", "validation", "holdout"],
    }
