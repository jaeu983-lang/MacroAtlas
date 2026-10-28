from dataclasses import replace

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
    assert report["groups"]["rankable"]["fields_expected"] > 0
    assert report["groups"]["rankable"]["fields_returned"] == 0
    assert report["groups"]["rankable"]["status_returned"] == 0
    assert "holdout" in report["not_measured"]


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
            lambda request, candidates: [{"candidate": changed, "match_status": status}],
        )
        return evaluate_development(corpus)["groups"]["rankable"]

    expected = rank_with(None, "review_required")
    altered = rank_with("USD", "related")
    assert expected["fields_returned"] > 0
    assert altered["fields_returned"] == expected["fields_returned"]
    assert altered["fields_matches"] < expected["fields_matches"]
    assert altered["status_matches"] < expected["status_matches"]
