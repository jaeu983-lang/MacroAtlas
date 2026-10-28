"""Create local, incomplete case-authoring seeds from explicitly reviewed feedback."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from macro_data_platform.config import Settings
from macro_data_platform.storage.feedback import FeedbackStore

_FEEDBACK_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,89}")
_REVIEWER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_CATEGORIES = {
    "candidate_group", "question_order", "output_preference", "source_method",
    "statistical_definition", "other",
}
_DRAFT_FIELDS = {
    "schema", "schema_version", "draft_id", "draft_status", "created_at", "target_split",
    "provenance", "privacy_review", "sanitized_question", "required_case_fields",
    "promotion_status",
}
_PROVENANCE_FIELDS = {
    "origin", "feedback_id", "feedback_revision", "feedback_category",
}
_PRIVACY_FIELDS = {"decision", "reviewer_id", "reviewed_at", "basis"}
_PRIVACY_BASIS = (
    "Reviewer explicitly confirmed the included sanitized text and category are cleared; "
    "the original feedback body and task metadata are omitted."
)
_CASE_FIELDS_TO_COMPLETE = (
    "question_variants_and_contrast_family",
    "expected_state_and_candidate_or_series_fields",
    "required_official_evidence_and_hashes",
    "prohibited_actions",
    "excel_policy",
    "independent_case_review_before_corpus_admission",
)


def build_feedback_case_draft(
    feedback_store: FeedbackStore,
    *,
    feedback_id: str,
    expected_revision: int,
    sanitized_question: str,
    reviewer_id: str,
    privacy_cleared: bool,
) -> dict[str, Any]:
    """Build a development-only seed without copying the source feedback body."""
    if not isinstance(feedback_id, str) or _FEEDBACK_ID.fullmatch(feedback_id) is None:
        raise ValueError("invalid feedback identifier")
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("expected feedback revision must be a positive integer")
    if (not isinstance(sanitized_question, str) or not sanitized_question.strip()
            or len(sanitized_question) > 2000):
        raise ValueError("sanitized question must be a non-empty string of at most 2000 characters")
    if not isinstance(reviewer_id, str) or _REVIEWER_ID.fullmatch(reviewer_id) is None:
        raise ValueError("reviewer ID must be a bounded non-email identifier")
    if privacy_cleared is not True:
        raise ValueError("explicit privacy clearance is required")

    feedback = feedback_store.get(feedback_id)
    if feedback["revision"] != expected_revision:
        raise ValueError("stale feedback revision")
    if feedback["review_status"] != "accepted":
        raise ValueError("only accepted feedback can create a case draft")
    if feedback["knowledge_kind"] != "user_instruction":
        raise ValueError("only user-instruction feedback can seed a user case")

    reviewed_at = feedback_store.clock()
    if (not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None
            or reviewed_at.utcoffset() != UTC.utcoffset(reviewed_at)):
        raise ValueError("feedback clock must return UTC")
    draft_id = f"feedback-{feedback_id}-r{expected_revision}"
    return {
        "schema": "MacroAtlasFeedbackCaseDraft",
        "schema_version": 1,
        "draft_id": draft_id,
        "draft_status": "case_authoring_required",
        "created_at": reviewed_at.isoformat(),
        "target_split": "development",
        "provenance": {
            "origin": "reviewed_feedback_seed",
            "feedback_id": feedback_id,
            "feedback_revision": expected_revision,
            "feedback_category": feedback["category"],
        },
        "privacy_review": {
            "decision": "cleared",
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at.isoformat(),
            "basis": _PRIVACY_BASIS,
        },
        "sanitized_question": sanitized_question,
        "required_case_fields": list(_CASE_FIELDS_TO_COMPLETE),
        "promotion_status": "not_promoted",
    }


def write_feedback_case_draft(settings: Settings, draft: dict[str, Any]) -> Path:
    """Write one local draft, refusing path escapes, symlinks, and overwrite."""
    if not isinstance(draft, dict) or set(draft) != _DRAFT_FIELDS:
        raise ValueError("invalid feedback case draft")
    provenance, privacy = draft["provenance"], draft["privacy_review"]
    if (draft["schema"] != "MacroAtlasFeedbackCaseDraft"
            or type(draft["schema_version"]) is not int or draft["schema_version"] != 1
            or not isinstance(draft["draft_id"], str)
            or _FEEDBACK_ID.fullmatch(draft["draft_id"]) is None
            or draft["draft_status"] != "case_authoring_required"
            or draft["target_split"] != "development"
            or draft["promotion_status"] != "not_promoted"
            or not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_FIELDS
            or provenance["origin"] != "reviewed_feedback_seed"
            or not isinstance(provenance["feedback_id"], str)
            or _FEEDBACK_ID.fullmatch(provenance["feedback_id"]) is None
            or type(provenance["feedback_revision"]) is not int
            or provenance["feedback_revision"] < 1
            or not isinstance(provenance["feedback_category"], str)
            or provenance["feedback_category"] not in _CATEGORIES
            or draft["draft_id"] != (f"feedback-{provenance['feedback_id']}-r"
                                     f"{provenance['feedback_revision']}")
            or not isinstance(privacy, dict) or set(privacy) != _PRIVACY_FIELDS
            or privacy["decision"] != "cleared"
            or not isinstance(privacy["reviewer_id"], str)
            or _REVIEWER_ID.fullmatch(privacy["reviewer_id"]) is None
            or privacy["basis"] != _PRIVACY_BASIS
            or not isinstance(draft["sanitized_question"], str)
            or not draft["sanitized_question"].strip()
            or len(draft["sanitized_question"]) > 2000
            or draft["required_case_fields"] != list(_CASE_FIELDS_TO_COMPLETE)
            or not _is_utc(draft["created_at"])
            or not _is_utc(privacy["reviewed_at"])
            or draft["created_at"] != privacy["reviewed_at"]):
        raise ValueError("invalid feedback case draft")

    relative_dir = f"{settings.data_dir}/feedback_case_drafts"
    directory = settings._inside(relative_dir)
    root = settings.project_root.resolve()
    if not directory.is_relative_to(root):
        raise ValueError("feedback case draft directory escapes the project")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or not directory.resolve().is_relative_to(root):
        raise ValueError("feedback case draft directory must remain inside the project")

    path = directory / f"{draft['draft_id']}.json"
    if path.parent != directory or path.is_symlink():
        raise ValueError("invalid feedback case draft path")
    content = (json.dumps(draft, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _is_utc(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(parsed)
