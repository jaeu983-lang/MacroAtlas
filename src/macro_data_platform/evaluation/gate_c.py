"""Qualify and run one frozen Gate C holdout evaluation."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.search_baseline import (
    _HOLDOUT_RUN_TOKEN,
    SearchPolicy,
    _split_input_sha256,
    compare_development_policies,
    compare_split_policies,
    compare_validation_policies,
)
from macro_data_platform.evaluation.synthetic_gate_evidence import compare as compare_synthetic

_BASELINE = SearchPolicy(version="lexical-baseline-v1")
_CANDIDATE = SearchPolicy(
    version="semantic-disambiguation-v1",
    minimum_score=37.5,
    semantic_disambiguation=True,
)
_CODE_PATHS = (
    "src/macro_data_platform/evaluation/search_baseline.py",
    "src/macro_data_platform/evaluation/gate_c.py",
    "src/macro_data_platform/evaluation/synthetic_gate_evidence.py",
    "src/macro_data_platform/evaluation/cases.py",
    "src/macro_data_platform/evaluation/case_contracts.py",
    "src/macro_data_platform/evaluation/case_sets.py",
    "src/macro_data_platform/evaluation/review_ledger.py",
    "src/macro_data_platform/evaluation/split_audit.py",
    "src/macro_data_platform/discovery/series_search.py",
    "src/macro_data_platform/config.py",
    "src/macro_data_platform/contracts.py",
    "src/macro_data_platform/ingestion/freshness.py",
    "src/macro_data_platform/orchestration/models.py",
    "src/macro_data_platform/workflow_contracts.py",
)
_CASE_FIXTURES = (
    "tests/fixtures/evaluation/chatgpt_engine_smoke_examples_2026_10_28.json",
    "tests/fixtures/evaluation/chatgpt_engine_smoke_expectations_2026_10_28.json",
)
_QUALIFICATION_REL = Path("evaluation/results/gate_c_qualification.json")
_MANIFEST_REL = Path("evaluation/results/gate_c_candidate_manifest.json")
_LOCK_REL = Path("evaluation/results/gate_c_holdout_lock.json")
_HOLDOUT_REPORT_REL = Path("evaluation/results/gate_c_holdout_result.json")
_CASE_TYPES = {"rankable", "near_match", "insufficient_evidence", "unrelated"}


def _canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_fingerprint(root):
    return _digest({name: _file_sha256(root / name) for name in _CODE_PATHS})


def _read_json(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Gate C input file exceeds the size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load_budget(root):
    path = root / "tests/fixtures/evaluation/gate_c_budget_v1.json"
    budget = _read_json(path)
    required = {
        "schema_version",
        "budget_id",
        "scope",
        "timing_repetitions",
        "minimum_samples_per_case_type",
        "maximum_candidate_p95_ms_per_query",
        "maximum_candidate_to_baseline_p95_ratio",
        "maximum_external_calls",
        "maximum_external_cost_usd",
        "target_case_types",
        "target_improvement_rule",
        "non_target_case_types",
    }
    if not isinstance(budget, dict) or set(budget) != required or budget["schema_version"] != 1:
        raise ValueError("invalid frozen Gate C timing/cost budget")
    if (
        type(budget["timing_repetitions"]) is not int
        or not 1 <= budget["timing_repetitions"] <= 100
        or type(budget["minimum_samples_per_case_type"]) is not int
        or budget["minimum_samples_per_case_type"] < 1
        or not isinstance(budget["target_case_types"], list)
        or not isinstance(budget["non_target_case_types"], list)
        or not all(type(value) is str for value in budget["target_case_types"])
        or not all(type(value) is str for value in budget["non_target_case_types"])
        or budget["target_improvement_rule"]
        != "per_split_any; all_target_types_across_development_and_validation"
        or set(budget["target_case_types"]) & set(budget["non_target_case_types"])
        or set(budget["target_case_types"]) | set(budget["non_target_case_types"])
        != _CASE_TYPES
        or len(set(budget["target_case_types"])) != len(budget["target_case_types"])
        or len(set(budget["non_target_case_types"])) != len(budget["non_target_case_types"])
        or type(budget["maximum_external_calls"]) is not int
        or budget["maximum_external_calls"] != 0
        or not isinstance(budget["maximum_external_cost_usd"], (int, float))
        or isinstance(budget["maximum_external_cost_usd"], bool)
        or budget["maximum_external_cost_usd"] != 0
    ):
        raise ValueError("invalid Gate C budget values")
    for key in (
        "maximum_candidate_p95_ms_per_query",
        "maximum_candidate_to_baseline_p95_ratio",
    ):
        value = budget[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            raise ValueError("invalid Gate C timing budget")
        if value <= 0:
            raise ValueError("Gate C timing limits must be positive")
    return budget, _file_sha256(path)


def _git_revision(root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _require_committed(root, relative_paths):
    for relative in relative_paths:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(relative)],
            cwd=root, check=True, capture_output=True, text=True,
        )
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *map(str, relative_paths)],
        cwd=root, check=True, capture_output=True, text=True,
    )
    if result.stdout.strip():
        raise ValueError("frozen Gate C candidate/lock files must be committed and clean")


def _metric_comparison(report, budget):
    baseline = report["baseline"]["groups"]
    candidate = report["candidate"]["groups"]
    deltas = report["deltas"]
    checks = {}
    checks["search_confirmation"] = all(
        item["search_stage_safety"]["status"] == "PASS"
        for item in (report["baseline"], report["candidate"])
    )
    checks["unconfirmed_downstream_blocked"] = all(
        item["prohibited_action_measurement"]["status"] == "PASS"
        for item in (report["baseline"], report["candidate"])
    )
    checks["no_false_exact_or_forbidden_exact"] = all(
        values["false_exact_candidates"] == 0 and values["forbidden_exact_candidates"] == 0
        for groups in (baseline, candidate)
        for values in groups.values()
    )
    non_regression = True
    for case_type, before in baseline.items():
        after = candidate[case_type]
        for metric in (
            "top1_hits",
            "expected_state_matches",
            "status_matches",
            "fields_matches",
            "unrelated_abstentions",
        ):
            if after[metric] < before[metric]:
                non_regression = False
        for metric in ("relevant_missing_queries", "unrelated_with_candidates"):
            if after[metric] > before[metric]:
                non_regression = False
        if before["mrr"] is not None and after["mrr"] is not None and after["mrr"] < before["mrr"]:
            non_regression = False
    checks["no_case_type_regression"] = non_regression
    target_improvements = {
        case_type: deltas[case_type]
        for case_type in budget["target_case_types"]
        if case_type in deltas
        and any(
            (deltas[case_type].get(metric) or 0) > 0
            for metric in ("top1_hits", "expected_state_matches", "unrelated_abstentions")
        )
    }
    checks["target_type_improved"] = bool(target_improvements)

    timing = report.get("timing")
    timing_pass = bool(
        timing
        and timing["samples_per_policy_equal"]
        and timing["external_calls"] <= budget["maximum_external_calls"]
        and timing["estimated_external_cost_usd"] <= budget["maximum_external_cost_usd"]
    )
    if timing_pass:
        by_policy = timing["by_policy"]
        candidate_timing, baseline_timing = by_policy["candidate"], by_policy["baseline"]
        timing_pass = (
            candidate_timing["sample_count"] >= budget["minimum_samples_per_case_type"]
            and baseline_timing["sample_count"] == candidate_timing["sample_count"]
            and candidate_timing["p95_ms"] <= budget["maximum_candidate_p95_ms_per_query"]
            and baseline_timing["p95_ms"] > 0
            and candidate_timing["p95_ms"] / baseline_timing["p95_ms"]
            <= budget["maximum_candidate_to_baseline_p95_ratio"]
            and all(
                values["sample_count"] >= budget["minimum_samples_per_case_type"]
                and values["p95_ms"] <= budget["maximum_candidate_p95_ms_per_query"]
                for values in candidate_timing["by_case_type"].values()
            )
            and set(candidate_timing["by_case_type"]) == _CASE_TYPES
            and set(baseline_timing["by_case_type"]) == _CASE_TYPES
            and all(
                candidate_timing["by_case_type"][case_type]["sample_count"]
                == baseline_timing["by_case_type"][case_type]["sample_count"]
                for case_type in _CASE_TYPES
            )
        )
    checks["timing_and_cost_budget"] = timing_pass
    return {
        "checks": checks,
        "target_improvements": target_improvements,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def _case_documents(root):
    return [_read_json(root / relative) for relative in _CASE_FIXTURES]


def _comparison_summary(report, qualification):
    candidate = report["candidate"]
    timing = report["timing"]
    return {
        "status": qualification["status"],
        "checks": qualification["checks"],
        "target_improvements": qualification["target_improvements"],
        "deltas": report["deltas"],
        "candidate_action_trace": candidate["prohibited_action_measurement"]["trace"],
        "timing": {
            "baseline_p50_ms": timing["by_policy"]["baseline"]["p50_ms"],
            "baseline_p95_ms": timing["by_policy"]["baseline"]["p95_ms"],
            "candidate_p50_ms": timing["by_policy"]["candidate"]["p50_ms"],
            "candidate_p95_ms": timing["by_policy"]["candidate"]["p95_ms"],
            "samples_per_policy": timing["by_policy"]["candidate"]["sample_count"],
            "external_calls": timing["external_calls"],
            "estimated_external_cost_usd": timing["estimated_external_cost_usd"],
        },
    }


def qualify(root: Path) -> dict:
    """Run paired development and validation, then freeze a passing candidate manifest."""
    root = root.resolve()
    corpus = load_corpus(root / "tests/fixtures/evaluation/v2", repo_root=root)
    budget, budget_sha256 = _load_budget(root)
    if (root / _LOCK_REL).is_file():
        raise ValueError("candidate cannot be changed after the one-use holdout lock is written")
    development = compare_development_policies(
        corpus,
        _BASELINE,
        _CANDIDATE,
        timing_repetitions=budget["timing_repetitions"],
    )
    validation = compare_validation_policies(
        corpus,
        _BASELINE,
        _CANDIDATE,
        timing_repetitions=budget["timing_repetitions"],
    )
    synthetic_cases, synthetic_expectations = _case_documents(root)
    synthetic = compare_synthetic(corpus, synthetic_cases, synthetic_expectations)
    dev_check = _metric_comparison(development, budget)
    validation_check = _metric_comparison(validation, budget)
    improved_target_types = set(dev_check["target_improvements"]) | set(
        validation_check["target_improvements"]
    )
    target_coverage_pass = set(budget["target_case_types"]) <= improved_target_types
    synthetic_pass = (
        synthetic["measurements"]["candidate"]["matches"]
        == synthetic["measurements"]["candidate"]["case_count"]
    )
    qualified = (
        dev_check["status"] == validation_check["status"] == "PASS"
        and target_coverage_pass
        and synthetic_pass
    )

    report = {
        "schema_version": 1,
        "status": "READY_FOR_ONE_TIME_HOLDOUT" if qualified else "NOT_READY",
        "created_at": datetime.now(UTC).isoformat(),
        "corpus_version": corpus.manifest["corpus_version"],
        "case_sha256": corpus.case_sha256,
        "catalog_sha256": corpus.catalog_sha256,
        "budget_sha256": budget_sha256,
        "baseline_policy_sha256": _BASELINE.sha256,
        "candidate_policy_sha256": _CANDIDATE.sha256,
        "development": {"comparison": development, "qualification": dev_check},
        "validation": {"comparison": validation, "qualification": validation_check},
        "target_improvement_coverage": {
            "required_types": budget["target_case_types"],
            "improved_types": sorted(improved_target_types),
            "status": "PASS" if target_coverage_pass else "FAIL",
            "rule": budget["target_improvement_rule"],
        },
        "ai_simulated_development": synthetic,
        "ai_simulated_development_pass": synthetic_pass,
        "validation_integrity_note": (
            "The v2 validation cases were inspected while refining this candidate and are not a blind test. "
            "The separately frozen holdout remains the one-time generalization check."
        ),
        "holdout_independence_note": (
            "Holdout cases are hash-locked and are not sent to the ranker during qualification. "
            "The public repository makes their contents visible, so split separation is recorded but secrecy is not claimed."
        ),
        "gate_c_passed": False,
        "promotion_status": "NOT_PROMOTED",
        "not_measured": [
            "frozen_holdout", "blind_validation_independence", "promotion_eligibility",
            "human_observation",
        ],
    }
    report_sha256 = _digest(report)
    _atomic_json(root / _QUALIFICATION_REL, report)
    manifest_core = {
        "schema_version": 1,
        "status": "FROZEN" if qualified else "BLOCKED",
        "created_at": report["created_at"],
        "repository_revision": _git_revision(root),
        "source_code_sha256": _source_fingerprint(root),
        "corpus_version": corpus.manifest["corpus_version"],
        "case_sha256": corpus.case_sha256,
        "split_input_sha256": {
            split: _split_input_sha256(corpus, split)
            for split in ("development", "validation", "holdout")
        },
        "catalog_sha256": corpus.catalog_sha256,
        "budget_sha256": budget_sha256,
        "baseline_policy": {**_BASELINE.__dict__, "sha256": _BASELINE.sha256},
        "candidate_policy": {**_CANDIDATE.__dict__, "sha256": _CANDIDATE.sha256},
        "qualification_report_sha256": report_sha256,
        "development_pass": dev_check["status"] == "PASS",
        "validation_pass": validation_check["status"] == "PASS",
        "target_improvement_coverage_pass": target_coverage_pass,
        "ai_simulated_development_pass": synthetic_pass,
    }
    manifest = {**manifest_core, "manifest_sha256": _digest(manifest_core)}
    _atomic_json(root / _MANIFEST_REL, manifest)
    return {
        "status": report["status"],
        "gate_c_passed": False,
        "promotion_status": "NOT_PROMOTED",
        "corpus_version": report["corpus_version"],
        "case_sha256": report["case_sha256"],
        "catalog_sha256": report["catalog_sha256"],
        "budget_sha256": budget_sha256,
        "development": _comparison_summary(development, dev_check),
        "validation": _comparison_summary(validation, validation_check),
        "target_improvement_coverage": report["target_improvement_coverage"],
        "ai_simulated_development": {
            "baseline_matches": synthetic["measurements"]["baseline"]["matches"],
            "prior_candidate_v2_matches": synthetic["measurements"]["prior_candidate_v2"][
                "matches"
            ],
            "candidate_matches": synthetic["measurements"]["candidate"]["matches"],
            "case_count": synthetic["measurements"]["candidate"]["case_count"],
        },
        "validation_integrity_note": report["validation_integrity_note"],
        "holdout_independence_note": report["holdout_independence_note"],
        "qualification_report": str(_QUALIFICATION_REL),
        "candidate_manifest": str(_MANIFEST_REL),
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "holdout_status": "NOT_RUN",
    }


def initialize_holdout_lock(root: Path) -> dict:
    root = root.resolve()
    _require_committed(root, (_QUALIFICATION_REL, _MANIFEST_REL))
    manifest = _read_json(root / _MANIFEST_REL)
    if (
        manifest.get("status") != "FROZEN"
        or not manifest.get("development_pass")
        or not manifest.get("validation_pass")
    ):
        raise ValueError("only a development/validation-qualified candidate can lock the holdout")
    corpus = load_corpus(root / "tests/fixtures/evaluation/v2", repo_root=root)
    _budget, budget_sha256 = _load_budget(root)
    _verify_manifest(root, manifest, corpus, budget_sha256)
    if manifest.get("source_code_sha256") != _source_fingerprint(root):
        raise ValueError("candidate source changed after qualification")
    if (
        manifest.get("case_sha256") != corpus.case_sha256
        or manifest.get("catalog_sha256") != corpus.catalog_sha256
    ):
        raise ValueError("case or catalog changed after qualification")
    if manifest.get("budget_sha256") != budget_sha256:
        raise ValueError("timing/cost budget changed after qualification")
    path = root / _LOCK_REL
    if path.exists():
        raise ValueError("holdout lock already exists; do not reset or rerun it")
    lock_core = {
        "schema_version": 1,
        "state": "AVAILABLE",
        "case_sha256": corpus.case_sha256,
        "holdout_input_sha256": manifest["split_input_sha256"]["holdout"],
        "catalog_sha256": corpus.catalog_sha256,
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    lock = {**lock_core, "lock_sha256": _digest(lock_core)}
    _atomic_json(path, lock)
    return {
        "status": lock["state"],
        "lock_path": str(_LOCK_REL),
        "lock_sha256": lock["lock_sha256"],
    }


def _verify_manifest(root, manifest, corpus, budget_sha256):
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "status",
        "created_at",
        "repository_revision",
        "source_code_sha256",
        "corpus_version",
        "case_sha256",
        "split_input_sha256",
        "catalog_sha256",
        "budget_sha256",
        "baseline_policy",
        "candidate_policy",
        "qualification_report_sha256",
        "development_pass",
        "validation_pass",
        "target_improvement_coverage_pass",
        "ai_simulated_development_pass",
        "manifest_sha256",
    }:
        raise ValueError("invalid frozen candidate manifest")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest["manifest_sha256"] != _digest(core):
        raise ValueError("candidate manifest hash mismatch")
    if manifest["status"] != "FROZEN" or not all(
        manifest[key] is True
        for key in (
            "development_pass",
            "validation_pass",
            "target_improvement_coverage_pass",
            "ai_simulated_development_pass",
        )
    ):
        raise ValueError("candidate manifest is not qualified")
    if manifest["source_code_sha256"] != _source_fingerprint(root):
        raise ValueError("candidate source code changed after freeze")
    if (
        manifest["case_sha256"] != corpus.case_sha256
        or manifest["catalog_sha256"] != corpus.catalog_sha256
        or manifest["budget_sha256"] != budget_sha256
        or manifest["split_input_sha256"].get("holdout") != _split_input_sha256(corpus, "holdout")
    ):
        raise ValueError("frozen holdout inputs or budget changed")
    if manifest["candidate_policy"].get("sha256") != _CANDIDATE.sha256:
        raise ValueError("candidate policy changed after freeze")
    qualification_path = root / _QUALIFICATION_REL
    if (
        not qualification_path.is_file()
        or _digest(_read_json(qualification_path)) != manifest["qualification_report_sha256"]
    ):
        raise ValueError("qualification report changed after candidate freeze")


def run_holdout(root: Path) -> dict:
    root = root.resolve()
    manifest_path, lock_path, report_path = (
        root / _MANIFEST_REL,
        root / _LOCK_REL,
        root / _HOLDOUT_REPORT_REL,
    )
    _require_committed(root, (_QUALIFICATION_REL, _MANIFEST_REL, _LOCK_REL))
    manifest = _read_json(manifest_path)
    corpus = load_corpus(root / "tests/fixtures/evaluation/v2", repo_root=root)
    budget, budget_sha256 = _load_budget(root)
    _verify_manifest(root, manifest, corpus, budget_sha256)
    lock = _read_json(lock_path)
    if lock.get("state") != "AVAILABLE":
        raise ValueError("holdout is already consumed; create and freeze a new holdout version")
    lock_core = {key: value for key, value in lock.items() if key != "lock_sha256"}
    if lock.get("lock_sha256") != _digest(lock_core):
        raise ValueError("holdout lock hash mismatch")
    if (
        lock.get("candidate_manifest_sha256") != manifest["manifest_sha256"]
        or lock.get("case_sha256") != corpus.case_sha256
        or lock.get("holdout_input_sha256") != _split_input_sha256(corpus, "holdout")
        or lock.get("catalog_sha256") != corpus.catalog_sha256
    ):
        raise ValueError("holdout lock does not match frozen candidate inputs")
    if report_path.exists():
        raise ValueError("holdout result already exists; refusing a second run")

    started_at = datetime.now(UTC).isoformat()
    started_core = lock_core | {"state": "STARTED", "started_at": started_at}
    _atomic_json(lock_path, {**started_core, "lock_sha256": _digest(started_core)})
    comparison = compare_split_policies(
        corpus,
        _BASELINE,
        _CANDIDATE,
        split="holdout",
        timing_repetitions=budget["timing_repetitions"],
        _holdout_token=_HOLDOUT_RUN_TOKEN,
    )
    qualification = _metric_comparison(comparison, budget)
    result = {
        "schema_version": 1,
        "gate_c_status": qualification["status"],
        "gate_c_passed": qualification["status"] == "PASS",
        "promotion_status": "NOT_PROMOTED",
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "holdout_integrity_note": (
            "Holdout questions were not sent to the ranker during qualification; only their split hash "
            "was bound into the candidate manifest. This public split is separate, not secret. Validation "
            "was inspected during candidate refinement and is not blind evidence."
        ),
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "case_sha256": corpus.case_sha256,
        "holdout_input_sha256": _split_input_sha256(corpus, "holdout"),
        "catalog_sha256": corpus.catalog_sha256,
        "budget_sha256": budget_sha256,
        "comparison": comparison,
        "qualification": qualification,
        "not_measured": [
            "promotion_eligibility",
            "human_observation",
            "proof_of_statistical_equivalence",
        ],
    }
    report_sha256 = _digest(result)
    _atomic_json(report_path, result)
    completed_core = started_core | {
        "state": "COMPLETED",
        "completed_at": result["completed_at"],
        "result_sha256": report_sha256,
        "gate_c_status": result["gate_c_status"],
    }
    _atomic_json(lock_path, {**completed_core, "lock_sha256": _digest(completed_core)})
    return {
        "gate_c_status": result["gate_c_status"],
        "gate_c_passed": result["gate_c_passed"],
        "promotion_status": "NOT_PROMOTED",
        "case_sha256": result["case_sha256"],
        "holdout_input_sha256": result["holdout_input_sha256"],
        "candidate_manifest_sha256": result["candidate_manifest_sha256"],
        "qualification": qualification["checks"],
        "deltas": comparison["deltas"],
        "timing": {
            "baseline_p95_ms": comparison["timing"]["by_policy"]["baseline"]["p95_ms"],
            "candidate_p95_ms": comparison["timing"]["by_policy"]["candidate"]["p95_ms"],
            "samples_per_policy": comparison["timing"]["by_policy"]["candidate"]["sample_count"],
        },
        "report_path": str(_HOLDOUT_REPORT_REL),
        "result_sha256": report_sha256,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("qualify", "measure development and validation and freeze a passing candidate"),
        ("initialize-holdout", "write the one-use holdout lock after a passing qualification"),
        ("holdout", "consume the frozen holdout exactly once"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = {
            "qualify": qualify,
            "initialize-holdout": initialize_holdout_lock,
            "holdout": run_holdout,
        }[args.command](args.project_root)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if result.get("gate_c_status", result.get("status")) not in {"FAIL", "NOT_READY", "BLOCKED"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
