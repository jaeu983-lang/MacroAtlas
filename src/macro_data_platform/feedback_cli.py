"""Explicit task-linked feedback CLI; see docs/DEVELOPER_GUIDE.md for the operator workflow."""
import argparse
import json
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.history import HistoryStore


def _json(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("expected valid JSON") from exc


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="record explicit user, source, or inference feedback")
    add.add_argument("--task-id", required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--category", choices=sorted({"candidate_group", "question_order",
                     "output_preference", "source_method", "statistical_definition", "other"}),
                     default="other")
    add.add_argument("--knowledge-kind", choices=("user_instruction", "official_evidence",
                     "inference"), default="user_instruction")
    add.add_argument("--scope-json", type=_json, default={})
    add.add_argument("--evidence-json", type=_json, default=[])
    add.add_argument("--stage-run-id")
    add.add_argument("--related-record-id")
    add.add_argument("--supersedes-feedback-id")
    add.add_argument("--idempotency-key")

    listing = commands.add_parser("list", help="list feedback for one task")
    listing.add_argument("--task-id", required=True)
    listing.add_argument("--institution-id")
    listing.add_argument("--category", choices=sorted({"candidate_group", "question_order",
                         "output_preference", "source_method", "statistical_definition", "other"}))
    listing.add_argument("--limit", type=int, default=100)

    edit = commands.add_parser("edit", help="append an edit revision")
    edit.add_argument("--feedback-id", required=True)
    edit.add_argument("--expected-revision", required=True, type=int)
    edit.add_argument("--changes-json", required=True, type=_json)

    review = commands.add_parser("review", help="record a review decision")
    review.add_argument("--feedback-id", required=True)
    review.add_argument("--expected-revision", required=True, type=int)
    review.add_argument("--status", choices=("accepted", "rejected", "unreviewed"), required=True)
    review.add_argument("--note")

    withdraw = commands.add_parser("withdraw", help="withdraw without deleting history")
    withdraw.add_argument("--feedback-id", required=True)
    withdraw.add_argument("--expected-revision", required=True, type=int)
    withdraw.add_argument("--reason", required=True)
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    store = FeedbackStore(HistoryStore(Settings(args.project_root.resolve())))
    if args.command == "add":
        result = store.record(
            args.task_id, text=args.text, category=args.category,
            knowledge_kind=args.knowledge_kind, scope=args.scope_json,
            evidence_refs=args.evidence_json, stage_run_id=args.stage_run_id,
            related_record_id=args.related_record_id,
            supersedes_feedback_id=args.supersedes_feedback_id,
            idempotency_key=args.idempotency_key,
        )
    elif args.command == "list":
        result = store.for_task(args.task_id, institution_id=args.institution_id,
                                category=args.category, limit=args.limit)
    elif args.command == "edit":
        result = store.revise(args.feedback_id, expected_revision=args.expected_revision,
                              changes=args.changes_json)
    elif args.command == "review":
        result = store.review(args.feedback_id, expected_revision=args.expected_revision,
                              status=args.status, reviewer_note=args.note)
    else:
        result = store.withdraw(args.feedback_id, expected_revision=args.expected_revision,
                                reason=args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
