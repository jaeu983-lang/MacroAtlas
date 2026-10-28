"""Record and verify explicit, independently reviewed evaluation policy decisions."""

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.storage.promotion import PromotionLedger

_ARTIFACTS = {
    "qualification": "evaluation/results/gate_c_qualification.json",
    "manifest": "evaluation/results/gate_c_candidate_manifest.json",
    "lock": "evaluation/results/gate_c_holdout_lock.json",
    "result": "evaluation/results/gate_c_holdout_result.json",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REASON_CODES = {
    "accept": frozenset({"reviewed_and_approved"}),
    "hold": frozenset({
        "evidence_follow_up_needed", "policy_scope_unclear", "risk_unresolved",
    }),
    "reject": frozenset({
        "policy_not_approved", "gate_evidence_rejected", "candidate_not_desired",
    }),
    "rollback": frozenset({"regression_observed", "policy_withdrawn", "operational_issue"}),
}
_GROUP_METRICS = (
    "cases", "queries", "top1_hits", "expected_state_matches", "relevant_missing_queries",
    "forbidden_candidate_returns", "forbidden_exact_candidates", "unrelated_with_candidates",
    "unrelated_abstentions", "false_exact_candidates", "status_matches", "fields_matches",
    "fields_unmeasured", "mrr",
)
_TRACE_METRICS = (
    "search_queries", "explicit_confirmation_required", "confirmation_bypasses",
    "selection_or_collection_payloads", "unconfirmed_collection_plan_attempts",
    "unconfirmed_collection_plans_created", "blocked_before_task_creation",
)
_PROHIBITIONS = (
    "auto_select_or_collect_without_explicit_confirmation",
    "collect_a_candidate_that_was_not_explicitly_selected",
    "infer_unknown_unit_frequency_definition_or_availability",
    "overwrite_raw_data_or_existing_exports",
    "merge_incompatible_series_or_fill_missing_values",
)


def _canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in Gate C evidence")
        result[key] = value
    return result


def _read_json(path):
    return _parse_json(path.read_bytes())


def _parse_json(raw):
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Gate C evidence file exceeds the size limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except UnicodeDecodeError as exc:
        raise ValueError("Gate C evidence file is not valid UTF-8") from exc


def _require_hash(value, name):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"invalid {name} hash")
    return value


def _require_revision(value, name):
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        raise ValueError(f"invalid {name} revision")
    return value


def _run_git(root, *arguments, binary=False):
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True,
        text=not binary,
    )
    return result.stdout if binary else result.stdout.strip()


def _is_ancestor(root, ancestor, descendant):
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root, check=False, capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        raise ValueError("unable to verify Git commit ancestry")
    return result.returncode == 0


def _verify_committed_artifacts(root, raw_hashes, candidate_revision):
    head = _run_git(root, "rev-parse", "HEAD")
    _require_revision(head, "evidence commit")
    for name, relative in _ARTIFACTS.items():
        _run_git(root, "ls-files", "--error-unmatch", relative)
        if _run_git(root, "status", "--porcelain", "--", relative):
            raise ValueError("Gate C evidence files must be committed and clean")
        committed = _run_git(root, "show", f"HEAD:{relative}", binary=True)
        if hashlib.sha256(committed).hexdigest() != raw_hashes[name]:
            raise ValueError("working tree Gate C evidence differs from committed evidence")
    _run_git(root, "cat-file", "-e", f"{candidate_revision}^{{commit}}")
    if not _is_ancestor(root, candidate_revision, head):
        raise ValueError("candidate revision is not an ancestor of the evidence commit")
    return head


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"invalid numeric Gate C metric: {name}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"invalid numeric Gate C metric: {name}")
    return value


def _metric_subset(group):
    return {
        key: (None if key == "mrr" and group[key] is None else _finite_number(group[key], key))
        for key in _GROUP_METRICS if key in group
    }


def _comparison_summary(report):
    comparison = report["comparison"]
    summary = {
        "status": report["gate_c_status"],
        "qualification_checks": {
            key: value for key, value in report["qualification"]["checks"].items()
            if isinstance(key, str) and type(value) is bool
        },
        "deltas": {
            case_type: _metric_subset(metrics)
            for case_type, metrics in comparison["deltas"].items()
        },
        "policy_groups": {},
        "confirmation_trace": {},
        "timing": {},
    }
    for policy_name in ("baseline", "candidate"):
        policy = comparison[policy_name]
        summary["policy_groups"][policy_name] = {
            case_type: _metric_subset(metrics)
            for case_type, metrics in policy["groups"].items()
        }
        safety = policy["search_stage_safety"]
        action_counts = {}
        for action in _PROHIBITIONS:
            counts = safety["prohibited_actions"][action]
            action_counts[action] = {
                key: _finite_number(counts[key], f"{action}.{key}")
                for key in ("case_queries", "guarded_before_task_creation", "violations",
                            "unknown_fields_inferred")
            }
        summary["confirmation_trace"][policy_name] = {
            "status": safety["status"],
            **{key: _finite_number(safety[key], key) for key in _TRACE_METRICS},
            "prohibited_actions": action_counts,
        }
        timing = comparison["timing"]["by_policy"][policy_name]
        summary["timing"][policy_name] = {
            key: _finite_number(timing[key], key)
            for key in ("sample_count", "query_count_per_repetition", "p50_ms", "p95_ms",
                        "throughput_queries_per_second")
        }
    candidate_p95 = summary["timing"]["candidate"]["p95_ms"]
    baseline_p95 = summary["timing"]["baseline"]["p95_ms"]
    summary["timing"]["candidate_to_baseline_p95_ratio"] = (
        candidate_p95 / baseline_p95 if baseline_p95 else None
    )
    return summary


def _evidence_snapshot(documents, raw_hashes, evidence_commit):
    qualification = documents["qualification"]
    manifest = documents["manifest"]
    lock = documents["lock"]
    result = documents["result"]
    if not all(isinstance(item, dict) for item in (qualification, manifest, lock, result)):
        raise ValueError("Gate C evidence artifacts must be JSON objects")
    if not isinstance(manifest.get("baseline_policy"), dict) or not isinstance(
        manifest.get("candidate_policy"), dict
    ):
        raise TypeError("candidate manifest policy bindings must be objects")
    if not isinstance(result.get("qualification"), dict) or not isinstance(
        result.get("comparison"), dict
    ):
        raise TypeError("Gate C result qualification/comparison must be objects")
    comparison = result["comparison"]
    if not all(isinstance(comparison.get(key), dict) for key in ("baseline", "candidate")):
        raise ValueError("Gate C policy comparison is invalid")

    manifest_hash = _require_hash(manifest.get("manifest_sha256"), "candidate manifest")
    if _digest({key: value for key, value in manifest.items() if key != "manifest_sha256"}) != manifest_hash:
        raise ValueError("candidate manifest self-hash mismatch")
    qualification_hash = _require_hash(manifest.get("qualification_report_sha256"), "qualification")
    if _digest(qualification) != qualification_hash:
        raise ValueError("qualification report hash mismatch")
    lock_hash = _require_hash(lock.get("lock_sha256"), "holdout lock")
    if _digest({key: value for key, value in lock.items() if key != "lock_sha256"}) != lock_hash:
        raise ValueError("holdout lock self-hash mismatch")
    result_hash = _digest(result)
    if _require_hash(lock.get("result_sha256"), "holdout result") != result_hash:
        raise ValueError("holdout result hash does not match the completed lock")

    candidate_revision = _require_revision(manifest.get("repository_revision"), "candidate")
    case_hash = _require_hash(manifest.get("case_sha256"), "case")
    catalog_hash = _require_hash(manifest.get("catalog_sha256"), "catalog")
    budget_hash = _require_hash(manifest.get("budget_sha256"), "budget")
    source_code_hash = _require_hash(manifest.get("source_code_sha256"), "candidate source")
    baseline_policy_hash = _require_hash(
        manifest.get("baseline_policy", {}).get("sha256"), "baseline policy"
    )
    candidate_policy_hash = _require_hash(
        manifest.get("candidate_policy", {}).get("sha256"), "candidate policy"
    )
    candidate_policy_version = manifest["candidate_policy"].get("version")
    if not isinstance(candidate_policy_version, str) or not candidate_policy_version:
        raise ValueError("candidate policy version is missing")
    corpus_version = manifest.get("corpus_version")
    if not isinstance(corpus_version, str) or not corpus_version:
        raise ValueError("candidate corpus version is missing")
    split_hashes = manifest.get("split_input_sha256")
    if not isinstance(split_hashes, dict):
        raise TypeError("candidate manifest split hashes must be an object")
    for split in ("development", "validation", "holdout"):
        _require_hash(split_hashes.get(split), f"{split} split")

    if lock.get("state") != "COMPLETED":
        raise ValueError("Gate C holdout is not completed")
    if manifest.get("status") != "FROZEN":
        raise ValueError("candidate manifest is not frozen")
    development = qualification.get("development")
    validation = qualification.get("validation")
    if not isinstance(development, dict) or not isinstance(validation, dict):
        raise TypeError("development/validation qualification evidence must be objects")
    qualification_checks = development.get("qualification")
    validation_checks = validation.get("qualification")
    if not isinstance(qualification_checks, dict) or not isinstance(validation_checks, dict):
        raise TypeError("development/validation qualification checks must be objects")
    target_coverage = qualification.get("target_improvement_coverage")
    if not isinstance(target_coverage, dict):
        raise TypeError("target improvement coverage evidence must be an object")
    for key in ("development_pass", "validation_pass", "target_improvement_coverage_pass",
                "ai_simulated_development_pass"):
        if type(manifest.get(key)) is not bool:
            raise ValueError("candidate manifest qualification flags must be booleans")
    qualification_bindings = (
        (qualification.get("case_sha256"), case_hash),
        (qualification.get("catalog_sha256"), catalog_hash),
        (qualification.get("budget_sha256"), budget_hash),
        (qualification.get("baseline_policy_sha256"), baseline_policy_hash),
        (qualification.get("candidate_policy_sha256"), candidate_policy_hash),
        (manifest.get("development_pass"), qualification_checks.get("status") == "PASS"),
        (manifest.get("validation_pass"), validation_checks.get("status") == "PASS"),
    )
    if any(left != right for left, right in qualification_bindings):
        raise ValueError("qualification evidence does not match the frozen manifest")
    comparison = result["comparison"]
    cross_bindings = (
        (lock.get("candidate_manifest_sha256"), manifest_hash),
        (lock.get("case_sha256"), case_hash),
        (lock.get("catalog_sha256"), catalog_hash),
        (lock.get("holdout_input_sha256"), split_hashes["holdout"]),
        (result.get("candidate_manifest_sha256"), manifest_hash),
        (result.get("case_sha256"), case_hash),
        (result.get("catalog_sha256"), catalog_hash),
        (result.get("holdout_input_sha256"), split_hashes["holdout"]),
        (result.get("budget_sha256"), budget_hash),
        (result.get("gate_c_status"), lock.get("gate_c_status")),
        (comparison.get("input_sha256"), split_hashes["holdout"]),
        (comparison.get("case_sha256"), case_hash),
        (comparison.get("catalog_sha256"), catalog_hash),
        (comparison.get("baseline", {}).get("policy_sha256"), baseline_policy_hash),
        (comparison.get("candidate", {}).get("policy_sha256"), candidate_policy_hash),
    )
    if any(left != right for left, right in cross_bindings):
        raise ValueError("Gate C artifacts do not bind to the same candidate and split")
    if result.get("promotion_status") != "NOT_PROMOTED":
        raise ValueError("Gate C result must remain an immutable unpromoted evaluation")

    qualification_status = result["qualification"].get("status")
    gate_c_passed = result.get("gate_c_passed") is True and result.get("gate_c_status") == "PASS"
    if result.get("gate_c_status") not in {"PASS", "FAIL"}:
        raise ValueError("Gate C status is invalid")
    if result.get("gate_c_passed") is not (result.get("gate_c_status") == "PASS"):
        raise ValueError("Gate C status and pass flag conflict")
    checks = result["qualification"].get("checks")
    if not isinstance(checks, dict) or not checks or any(type(value) is not bool for value in checks.values()):
        raise ValueError("Gate C qualification checks are missing or invalid")
    if gate_c_passed and (qualification_status != "PASS" or not all(checks.values())):
        raise ValueError("Gate C PASS lacks passing qualification checks")
    if gate_c_passed and (
        qualification.get("status") != "READY_FOR_ONE_TIME_HOLDOUT"
        or target_coverage.get("status") != "PASS"
        or type(manifest.get("development_pass")) is not bool
        or manifest.get("development_pass") is not True
        or type(manifest.get("validation_pass")) is not bool
        or manifest.get("validation_pass") is not True
        or type(manifest.get("target_improvement_coverage_pass")) is not bool
        or manifest.get("target_improvement_coverage_pass") is not True
        or type(manifest.get("ai_simulated_development_pass")) is not bool
        or manifest.get("ai_simulated_development_pass") is not True
        or comparison.get("split") != "holdout"
        or comparison.get("status") != "SPLIT_COMPARISON_ONLY"
    ):
        raise ValueError("Gate C PASS lacks qualified frozen development, validation, or holdout")

    evidence = {
        "schema_version": 1,
        "gate_c_status": result.get("gate_c_status"),
        "gate_c_passed": gate_c_passed,
        "candidate_revision": candidate_revision,
        "source_code_sha256": source_code_hash,
        "candidate_manifest_sha256": manifest_hash,
        "qualification_report_sha256": qualification_hash,
        "holdout_lock_sha256": lock_hash,
        "holdout_result_sha256": result_hash,
        "case_sha256": case_hash,
        "development_split_sha256": split_hashes["development"],
        "validation_split_sha256": split_hashes["validation"],
        "holdout_split_sha256": split_hashes["holdout"],
        "catalog_sha256": catalog_hash,
        "budget_sha256": budget_hash,
        "baseline_policy_sha256": baseline_policy_hash,
        "candidate_policy_sha256": candidate_policy_hash,
        "candidate_policy_version": candidate_policy_version,
        "corpus_version": corpus_version,
        "artifact_file_sha256": raw_hashes,
        "metrics": _comparison_summary(result),
        "evidence_commit": evidence_commit,
    }
    return evidence


def load_gate_c_evidence(root: Path, *, verify_git=True):
    """Validate the frozen C evidence and return a privacy-minimal evidence snapshot."""
    root = Path(root).resolve()
    documents, raw_hashes = {}, {}
    for name, relative in _ARTIFACTS.items():
        raw = (root / relative).read_bytes()
        documents[name] = _parse_json(raw)
        raw_hashes[name] = hashlib.sha256(raw).hexdigest()
    candidate_revision = _require_revision(
        documents["manifest"].get("repository_revision"), "candidate"
    )
    evidence_commit = (
        _verify_committed_artifacts(root, raw_hashes, candidate_revision)
        if verify_git else None
    )
    return _evidence_snapshot(documents, raw_hashes, evidence_commit)


def _identifier(value, name):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _validate_people(decision_maker_id, reviewer_id, decision_maker_is_human,
                     reviewer_is_human):
    _identifier(decision_maker_id, "decision maker ID")
    _identifier(reviewer_id, "reviewer ID")
    if decision_maker_id == reviewer_id:
        raise ValueError("decision maker and independent reviewer must be different people")
    if decision_maker_is_human is not True or reviewer_is_human is not True:
        raise ValueError("both people must explicitly attest to their human roles")


def _resolve_commit(root, value, label):
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        raise ValueError(f"{label} must be a full Git commit SHA")
    resolved = _run_git(root, "rev-parse", f"{value}^{{commit}}")
    if resolved != value:
        raise ValueError(f"{label} must be the canonical full Git commit SHA")
    return value


def _require_ancestor(root, ancestor, descendant, label):
    if not _is_ancestor(root, ancestor, descendant):
        raise ValueError(f"{label} must descend from the required commit")


def _active_acceptance(events):
    active = None
    for event in events:
        body = event["body"]
        if body.get("schema_version") != 1:
            raise ValueError("unsupported promotion ledger event version")
        record_type = body.get("record_type")
        if record_type == "decision":
            decision = body.get("decision")
            if decision not in {"accept", "hold", "reject"}:
                raise ValueError("unknown decision in promotion ledger")
            _validate_people(
                body.get("decision_maker_id"), body.get("reviewer_id"),
                body.get("decision_maker_is_human"), body.get("reviewer_is_human"),
            )
            if body.get("reason_code") not in _REASON_CODES[decision]:
                raise ValueError("invalid decision reason in promotion ledger")
            if active is not None:
                raise ValueError("an active acceptance must be rolled back before another decision")
            if decision == "accept":
                evidence = body.get("evidence")
                if not isinstance(evidence, dict):
                    raise TypeError("acceptance evidence must be an object")
                if evidence.get("gate_c_passed") is not True:
                    raise ValueError("promotion ledger contains an acceptance without Gate C PASS")
                if not body.get("applied_commit"):
                    raise ValueError("promotion ledger acceptance has no applied commit")
                _require_revision(body["applied_commit"], "applied commit")
                active = event
            elif body.get("applied_commit") is not None:
                raise ValueError("hold/reject decisions cannot contain an applied commit")
        elif record_type == "rollback":
            _validate_people(
                body.get("decision_maker_id"), body.get("reviewer_id"),
                body.get("decision_maker_is_human"), body.get("reviewer_is_human"),
            )
            if body.get("reason_code") not in _REASON_CODES["rollback"]:
                raise ValueError("invalid rollback reason in promotion ledger")
            if active is None or active["event_id"] != body.get("acceptance_event_id"):
                raise ValueError("rollback does not reference the active acceptance")
            if body.get("applied_commit") != active["body"].get("applied_commit"):
                raise ValueError("rollback applied commit does not match the acceptance")
            rollback_evidence = body.get("evidence")
            accepted_evidence = active["body"].get("evidence")
            if not isinstance(rollback_evidence, dict) or not isinstance(accepted_evidence, dict):
                raise TypeError("acceptance and rollback evidence must be objects")
            if rollback_evidence.get("candidate_policy_sha256") != accepted_evidence.get(
                "candidate_policy_sha256"
            ):
                raise ValueError("rollback evidence does not identify the accepted policy")
            if not body.get("rollback_commit") or body["rollback_commit"] == body["applied_commit"]:
                raise ValueError("rollback must use a new, distinct commit")
            _require_revision(body["applied_commit"], "applied commit")
            _require_revision(body["rollback_commit"], "rollback commit")
            active = None
        else:
            raise ValueError("unknown promotion ledger record type")
    return active


def _historical_git_verify(root, event):
    body = event["body"]
    evidence = body.get("evidence")
    if not isinstance(evidence, dict):
        raise TypeError("promotion ledger event evidence must be an object")
    evidence_commit = _resolve_commit(root, evidence.get("evidence_commit"), "evidence commit")
    candidate_revision = _resolve_commit(root, evidence.get("candidate_revision"), "candidate revision")
    _require_ancestor(root, candidate_revision, evidence_commit, "evidence commit")
    raw_hashes = evidence.get("artifact_file_sha256")
    if not isinstance(raw_hashes, dict) or set(raw_hashes) != set(_ARTIFACTS):
        raise ValueError("promotion ledger event has incomplete artifact hashes")
    documents, verified_raw_hashes = {}, {}
    for name, relative in _ARTIFACTS.items():
        expected = _require_hash(raw_hashes[name], f"{name} artifact")
        actual = _run_git(root, "show", f"{evidence_commit}:{relative}", binary=True)
        if hashlib.sha256(actual).hexdigest() != expected:
            raise ValueError("historical Gate C artifact hash does not match its evidence commit")
        if len(actual) > 16 * 1024 * 1024:
            raise ValueError("historical Gate C evidence file exceeds the size limit")
        documents[name] = _parse_json(actual)
        verified_raw_hashes[name] = expected
    rebuilt_evidence = _evidence_snapshot(documents, verified_raw_hashes, evidence_commit)
    if _canonical_bytes(rebuilt_evidence) != _canonical_bytes(evidence):
        raise ValueError("promotion ledger evidence snapshot does not match its Git evidence")
    if body.get("record_type") == "decision" and body.get("decision") == "accept":
        applied_commit = _resolve_commit(root, body.get("applied_commit"), "applied commit")
        _require_ancestor(root, candidate_revision, applied_commit, "applied commit")
        _require_ancestor(root, applied_commit, evidence_commit, "evidence commit")
    elif body.get("record_type") == "rollback":
        applied_commit = _resolve_commit(root, body.get("applied_commit"), "applied commit")
        rollback_commit = _resolve_commit(root, body.get("rollback_commit"), "rollback commit")
        _require_ancestor(root, applied_commit, rollback_commit, "rollback commit")
        _require_ancestor(root, rollback_commit, evidence_commit, "evidence commit")


def inspect_ledger(ledger):
    events = ledger.events()
    active = _active_acceptance(events)
    return {
        **ledger.verify(),
        "active_acceptance_event_id": active["event_id"] if active else None,
        "latest_decision": next(
            (event["body"].get("decision") for event in reversed(events)
             if event["body"].get("record_type") == "decision"),
            None,
        ),
    }


def verify_ledger(ledger, root):
    events = ledger.events()
    active = _active_acceptance(events)
    for event in events:
        _historical_git_verify(root, event)
    ledger_path = ledger.path.relative_to(Path(root).resolve()).as_posix()
    _run_git(root, "ls-files", "--error-unmatch", ledger_path)
    working_tree_status = _run_git(root, "status", "--porcelain", "--", ledger_path)
    committed_ledger = _run_git(root, "show", f"HEAD:{ledger_path}", binary=True)
    ledger_is_committed = not working_tree_status and committed_ledger == ledger.path.read_bytes()
    return {
        **ledger.verify(),
        "status": "PASS" if ledger_is_committed else "UNCOMMITTED",
        "active_acceptance_event_id": active["event_id"] if active else None,
        "historical_evidence": "PASS",
        "working_tree_status": "CLEAN" if ledger_is_committed else "UNCOMMITTED_LEDGER_ENTRY",
    }


def _require_committed_clean_ledger(ledger, root):
    ledger_path = ledger.path.relative_to(Path(root).resolve()).as_posix()
    _run_git(root, "ls-files", "--error-unmatch", ledger_path)
    if _run_git(root, "status", "--porcelain", "--", ledger_path):
        raise ValueError("commit the previous promotion ledger entry before adding another")
    committed_ledger = _run_git(root, "show", f"HEAD:{ledger_path}", binary=True)
    if committed_ledger != ledger.path.read_bytes():
        raise ValueError("working tree promotion ledger differs from the committed ledger")


def record_decision(ledger, root, *, decision, decision_maker_id, reviewer_id,
                    decision_maker_is_human, reviewer_is_human, reason_code,
                    applied_commit=None):
    if decision not in _REASON_CODES or decision == "rollback":
        raise ValueError("decision must be accept, hold, or reject")
    _validate_people(
        decision_maker_id, reviewer_id, decision_maker_is_human, reviewer_is_human
    )
    if reason_code not in _REASON_CODES[decision]:
        raise ValueError("invalid reason code for decision")
    events = ledger.events()
    if _active_acceptance(events) is not None:
        raise ValueError("active acceptance must be rolled back before another decision")
    root = Path(root).resolve()
    evidence = load_gate_c_evidence(root, verify_git=True)
    if decision == "accept" and not evidence["gate_c_passed"]:
        raise ValueError("Gate C did not pass; candidate promotion is blocked")
    _require_committed_clean_ledger(ledger, root)
    if decision == "accept":
        if applied_commit is None:
            raise ValueError("accept requires the applied policy commit")
        applied_commit = _resolve_commit(root, applied_commit, "applied commit")
        _require_ancestor(
            root, evidence["candidate_revision"], applied_commit, "applied commit"
        )
        _require_ancestor(
            root, applied_commit, evidence["evidence_commit"], "evidence commit"
        )
    elif applied_commit is not None:
        raise ValueError("only accept decisions may include an applied commit")
    return ledger.append({
        "schema_version": 1,
        "record_type": "decision",
        "decision": decision,
        "decision_maker_id": decision_maker_id,
        "decision_maker_is_human": True,
        "reviewer_id": reviewer_id,
        "reviewer_is_human": True,
        "reason_code": reason_code,
        "applied_commit": applied_commit,
        "evidence": evidence,
    })


def record_rollback(ledger, root, *, acceptance_event_id, decision_maker_id, reviewer_id,
                    decision_maker_is_human, reviewer_is_human, reason_code, rollback_commit):
    _validate_people(
        decision_maker_id, reviewer_id, decision_maker_is_human, reviewer_is_human
    )
    if reason_code not in _REASON_CODES["rollback"]:
        raise ValueError("invalid rollback reason code")
    events = ledger.events()
    active = _active_acceptance(events)
    if active is None or active["event_id"] != acceptance_event_id:
        raise ValueError("rollback must reference the current active acceptance event")
    root = Path(root).resolve()
    _require_committed_clean_ledger(ledger, root)
    rollback_commit = _resolve_commit(root, rollback_commit, "rollback commit")
    applied_commit = active["body"]["applied_commit"]
    if rollback_commit == applied_commit:
        raise ValueError("rollback must be a new commit")
    _require_ancestor(root, applied_commit, rollback_commit, "rollback commit")
    evidence = load_gate_c_evidence(root, verify_git=True)
    if evidence["candidate_policy_sha256"] != active["body"]["evidence"][
        "candidate_policy_sha256"
    ]:
        raise ValueError("current Gate C evidence does not bind to the accepted policy")
    _require_ancestor(root, rollback_commit, evidence["evidence_commit"], "evidence commit")
    return ledger.append({
        "schema_version": 1,
        "record_type": "rollback",
        "acceptance_event_id": acceptance_event_id,
        "decision_maker_id": decision_maker_id,
        "decision_maker_is_human": True,
        "reviewer_id": reviewer_id,
        "reviewer_is_human": True,
        "reason_code": reason_code,
        "applied_commit": applied_commit,
        "rollback_commit": rollback_commit,
        "evidence": evidence,
    })


def _ledger_for_root(root):
    root = Path(root).resolve()
    settings = Settings(root)
    relative = Path("evaluation/results/promotion_ledger.jsonl")
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("promotion ledger path cannot contain symlinks")
    return PromotionLedger(settings._inside(relative.as_posix()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="show append-only decision history and active policy")
    commands.add_parser("verify", help="verify ledger chain and bound Git evidence")
    decide = commands.add_parser("decide", help="record an explicit accept, hold, or reject")
    decide.add_argument("--decision", required=True, choices=("accept", "hold", "reject"))
    decide.add_argument("--decision-maker-id", required=True)
    decide.add_argument("--reviewer-id", required=True)
    decide.add_argument("--decision-maker-is-human", action="store_true", required=True)
    decide.add_argument("--reviewer-is-human", action="store_true", required=True)
    decide.add_argument("--reason-code", required=True, choices=sorted({
        reason for decision in ("accept", "hold", "reject") for reason in _REASON_CODES[decision]
    }))
    decide.add_argument("--applied-commit")
    rollback = commands.add_parser("rollback", help="record rollback as a new Git commit")
    rollback.add_argument("--acceptance-event-id", required=True)
    rollback.add_argument("--decision-maker-id", required=True)
    rollback.add_argument("--reviewer-id", required=True)
    rollback.add_argument("--decision-maker-is-human", action="store_true", required=True)
    rollback.add_argument("--reviewer-is-human", action="store_true", required=True)
    rollback.add_argument("--reason-code", required=True, choices=sorted(_REASON_CODES["rollback"]))
    rollback.add_argument("--rollback-commit", required=True)
    args = parser.parse_args(argv)

    try:
        root = args.project_root.resolve()
        ledger = _ledger_for_root(root)
        if args.command == "inspect":
            result = inspect_ledger(ledger)
        elif args.command == "verify":
            result = verify_ledger(ledger, root)
        elif args.command == "decide":
            event = record_decision(
                ledger,
                root,
                decision=args.decision,
                decision_maker_id=args.decision_maker_id,
                reviewer_id=args.reviewer_id,
                decision_maker_is_human=args.decision_maker_is_human,
                reviewer_is_human=args.reviewer_is_human,
                reason_code=args.reason_code,
                applied_commit=args.applied_commit,
            )
            result = {"status": "RECORDED", **event}
        else:
            event = record_rollback(
                ledger,
                root,
                acceptance_event_id=args.acceptance_event_id,
                decision_maker_id=args.decision_maker_id,
                reviewer_id=args.reviewer_id,
                decision_maker_is_human=args.decision_maker_is_human,
                reviewer_is_human=args.reviewer_is_human,
                reason_code=args.reason_code,
                rollback_commit=args.rollback_commit,
            )
            result = {"status": "RECORDED", **event}
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
