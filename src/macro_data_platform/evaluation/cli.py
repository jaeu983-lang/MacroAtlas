"""Validate evaluation scaffolds and immutable corpora without running an engine."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from macro_data_platform.evaluation.case_sets import validate_case_sets
from macro_data_platform.evaluation.cases import load_corpus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate the split-set scaffold")
    validate.add_argument("--sets-dir", type=Path, default=Path.cwd() / "evaluation" / "sets")
    corpus = commands.add_parser(
        "validate-corpus", help="validate the evidence-backed immutable case corpus"
    )
    corpus.add_argument(
        "--corpus-dir", type=Path,
        default=Path.cwd() / "tests" / "fixtures" / "evaluation" / "v1",
    )
    corpus.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "validate":
        report = validate_case_sets(args.sets_dir)
        ready = report["status"] in {"READY", "VALID_BUT_EMPTY"}
    else:
        try:
            loaded = load_corpus(args.corpus_dir, repo_root=args.repo_root)
        except (OSError, ValueError) as exc:
            report = {"status": "INVALID", "ready": False, "errors": [str(exc)]}
            ready = False
        else:
            complete = loaded.manifest["gate_status"] == "complete"
            report = {
                "status": "READY" if complete else "BLOCKED",
                "ready": complete,
                "corpus_version": loaded.manifest["corpus_version"],
                "case_count": len(loaded.cases),
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
