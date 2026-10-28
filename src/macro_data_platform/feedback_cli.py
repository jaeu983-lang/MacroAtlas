"""Explicit task-linked feedback CLI; see docs/DEVELOPER_GUIDE.md for the operator workflow."""
import argparse
import json
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.feedback_classification import FeedbackClassificationStore
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
    history = commands.add_parser("history", help="inspect revisions for one feedback item")
    history.add_argument("--feedback-id", required=True)

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
    commands.add_parser("classification-snapshot", help="freeze feedback revision identities")
    batch = commands.add_parser("classification-import", help="validate and store manual labels")
    batch.add_argument("--results", required=True, type=Path)
    batch.add_argument("--privacy-cleared", required=True, action="store_true",
                       help="attest that external classification input was privacy reviewed")
    commands.add_parser("classification-list", help="list stored classification batches")
    show = commands.add_parser("classification-show", help="inspect labels in one batch")
    show.add_argument("--batch-id", required=True)
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
    elif args.command == "history":
        result = store.history_for(args.feedback_id)
    elif args.command == "edit":
        result = store.revise(args.feedback_id, expected_revision=args.expected_revision,
                              changes=args.changes_json)
    elif args.command == "review":
        result = store.review(args.feedback_id, expected_revision=args.expected_revision,
                              status=args.status, reviewer_note=args.note)
    elif args.command == "withdraw":
        result = store.withdraw(args.feedback_id, expected_revision=args.expected_revision,
                                reason=args.reason)
    elif args.command == "classification-snapshot":
        result = FeedbackClassificationStore(store).snapshot()
    elif args.command == "classification-import":
        document = json.loads(args.results.read_text(encoding="utf-8"))
        result = FeedbackClassificationStore(store).import_batch(document)
    elif args.command == "classification-list":
        result = FeedbackClassificationStore(store).batches()
    else:
        result = FeedbackClassificationStore(store).batch_rows(args.batch_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
