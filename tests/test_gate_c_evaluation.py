import json
import subprocess
from pathlib import Path

import pytest

from macro_data_platform.evaluation import gate_c


def test_qualification_measures_dev_validation_actions_latency_and_synthetic_cases(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(gate_c, "_QUALIFICATION_REL", tmp_path / "qualification.json")
    monkeypatch.setattr(gate_c, "_MANIFEST_REL", tmp_path / "candidate.json")
    monkeypatch.setattr(gate_c, "_LOCK_REL", tmp_path / "holdout-lock.json")

    report = gate_c.qualify(Path.cwd())

    assert report["status"] == "READY_FOR_ONE_TIME_HOLDOUT"
    assert report["gate_c_passed"] is False
    assert report["promotion_status"] == "NOT_PROMOTED"
    assert report["development"]["status"] == "PASS"
    assert report["validation"]["status"] == "PASS"
    assert report["target_improvement_coverage"]["status"] == "PASS"
    assert set(report["target_improvement_coverage"]["improved_types"]) == {
        "rankable",
        "near_match",
        "unrelated",
    }
    assert report["development"]["candidate_action_trace"]["blocked_before_task_creation"] == 34
    assert report["validation"]["candidate_action_trace"]["blocked_before_task_creation"] == 36
    assert report["development"]["candidate_action_trace"]["prohibited_actions"][
        "infer_unknown_unit_frequency_definition_or_availability"
    ]["unknown_fields_disclosed"] == 4
    assert report["ai_simulated_development"] == {
        "baseline_matches": 0,
        "prior_candidate_v2_matches": 2,
        "candidate_matches": 4,
        "case_count": 4,
    }
    manifest = json.loads((tmp_path / "candidate.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FROZEN"
    assert manifest["development_pass"] is True
    assert manifest["validation_pass"] is True
    assert manifest["target_improvement_coverage_pass"] is True


def test_holdout_runner_requires_committed_candidate_and_lock_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Gate C test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "gate-c-test@example.invalid"],
                   cwd=tmp_path, check=True)
    paths = ("evaluation/qualification.json", "evaluation/candidate.json", "evaluation/lock.json")
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", *paths], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "freeze candidate and lock"],
                   cwd=tmp_path, check=True)

    gate_c._require_committed(tmp_path, paths)

    (tmp_path / paths[1]).write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be committed and clean"):
        gate_c._require_committed(tmp_path, paths)
