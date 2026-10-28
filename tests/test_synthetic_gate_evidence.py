import json
from copy import deepcopy
from pathlib import Path

import pytest

from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.search_baseline import SearchPolicy
from macro_data_platform.evaluation.synthetic_gate_evidence import compare, main
from macro_data_platform.workflow_contracts import DataRequest

FIXTURES = Path("tests/fixtures/evaluation")


def inputs():
    corpus = load_corpus(FIXTURES / "v2", repo_root=".")
    cases = json.loads((FIXTURES / "synthetic_gpt_examples.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (FIXTURES / "synthetic_gpt_expectations.json").read_text(encoding="utf-8")
    )
    return corpus, cases, expected


def test_simulated_evidence_measures_both_policies_without_claiming_user_or_gate_pass():
    corpus, cases, expected = inputs()
    report = compare(corpus, cases, expected)
    assert report["gate_evidence"] is True and report["gate_passed"] is False
    assert report["origin"] == "ai_simulated" and report["human_observed"] is False
    assert (
        report["review_independence"] == "same_assistant" and report["reviewer_id"] == "codex-gpt6"
    )
    assert report["measurements"]["baseline"]["matches"] == 1
    assert report["measurements"]["candidate"]["matches"] == 2
    assert report["measurements"]["prior_candidate_v2"]["matches"] == 2
    assert {
        "holdout",
        "downstream_actions",
        "false_exact",
        "non_target_regression",
        "split_leakage",
        "timing_cost_budget",
    } <= set(report["not_measured"])


def test_simulated_cases_cannot_be_disguised_as_holdout_or_human():
    corpus, cases, expected = inputs()
    for change in ({"split": "holdout"}, {"human_observed": True}, {"decision": "rejected"}):
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


def test_semantic_candidate_resolves_gdp_basis_and_cpi_rate_cases():
    corpus = load_corpus(FIXTURES / "v2", repo_root=".")
    cases = json.loads(
        (FIXTURES / "chatgpt_engine_smoke_examples_2026_10_28.json").read_text(encoding="utf-8")
    )
    expected_doc = json.loads(
        (FIXTURES / "chatgpt_engine_smoke_expectations_2026_10_28.json").read_text(encoding="utf-8")
    )
    expected = {row["case_id"]: row for row in expected_doc["cases"]}
    policies = {
        "baseline": SearchPolicy(version="baseline"),
        "candidate": SearchPolicy(
            version="semantic-v1", minimum_score=37.5, semantic_disambiguation=True
        ),
    }

    matches = {name: 0 for name in policies}
    for case in cases:
        request = DataRequest(case["case_id"], case["question"])
        spec = expected[case["case_id"]]
        for name, policy in policies.items():
            ranked = policy.rank(request, corpus.candidates, limit=3)
            ids = [row["candidate"].candidate_id for row in ranked]
            match = (
                not ids
                if spec["expected_state"] == "unmatched"
                else bool(ids and ids[0] in spec["expected_candidate_ids"])
            )
            matches[name] += match

    assert matches == {"baseline": 0, "candidate": 4}


def test_cli_accepts_explicit_reviewed_synthetic_files(tmp_path, capsys):
    _, cases, expectations = inputs()
    cases_path = tmp_path / "cases.json"
    expected_path = tmp_path / "expectations.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    expected_path.write_text(json.dumps(expectations), encoding="utf-8")
    assert main(["--cases", str(cases_path), "--expectations", str(expected_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["split"] == "development" and report["human_observed"] is False
    assert "split_leakage" in report["not_measured"]
