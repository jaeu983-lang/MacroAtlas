"""Offline split-set measurements for evaluation-only search policies."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from time import perf_counter_ns

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageStatus
from macro_data_platform.discovery.series_search import (
    CandidateSearchEngine,
    build_confirmed_collection_plan,
    rank_candidates,
)
from macro_data_platform.evaluation.cases import EvaluationCorpus
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.workflow_contracts import CandidateProposal, DataRequest

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
_HOLDOUT_RUN_TOKEN = object()
_PROHIBITED_ACTION_METHODS = {
    "auto_select_or_collect_without_explicit_confirmation": "unconfirmed proposal is sent to the real collection-plan builder",
    "collect_a_candidate_that_was_not_explicitly_selected": "proposal without a selected candidate is sent to the real collection-plan builder",
    "infer_unknown_unit_frequency_definition_or_availability": "returned candidate fields are checked against unknown expectations",
    "overwrite_raw_data_or_existing_exports": "plan creation must fail before any collection/raw/export stage is reachable",
    "merge_incompatible_series_or_fill_missing_values": "no task/export plan is created by the local search evaluation path",
}
DEFAULT_CANDIDATE_MINIMUM_SCORE = 37.5
DEFAULT_CANDIDATE_POLICY_VERSION = "lexical-min-score-candidate-v2"


@dataclass(frozen=True)
class SearchPolicy:
    """Evaluation-only ranker wrapper; it cannot confirm or collect a candidate."""

    version: str = "lexical-v1"
    limit: int = 50
    minimum_score: float = 0
    semantic_disambiguation: bool = False

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
        if type(self.semantic_disambiguation) is not bool:
            raise ValueError("semantic_disambiguation must be a boolean")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def rank(self, request, candidates, *, limit=None):
        result_limit = self.limit if limit is None else limit
        if type(result_limit) is not int or not 1 <= result_limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        ranked = rank_candidates(request, candidates, limit=50)
        if self.semantic_disambiguation:
            for row in ranked:
                row["ranking_score"] = row["score"] + _semantic_adjustment(
                    request,
                    row["candidate"],
                )
            ranked.sort(
                key=lambda row: (
                    -row["ranking_score"],
                    -row["score"],
                    row["candidate"].candidate_id,
                )
            )
        return [row for row in ranked if row["score"] >= self.minimum_score][:result_limit]


def _semantic_adjustment(request, candidate) -> float:
    """Apply explicit measure/basis contrasts in the evaluation-only candidate policy."""
    query = " ".join(
        re.findall(
            r"[a-z0-9%$]+",
            f"{request.text} {request.concept or ''}".casefold(),
        )
    )
    label = " ".join(re.findall(r"[a-z0-9%$]+", candidate.label.casefold()))
    adjustment = 0.0

    asks_gdp = "gdp" in query
    asks_per_capita = any(
        phrase in query
        for phrase in (
            "per capita",
            "per person",
            "per head",
        )
    )
    candidate_per_capita = any(
        phrase in label
        for phrase in (
            "per capita",
            "per person",
            "per head",
        )
    )
    if asks_gdp and asks_per_capita:
        adjustment += 35 if candidate_per_capita else -35
    elif asks_gdp:
        adjustment += -35 if candidate_per_capita else 12

    asks_ppp = (
        "ppp" in query or "purchasing power parity" in query or "international dollars" in query
    )
    asks_constant = "constant" in query or "real gdp" in query
    asks_current = (
        "nominal" in query
        or "current price" in query
        or ("current" in query.split() and ("dollar" in query or "$" in query))
    )
    candidate_ppp = (
        "ppp" in label or "purchasing power parity" in label or "international $" in label
    )
    candidate_constant = "constant" in label or "real gdp" in label
    candidate_current = "current" in label and ("$" in label or "dollar" in label)
    if asks_ppp:
        adjustment += 30 if candidate_ppp else -35
    elif asks_constant:
        adjustment += 30 if candidate_constant else -35
    elif asks_current:
        adjustment += 30 if candidate_current and not candidate_ppp else -35

    asks_price_rate = (
        "inflation" in query
        or any(
            word in query.split()
            for word in (
                "rise",
                "rose",
                "rising",
                "increase",
                "increased",
                "increasing",
                "fast",
            )
        )
    ) and any(phrase in query for phrase in ("consumer price", "consumer prices", "cpi"))
    asks_price_index = ("cpi" in query or "consumer price index" in query) and not asks_price_rate
    candidate_price_rate = "inflation" in label and "consumer" in label
    candidate_price_index = "consumer price index" in label
    candidate_gdp_deflator = "gdp deflator" in label
    excludes_consumer_inflation = any(
        phrase in query
        for phrase in (
            "not the consumer",
            "not consumer",
            "not cpi",
            "rather than cpi",
            "rather than the consumer",
            "distinct from cpi",
            "distinct from consumer",
            "exclude cpi",
            "exclude the consumer",
            "not the consumer price basket",
        )
    )
    asks_gdp_deflator = "gdp deflator" in query
    if asks_gdp_deflator and excludes_consumer_inflation:
        adjustment += 45 if candidate_gdp_deflator else -45 if candidate_price_rate else 0
    elif asks_price_rate:
        if candidate_price_rate:
            adjustment += 35
        elif candidate_price_index or candidate_gdp_deflator:
            adjustment -= 40
    elif asks_price_index:
        if candidate_price_index:
            adjustment += 35
        elif candidate_price_rate:
            adjustment -= 40
    return adjustment


def _candidate_field(candidate, name):
    if name in _FIELDS:
        return getattr(candidate, name)
    if name == "geography":
        return candidate.countries[0] if len(candidate.countries) == 1 else _UNSUPPORTED
    if name.startswith("series_key."):
        return candidate.series_key.get(name.removeprefix("series_key."))
    return _UNSUPPORTED


def _unknown_field_is_preserved(name: str, value) -> bool:
    if value is None:
        return True
    return (
        name == "definition"
        and isinstance(value, str)
        and "official indicator label only:" in value.casefold()
        and "does not contain the full methodological definition" in value.casefold()
    )


def _state_matches(case, rows, returned_ids):
    """Compare the case's expected search state using only labeled candidates."""
    if case.expected_state == "candidate_found":
        return bool(set(case.relevant_candidate_ids).intersection(returned_ids))
    if case.expected_state == "unmatched":
        return not rows
    labeled = set(case.relevant_candidate_ids) | set(case.forbidden_candidate_ids)
    return any(
        row["candidate"].candidate_id in labeled and row["match_status"] == "review_required"
        for row in rows
    )


def _proposal_boundary_trace(payload: dict) -> dict:
    """Try the real proposal-to-collection boundary without running any side effects."""
    forbidden_payload_fields = {
        "selection",
        "confirmed_selection",
        "collection_plan",
        "task_plan",
    }.intersection(payload)
    try:
        proposal = CandidateProposal.from_dict(payload["proposal"])
        build_confirmed_collection_plan(proposal, Settings(Path.cwd()))
    except TypeError as exc:
        blocked = str(exc) == "expected an explicitly confirmed candidate selection"
    except (KeyError, ValueError):
        blocked = False
    else:
        blocked = False
    return {
        "confirmation_required": payload.get("selection_requires_explicit_confirmation") is True,
        "unconfirmed_plan_attempted": True,
        "blocked_before_task_creation": blocked,
        "collection_plan_created": not blocked,
        "selection_or_collection_payload_present": bool(forbidden_payload_fields),
    }


def _percentile(samples: list[int], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    return round(ordered[max(0, ceil(percentile * len(ordered)) - 1)] / 1_000_000, 6)


def _finalize_prohibited_action_trace(action_trace: dict, expected_queries: int) -> dict:
    result = {}
    for action, measurements in action_trace.items():
        violations = measurements["violations"]
        measured = measurements["case_queries"] == expected_queries and expected_queries > 0
        if action == "infer_unknown_unit_frequency_definition_or_availability":
            measured = measured and measurements["unknown_fields_expected"] > 0
            violations += measurements["unknown_fields_inferred"]
            violations += measurements["unknown_fields_unmeasured"]
        result[action] = {
            **measurements,
            "status": "PASS" if measured and violations == 0 else "FAIL",
            "method": _PROHIBITED_ACTION_METHODS[action],
        }
    return result


def _benchmark_policy_pair(corpus, baseline, candidate, *, split, repetitions):
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("timing repetitions must be between 1 and 100")
    engines = {
        "baseline": CandidateSearchEngine(
            settings=None,
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            candidate_loader=lambda _settings: corpus.candidates,
            ranker=baseline.rank,
        ),
        "candidate": CandidateSearchEngine(
            settings=None,
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            candidate_loader=lambda _settings: corpus.candidates,
            ranker=candidate.rank,
        ),
    }
    samples = {name: {} for name in engines}
    query_count = 0
    for case in corpus.cases:
        if case.split != split:
            continue
        for variant_index, variant in enumerate(case.query_variants):
            request = dict(case.request)
            request["text"] = variant
            structured_request = DataRequest.from_dict(request)
            stage_input = StageInput(
                f"gate-c-{split}",
                variant,
                "series_search",
                {"request": structured_request.to_dict(), "limit": 50},
                None,
                (),
            )
            # Warm both policies on the exact input; warmup is excluded from samples.
            for engine in engines.values():
                engine.run(stage_input)
            for repetition in range(repetitions):
                order = (
                    ("baseline", "candidate")
                    if (repetition + variant_index) % 2 == 0
                    else (
                        "candidate",
                        "baseline",
                    )
                )
                for name in order:
                    started = perf_counter_ns()
                    result = engines[name].run(stage_input)
                    elapsed = perf_counter_ns() - started
                    if result.status != StageStatus.SUCCEEDED:
                        raise ValueError("candidate search failed during timing measurement")
                    samples[name].setdefault(case.case_type, []).append(elapsed)
            query_count += 1

    summary = {}
    for name, groups in samples.items():
        group_summary = {}
        all_values = []
        for case_type, values in sorted(groups.items()):
            all_values.extend(values)
            total_seconds = sum(values) / 1_000_000_000
            group_summary[case_type] = {
                "sample_count": len(values),
                "p50_ms": _percentile(values, 0.50),
                "p95_ms": _percentile(values, 0.95),
                "throughput_queries_per_second": round(len(values) / total_seconds, 3)
                if total_seconds
                else None,
            }
        total_seconds = sum(all_values) / 1_000_000_000
        summary[name] = {
            "sample_count": len(all_values),
            "query_count_per_repetition": query_count,
            "p50_ms": _percentile(all_values, 0.50),
            "p95_ms": _percentile(all_values, 0.95),
            "throughput_queries_per_second": round(len(all_values) / total_seconds, 3)
            if total_seconds
            else None,
            "by_case_type": group_summary,
        }
    return {
        "scope": "offline fixed-catalog CandidateSearchEngine.run; no task, network, raw write, or export",
        "repetitions": repetitions,
        "alternating_policy_order": True,
        "samples_per_policy_equal": summary["baseline"]["sample_count"]
        == summary["candidate"]["sample_count"],
        "external_calls": 0,
        "estimated_external_cost_usd": 0,
        "by_policy": summary,
    }


def _split_input_sha256(corpus, split):
    payload = [case.to_dict() for case in corpus.cases if case.split == split]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_split(
    corpus: EvaluationCorpus,
    policy: SearchPolicy | None = None,
    *,
    split: str,
    _holdout_token=None,
) -> dict:
    """Measure rank and unmatched behavior without running collection or promotion."""
    if split not in {"development", "validation", "holdout"}:
        raise ValueError("Unknown evaluation split")
    if split == "holdout" and _holdout_token is not _HOLDOUT_RUN_TOKEN:
        raise ValueError("Holdout evaluation is only available through the frozen one-time runner")
    policy = policy or SearchPolicy()
    groups = {}
    action_trace = {
        "search_queries": 0,
        "explicit_confirmation_required": 0,
        "confirmation_bypasses": 0,
        "selection_or_collection_payloads": 0,
        "unconfirmed_collection_plan_attempts": 0,
        "unconfirmed_collection_plans_created": 0,
        "blocked_before_task_creation": 0,
        "prohibited_actions": {
            action: {
                "case_queries": 0,
                "guarded_before_task_creation": 0,
                "unreached_queries": 0,
                "violations": 0,
                "unknown_fields_expected": 0,
                "unknown_fields_observed": 0,
                "unknown_fields_disclosed": 0,
                "unknown_fields_inferred": 0,
                "unknown_fields_unmeasured": 0,
            }
            for action in _PROHIBITED_ACTION_METHODS
        },
    }
    search_engine = CandidateSearchEngine(
        settings=None,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        candidate_loader=lambda _settings: corpus.candidates,
        ranker=policy.rank,
    )
    for case in corpus.cases:
        if case.split != split:
            continue
        group = groups.setdefault(
            case.case_type,
            {
                "cases": 0,
                "queries": 0,
                "rankable_queries": 0,
                "top1_hits": 0,
                "reciprocal_rank_sum": 0.0,
                "queries_with_candidates": 0,
                "empty_result_queries": 0,
                "expected_state_matches": 0,
                "expected_state_queries": 0,
                "relevant_missing_queries": 0,
                "forbidden_candidate_returns": 0,
                "forbidden_exact_candidates": 0,
                "unrelated_queries": 0,
                "unrelated_with_candidates": 0,
                "unrelated_abstentions": 0,
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
            structured_request = DataRequest.from_dict(request)
            result = search_engine.run(
                StageInput(
                    "evaluation",
                    variant,
                    "series_search",
                    {"request": structured_request.to_dict(), "limit": policy.limit},
                    None,
                    (),
                )
            )
            if result.status != StageStatus.SUCCEEDED or result.payload is None:
                raise ValueError("CandidateSearchEngine failed on a validated evaluation request")
            payload = result.payload
            action_trace["search_queries"] += 1
            confirmation_required = payload.get("selection_requires_explicit_confirmation") is True
            action_trace["explicit_confirmation_required"] += confirmation_required
            action_trace["confirmation_bypasses"] += not confirmation_required
            action_trace["selection_or_collection_payloads"] += bool(
                {"selection", "confirmed_selection", "collection_plan", "task_plan"} & set(payload)
            )
            boundary = _proposal_boundary_trace(payload)
            case_actions = set(case.prohibited_actions)
            for action in case_actions:
                measurement = action_trace["prohibited_actions"].get(action)
                if measurement is None:
                    continue
                measurement["case_queries"] += 1
                if action in {
                    "auto_select_or_collect_without_explicit_confirmation",
                    "collect_a_candidate_that_was_not_explicitly_selected",
                    "overwrite_raw_data_or_existing_exports",
                    "merge_incompatible_series_or_fill_missing_values",
                }:
                    blocked = boundary["blocked_before_task_creation"]
                    measurement["guarded_before_task_creation"] += blocked
                    measurement["unreached_queries"] += blocked
                    measurement["violations"] += not blocked
            action_trace["unconfirmed_collection_plan_attempts"] += boundary[
                "unconfirmed_plan_attempted"
            ]
            action_trace["unconfirmed_collection_plans_created"] += not boundary[
                "blocked_before_task_creation"
            ]
            action_trace["blocked_before_task_creation"] += boundary["blocked_before_task_creation"]
            proposal = CandidateProposal.from_dict(payload["proposal"])
            metadata_by_id = {row["candidate_id"]: row for row in payload["ranking"]}
            ranked = [
                {"candidate": candidate, **metadata_by_id[candidate.candidate_id]}
                for candidate in proposal.candidates
            ]
            ids = [row["candidate"].candidate_id for row in ranked]
            by_id = {row["candidate"].candidate_id: row for row in ranked}
            unknown_action = action_trace["prohibited_actions"][
                "infer_unknown_unit_frequency_definition_or_availability"
            ]
            if "infer_unknown_unit_frequency_definition_or_availability" in case_actions:
                for candidate_id, fields in case.expected_fields.items():
                    for name, expectation in fields.items():
                        if expectation["state"] != "unknown":
                            continue
                        unknown_action["unknown_fields_expected"] += 1
                        if candidate_id not in by_id:
                            continue
                        unknown_action["unknown_fields_observed"] += 1
                        actual = _candidate_field(by_id[candidate_id]["candidate"], name)
                        unknown_action["unknown_fields_unmeasured"] += actual is _UNSUPPORTED
                        if actual is not _UNSUPPORTED and actual is not None:
                            disclosed = _unknown_field_is_preserved(name, actual)
                            unknown_action["unknown_fields_disclosed"] += disclosed
                            unknown_action["unknown_fields_inferred"] += not disclosed
            group["queries"] += 1
            group["queries_with_candidates"] += bool(ranked)
            group["empty_result_queries"] += not ranked
            group["expected_state_queries"] += 1
            group["expected_state_matches"] += _state_matches(case, ranked, ids)
            relevant = set(case.relevant_candidate_ids)
            if relevant:
                group["rankable_queries"] += 1
                group["top1_hits"] += bool(ids and ids[0] in relevant)
                ranks = [index for index, identifier in enumerate(ids, 1) if identifier in relevant]
                if ranks:
                    group["reciprocal_rank_sum"] += 1 / min(ranks)
                else:
                    group["relevant_missing_queries"] += 1
            forbidden = set(case.forbidden_candidate_ids)
            group["forbidden_candidate_returns"] += len(forbidden.intersection(ids))
            group["forbidden_exact_candidates"] += sum(
                row["candidate"].candidate_id in forbidden and row["match_status"] == "exact"
                for row in ranked
            )
            if case.case_type == "unrelated":
                group["unrelated_queries"] += 1
                group["unrelated_with_candidates"] += bool(ids)
                group["unrelated_abstentions"] += not ids
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
                        group["fields_matches"] += _unknown_field_is_preserved(name, actual)
                    elif state == "known":
                        group["fields_matches"] += actual == expectation["value"]
    for group in groups.values():
        denominator = group["rankable_queries"]
        group["mrr"] = round(group["reciprocal_rank_sum"] / denominator, 6) if denominator else None
        group["reciprocal_rank_sum"] = round(group["reciprocal_rank_sum"], 6)
    not_measured = ["semantic_equivalence", "timing_cost_budget"]
    if split != "holdout":
        not_measured.append("holdout")
    if split == "development":
        not_measured.append("validation")
    return {
        "status": "POLICY_MEASUREMENT_ONLY",
        "split": split,
        "input_sha256": _split_input_sha256(corpus, split),
        "case_sha256": corpus.case_sha256,
        "catalog_sha256": corpus.catalog_sha256,
        "policy": asdict(policy),
        "policy_sha256": policy.sha256,
        "groups": groups,
        "field_measurement": "structural equality only; missing candidates and unsupported fields are reported separately",
        "execution_boundary": "fixed_catalog_candidate_search_stage_no_task_db_collection_or_export",
        "search_stage_safety": {
            "status": "PASS"
            if action_trace["confirmation_bypasses"] == 0
            and action_trace["selection_or_collection_payloads"] == 0
            else "FAIL",
            **action_trace,
            "scope": "Each proposal was submitted to the real collection-plan builder without confirmation; blocked proposals created no TaskPlan. This evaluator does not start an executor.",
        },
        "prohibited_action_measurement": {
            "status": "PASS"
            if action_trace["unconfirmed_collection_plan_attempts"]
            == action_trace["search_queries"]
            and action_trace["unconfirmed_collection_plans_created"] == 0
            and action_trace["blocked_before_task_creation"] == action_trace["search_queries"]
            and all(
                measurement["status"] == "PASS"
                for measurement in _finalize_prohibited_action_trace(
                    action_trace["prohibited_actions"], action_trace["search_queries"]
                ).values()
            )
            else "FAIL",
            "method": "proposal-to-plan boundary probe; collection plan rejection is the guard before task creation, network, raw write, and export",
            "case_count": sum(group["cases"] for group in groups.values()),
            "trace": {
                **action_trace,
                "prohibited_actions": _finalize_prohibited_action_trace(
                    action_trace["prohibited_actions"], action_trace["search_queries"]
                ),
            },
        },
        "not_measured": not_measured,
    }


def evaluate_development(corpus: EvaluationCorpus, policy: SearchPolicy | None = None) -> dict:
    return evaluate_split(corpus, policy, split="development")


def compare_development_policies(
    corpus: EvaluationCorpus,
    baseline: SearchPolicy,
    candidate: SearchPolicy,
    *,
    timing_repetitions: int = 0,
) -> dict:
    """Compare two policies on the same development cases and catalog snapshot."""
    return compare_split_policies(
        corpus,
        baseline,
        candidate,
        split="development",
        timing_repetitions=timing_repetitions,
    )


def compare_validation_policies(
    corpus: EvaluationCorpus,
    baseline: SearchPolicy,
    candidate: SearchPolicy,
    *,
    timing_repetitions: int = 0,
) -> dict:
    """Compare frozen candidate behavior on validation without touching holdout."""
    return compare_split_policies(
        corpus,
        baseline,
        candidate,
        split="validation",
        timing_repetitions=timing_repetitions,
    )


def compare_split_policies(
    corpus: EvaluationCorpus,
    baseline: SearchPolicy,
    candidate: SearchPolicy,
    *,
    split: str,
    timing_repetitions: int = 0,
    _holdout_token=None,
) -> dict:
    if split not in {"development", "validation", "holdout"}:
        raise ValueError("Unknown evaluation split")
    if split == "holdout" and _holdout_token is not _HOLDOUT_RUN_TOKEN:
        raise ValueError("Holdout comparison is only available through the frozen one-time runner")
    baseline_report = evaluate_split(
        corpus,
        baseline,
        split=split,
        _holdout_token=_holdout_token,
    )
    candidate_report = evaluate_split(
        corpus,
        candidate,
        split=split,
        _holdout_token=_holdout_token,
    )
    not_measured = [
        "semantic_equivalence",
        "timing_cost_budget",
        "promotion_eligibility",
    ]
    if split != "holdout":
        not_measured.append("holdout")
    if split == "development":
        not_measured.append("validation")
    timing = None
    if timing_repetitions:
        timing = _benchmark_policy_pair(
            corpus,
            baseline,
            candidate,
            split=split,
            repetitions=timing_repetitions,
        )
        not_measured.remove("timing_cost_budget")
    deltas = {}
    for case_type, before in baseline_report["groups"].items():
        after = candidate_report["groups"][case_type]
        deltas[case_type] = {
            metric: after[metric] - before[metric]
            for metric in (
                "top1_hits",
                "rankable_queries",
                "expected_state_matches",
                "expected_state_queries",
                "relevant_missing_queries",
                "forbidden_candidate_returns",
                "forbidden_exact_candidates",
                "unrelated_with_candidates",
                "unrelated_abstentions",
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
        "status": "SPLIT_COMPARISON_ONLY",
        "split": split,
        "input_sha256": baseline_report["input_sha256"],
        "case_sha256": corpus.case_sha256,
        "catalog_sha256": corpus.catalog_sha256,
        "baseline": baseline_report,
        "candidate": candidate_report,
        "deltas": deltas,
        "timing": timing,
        "not_measured": not_measured,
    }
