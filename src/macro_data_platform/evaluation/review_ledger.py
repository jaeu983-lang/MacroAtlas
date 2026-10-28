"""Verify case-by-case review records before draft cases enter a fixed corpus."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from macro_data_platform.evaluation.case_contracts import EvaluationCase

_MAX_LEDGER_BYTES = 4 * 1024 * 1024
_MAX_DRAFT_BYTES = 512 * 1024
_SHA256 = re.compile(r"[a-f0-9]{64}")
_ID = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}")
_FIELDS = {
    "review_id", "source_draft_id", "source_draft_path", "source_draft_sha256",
    "source_case_id", "source_case_version", "source_case_sha256", "case_id", "case_version",
    "accepted_case_sha256", "reviewer_id", "reviewer_type", "reviewer_model",
    "reviewed_at", "decision", "scope", "assessment", "evidence", "privacy",
    "corrections", "limitations",
}
_DECISIONS = {"approved", "approved_after_revision"}


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonstandard JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _read_bounded(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError("Review source exceeds its size limit")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Review source exceeds its size limit")
    return data


def _text(value: Any, name: str, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Invalid review {name}")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"Invalid review {name}")
    return value


def _safe_draft_path(value: Any, repo_root: Path) -> Path:
    _text(value, "draft path", 512)
    relative = PurePosixPath(value)
    expected_prefix = PurePosixPath("tests/fixtures/evaluation/drafts")
    if (relative.is_absolute() or ".." in relative.parts or "\\" in value
            or relative.parent != expected_prefix or relative.suffix != ".json"):
        raise ValueError("Review draft path must be a direct JSON child of the draft pool")
    root = (repo_root / expected_prefix.as_posix()).resolve()
    path = (repo_root / relative.as_posix()).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("Review draft path is missing or outside the draft pool")
    return path


def _string_list(value: Any, name: str, *, maximum: int = 32) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"Invalid review {name}")
    result = tuple(_text(item, name, 1000) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"Duplicate review {name}")
    return result


def validate_review_ledger(
    ledger_path: str | Path,
    cases: tuple[EvaluationCase, ...],
    repo_root: str | Path,
    *,
    expected_count: int,
) -> tuple[dict[str, Any], ...]:
    """Validate source hashes, decisions, evidence links, and promoted case hashes."""
    path = Path(ledger_path)
    root = Path(repo_root).resolve()
    raw = _read_bounded(path, _MAX_LEDGER_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Review ledger must be UTF-8") from None
    if not text or not text.endswith("\n"):
        raise ValueError("Review ledger must be non-empty JSONL ending in a newline")

    draft_root = root / "tests/fixtures/evaluation/drafts"
    try:
        draft_manifest = json.loads(
            _read_bounded(draft_root / "manifest.json", 128 * 1024).decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid draft source manifest") from None
    if (not isinstance(draft_manifest, dict)
            or not isinstance(draft_manifest.get("files"), dict)
            or type(draft_manifest.get("draft_case_count")) is not int
            or draft_manifest["draft_case_count"] != expected_count
            or len(draft_manifest["files"]) != expected_count):
        raise ValueError("Draft source manifest does not match the review quota")
    source_case_ids = source_case_ids_from_manifest(draft_root, draft_manifest, root)
    if len(source_case_ids) != expected_count:
        raise ValueError("Draft source manifest contains duplicate case identifiers")

    cases_by_id = {case.case_id: case for case in cases}
    rows = []
    review_ids = set()
    source_draft_ids = set()
    reviewed_case_ids = set()
    source_paths = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or len(line.encode("utf-8")) > 256 * 1024:
            raise ValueError(f"Invalid review ledger line {line_number}")
        try:
            row = json.loads(line, object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            raise ValueError(f"Invalid review ledger line {line_number}") from None
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError(f"Invalid review ledger fields at line {line_number}")

        for name in ("review_id", "source_draft_id", "source_case_id", "case_id", "reviewer_id"):
            if not isinstance(row[name], str) or _ID.fullmatch(row[name]) is None:
                raise ValueError(f"Invalid review {name}")
        if (row["review_id"] in review_ids or row["source_draft_id"] in source_draft_ids
                or row["case_id"] in reviewed_case_ids):
            raise ValueError("Duplicate review record, source draft, or promoted case")
        review_ids.add(row["review_id"])
        source_draft_ids.add(row["source_draft_id"])
        reviewed_case_ids.add(row["case_id"])

        draft_path = _safe_draft_path(row["source_draft_path"], root)
        relative_path = PurePosixPath(row["source_draft_path"]).name
        if relative_path in source_paths:
            raise ValueError("Duplicate review source path")
        source_paths.add(relative_path)
        actual_draft_hash = hashlib.sha256(_read_bounded(draft_path, _MAX_DRAFT_BYTES)).hexdigest()
        declared_draft_hash = _digest(row["source_draft_sha256"], "draft SHA-256")
        if (actual_draft_hash != declared_draft_hash
                or draft_manifest["files"].get(relative_path) != declared_draft_hash):
            raise ValueError("Review source draft hash mismatch")

        try:
            draft = json.loads(_read_bounded(draft_path, _MAX_DRAFT_BYTES).decode("utf-8"),
                               object_pairs_hook=_unique_object,
                               parse_constant=_reject_constant)
            source_case = EvaluationCase.from_dict(draft["case"])
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
            raise ValueError("Invalid reviewed source draft") from None
        if (draft.get("draft_id") != row["source_draft_id"]
                or source_case.case_id != row["source_case_id"]):
            raise ValueError("Review record does not identify its source draft")
        if (draft.get("draft_status") != "independent_review_pending"
                or draft.get("authorship") != {
                    "origin": "assistant_simulated", "human_observed": False,
                    "independent_review_completed": False,
                }):
            raise ValueError("Review source is not an unchanged assistant-generated draft")
        if (type(row["source_case_version"]) is not int
                or row["source_case_version"] != source_case.case_version):
            raise ValueError("Review source case version mismatch")
        if hashlib.sha256(source_case.to_json().encode("utf-8")).hexdigest() != _digest(
                row["source_case_sha256"], "source case SHA-256"):
            raise ValueError("Review source case hash mismatch")

        decision = row["decision"]
        if not isinstance(decision, str) or decision not in _DECISIONS:
            raise ValueError("Only approved cases may enter the fixed corpus")
        corrections = _string_list(row["corrections"], "correction", maximum=16)
        if (decision == "approved_after_revision") != bool(corrections):
            raise ValueError("Review correction status does not match its decision")

        if type(row["case_version"]) is not int or row["case_version"] < 1:
            raise ValueError("Invalid reviewed case version")
        case = cases_by_id.get(row["case_id"])
        if (case is None or case.case_version != row["case_version"]
                or case.case_id != source_case.case_id):
            raise ValueError("Approved review has no matching corpus case")
        accepted_hash = hashlib.sha256(case.to_json().encode("utf-8")).hexdigest()
        if accepted_hash != _digest(row["accepted_case_sha256"], "accepted case SHA-256"):
            raise ValueError("Review accepted case hash mismatch")

        evidence = row["evidence"]
        expected_evidence = [
            {"evidence_id": item["evidence_id"], "local_ref": item["local_ref"],
             "sha256": item["sha256"]}
            for item in case.to_dict()["required_evidence"]
        ]
        if evidence != expected_evidence:
            raise ValueError("Review evidence list does not match the accepted case")

        if (row["reviewer_type"] != "ai_assistant"
                or row["reviewer_model"] != "GPT-6"):
            raise ValueError("Review provenance must identify the GPT reviewer")
        _text(row["reviewer_model"], "model", 128)
        _text(row["scope"], "scope", 1000)
        _text(row["assessment"], "assessment")
        _text(row["reviewed_at"], "timestamp", 64)
        try:
            reviewed_at = datetime.fromisoformat(row["reviewed_at"])
        except ValueError:
            raise ValueError("Invalid review timestamp") from None
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() != UTC.utcoffset(reviewed_at):
            raise ValueError("Review timestamp must be UTC")
        if not isinstance(row["privacy"], dict) or set(row["privacy"]) != {"decision", "basis"}:
            raise ValueError("Invalid review privacy decision")
        if row["privacy"]["decision"] != "clear":
            raise ValueError("Cases without privacy clearance cannot be promoted")
        _text(row["privacy"]["basis"], "privacy basis")
        if not _string_list(row["limitations"], "limitation", maximum=16):
            raise ValueError("Review limitations must be explicit")
        rows.append(row)

    if (len(rows) != expected_count or source_paths != set(draft_manifest["files"])
            or reviewed_case_ids != source_case_ids
            or not source_case_ids.issubset(cases_by_id)):
        raise ValueError("Review ledger does not cover every draft and promoted case")
    return tuple(rows)


def source_case_ids_from_manifest(
    draft_root: Path, manifest: dict[str, Any], repo_root: Path,
) -> set[str]:
    """Read source case identifiers to ensure every promoted draft has a review row."""
    result = set()
    for filename in manifest["files"]:
        path = (repo_root / "tests/fixtures/evaluation/drafts" / filename).resolve()
        if path.parent != draft_root.resolve():
            raise ValueError("Draft manifest path escapes its directory")
        try:
            draft = json.loads(_read_bounded(path, _MAX_DRAFT_BYTES).decode("utf-8"),
                               object_pairs_hook=_unique_object,
                               parse_constant=_reject_constant)
            case = EvaluationCase.from_dict(draft["case"])
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
            raise ValueError("Invalid case in source draft manifest") from None
        result.add(case.case_id)
    return result
