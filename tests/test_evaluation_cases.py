"""Iteration 28: immutable, evidence-backed evaluation case inputs."""

import copy
import json
import shutil
from pathlib import Path

import pytest

from macro_data_platform.evaluation import EvaluationCase, load_corpus, read_cases

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/evaluation/v1"


def test_initial_manifest_and_case_snapshots_are_deterministic_and_evidence_checked():
    corpus = load_corpus(CORPUS)
    assert len(corpus.cases) == 9
    assert len(corpus.candidates) == 1
    assert corpus.manifest["gate_status"] == "blocked"
    assert corpus.manifest["counts_by_split"] == {
        "development": 3, "validation": 3, "holdout": 3,
    }
    assert corpus.manifest["counts_by_type"] == {
        "rankable": 3, "near_match": 0,
        "insufficient_evidence": 3, "unrelated": 3,
    }
    for case in corpus.cases:
        serialized = case.to_json()
        restored = EvaluationCase.from_json(serialized)
        assert restored.to_json() == serialized
        for evidence in case.required_evidence:
            assert evidence["sha256"]


def test_case_contract_freezes_nested_request_and_expectation_data():
    case = read_cases(CORPUS / "cases.jsonl")[0]
    with pytest.raises(TypeError):
        case.request["text"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        case.expected_fields[next(iter(case.expected_fields))]["unit"]["state"] = "known"


@pytest.mark.parametrize("mutation", [
    lambda row: row.update(case_type="rankable", relevant_candidate_ids=[],
                           expected_state="candidate_found"),
    lambda row: row.update(case_type="near_match", relevant_candidate_ids=["c1"],
                           forbidden_candidate_ids=[], expected_state="review_required"),
    lambda row: row.update(case_type="insufficient_evidence", expected_state="candidate_found"),
    lambda row: row.update(case_type="unrelated", expected_state="review_required"),
    lambda row: row.update(expected_match_status={"worldbank:2:USA:NY.GDP.MKTP.CD": "exact"},
                           expected_fields={"worldbank:2:USA:NY.GDP.MKTP.CD": {
                               "unit": {"state": "unknown"}}}),
])
def test_invalid_cross_field_case_contracts_are_rejected(mutation):
    source = read_cases(CORPUS / "cases.jsonl")[0].to_dict()
    row = copy.deepcopy(source)
    mutation(row)
    with pytest.raises(ValueError):
        EvaluationCase.from_dict(row)


def test_near_match_and_expected_unknown_fields_require_evidence_and_review_status():
    case = next(item for item in read_cases(CORPUS / "cases.jsonl")
                if item.case_type == "rankable")
    row = case.to_dict()
    candidate_id = row["relevant_candidate_ids"][0]
    row.update(case_type="near_match", expected_state="review_required",
               forbidden_candidate_ids=["worldbank:2:USA:OTHER"])
    row["expected_match_status"][candidate_id] = "exact"
    row["expected_match_status"]["worldbank:2:USA:OTHER"] = "related"
    with pytest.raises(ValueError, match="Unknown/conflict"):
        EvaluationCase.from_dict(row)

    row["forbidden_candidate_ids"] = ["worldbank:2:USA:NY.GDP.MKTP.CD"]
    row["relevant_candidate_ids"] = []
    row["case_type"] = "insufficient_evidence"
    row["expected_state"] = "review_required"
    row["expected_match_status"].pop("worldbank:2:USA:OTHER")
    row["expected_match_status"][candidate_id] = "review_required"
    assert EvaluationCase.from_dict(row).case_type == "insufficient_evidence"


def test_evidence_refs_reject_credentials_and_repository_traversal():
    case = read_cases(CORPUS / "cases.jsonl")[0]
    row = case.to_dict()
    for name, value in (("official_uri", "https://example.org/data?api_key=secret"),
                        ("local_ref", "../../outside.json")):
        changed = copy.deepcopy(row)
        changed["required_evidence"][0][name] = value
        with pytest.raises(ValueError):
            EvaluationCase.from_dict(changed)


def test_jsonl_reader_rejects_duplicate_keys_duplicate_ids_and_blank_lines(tmp_path):
    valid_line = (CORPUS / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0]
    duplicate_key = valid_line[:-1] + ',"case_id":"duplicate"}'
    for content in (duplicate_key + "\n", valid_line + "\n" + valid_line + "\n",
                    valid_line + "\n\n"):
        path = tmp_path / "cases.jsonl"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            read_cases(path)


def test_manifest_detects_tampering_without_touching_the_source_corpus(tmp_path):
    copied = tmp_path / "v1"
    shutil.copytree(CORPUS, copied)
    with (copied / "catalog_snapshot.json").open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="manifest hash"):
        load_corpus(copied, repo_root=ROOT)


def test_manifest_reports_partial_gate_without_promoting_it_to_complete():
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intended_case_count"] == 36
    assert manifest["case_count"] == 9
    assert manifest["gate_status"] == "blocked"
    assert any("near-match distractor" in message for message in manifest["gate_blockers"])
