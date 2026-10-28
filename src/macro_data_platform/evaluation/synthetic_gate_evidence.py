"""Measure AI-simulated development cases without claiming human observation or Gate passage."""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns

from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.search_baseline import SearchPolicy
from macro_data_platform.evaluation.synthetic_feedback import _validate
from macro_data_platform.workflow_contracts import DataRequest


def compare(corpus, cases, expectations):
    if (not isinstance(cases, list) or not 1 <= len(cases) <= 500 or not isinstance(expectations, dict)
            or set(expectations) != {"schema_version", "split", "origin", "human_observed",
                                     "reviewer_type", "reviewer_model", "cases"}
            or type(expectations["schema_version"]) is not int or expectations["schema_version"] != 1
            or expectations["split"] != "development"
            or expectations["origin"] != "ai_simulated" or expectations["human_observed"] is not False
            or expectations["reviewer_type"] != "ai_assistant"
            or not isinstance(expectations["reviewer_model"], str)
            or not expectations["reviewer_model"].strip() or not isinstance(expectations["cases"], list)):
        raise ValueError("invalid AI-simulated development evidence")
    by_id = {}
    for case in cases:
        _validate(case)
        if case["case_id"] in by_id or case["catalog_sha256"] != corpus.catalog_sha256:
            raise ValueError("duplicate case or catalog mismatch")
        by_id[case["case_id"]] = case
    expected = {}
    available = {candidate.candidate_id for candidate in corpus.candidates}
    for row in expectations["cases"]:
        if (not isinstance(row, dict)
                or set(row) != {"case_id", "expected_state", "expected_candidate_ids"}
                or not isinstance(row["case_id"], str) or row["case_id"] in expected
                or not isinstance(row["expected_state"], str)
                or row["expected_state"] not in {"candidate_found", "unmatched"}
                or not isinstance(row["expected_candidate_ids"], list)
                or not all(isinstance(x, str) and x in available for x in row["expected_candidate_ids"])
                or len(set(row["expected_candidate_ids"])) != len(row["expected_candidate_ids"])
                or (row["expected_state"] == "unmatched") != (not row["expected_candidate_ids"])):
            raise ValueError("invalid synthetic expectation")
        expected[row["case_id"]] = row
    if set(by_id) != set(expected):
        raise ValueError("synthetic case and expectation key sets differ")
    policies = {"baseline": SearchPolicy(version="lexical-baseline-v1"),
                "candidate": SearchPolicy(version="lexical-min-score-candidate-v2", minimum_score=37.5)}
    measurements = {}
    for name, policy in policies.items():
        rows = []
        for case_id in sorted(by_id):
            case, spec = by_id[case_id], expected[case_id]
            start = perf_counter_ns()
            ranked = policy.rank(DataRequest(case_id, case["question"]), corpus.candidates, limit=3)
            elapsed_ns = perf_counter_ns() - start
            ids = [item["candidate"].candidate_id for item in ranked]
            ok = (not ids if spec["expected_state"] == "unmatched"
                  else bool(ids and ids[0] in spec["expected_candidate_ids"]))
            rows.append({"case_id": case_id, "expected_state": spec["expected_state"],
                         "top_candidate_id": ids[0] if ids else None,
                         "candidate_count": len(ids), "matches_expectation": ok,
                         "elapsed_ns": elapsed_ns})
        measurements[name] = {"policy_sha256": policy.sha256, "case_count": len(rows),
                              "matches": sum(row["matches_expectation"] for row in rows),
                              "rows": rows}
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode()).hexdigest()
    return {"status": "AI_SIMULATED_DEVELOPMENT_EVIDENCE", "origin": "ai_simulated",
            "human_observed": False, "reviewer_type": expectations["reviewer_type"],
            "reviewer_model": expectations["reviewer_model"], "split": "development",
            "gate_evidence": True, "gate_passed": False,
            "case_sha256": digest(cases), "expectations_sha256": digest(expectations),
            "catalog_sha256": corpus.catalog_sha256, "measurements": measurements,
            "delta_matches": measurements["candidate"]["matches"] - measurements["baseline"]["matches"],
            "not_measured": ["actual_user_observation", "downstream_actions", "false_exact", "split_leakage",
                             "non_target_regression", "timing_cost_budget", "validation",
                             "holdout", "promotion_eligibility"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--cases", type=Path, help="reviewed synthetic cases JSON; development only")
    parser.add_argument("--expectations", type=Path, help="AI provenance and expectations JSON")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    fixture = root / "tests/fixtures/evaluation"
    corpus = load_corpus(fixture / "v2", repo_root=root)
    def read_json(path):
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("synthetic evidence file exceeds size budget")
        return json.loads(path.read_text(encoding="utf-8"))
    cases = read_json(args.cases or fixture / "synthetic_gpt_examples.json")
    expectations = read_json(args.expectations or fixture / "synthetic_gpt_expectations.json")
    print(json.dumps(compare(corpus, cases, expectations), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
