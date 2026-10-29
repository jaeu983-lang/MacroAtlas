"""Promotion records are explicit, immutable, and bound to frozen Gate C evidence."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from macro_data_platform.evaluation import promotion
from macro_data_platform.storage.promotion import PromotionLedger

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = promotion._ARTIFACTS


def _copy_gate_artifacts(destination):
    for relative in ARTIFACTS.values():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)


def _person_fields():
    return {
        "decision_maker_id": "operator-1",
        "reviewer_id": "reviewer-2",
        "decision_maker_is_human": True,
        "reviewer_is_human": True,
    }


def _decision_event(event_id, *, decision="accept", evidence_passed=True):
    return {
        "event_id": event_id,
        "body": {
            "schema_version": 1,
            "record_type": "decision",
            "decision": decision,
            **_person_fields(),
            "reason_code": {
                "accept": "reviewed_and_approved",
                "hold": "risk_unresolved",
                "reject": "candidate_not_desired",
            }[decision],
            "applied_commit": "a" * 40 if decision == "accept" else None,
            "evidence": {
                "gate_c_passed": evidence_passed,
                "candidate_policy_sha256": "c" * 64,
            },
        },
    }


def _rollback_event(event_id, acceptance_event_id, *, rollback_commit="b" * 40):
    return {
        "event_id": event_id,
        "body": {
            "schema_version": 1,
            "record_type": "rollback",
            "acceptance_event_id": acceptance_event_id,
            **_person_fields(),
            "reason_code": "regression_observed",
            "applied_commit": "a" * 40,
            "rollback_commit": rollback_commit,
            "evidence": {"candidate_policy_sha256": "c" * 64},
        },
    }


def test_current_gate_c_evidence_is_hash_bound_and_privacy_minimal():
    manifest = json.loads((REPO_ROOT / ARTIFACTS["manifest"]).read_text(encoding="utf-8"))
    candidate_revision = manifest["repository_revision"]
    revision_available = subprocess.run(
        ["git", "cat-file", "-e", f"{candidate_revision}^{{commit}}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    ).returncode == 0
    evidence = promotion.load_gate_c_evidence(REPO_ROOT, verify_git=revision_available)
    assert evidence["gate_c_status"] == "PASS"
    assert evidence["gate_c_passed"] is True
    assert evidence["metrics"]["confirmation_trace"]["candidate"][
        "unconfirmed_collection_plans_created"
    ] == 0
    assert evidence["metrics"]["timing"]["candidate"]["sample_count"] == 360
    assert "question" not in json.dumps(evidence).lower()
    if revision_available:
        promotion._historical_git_verify(REPO_ROOT, {"body": {"evidence": evidence}})
        altered = evidence | {"gate_c_passed": False}
        with pytest.raises(ValueError, match="snapshot does not match"):
            promotion._historical_git_verify(REPO_ROOT, {"body": {"evidence": altered}})


def test_changed_gate_c_artifact_fails_hash_binding(tmp_path):
    _copy_gate_artifacts(tmp_path)
    manifest_path = tmp_path / ARTIFACTS["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_policy"]["version"] = "altered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="self-hash mismatch"):
        promotion.load_gate_c_evidence(tmp_path, verify_git=False)


def test_failed_gate_c_blocks_acceptance_before_commit_check(tmp_path, monkeypatch):
    ledger = PromotionLedger(tmp_path / "promotion.sqlite")
    evidence = {"gate_c_passed": False}
    monkeypatch.setattr(
        promotion, "load_gate_c_evidence", lambda root, verify_git=True: evidence
    )
    with pytest.raises(ValueError, match="Gate C did not pass"):
        promotion.record_decision(
            ledger,
            tmp_path,
            decision="accept",
            reason_code="reviewed_and_approved",
            applied_commit=None,
            **_person_fields(),
        )
    assert ledger.events() == []


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"reviewer_id": "operator-1"}, "different people"),
        ({"reviewer_is_human": False}, "human roles"),
    ],
)
def test_human_attestation_and_independent_reviewer_are_required(changes, message):
    people = _person_fields() | changes
    with pytest.raises(ValueError, match=message):
        promotion._validate_people(**people)


def test_ai_decision_is_labeled_and_does_not_claim_independent_review():
    fields = promotion._validate_ai_review(
        "gpt-6-codex-primary", "gpt-6-codex-primary", False, False,
        "GPT-6", "user_instruction_2026-10-29", "fixed_local_search_policy",
    )
    assert fields["schema_version"] == 2
    assert fields["decision_maker_type"] == "AI"
    assert fields["reviewer_type"] == "AI"
    assert fields["independent_reviewer"] is False


def test_ai_acceptance_requires_explicit_delegation_and_is_active_only_with_gate_c_pass():
    body = {
        "schema_version": 2,
        "record_type": "decision",
        "decision": "accept",
        **promotion._validate_ai_review(
            "gpt-6-codex-primary", "gpt-6-codex-primary", False, False,
            "GPT-6", "user_instruction_2026-10-29", "fixed_local_search_policy",
        ),
        "reason_code": "reviewed_and_approved",
        "applied_commit": "a" * 40,
        "evidence": {"gate_c_passed": True, "candidate_policy_sha256": "c" * 64},
    }
    event = {"event_id": "ai-accept", "body": body}
    assert promotion._active_acceptance([event]) is event

    invalid = {**body, "evidence": {"gate_c_passed": False}}
    with pytest.raises(ValueError, match="without Gate C PASS"):
        promotion._active_acceptance([{"event_id": "ai-invalid", "body": invalid}])

    invalid = {**body, "independent_reviewer": True}
    with pytest.raises(ValueError, match="non-independent"):
        promotion._active_acceptance([{"event_id": "ai-false-independence", "body": invalid}])

    rollback = {
        "schema_version": 2,
        "record_type": "rollback",
        "acceptance_event_id": "ai-accept",
        **promotion._validate_ai_review(
            "gpt-6-codex-primary", "gpt-6-codex-primary", False, False,
            "GPT-6", "user_instruction_2026-10-29", "fixed_local_search_policy",
        ),
        "reason_code": "regression_observed",
        "applied_commit": "a" * 40,
        "rollback_commit": "b" * 40,
        "evidence": {"candidate_policy_sha256": "c" * 64},
    }
    assert promotion._active_acceptance([
        event, {"event_id": "ai-rollback", "body": rollback},
    ]) is None


def test_ai_decision_cli_records_explicit_authorization_and_scope(monkeypatch, tmp_path, capsys):
    captured = {}
    monkeypatch.setattr(promotion, "_ledger_for_root", lambda _root: object())

    def capture(_ledger, _root, **kwargs):
        captured.update(kwargs)
        return {"event_id": "review-event"}

    monkeypatch.setattr(promotion, "record_decision", capture)
    status = promotion.main([
        "--project-root", str(tmp_path), "decide", "--decision", "accept",
        "--decision-maker-id", "gpt-6-codex-primary",
        "--reviewer-id", "gpt-6-codex-primary", "--reviewer-type", "AI",
        "--reviewer-model", "GPT-6",
        "--authorization-ref", "user_instruction_2026-10-29",
        "--review-scope", "fixed_local_search_policy",
        "--reason-code", "reviewed_and_approved", "--applied-commit", "a" * 40,
    ])
    assert status == 0
    assert captured["decision_maker_is_human"] is False
    assert captured["reviewer_is_human"] is False
    assert captured["reviewer_type"] == "AI"
    assert captured["reviewer_model"] == "GPT-6"
    assert captured["authorization_ref"] == "user_instruction_2026-10-29"
    assert captured["review_scope"] == "fixed_local_search_policy"
    assert json.loads(capsys.readouterr().out)["status"] == "RECORDED"


def test_active_acceptance_requires_a_new_rollback_before_another_decision():
    acceptance = _decision_event("event-accept")
    assert promotion._active_acceptance([acceptance]) is acceptance
    with pytest.raises(ValueError, match="rolled back"):
        promotion._active_acceptance([acceptance, _decision_event("event-hold", decision="hold")])
    rollback = _rollback_event("event-rollback", "event-accept")
    assert promotion._active_acceptance([acceptance, rollback]) is None


def test_acceptance_requires_gate_c_pass_and_rollback_requires_active_acceptance():
    with pytest.raises(ValueError, match="without Gate C PASS"):
        promotion._active_acceptance([_decision_event("event-accept", evidence_passed=False)])
    with pytest.raises(ValueError, match="active acceptance"):
        promotion._active_acceptance([_rollback_event("event-rollback", "missing")])


def test_ledger_is_append_only_and_detects_tampering(tmp_path):
    ledger = PromotionLedger(tmp_path / "promotion_ledger.jsonl")
    first = ledger.append({"record_type": "test", "value": 1})
    second = ledger.append({"record_type": "test", "value": 2})
    assert second["previous_event_hash"] == first["event_hash"]
    assert ledger.verify()["event_count"] == 2

    rows = ledger.path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(rows[0])
    tampered["body"]["value"] = 100
    rows[0] = json.dumps(tampered)
    ledger.path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        ledger.verify()


def test_ledger_cli_help_lists_explicit_decisions(capsys):
    with pytest.raises(SystemExit) as exit_info:
        promotion.main(["--help"])
    assert exit_info.value.code == 0
    assert "rollback" in capsys.readouterr().out
