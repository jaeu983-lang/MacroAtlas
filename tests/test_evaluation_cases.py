"""Iteration 28: immutable, evidence-backed evaluation case inputs."""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from macro_data_platform.evaluation import (
    EvaluationCase,
    audit_split_leakage,
    load_corpus,
    read_cases,
)
from macro_data_platform.workflow_contracts import Candidate

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


def test_synthetic_fixture_evidence_is_candidate_scoped_and_never_official():
    row = read_cases(CORPUS / "cases.jsonl")[0].to_dict()
    fixture_path = ROOT / "tests/fixtures/evaluation/synthetic_fixture_evidence.json"
    evidence = {
        "evidence_id": "synthetic-fixture-test",
        "evidence_kind": "synthetic_fixture",
        "official_uri": None,
        "local_ref": "tests/fixtures/evaluation/synthetic_fixture_evidence.json",
        "retrieved_at": None,
        "sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "claim": "This is synthetic evaluation data and not official source evidence.",
        "purpose": "Unit-test fixture classification only.",
        "candidate_id": "synthetic:test:sample",
    }
    row["required_evidence"].append(evidence)
    assert EvaluationCase.from_dict(row).required_evidence[-1]["candidate_id"] == evidence[
        "candidate_id"
    ]

    missing_candidate = copy.deepcopy(row)
    del missing_candidate["required_evidence"][-1]["candidate_id"]
    with pytest.raises(ValueError):
        EvaluationCase.from_dict(missing_candidate)

    invented_official_source = copy.deepcopy(row)
    invented_official_source["required_evidence"][-1]["official_uri"] = (
        "https://example.org/synthetic-fixture"
    )
    with pytest.raises(ValueError):
        EvaluationCase.from_dict(invented_official_source)


def test_agent_authorship_round_trips_without_becoming_human_observation():
    row = read_cases(CORPUS / "cases.jsonl")[0].to_dict()
    row["authorship"] = {
        "origin": "agent_simulated",
        "run_id": "test-run-01",
        "generator_agents": ["case_generator"],
        "reviewer_agents": ["independent_reviewer"],
        "prompt_sha256": "a" * 64,
        "review_status": "multi_agent_reviewed",
        "human_observed": False,
    }
    restored = EvaluationCase.from_json(EvaluationCase.from_dict(row).to_json())
    assert restored.authorship["origin"] == "agent_simulated"
    assert restored.authorship["human_observed"] is False

    row["authorship"]["human_observed"] = True
    with pytest.raises(ValueError, match="human observed"):
        EvaluationCase.from_dict(row)


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
    corpus = load_corpus(CORPUS)
    assert manifest["intended_case_count"] == 36
    assert manifest["case_count"] == 9
    assert manifest["gate_status"] == "blocked"
    assert any("9 near-match drafts" in message for message in manifest["gate_blockers"])
    assert any("27-case assistant-simulated draft pool" in message
               for message in manifest["gate_blockers"])
    assert not any("split leakage" in message for message in manifest["gate_blockers"])
    assert corpus.split_leakage_issues == ()


def test_split_audit_catches_year_only_query_variants_across_splits():
    source = next(case for case in read_cases(CORPUS / "cases.jsonl")
                  if case.split == "development" and case.case_type == "rankable")
    row = source.to_dict()
    row["case_id"] = "eval-v1-validation-rankable-period-audit"
    row["case_family_id"] = source.case_family_id
    row["split"] = "validation"
    row["request"]["request_id"] = row["case_id"]
    row["request"]["text"] = "GDP for the United States in 2021"
    row["query_variants"] = ["GDP for the United States in 2021"]
    second = EvaluationCase.from_dict(row)

    issues = audit_split_leakage((source, second))
    assert any(issue.kind == "query_template_crosses_splits"
               and set(issue.case_ids) == {source.case_id, second.case_id}
               for issue in issues)
    assert any(issue.kind == "case_family_crosses_splits"
               and set(issue.case_ids) == {source.case_id, second.case_id}
               for issue in issues)


def test_unreviewed_official_near_match_draft_stays_outside_fixed_corpus():
    draft_path = ROOT / "tests/fixtures/evaluation/drafts/worldbank_gdp_price_basis_near_match.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["draft_status"] == "independent_review_pending"
    assert draft["authorship"] == {
        "origin": "assistant_simulated",
        "human_observed": False,
        "independent_review_completed": False,
    }

    case = EvaluationCase.from_dict(draft["case"])
    candidate = Candidate.from_dict(draft["candidate"])
    assert case.case_type == "near_match"
    assert candidate.candidate_id in case.relevant_candidate_ids
    assert case.forbidden_candidate_ids == ("worldbank:2:USA:NY.GDP.MKTP.CD",)
    for evidence in case.required_evidence:
        evidence_path = ROOT / evidence["local_ref"]
        assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == evidence["sha256"]
    for evidence in candidate.evidence:
        evidence_path = ROOT / evidence.original_ref.split(":", 1)[0]
        assert evidence_path.is_file()

    corpus = load_corpus(CORPUS)
    assert len(corpus.cases) == 9
    assert case.case_id not in {item.case_id for item in corpus.cases}
    assert candidate.candidate_id not in {item.candidate_id for item in corpus.candidates}


def test_unreviewed_gdp_total_vs_per_capita_draft_stays_outside_fixed_corpus():
    draft_path = ROOT / "tests/fixtures/evaluation/drafts/worldbank_gdp_total_vs_per_capita_near_match.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["draft_status"] == "independent_review_pending"
    assert draft["authorship"] == {
        "origin": "assistant_simulated",
        "human_observed": False,
        "independent_review_completed": False,
    }

    case = EvaluationCase.from_dict(draft["case"])
    candidate = Candidate.from_dict(draft["candidate"])
    assert case.case_type == "near_match"
    assert "worldbank:2:USA:NY.GDP.MKTP.CD" in case.relevant_candidate_ids
    assert case.forbidden_candidate_ids == ("worldbank:2:USA:NY.GDP.PCAP.CD",)
    assert candidate.candidate_id in case.forbidden_candidate_ids
    assert candidate.support_status == "unsupported"
    for evidence in case.required_evidence:
        evidence_path = ROOT / evidence["local_ref"]
        assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == evidence["sha256"]
    for evidence in candidate.evidence:
        evidence_path = ROOT / evidence.original_ref.split(":", 1)[0]
        assert evidence_path.is_file()

    corpus = load_corpus(CORPUS)
    assert len(corpus.cases) == 9
    assert case.case_id not in {item.case_id for item in corpus.cases}
    assert candidate.candidate_id not in {item.candidate_id for item in corpus.candidates}


@pytest.mark.parametrize(("filename", "split", "relevant_id", "forbidden_id"), [
    (
        "worldbank_cpi_inflation_vs_index_near_match.json",
        "validation",
        "worldbank:2:USA:FP.CPI.TOTL.ZG",
        "worldbank:2:USA:FP.CPI.TOTL",
    ),
    (
        "worldbank_population_total_vs_urban_share_near_match.json",
        "holdout",
        "worldbank:2:USA:SP.POP.TOTL",
        "worldbank:2:USA:SP.URB.TOTL.IN.ZS",
    ),
])
def test_official_metric_near_match_drafts_are_validated_but_not_promoted(
        filename, split, relevant_id, forbidden_id):
    draft_path = ROOT / "tests/fixtures/evaluation/drafts" / filename
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["draft_status"] == "independent_review_pending"
    assert draft["intended_split"] == split
    assert draft["authorship"] == {
        "origin": "assistant_simulated",
        "human_observed": False,
        "independent_review_completed": False,
    }

    case = EvaluationCase.from_dict(draft["case"])
    candidates = tuple(Candidate.from_dict(draft[key])
                       for key in ("candidate", "distractor_candidate"))
    assert case.case_type == "near_match"
    assert case.relevant_candidate_ids == (relevant_id,)
    assert case.forbidden_candidate_ids == (forbidden_id,)
    assert {candidate.candidate_id for candidate in candidates} == {
        relevant_id, forbidden_id,
    }
    assert all(candidate.support_status == "unsupported" for candidate in candidates)
    assert case.expected_fields[relevant_id]["unit"]["state"] == "unknown"
    assert case.expected_fields[relevant_id]["frequency"]["state"] == "unknown"
    for evidence in case.required_evidence:
        evidence_path = ROOT / evidence["local_ref"]
        assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == evidence["sha256"]
    for candidate in candidates:
        for evidence in candidate.evidence:
            evidence_path = ROOT / evidence.original_ref.split(":", 1)[0]
            assert evidence_path.is_file()

    corpus = load_corpus(CORPUS)
    assert len(corpus.cases) == 9
    assert case.case_id not in {item.case_id for item in corpus.cases}
    assert {candidate.candidate_id for candidate in candidates}.isdisjoint(
        {item.candidate_id for item in corpus.candidates}
    )


def test_near_match_draft_batch_has_no_text_template_leakage_across_splits():
    draft_names = (
        "worldbank_gdp_price_basis_near_match.json",
        "worldbank_gdp_total_vs_per_capita_near_match.json",
        "worldbank_cpi_inflation_vs_index_near_match.json",
        "worldbank_population_total_vs_urban_share_near_match.json",
    )
    cases = tuple(
        EvaluationCase.from_dict(json.loads(
            (ROOT / "tests/fixtures/evaluation/drafts" / name).read_text(encoding="utf-8")
        )["case"])
        for name in draft_names
    )
    assert audit_split_leakage(cases) == ()


def test_simulated_draft_corpus_fills_quotas_without_promotion_or_split_leakage():
    corpus = load_corpus(CORPUS)
    draft_manifest_path = ROOT / "tests/fixtures/evaluation/drafts/manifest.json"
    draft_manifest = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
    draft_cases = []
    draft_counts = {}
    fixed_case_ids = {case.case_id for case in corpus.cases}
    draft_paths = sorted(
        path for path in (ROOT / "tests/fixtures/evaluation/drafts").glob("*.json")
        if path.name != "manifest.json"
    )
    expected_file_hashes = {}
    expected_evidence_hashes = {}
    for draft_path in draft_paths:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        if "case" not in draft:
            continue
        assert draft["draft_status"] == "independent_review_pending"
        assert draft["authorship"] == {
            "origin": "assistant_simulated",
            "human_observed": False,
            "independent_review_completed": False,
        }
        case = EvaluationCase.from_dict(draft["case"])
        draft_cases.append(case)
        expected_file_hashes[draft_path.name] = hashlib.sha256(
            draft_path.read_bytes()
        ).hexdigest()
        assert case.case_id not in fixed_case_ids
        draft_counts[(case.split, case.case_type)] = (
            draft_counts.get((case.split, case.case_type), 0) + 1
        )
        for evidence in case.required_evidence:
            evidence_path = ROOT / evidence["local_ref"]
            actual_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            assert actual_hash == evidence["sha256"]
            expected_evidence_hashes[evidence["local_ref"]] = actual_hash
        for key in ("candidate", "distractor_candidate"):
            if key in draft:
                Candidate.from_dict(draft[key])

    assert len(draft_cases) == 27
    assert audit_split_leakage((*corpus.cases, *draft_cases)) == ()
    assert draft_manifest["draft_manifest_version"] == 1
    assert draft_manifest["draft_status"] == "independent_review_pending"
    assert draft_manifest["authorship"] == {
        "origin": "assistant_simulated",
        "human_observed": False,
        "independent_review_completed": False,
    }
    assert draft_manifest["files"] == expected_file_hashes
    assert draft_manifest["evidence_files"] == expected_evidence_hashes
    assert draft_manifest["cross_split_text_audit_issue_count"] == 0
    assert draft_manifest["gate_status"] == "blocked"
    for split in ("development", "validation", "holdout"):
        for case_type in ("rankable", "near_match", "insufficient_evidence", "unrelated"):
            fixed_count = sum(
                case.split == split and case.case_type == case_type
                for case in corpus.cases
            )
            assert fixed_count + draft_counts.get((split, case_type), 0) == 3
    assert corpus.manifest["gate_status"] == "blocked"
