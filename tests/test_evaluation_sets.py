import hashlib
import json

from macro_data_platform.evaluation.case_sets import validate_case_sets
from macro_data_platform.evaluation.cases import validate_case_sets as compatible_validator_import
from macro_data_platform.evaluation.cli import main


def _case(split, case_id=None, **overrides):
    case = {
        "schema_version": 1,
        "case_id": case_id or f"case-{split}",
        "case_version": 1,
        "split": split,
        "review": {
            "status": "reviewed", "reviewer": "reviewer-1",
            "reviewed_at": "2026-10-27T00:00:00+00:00", "privacy_cleared": True,
        },
        "provenance": {"origin": "synthetic", "feedback_id": None, "evidence": []},
        "contrast_group": None,
        "question": {"canonical": f"question for {split}", "variants": []},
        "expected": {
            "state": "ANSWERABLE",
            "entities": [{"source_agency": "WB", "dataset_id": "WDI",
                          "series_id": "NY.GDP.MKTP.CD", "field": "GDP"}],
        },
        "required_evidence": ["source_url", "source_identifier", "unit", "frequency"],
        "forbidden_actions": ["guess_identifier", "interpolate_missing_values", "forward_fill"],
        "excel_expectation": {
            "policy": "source_series_worksheet", "missing_value": "blank",
            "overlap_conflict": "review_required", "interpolate": False,
            "forward_fill": False,
        },
    }
    case.update(overrides)
    return case


def _write_sets(directory, cases=None):
    directory.mkdir(parents=True, exist_ok=True)
    cases = cases or {}
    for split in ("development", "validation", "holdout"):
        (directory / f"{split}.json").write_text(json.dumps({
            "schema_version": 1, "split": split, "set_version": 1,
            "cases": cases.get(split, []),
        }), encoding="utf-8")
    frozen = {}
    for split in ("validation", "holdout"):
        raw = (directory / f"{split}.json").read_bytes()
        frozen[split] = {"set_version": 1, "sha256": hashlib.sha256(raw).hexdigest()}
    (directory / "frozen.json").write_text(json.dumps({
        "schema_version": 1, "frozen_splits": frozen,
    }), encoding="utf-8")


def test_original_validator_import_path_remains_compatible():
    assert compatible_validator_import is validate_case_sets


def test_empty_versioned_sets_are_valid_but_not_ready(tmp_path):
    _write_sets(tmp_path)

    report = validate_case_sets(tmp_path)

    assert report["status"] == "VALID_BUT_EMPTY"
    assert not report["ready"]
    assert report["reviewed_feedback_split_coverage"] == "none"
    assert all(value["case_count"] == 0 for value in report["sets"].values())
    assert report["errors"] == []


def test_three_populated_sets_are_ready(tmp_path):
    _write_sets(tmp_path, {
        split: [_case(split)] for split in ("development", "validation", "holdout")
    })

    report = validate_case_sets(tmp_path)

    assert report["status"] == "READY"
    assert report["ready"]
    assert report["reviewed_feedback_split_coverage"] == "none"
    assert report["sets"]["development"]["provenance_counts"] == {
        "synthetic": 1, "reviewed_feedback": 0, "official_reference": 0,
    }
    assert report["errors"] == []


def test_reviewed_feedback_coverage_requires_each_split(tmp_path):
    cases = {}
    for split in ("development", "validation", "holdout"):
        case = _case(split)
        case["provenance"] = {
            "origin": "reviewed_feedback", "feedback_id": f"feedback-{split}",
            "evidence": [],
        }
        cases[split] = [case]
    _write_sets(tmp_path, cases)

    report = validate_case_sets(tmp_path)

    assert report["status"] == "READY"
    assert report["reviewed_feedback_split_coverage"] == "complete"
    assert all(summary["provenance_counts"]["reviewed_feedback"] == 1
               for summary in report["sets"].values())


def test_contrast_group_and_exact_question_cannot_leak_between_splits(tmp_path):
    dev = _case("development", contrast_group="holdings-vs-transactions")
    validation = _case("validation", case_id="case-validation",
                       contrast_group="holdings-vs-transactions")
    validation["question"]["canonical"] = "another question"
    _write_sets(tmp_path, {"development": [dev], "validation": [validation]})

    report = validate_case_sets(tmp_path)

    assert any("contrast_group leaks across development and validation" in error
               for error in report["errors"])

    validation["contrast_group"] = None
    validation["question"]["canonical"] = "  QUESTION   FOR DEVELOPMENT "
    _write_sets(tmp_path, {"development": [dev], "validation": [validation]})
    report = validate_case_sets(tmp_path)
    assert any("question duplicates exact text in development" in error
               for error in report["errors"])


def test_case_requires_review_privacy_and_safe_excel_policy(tmp_path):
    case = _case("development")
    case["review"]["privacy_cleared"] = False
    case["excel_expectation"]["forward_fill"] = True
    _write_sets(tmp_path, {"development": [case]})

    report = validate_case_sets(tmp_path)

    assert any("privacy_cleared must be true" in error for error in report["errors"])
    assert any("cannot enable interpolation or forward-fill" in error
               for error in report["errors"])


def test_reviewed_feedback_cases_require_feedback_reference(tmp_path):
    case = _case("development")
    case["provenance"] = {"origin": "reviewed_feedback", "feedback_id": None,
                          "evidence": []}
    _write_sets(tmp_path, {"development": [case]})

    report = validate_case_sets(tmp_path)

    assert any("feedback_id is required for reviewed feedback" in error
               for error in report["errors"])


def test_malformed_enum_types_are_reported_instead_of_raising(tmp_path):
    case = _case("development")
    case["provenance"]["origin"] = []
    case["expected"]["state"] = {}
    case["excel_expectation"]["policy"] = []
    case["required_evidence"] = [{}]
    case["forbidden_actions"] = [[]]
    _write_sets(tmp_path, {"development": [case]})

    report = validate_case_sets(tmp_path)

    assert report["status"] == "INVALID"
    assert any("provenance.origin is unsupported" in error for error in report["errors"])
    assert any("expected.state is unsupported" in error for error in report["errors"])
    assert any("excel_expectation.policy is unsupported" in error for error in report["errors"])
    assert any("required_evidence[0]" in error for error in report["errors"])
    assert any("forbidden_actions[0]" in error for error in report["errors"])


def test_missing_split_is_invalid_and_cli_returns_nonzero(tmp_path, capsys):
    _write_sets(tmp_path)
    (tmp_path / "holdout.json").unlink()

    assert main(["validate", "--sets-dir", str(tmp_path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "INVALID"
    assert report["ready"] is False
    assert any("missing case-set file: holdout.json" in error for error in report["errors"])


def test_editing_frozen_holdout_requires_lock_hash_update(tmp_path):
    _write_sets(tmp_path)
    holdout = tmp_path / "holdout.json"
    document = json.loads(holdout.read_text(encoding="utf-8"))
    document["cases"].append(_case("holdout"))
    holdout.write_text(json.dumps(document), encoding="utf-8")

    report = validate_case_sets(tmp_path)

    assert report["status"] == "INVALID"
    assert report["frozen_splits"]["holdout"] == "MISMATCH"
    assert any("frozen case-set version/hash" in error for error in report["errors"])
