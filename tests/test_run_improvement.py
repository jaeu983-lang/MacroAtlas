"""Tests for bounded maintenance update planning and path isolation."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "maintenance_update", Path(__file__).parents[1] / "scripts/run_improvement.py"
)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("src/macro_data_platform/engine.py", True),
        ("tests/test_engine.py", True),
        ("docs/ENGINE.md", True),
        ("scripts/run_improvement.ps1", True),
        ("README.md", True),
        ("PROJECT_PLAN.md", True),
        ("data/catalog.sqlite", False),
        (".env", False),
        ("docs/.env.production", False),
        ("src/private.key", False),
        ("data/credentials.json", False),
        ("tests/catalog.sqlite3", False),
        (".github/workflows/ci.yml", False),
        ("reports/run/report.json", False),
        ("src/../data/raw.bin", False),
        ("/tmp/outside.py", False),
    ],
)
def test_changed_path_allowlist(path, expected):
    assert maintenance._allowed_path(path) is expected


def test_porcelain_z_parser_handles_untracked_modified_and_renamed_paths(monkeypatch, tmp_path):
    output = b" M src/current.py\0?? tests/new_test.py\0R  docs/new.md\0docs/old.md\0"
    monkeypatch.setattr(
        maintenance,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=output),
    )

    assert maintenance._changed_paths(tmp_path) == [
        "docs/new.md",
        "docs/old.md",
        "src/current.py",
        "tests/new_test.py",
    ]


def test_staged_symlink_is_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(
        maintenance,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout=":100644 120000 old new A\tsrc/link.py\n"
        ),
    )

    assert maintenance._has_staged_symlink(tmp_path) is True


def _initialize_repository(root):
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
    )
    (root / "prompts").mkdir()
    (root / "prompts" / "weekly_improvement.md").write_text("test prompt\n", encoding="utf-8")
    (root / "README.md").write_text("test repository\n", encoding="utf-8")
    (root / ".gitignore").write_text("reports/\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=root, check=True)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=root, check=True
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=root,
        check=True,
    )


def test_dry_run_resolves_origin_head_without_creating_worktree_or_report(tmp_path):
    _initialize_repository(tmp_path)

    report, path = maintenance.run(tmp_path, dry_run=True)

    assert report["status"] == "DRY_RUN"
    assert report["base_ref"] == "refs/remotes/origin/main"
    assert report["base_commit"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    assert report["network_requested"] is False
    assert path is None
    assert not (tmp_path / "reports").exists()


def test_missing_origin_head_requires_explicit_base_ref(tmp_path):
    _initialize_repository(tmp_path)
    subprocess.run(
        ["git", "symbolic-ref", "--delete", "refs/remotes/origin/HEAD"], cwd=tmp_path,
        check=True,
    )

    with pytest.raises(ValueError, match="pass --base-ref explicitly"):
        maintenance.run(tmp_path, dry_run=True)


def test_noop_update_uses_temporary_worktree_and_never_pushes(monkeypatch, tmp_path):
    _initialize_repository(tmp_path)
    monkeypatch.setattr(maintenance.shutil, "which", lambda _: "/fake/tool")
    monkeypatch.setattr(
        maintenance,
        "_run_codex",
        lambda *args, **kwargs: subprocess.CompletedProcess(["codex"], 0),
    )

    report, path = maintenance.run(tmp_path, timeout=30)

    assert report["status"] == "NO_ACTIONABLE_CHANGE"
    assert report["cleanup"] == "PASSED"
    assert report["push_status"] == "NOT_RUN"
    assert report["pull_request"] is None
    assert path.is_file()
    assert not Path(report["worktree"]).exists()
    branch = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{report['branch']}"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )
    assert branch.returncode != 0


def test_out_of_scope_change_is_preserved_locally_and_never_pushed(monkeypatch, tmp_path):
    _initialize_repository(tmp_path)
    monkeypatch.setattr(maintenance.shutil, "which", lambda _: "/fake/tool")

    def fake_codex(worktree, prompt, log_path, timeout):
        (worktree / "data").mkdir()
        (worktree / "data" / "capture.bin").write_bytes(b"raw")
        return subprocess.CompletedProcess(["codex"], 0)

    monkeypatch.setattr(maintenance, "_run_codex", fake_codex)
    report, _ = maintenance.run(tmp_path, timeout=30)

    assert report["status"] == "OUT_OF_SCOPE_CHANGES"
    assert report["changed_paths"] == ["data/capture.bin"]
    assert report["push_status"] == "NOT_RUN"
    assert Path(report["worktree"], "data", "capture.bin").is_file()


def test_failed_candidate_qa_never_pushes_or_opens_pr(monkeypatch, tmp_path):
    _initialize_repository(tmp_path)
    real_run = subprocess.run
    actions = []
    monkeypatch.setattr(maintenance.shutil, "which", lambda _: "/fake/tool")

    def fake_codex(worktree, prompt, log_path, timeout):
        (worktree / "README.md").write_text("candidate change\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0)

    monkeypatch.setattr(maintenance, "_run_codex", fake_codex)

    def fake_run(command, *args, **kwargs):
        if len(command) > 1 and command[1].endswith("run_maintenance_qa.py"):
            actions.append("qa")
            kwargs["stdout"].write(b'{"status":"FAILED","report":"qa.json"}\n')
            return subprocess.CompletedProcess(command, 1)
        if command[0] == "git" and len(command) > 1 and command[1] == "push":
            actions.append("push")
            return subprocess.CompletedProcess(command, 0, stdout="pushed\n", stderr="")
        if command[0] == "gh":
            actions.append("pull_request")
            return subprocess.CompletedProcess(
                command, 0, stdout="https://github.com/example/repo/pull/1\n", stderr=""
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(maintenance.subprocess, "run", fake_run)
    report, _ = maintenance.run(tmp_path, timeout=30)

    assert report["status"] == "QA_FAILED"
    assert report["push_status"] == "NOT_RUN"
    assert actions == ["qa"]


def test_only_passing_candidate_qa_precedes_push_and_review_pr(monkeypatch, tmp_path):
    _initialize_repository(tmp_path)
    real_run = subprocess.run
    actions = []
    monkeypatch.setattr(maintenance.shutil, "which", lambda _: "/fake/tool")

    def fake_codex(worktree, prompt, log_path, timeout):
        (worktree / "README.md").write_text("candidate change\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0)

    monkeypatch.setattr(maintenance, "_run_codex", fake_codex)

    def fake_run(command, *args, **kwargs):
        if len(command) > 1 and command[1].endswith("run_maintenance_qa.py"):
            actions.append("qa")
            kwargs["stdout"].write(b'{"status":"PASSED","report":"qa.json"}\n')
            return subprocess.CompletedProcess(command, 0)
        if command[0] == "git" and len(command) > 1 and command[1] == "push":
            actions.append("push")
            return subprocess.CompletedProcess(command, 0, stdout="pushed\n", stderr="")
        if command[0] == "/fake/tool":
            actions.append("pull_request")
            return subprocess.CompletedProcess(
                command, 0, stdout="https://github.com/example/repo/pull/1\n", stderr=""
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(maintenance.subprocess, "run", fake_run)
    report, path = maintenance.run(tmp_path, timeout=30)

    assert report["status"] == "PULL_REQUEST_CREATED"
    assert report["push_status"] == "PASSED"
    assert report["pull_request"] == "https://github.com/example/repo/pull/1"
    assert report["cleanup"] == "PASSED"
    assert actions == ["qa", "push", "pull_request"]
    assert path.is_file()
    assert not Path(report["worktree"]).exists()
