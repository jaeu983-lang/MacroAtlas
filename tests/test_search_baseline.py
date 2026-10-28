from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.search_baseline import evaluate_development


def test_development_baseline_runs_all_variants_without_validation_or_holdout(monkeypatch):
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    seen = []

    def no_results(request, candidates):
        seen.append(request.text)
        return []

    monkeypatch.setattr("macro_data_platform.evaluation.search_baseline.rank_candidates", no_results)
    report = evaluate_development(corpus)
    expected = [variant for case in corpus.cases if case.split == "development"
                for variant in case.query_variants]
    assert seen == expected
    assert report["status"] == "BASELINE_ONLY"
    assert report["groups"]["rankable"]["top1_hits"] == 0
    assert report["groups"]["rankable"]["mrr"] == 0
    assert report["groups"]["unrelated"]["unrelated_with_candidates"] == 0
    assert "holdout" in report["not_measured"]


def test_baseline_is_repeatable_and_reports_unrelated_candidates():
    corpus = load_corpus("tests/fixtures/evaluation/v2", repo_root=".")
    report = evaluate_development(corpus)
    assert report == evaluate_development(corpus)
    assert report["groups"]["unrelated"]["unrelated_queries"] == 8
    assert report["groups"]["unrelated"]["unrelated_with_candidates"] == 8
    assert report["case_sha256"] == corpus.case_sha256
