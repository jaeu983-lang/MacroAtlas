from dataclasses import replace

from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.search_baseline import (
    DEFAULT_CANDIDATE_MINIMUM_SCORE,
    DEFAULT_CANDIDATE_POLICY_VERSION,
    SearchPolicy,
    compare_development_policies,
    compare_validation_policies,
    evaluate_development,
    evaluate_split,
)


def test_development_baseline_runs_all_variants_without_validation_or_holdout(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    seen = []

    def no_results(request, candidates, *, limit):
        seen.append(request.text)
        return []

    monkeypatch.setattr(
        "macro_data_platform.evaluation.search_baseline.rank_candidates", no_results
    )
    report = evaluate_development(corpus)
    expected = [
        variant
        for case in corpus.cases
        if case.split == "development"
        for variant in case.query_variants
    ]
    assert seen == expected
    assert report["status"] == "POLICY_MEASUREMENT_ONLY"
    assert report["groups"]["rankable"]["top1_hits"] == 0
    assert report["groups"]["rankable"]["mrr"] == 0
    assert report["groups"]["unrelated"]["unrelated_with_candidates"] == 0
    assert report["groups"]["rankable"]["fields_expected"] > 0
    assert report["groups"]["rankable"]["fields_returned"] == 0
    assert report["groups"]["rankable"]["status_returned"] == 0
    assert "holdout" in report["not_measured"]
    safety = report["search_stage_safety"]
    assert safety["status"] == "PASS"
    assert safety["search_queries"] == len(expected)
    assert safety["explicit_confirmation_required"] == len(expected)
    assert safety["confirmation_bypasses"] == 0
    assert safety["selection_or_collection_payloads"] == 0
    assert report["prohibited_action_measurement"]["status"] == "NOT_MEASURED"


def test_baseline_is_repeatable_and_reports_unrelated_candidates():
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    report = evaluate_development(corpus)
    assert report == evaluate_development(corpus)
    assert report["groups"]["unrelated"]["unrelated_queries"] == 8
    assert report["groups"]["unrelated"]["unrelated_with_candidates"] == 8
    assert report["case_sha256"] == corpus.case_sha256


def test_field_and_status_measurement_detects_changed_returned_candidate(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    candidate = next(c for c in corpus.candidates if c.candidate_id.endswith("NY.GDP.MKTP.CD"))

    def rank_with(unit, status):
        changed = replace(candidate, unit=unit)
        monkeypatch.setattr(
            "macro_data_platform.evaluation.search_baseline.rank_candidates",
            lambda request, candidates, *, limit: [
                {"candidate": changed, "match_status": status, "score": 100}
            ],
        )
        return evaluate_development(corpus)["groups"]["rankable"]

    expected = rank_with(None, "review_required")
    altered = rank_with("USD", "related")
    assert expected["fields_returned"] > 0
    assert altered["fields_returned"] == expected["fields_returned"]
    assert altered["fields_matches"] < expected["fields_matches"]
    assert altered["status_matches"] < expected["status_matches"]


def test_policy_comparison_uses_same_development_queries_and_reports_policy_hashes(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    seen = []

    def ranked(request, candidates, *, limit):
        seen.append(request.text)
        return [{"candidate": candidates[0], "score": 60, "match_status": "review_required"}]

    monkeypatch.setattr("macro_data_platform.evaluation.search_baseline.rank_candidates", ranked)
    baseline = SearchPolicy(version="baseline")
    candidate = SearchPolicy(version="candidate", minimum_score=70)
    report = compare_development_policies(corpus, baseline, candidate)
    expected = [
        variant
        for case in corpus.cases
        if case.split == "development"
        for variant in case.query_variants
    ]
    assert seen == expected + expected
    assert report["status"] == "SPLIT_COMPARISON_ONLY"
    assert report["baseline"]["case_sha256"] == report["candidate"]["case_sha256"]
    assert report["baseline"]["catalog_sha256"] == report["candidate"]["catalog_sha256"]
    assert report["baseline"]["policy_sha256"] != report["candidate"]["policy_sha256"]
    assert report["deltas"]["rankable"]["top1_hits"] <= 0
    assert "promotion_eligibility" in report["not_measured"]


def test_search_policy_rejects_out_of_range_thresholds():
    import pytest

    with pytest.raises(ValueError):
        SearchPolicy(minimum_score=100.1)


def test_abstention_and_unmatched_behavior_are_reported_separately(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    monkeypatch.setattr(
        "macro_data_platform.evaluation.search_baseline.rank_candidates",
        lambda request, candidates, *, limit: [],
    )

    report = evaluate_development(corpus)
    unrelated = report["groups"]["unrelated"]
    rankable = report["groups"]["rankable"]
    assert unrelated["unrelated_abstentions"] == unrelated["unrelated_queries"]
    assert unrelated["unrelated_with_candidates"] == 0
    assert rankable["relevant_missing_queries"] == rankable["rankable_queries"]
    assert report["prohibited_action_measurement"]["status"] == "NOT_MEASURED"
    assert report["execution_boundary"].startswith("fixed_catalog_candidate_search_stage")


def test_forbidden_exact_candidate_fails_expected_review_state(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    case = next(
        item
        for item in corpus.cases
        if item.split == "development" and item.case_type == "insufficient_evidence"
    )
    candidate_id = case.forbidden_candidate_ids[0]
    candidate = next(item for item in corpus.candidates if item.candidate_id == candidate_id)

    def rank(request, candidates, *, limit):
        if request.request_id == case.case_id:
            return [{"candidate": candidate, "score": 100, "match_status": "exact"}]
        return []

    monkeypatch.setattr("macro_data_platform.evaluation.search_baseline.rank_candidates", rank)
    group = evaluate_development(corpus)["groups"]["insufficient_evidence"]
    assert group["forbidden_candidate_returns"] == len(case.query_variants)
    assert group["forbidden_exact_candidates"] == len(case.query_variants)
    assert group["expected_state_matches"] == 0


def test_candidate_policy_improves_unrelated_without_regressing_development_metrics():
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    baseline = evaluate_development(corpus, SearchPolicy(version="baseline"))
    candidate = evaluate_development(
        corpus,
        SearchPolicy(
            version=DEFAULT_CANDIDATE_POLICY_VERSION,
            minimum_score=DEFAULT_CANDIDATE_MINIMUM_SCORE,
        ),
    )

    assert baseline["groups"]["unrelated"]["unrelated_with_candidates"] == 8
    assert candidate["groups"]["unrelated"]["unrelated_with_candidates"] == 0
    for case_type in ("rankable", "near_match", "insufficient_evidence"):
        before, after = baseline["groups"][case_type], candidate["groups"][case_type]
        assert after["top1_hits"] >= before["top1_hits"]
        assert after["expected_state_matches"] >= before["expected_state_matches"]
        assert after["status_matches"] >= before["status_matches"]
        assert after["fields_matches"] >= before["fields_matches"]
        if before["mrr"] is not None:
            assert after["mrr"] >= before["mrr"]
        assert after["false_exact_candidates"] == 0
        assert after["forbidden_exact_candidates"] == 0


def test_frozen_candidate_keeps_validation_non_target_metrics_and_improves_unrelated():
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    report = compare_validation_policies(
        corpus,
        SearchPolicy(version="baseline"),
        SearchPolicy(
            version=DEFAULT_CANDIDATE_POLICY_VERSION,
            minimum_score=DEFAULT_CANDIDATE_MINIMUM_SCORE,
        ),
    )
    baseline, candidate = report["baseline"]["groups"], report["candidate"]["groups"]

    assert baseline["unrelated"]["unrelated_with_candidates"] == 8
    assert candidate["unrelated"]["unrelated_with_candidates"] == 0
    assert candidate["unrelated"]["expected_state_matches"] == 8
    for case_type in ("rankable", "near_match", "insufficient_evidence"):
        before, after = baseline[case_type], candidate[case_type]
        assert after["top1_hits"] >= before["top1_hits"]
        assert after["expected_state_matches"] >= before["expected_state_matches"]
        assert after["fields_matches"] >= before["fields_matches"]
        assert after["status_matches"] >= before["status_matches"]
        if before["mrr"] is not None:
            assert after["mrr"] >= before["mrr"]
    assert "holdout" in report["not_measured"]


def test_validation_comparison_never_runs_holdout_and_marks_it_unmeasured(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    seen = []

    def no_results(request, candidates, *, limit):
        seen.append(request.request_id)
        return []

    monkeypatch.setattr(
        "macro_data_platform.evaluation.search_baseline.rank_candidates", no_results
    )
    report = compare_validation_policies(
        corpus,
        SearchPolicy(version="baseline"),
        SearchPolicy(version="candidate", minimum_score=70),
    )
    expected_cases = [case for case in corpus.cases if case.split == "validation"]
    expected = [case.case_id for case in expected_cases for _ in case.query_variants]
    assert seen == expected + expected
    assert report["split"] == "validation"
    assert "holdout" in report["not_measured"]
    assert "validation" not in report["not_measured"]
    assert report["baseline"]["input_sha256"] == report["candidate"]["input_sha256"]
    import pytest

    with pytest.raises(ValueError, match="Only development and validation"):
        evaluate_split(corpus, split="holdout")
