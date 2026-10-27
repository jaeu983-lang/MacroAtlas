"""Validation for the original split-set evaluation scaffold format.

The evidence-backed JSONL corpus contract is implemented in ``cases.py``.
This module keeps the earlier JSON-per-split scaffold validator available for
its existing fixtures and CLI command. It never executes or scores an engine.
"""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

CASE_SCHEMA_VERSION = 1
SET_SCHEMA_VERSION = 1
SPLITS = ("development", "validation", "holdout")
_MAX_SET_BYTES = 16 * 1024 * 1024
_MAX_CASES_PER_SET = 10_000
_MAX_TEXT = 4_000
_REQUIRED_EVIDENCE = {
    "source_url", "source_identifier", "definition", "unit", "frequency",
    "observation_period", "retrieved_at", "raw_hash", "request_manifest",
}
_EXPECTED_STATES = {"ANSWERABLE", "NEEDS_REVIEW", "NO_RESULT", "OUT_OF_SCOPE"}
_EXCEL_POLICIES = {
    "not_applicable", "source_series_worksheet", "separate_incompatible_series",
    "alignment_sheet_with_explicit_transform",
}
_MISSING_VALUE_POLICIES = {"blank", "not_applicable"}
_OVERLAP_POLICIES = {"preserve_separately", "review_required", "not_applicable"}
_CASE_KEYS = {
    "schema_version", "case_id", "case_version", "split", "review", "provenance",
    "contrast_group", "question", "expected", "required_evidence", "forbidden_actions",
    "excel_expectation",
}


def _is_text(value, *, maximum=_MAX_TEXT):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _is_utc_timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        from datetime import UTC, datetime

        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(parsed)


def _unique_text_list(value, *, field, errors, maximum_items=50):
    if not isinstance(value, list) or len(value) > maximum_items:
        errors.append(f"{field} must be a list of at most {maximum_items} strings")
        return []
    normalized = set()
    valid = []
    for index, item in enumerate(value):
        if not _is_text(item, maximum=512):
            errors.append(f"{field}[{index}] must be a non-empty string")
            continue
        key = " ".join(item.split()).casefold()
        if key in normalized:
            errors.append(f"{field} contains a duplicate value")
            continue
        normalized.add(key)
        valid.append(item)
    return valid


def _keys(value, expected, field, errors):
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return False
    missing, extra = expected - value.keys(), value.keys() - expected
    if missing:
        errors.append(f"{field} missing keys: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{field} has unsupported keys: {', '.join(sorted(extra))}")
    return not missing and not extra


def _validate_case(case, *, split, where):
    errors = []
    if not _keys(case, _CASE_KEYS, where, errors):
        return errors
    if type(case["schema_version"]) is not int or case["schema_version"] != CASE_SCHEMA_VERSION:
        errors.append(f"{where}.schema_version must be {CASE_SCHEMA_VERSION}")
    if not _is_text(case["case_id"], maximum=128):
        errors.append(f"{where}.case_id must be a non-empty string")
    if type(case["case_version"]) is not int or case["case_version"] < 1:
        errors.append(f"{where}.case_version must be a positive integer")
    if case["split"] != split:
        errors.append(f"{where}.split does not match its case-set file")

    review = case["review"]
    if _keys(review, {"status", "reviewer", "reviewed_at", "privacy_cleared"},
             f"{where}.review", errors):
        if review["status"] != "reviewed":
            errors.append(f"{where}.review.status must be reviewed")
        if not _is_text(review["reviewer"], maximum=128):
            errors.append(f"{where}.review.reviewer must be a non-empty string")
        if not _is_utc_timestamp(review["reviewed_at"]):
            errors.append(f"{where}.review.reviewed_at must be a UTC timestamp")
        if review["privacy_cleared"] is not True:
            errors.append(f"{where}.review.privacy_cleared must be true")

    provenance = case["provenance"]
    if _keys(provenance, {"origin", "feedback_id", "evidence"},
             f"{where}.provenance", errors):
        origin = provenance["origin"]
        if (not isinstance(origin, str)
                or origin not in {"synthetic", "reviewed_feedback", "official_reference"}):
            errors.append(f"{where}.provenance.origin is unsupported")
        feedback_id = provenance["feedback_id"]
        if feedback_id is not None and not _is_text(feedback_id, maximum=128):
            errors.append(f"{where}.provenance.feedback_id must be null or a non-empty string")
        if provenance["origin"] == "reviewed_feedback" and feedback_id is None:
            errors.append(f"{where}.provenance.feedback_id is required for reviewed feedback")
        evidence = provenance["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 20:
            errors.append(f"{where}.provenance.evidence must contain at most 20 references")
        else:
            for index, ref in enumerate(evidence):
                field = f"{where}.provenance.evidence[{index}]"
                if not _keys(ref, {"source_url", "source_version", "captured_at"}, field, errors):
                    continue
                url = ref["source_url"]
                try:
                    parsed = urlsplit(url) if isinstance(url, str) else None
                    safe_url = (parsed is not None and parsed.scheme == "https"
                                and parsed.hostname is not None and parsed.username is None
                                and parsed.password is None and parsed.query == ""
                                and parsed.fragment == "")
                except ValueError:
                    safe_url = False
                if not isinstance(url, str) or not safe_url or len(url) > 512:
                    errors.append(f"{field}.source_url must be a clean HTTPS reference without query data")
                if not _is_text(ref["source_version"], maximum=128):
                    errors.append(f"{field}.source_version must be a non-empty string")
                if not _is_utc_timestamp(ref["captured_at"]):
                    errors.append(f"{field}.captured_at must be a UTC timestamp")
        if provenance["origin"] == "official_reference" and not evidence:
            errors.append(f"{where}.provenance.evidence is required for official references")

    group = case["contrast_group"]
    if group is not None and not _is_text(group, maximum=128):
        errors.append(f"{where}.contrast_group must be null or a non-empty string")

    question = case["question"]
    if _keys(question, {"canonical", "variants"}, f"{where}.question", errors):
        if not _is_text(question["canonical"]):
            errors.append(f"{where}.question.canonical must be a non-empty string")
        variants = _unique_text_list(question["variants"], field=f"{where}.question.variants",
                                     errors=errors, maximum_items=20)
        if isinstance(question["canonical"], str):
            canonical = " ".join(question["canonical"].split()).casefold()
            if any(" ".join(item.split()).casefold() == canonical for item in variants
                   if isinstance(item, str)):
                errors.append(f"{where}.question.variants repeats the canonical question")

    expected = case["expected"]
    if _keys(expected, {"state", "entities"}, f"{where}.expected", errors):
        state = expected["state"]
        if not isinstance(state, str) or state not in _EXPECTED_STATES:
            errors.append(f"{where}.expected.state is unsupported")
        entities = expected["entities"]
        if not isinstance(entities, list) or len(entities) > 50:
            errors.append(f"{where}.expected.entities must be a list of at most 50 entities")
        else:
            for index, entity in enumerate(entities):
                field = f"{where}.expected.entities[{index}]"
                if not _keys(entity, {"source_agency", "dataset_id", "series_id", "field"},
                             field, errors):
                    continue
                for key in ("source_agency", "field"):
                    if not _is_text(entity[key], maximum=256):
                        errors.append(f"{field}.{key} must be a non-empty string")
                for key in ("dataset_id", "series_id"):
                    if entity[key] is not None and not _is_text(entity[key], maximum=256):
                        errors.append(f"{field}.{key} must be null or a non-empty string")
            if state == "ANSWERABLE" and not entities:
                errors.append(f"{where}.expected.entities is required for ANSWERABLE cases")

    required = _unique_text_list(case["required_evidence"], field=f"{where}.required_evidence",
                                 errors=errors, maximum_items=20)
    unsupported = set(required) - _REQUIRED_EVIDENCE
    if unsupported:
        errors.append(f"{where}.required_evidence has unsupported values: "
                      f"{', '.join(sorted(unsupported))}")
    _unique_text_list(case["forbidden_actions"], field=f"{where}.forbidden_actions",
                      errors=errors, maximum_items=50)

    excel = case["excel_expectation"]
    if _keys(excel, {"policy", "missing_value", "overlap_conflict", "interpolate", "forward_fill"},
             f"{where}.excel_expectation", errors):
        if not isinstance(excel["policy"], str) or excel["policy"] not in _EXCEL_POLICIES:
            errors.append(f"{where}.excel_expectation.policy is unsupported")
        if (not isinstance(excel["missing_value"], str)
                or excel["missing_value"] not in _MISSING_VALUE_POLICIES):
            errors.append(f"{where}.excel_expectation.missing_value is unsupported")
        if (not isinstance(excel["overlap_conflict"], str)
                or excel["overlap_conflict"] not in _OVERLAP_POLICIES):
            errors.append(f"{where}.excel_expectation.overlap_conflict is unsupported")
        if type(excel["interpolate"]) is not bool or type(excel["forward_fill"]) is not bool:
            errors.append(f"{where}.excel_expectation interpolation and fill flags must be booleans")
        elif excel["interpolate"] or excel["forward_fill"]:
            errors.append(f"{where}.excel_expectation cannot enable interpolation or forward-fill")
    return errors


def validate_case_sets(directory: str | Path) -> dict:
    """Validate the three fixed split files and report whether they are usable.

    The report distinguishes structurally valid but empty sets from a populated,
    ready-to-evaluate case collection. Similar-case leakage is guarded using
    explicit contrast groups and exact normalized question text; semantic
    similarity still requires curator assignment to a contrast group.
    """
    root = Path(directory)
    errors = []
    summaries = {}
    case_ids = {}
    contrast_splits = {}
    questions = {}
    set_versions = {}
    set_bytes = {}
    for split in SPLITS:
        path = root / f"{split}.json"
        if not path.is_file():
            errors.append(f"missing case-set file: {path.name}")
            continue
        try:
            if path.stat().st_size > _MAX_SET_BYTES:
                raise ValueError("file exceeds size limit")
            raw = path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            errors.append(f"{path.name}: cannot read valid JSON ({exc})")
            continue
        required_keys = {"schema_version", "split", "set_version", "cases"}
        if not isinstance(document, dict) or set(document) != required_keys:
            errors.append(f"{path.name}: expected keys {', '.join(sorted(required_keys))}")
            continue
        if type(document["schema_version"]) is not int or document["schema_version"] != SET_SCHEMA_VERSION:
            errors.append(f"{path.name}: schema_version must be {SET_SCHEMA_VERSION}")
        if document["split"] != split:
            errors.append(f"{path.name}: split must be {split}")
        if type(document["set_version"]) is not int or document["set_version"] < 1:
            errors.append(f"{path.name}: set_version must be a positive integer")
        cases = document["cases"]
        if not isinstance(cases, list) or len(cases) > _MAX_CASES_PER_SET:
            errors.append(f"{path.name}: cases must be a list of at most {_MAX_CASES_PER_SET}")
            continue
        valid_cases = 0
        provenance_counts = {
            "synthetic": 0,
            "reviewed_feedback": 0,
            "official_reference": 0,
        }
        for index, case in enumerate(cases):
            where = f"{path.name}.cases[{index}]"
            case_errors = _validate_case(case, split=split, where=where)
            errors.extend(case_errors)
            if case_errors:
                continue
            valid_cases += 1
            origin = case["provenance"]["origin"]
            provenance_counts[origin] += 1
            case_id = case["case_id"]
            if case_id in case_ids:
                errors.append(f"{where}.case_id duplicates {case_ids[case_id]}")
            else:
                case_ids[case_id] = where
            group = case["contrast_group"]
            if group is not None:
                previous_split = contrast_splits.setdefault(group, split)
                if previous_split != split:
                    errors.append(f"{where}.contrast_group leaks across {previous_split} and {split}")
            texts = [case["question"]["canonical"], *case["question"]["variants"]]
            for text in texts:
                key = " ".join(text.split()).casefold()
                previous_split = questions.setdefault(key, split)
                if previous_split != split:
                    errors.append(f"{where}.question duplicates exact text in {previous_split}")
        summaries[split] = {
            "set_version": document["set_version"],
            "case_count": len(cases),
            "valid_case_count": valid_cases,
            "provenance_counts": provenance_counts,
        }
        set_versions[split] = document["set_version"]
        set_bytes[split] = raw

    lock_path = root / "frozen.json"
    frozen_status = {}
    try:
        if lock_path.stat().st_size > 64 * 1024:
            raise ValueError("file exceeds size limit")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        errors.append(f"frozen.json: cannot read valid lock ({exc})")
        lock = None
    if lock is not None:
        if (not isinstance(lock, dict)
                or set(lock) != {"schema_version", "frozen_splits"}
                or type(lock.get("schema_version")) is not int
                or lock.get("schema_version") != SET_SCHEMA_VERSION
                or not isinstance(lock.get("frozen_splits"), dict)
                or set(lock["frozen_splits"]) != {"validation", "holdout"}):
            errors.append("frozen.json: expected versioned validation and holdout hashes")
        else:
            for split, lock_record in lock["frozen_splits"].items():
                where = f"frozen.json.frozen_splits.{split}"
                if not _keys(lock_record, {"set_version", "sha256"}, where, errors):
                    frozen_status[split] = "INVALID"
                    continue
                expected_hash = lock_record["sha256"]
                if (type(lock_record["set_version"]) is not int
                        or lock_record["set_version"] < 1
                        or not isinstance(expected_hash, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
                    errors.append(f"{where} must contain a positive version and SHA-256")
                    frozen_status[split] = "INVALID"
                    continue
                current_hash = hashlib.sha256(set_bytes.get(split, b"")).hexdigest()
                matches = (set_versions.get(split) == lock_record["set_version"]
                           and split in set_bytes and current_hash == expected_hash)
                frozen_status[split] = "MATCH" if matches else "MISMATCH"
                if not matches:
                    errors.append(f"{where} does not match the frozen case-set version/hash")
    structurally_valid = not errors
    ready = structurally_valid and all(summaries.get(split, {}).get("case_count", 0) > 0
                                       for split in SPLITS)
    feedback_counts = [summaries.get(split, {}).get("provenance_counts", {}).get(
        "reviewed_feedback", 0) for split in SPLITS]
    feedback_coverage = (
        "complete" if ready and all(count > 0 for count in feedback_counts)
        else "partial" if any(count > 0 for count in feedback_counts)
        else "none"
    )
    return {
        "schema_version": SET_SCHEMA_VERSION,
        "status": "READY" if ready else "INVALID" if errors else "VALID_BUT_EMPTY",
        "ready": ready,
        "reviewed_feedback_split_coverage": feedback_coverage,
        "sets": summaries,
        "frozen_splits": frozen_status,
        "errors": errors,
    }
