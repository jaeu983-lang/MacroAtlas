"""Validate evaluation scaffolds and immutable corpora without running an engine."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.evaluation.case_sets import validate_case_sets
from macro_data_platform.evaluation.cases import load_corpus
from macro_data_platform.evaluation.feedback_bridge import (
    build_feedback_case_draft,
    write_feedback_case_draft,
)
from macro_data_platform.evaluation.search_baseline import (
    DEFAULT_CANDIDATE_MINIMUM_SCORE,
    DEFAULT_CANDIDATE_POLICY_VERSION,
    SearchPolicy,
    compare_development_policies,
    compare_validation_policies,
    evaluate_development,
)
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate the split-set scaffold")
    validate.add_argument("--sets-dir", type=Path, default=Path.cwd() / "evaluation" / "sets")
    corpus = commands.add_parser(
        "validate-corpus", help="validate the evidence-backed immutable case corpus"
    )
    corpus.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path.cwd() / "tests" / "fixtures" / "evaluation" / "v2",
    )
    corpus.add_argument("--repo-root", type=Path, default=None)
    baseline = commands.add_parser("search-baseline", help="measure development ranking offline")
    baseline.add_argument(
        "--corpus-dir", type=Path, default=Path.cwd() / "tests/fixtures/evaluation/v2"
    )
    baseline.add_argument("--repo-root", type=Path, default=None)
    compare = commands.add_parser(
        "search-compare", help="compare two ranker policies on development cases only"
    )
    compare.add_argument(
        "--corpus-dir", type=Path, default=Path.cwd() / "tests/fixtures/evaluation/v2"
    )
    compare.add_argument("--repo-root", type=Path, default=None)
    compare.add_argument(
        "--candidate-min-score", type=float, default=DEFAULT_CANDIDATE_MINIMUM_SCORE
    )
    compare.add_argument(
        "--candidate-policy",
        choices=("threshold-v2", "semantic-v1"),
        default="threshold-v2",
    )
    compare.add_argument("--timing-repetitions", type=int, default=0)
    validate_search = commands.add_parser(
        "search-validation", help="compare frozen policy behavior on validation only"
    )
    validate_search.add_argument(
        "--corpus-dir", type=Path, default=Path.cwd() / "tests/fixtures/evaluation/v2"
    )
    validate_search.add_argument("--repo-root", type=Path, default=None)
    validate_search.add_argument(
        "--candidate-min-score", type=float, default=DEFAULT_CANDIDATE_MINIMUM_SCORE
    )
    validate_search.add_argument(
        "--candidate-policy",
        choices=("threshold-v2", "semantic-v1"),
        default="threshold-v2",
    )
    validate_search.add_argument("--timing-repetitions", type=int, default=0)
    feedback_draft = commands.add_parser(
        "feedback-draft", help="create a local, incomplete case seed from reviewed feedback"
    )
    feedback_draft.add_argument("--project-root", type=Path, default=Path.cwd())
    feedback_draft.add_argument("--feedback-id", required=True)
    feedback_draft.add_argument("--expected-revision", type=int, required=True)
    feedback_draft.add_argument("--sanitized-question", required=True)
    feedback_draft.add_argument("--reviewer-id", required=True)
    feedback_draft.add_argument("--privacy-cleared", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate":
        report = validate_case_sets(args.sets_dir)
        ready = report["status"] in {"READY", "VALID_BUT_EMPTY"}
    elif args.command == "feedback-draft":
        try:
            settings = Settings(args.project_root.resolve())
            feedback = FeedbackStore(HistoryStore(settings))
            draft = build_feedback_case_draft(
                feedback,
                feedback_id=args.feedback_id,
                expected_revision=args.expected_revision,
                sanitized_question=args.sanitized_question,
                reviewer_id=args.reviewer_id,
                privacy_cleared=args.privacy_cleared,
            )
            path = write_feedback_case_draft(settings, draft)
        except (KeyError, OSError, ValueError) as exc:
            report = {"status": "REJECTED", "errors": [str(exc)]}
            ready = False
        else:
            report = {
                "status": "DRAFT_CREATED",
                "draft_id": draft["draft_id"],
                "draft_status": draft["draft_status"],
                "target_split": draft["target_split"],
                "promotion_status": draft["promotion_status"],
                "path": str(path),
            }
            ready = True
    else:
        try:
            loaded = load_corpus(args.corpus_dir, repo_root=args.repo_root)
        except (OSError, ValueError) as exc:
            report = {"status": "INVALID", "ready": False, "errors": [str(exc)]}
            ready = False
        else:
            complete = loaded.manifest["gate_status"] == "complete"
            if args.command == "search-baseline":
                report = evaluate_development(loaded)
                ready = True
            elif args.command == "search-compare":
                semantic = args.candidate_policy == "semantic-v1"
                try:
                    report = compare_development_policies(
                        loaded,
                        SearchPolicy(version="lexical-baseline-v1"),
                        SearchPolicy(
                            version=(
                                "semantic-disambiguation-v1"
                                if semantic
                                else DEFAULT_CANDIDATE_POLICY_VERSION
                            ),
                            minimum_score=args.candidate_min_score,
                            semantic_disambiguation=semantic,
                        ),
                        timing_repetitions=args.timing_repetitions,
                    )
                except ValueError as exc:
                    report = {"status": "INVALID_POLICY", "errors": [str(exc)]}
                    ready = False
                else:
                    ready = True
            elif args.command == "search-validation":
                semantic = args.candidate_policy == "semantic-v1"
                try:
                    report = compare_validation_policies(
                        loaded,
                        SearchPolicy(version="lexical-baseline-v1"),
                        SearchPolicy(
                            version=(
                                "semantic-disambiguation-v1"
                                if semantic
                                else DEFAULT_CANDIDATE_POLICY_VERSION
                            ),
                            minimum_score=args.candidate_min_score,
                            semantic_disambiguation=semantic,
                        ),
                        timing_repetitions=args.timing_repetitions,
                    )
                except ValueError as exc:
                    report = {"status": "INVALID_POLICY", "errors": [str(exc)]}
                    ready = False
                else:
                    ready = True
            else:
                report = {
                    "status": "READY" if complete else "BLOCKED",
                    "ready": complete,
                    "corpus_version": loaded.manifest["corpus_version"],
                    "case_count": len(loaded.cases),
                    "reviewed_draft_count": loaded.manifest.get("reviewed_draft_count", 0),
                    "gate_status": loaded.manifest["gate_status"],
                    "counts_by_split": dict(loaded.manifest["counts_by_split"]),
                    "counts_by_type": dict(loaded.manifest["counts_by_type"]),
                    "gate_blockers": list(loaded.manifest["gate_blockers"]),
                    "case_sha256": loaded.case_sha256,
                    "catalog_sha256": loaded.catalog_sha256,
                    "split_leakage_issues": [
                        asdict(issue) for issue in loaded.split_leakage_issues
                    ],
                    "evidence_files_verified": True,
                    "errors": [],
                }
                ready = complete
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
