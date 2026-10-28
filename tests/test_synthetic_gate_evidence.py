import json
from copy import deepcopy
from pathlib import Path

import pytest

from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.synthetic_gate_evidence import compare

FIXTURES = Path("tests/fixtures/evaluation")


def inputs():
    corpus = load_corpus(FIXTURES / "v2", repo_root=".")
    cases = json.loads((FIXTURES / "synthetic_gpt_examples.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "synthetic_gpt_expectations.json").read_text(encoding="utf-8"))
    return corpus, cases, expected


def test_simulated_evidence_measures_both_policies_without_claiming_user_or_gate_pass():
    corpus, cases, expected = inputs()
    report = compare(corpus, cases, expected)
    assert report["gate_evidence"] is True and report["gate_passed"] is False
    assert report["origin"] == "ai_simulated" and report["human_observed"] is False
    assert report["measurements"]["baseline"]["matches"] == 1
    assert report["measurements"]["candidate"]["matches"] == 2
    assert {"holdout", "downstream_actions", "false_exact", "non_target_regression",
            "timing_cost_budget"} <= set(report["not_measured"])


def test_simulated_cases_cannot_be_disguised_as_holdout_or_human():
    corpus, cases, expected = inputs()
    for change in ({"split": "holdout"}, {"human_observed": True}):
        with pytest.raises(ValueError, match="AI-simulated"):
            compare(corpus, cases, {**expected, **change})
    bad = deepcopy(cases)
    bad[0]["catalog_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="catalog mismatch"):
        compare(corpus, bad, expected)


def test_missing_expectation_cannot_silently_reduce_case_count():
    corpus, cases, expected = inputs()
    expected["cases"].pop()
    with pytest.raises(ValueError, match="key sets differ"):
        compare(corpus, cases, expected)
