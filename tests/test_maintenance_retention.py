"""Tests for conservative cleanup of old, successful routine reports."""
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

_RETENTION_PATH = Path(__file__).parents[1] / "scripts/maintenance_retention.py"
_RETENTION_SPEC = importlib.util.spec_from_file_location("maintenance_retention", _RETENTION_PATH)
retention = importlib.util.module_from_spec(_RETENTION_SPEC)
_RETENTION_SPEC.loader.exec_module(retention)
prune_reports = retention.prune_reports


def _initialize_repository(root):
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
    )
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=root, check=True)


def _write_report(run_dir, report):
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")


def test_prunes_only_old_noop_updater_report_after_cleanup_and_branch_are_gone(tmp_path):
    _initialize_repository(tmp_path)
    run_id = "20260101T000000Z-aaaaaaaa"
    run_dir = tmp_path / "reports" / f"improvement_{run_id}"
    report = {
        "run_id": run_id,
        "status": "NO_ACTIONABLE_CHANGE",
        "cleanup": "PASSED",
        "branch": f"agent/improvement-{run_id}",
        "worktree": str(run_dir / "checkout"),
        "finished_at": "2026-01-01T00:00:00+00:00",
    }
    _write_report(run_dir, report)
    (run_dir / "codex.log").write_text("no changes\n", encoding="utf-8")

    summary = prune_reports(
        tmp_path,
        report_type="improvement",
        now=datetime(2026, 10, 27, tzinfo=UTC),
    )

    assert summary["removed"] == [run_dir.name]
    assert not run_dir.exists()


def test_preserves_candidate_failed_cleanup_branch_and_unexpected_artifact_reports(tmp_path):
    _initialize_repository(tmp_path)
    now = datetime(2026, 10, 27, tzinfo=UTC)
    states = [
        ("20260101T000000Z-aaaaaaaa", "PULL_REQUEST_CREATED", "PASSED", False),
        ("20260102T000000Z-bbbbbbbb", "NO_ACTIONABLE_CHANGE", "FAILED", False),
        ("20260103T000000Z-cccccccc", "NO_ACTIONABLE_CHANGE", "PASSED", False),
        ("20260104T000000Z-dddddddd", "NO_ACTIONABLE_CHANGE", "PASSED", True),
        ("20260105T000000Z-eeeeeeee", "NO_ACTIONABLE_CHANGE", "PASSED", False),
    ]
    run_dirs = []
    for run_id, status, cleanup, keep_file in states:
        run_dir = tmp_path / "reports" / f"improvement_{run_id}"
        _write_report(run_dir, {
            "run_id": run_id,
            "status": status,
            "cleanup": cleanup,
            "branch": f"agent/improvement-{run_id}",
            "worktree": str(run_dir / "checkout"),
            "finished_at": "2026-01-01T00:00:00+00:00",
        })
        (run_dir / "codex.log").write_text("log\n", encoding="utf-8")
        if keep_file:
            (run_dir / "user-evidence.bin").write_bytes(b"preserve")
        if run_id.endswith("eeeeeeee"):
            (run_dir / "checkout").mkdir()
        run_dirs.append(run_dir)
    retained_branch = "agent/improvement-20260103T000000Z-cccccccc"
    subprocess.run(["git", "branch", retained_branch, "HEAD"], cwd=tmp_path, check=True)

    summary = prune_reports(tmp_path, report_type="improvement", now=now)

    assert summary["removed"] == []
    assert summary["preserved"] == 5
    assert all(run_dir.exists() for run_dir in run_dirs)


def test_prunes_old_successful_check_but_never_candidate_qa(tmp_path):
    _initialize_repository(tmp_path)
    old_run_id = "a" * 32
    old_dir = tmp_path / "reports" / f"maintenance_qa_{old_run_id}"
    _write_report(old_dir, {
        "run_id": old_run_id,
        "mode": "check",
        "status": "PASSED",
        "cleanup": "PASSED",
        "finished_at": "2026-01-01T00:00:00+00:00",
    })
    (old_dir / "pytest.log").write_text("passed\n", encoding="utf-8")
    candidate_id = "b" * 32
    candidate_dir = tmp_path / "reports" / f"maintenance_qa_{candidate_id}"
    _write_report(candidate_dir, {
        "run_id": candidate_id,
        "mode": "qa_candidate",
        "status": "PASSED",
        "cleanup": "PASSED",
        "finished_at": "2026-01-01T00:00:00+00:00",
    })

    summary = prune_reports(
        tmp_path,
        report_type="maintenance_qa",
        now=datetime(2026, 10, 27, tzinfo=UTC),
    )

    assert summary["removed"] == [old_dir.name]
    assert not old_dir.exists()
    assert candidate_dir.exists()
