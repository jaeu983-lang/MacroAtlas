"""Run a bounded developer maintenance update on an isolated branch/worktree."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4


def _git(root, *args, check=True, text=True, timeout=None):
    return subprocess.run(
        ["git", *args], cwd=root, check=check, capture_output=True, text=text, timeout=timeout
    )


def _resolve_base(root, base_ref):
    if base_ref is None:
        result = _git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False)
        if result.returncode:
            raise ValueError("origin/HEAD is not configured; pass --base-ref explicitly")
        base_ref = result.stdout.strip()
    if not base_ref or base_ref.startswith("-") or "\x00" in base_ref:
        raise ValueError("base ref must be a valid branch or commit reference")
    result = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}", check=False)
    if result.returncode:
        raise ValueError(f"base ref does not resolve to a commit: {base_ref}")
    base_sha = result.stdout.strip()
    pr_base = base_ref.removeprefix("refs/remotes/origin/").removeprefix("origin/")
    pr_base = pr_base.removeprefix("refs/heads/")
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pr_base):
        pr_base = None
    return base_ref, base_sha, pr_base


def _changed_paths(root):
    result = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", text=False)
    records = result.stdout.split(b"\0")
    paths = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError("could not safely parse git status output")
        status = record[:2].decode("ascii", errors="strict")
        paths.append(os.fsdecode(record[3:]))
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                raise ValueError("could not safely parse rename status output")
            paths.append(os.fsdecode(records[index]))
            index += 1
    return sorted(set(paths))


def _allowed_path(path):
    normalized = path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts or not parsed.parts:
        return False
    protected_names = {"credentials", "secrets", "id_rsa", "id_ed25519"}
    for part in parsed.parts:
        lowered = part.lower()
        if lowered in protected_names or (lowered.startswith(".env") and lowered != ".env.example"):
            return False
        if Path(lowered).suffix in {
            ".db", ".db3", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"
        }:
            return False
    if parsed.parts[0] in {"src", "tests", "docs"}:
        return len(parsed.parts) > 1
    if parsed.parts[0] == "scripts":
        return len(parsed.parts) > 1 and parsed.suffix.lower() in {".py", ".ps1", ".sh"}
    return len(parsed.parts) == 1 and parsed.name in {"README.md", "PROJECT_PLAN.md"}


def _has_staged_symlink(root):
    result = _git(root, "diff", "--cached", "--raw")
    for line in result.stdout.splitlines():
        header = line.split("\t", maxsplit=1)[0].split()
        if len(header) >= 3 and "120000" in header[:3]:
            return True
    return False


def _write_report(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_codex(worktree, prompt, log_path, timeout):
    codex = shutil.which("codex")
    if not codex:
        raise FileNotFoundError("Codex CLI not found")
    with log_path.open("wb") as log:
        return subprocess.run(
            [codex, "--ask-for-approval", "never", "exec", "--sandbox", "workspace-write", prompt],
            cwd=worktree,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )


def _validate_codex_cli(root, codex):
    result = subprocess.run(
        [
            codex,
            "--ask-for-approval",
            "never",
            "exec",
            "--sandbox",
            "workspace-write",
            "--help",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError("installed Codex CLI does not support the configured safe exec options")


def _codex_failure_kind(log_path):
    log_text = Path(log_path).read_text(encoding="utf-8", errors="replace").lower()
    auth_markers = (
        "401 unauthorized",
        "access token could not be refreshed",
        "could not parse your authentication token",
    )
    return "AUTHENTICATION_REQUIRED" if any(marker in log_text for marker in auth_markers) else None


def run(root, *, task_file="prompts/weekly_improvement.md", base_ref=None,
        timeout=3600, dry_run=False):
    root = Path(root).resolve()
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    prompt_path = (root / task_file).resolve()
    if root not in prompt_path.parents or not prompt_path.is_file():
        raise ValueError("task file must exist inside the repository")
    prompt = prompt_path.read_text(encoding="utf-8")
    resolved_base_ref, base_sha, pr_base = _resolve_base(root, base_ref)
    if dry_run:
        return {
            "status": "DRY_RUN",
            "base_ref": resolved_base_ref,
            "base_commit": base_sha,
            "task_file": prompt_path.relative_to(root).as_posix(),
            "network_requested": False,
        }, None
    if pr_base is None:
        raise ValueError("base ref must name a branch so a review PR can target it")

    if _git(root, "status", "--porcelain", "--untracked-files=all").stdout.strip():
        raise ValueError("source checkout must be clean; updater will not switch or modify it")
    for executable in ("codex", "gh"):
        if not shutil.which(executable):
            raise FileNotFoundError(f"{executable} CLI not found")
    _validate_codex_cli(root, shutil.which("codex"))

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    branch = f"agent/improvement-{run_id}"
    run_dir = root / "reports" / f"improvement_{run_id}"
    run_dir.mkdir(parents=True)
    report_path = run_dir / "report.json"
    worktree = run_dir / "checkout"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "RUNNING",
        "base_ref": resolved_base_ref,
        "base_commit": base_sha,
        "candidate_commit": None,
        "branch": branch,
        "task_file": prompt_path.relative_to(root).as_posix(),
        "changed_paths": [],
        "codex_exit_code": None,
        "qa_report": None,
        "push_status": "NOT_RUN",
        "pull_request": None,
        "network_requested": False,
        "started_at": datetime.now(UTC).isoformat(),
        "worktree": str(worktree),
    }
    _write_report(report_path, report)

    try:
        _git(root, "worktree", "add", "-b", branch, str(worktree), base_sha)
        try:
            codex_result = _run_codex(worktree, prompt, run_dir / "codex.log", timeout)
        except subprocess.TimeoutExpired:
            report["status"] = "CODEX_TIMED_OUT"
            return report, report_path
        report["codex_exit_code"] = codex_result.returncode
        if codex_result.returncode:
            failure_kind = _codex_failure_kind(run_dir / "codex.log")
            if failure_kind == "AUTHENTICATION_REQUIRED":
                report["status"] = "CODEX_AUTH_REQUIRED"
                report["failure_kind"] = failure_kind
                report["user_action_required"] = (
                    "Sign in to Codex CLI again, then rerun the maintenance updater."
                )
            else:
                report["status"] = "CODEX_FAILED"
            return report, report_path

        if _git(worktree, "rev-parse", "HEAD").stdout.strip() != base_sha:
            report["status"] = "UNEXPECTED_COMMIT"
            return report, report_path
        changed = _changed_paths(worktree)
        report["changed_paths"] = changed
        if not changed:
            report["status"] = "NO_ACTIONABLE_CHANGE"
            cleanup = _git(root, "worktree", "remove", str(worktree), check=False)
            report["cleanup"] = "PASSED" if cleanup.returncode == 0 else "FAILED"
            if cleanup.returncode == 0:
                _git(root, "branch", "-D", branch)
            else:
                report["status"] = "CLEANUP_FAILED"
            return report, report_path
        if any(not _allowed_path(path) for path in changed):
            report["status"] = "OUT_OF_SCOPE_CHANGES"
            return report, report_path

        _git(worktree, "add", "-A", "--", *changed)
        staged = _git(worktree, "diff", "--cached", "--name-only").stdout.splitlines()
        if (
            not staged
            or any(not _allowed_path(path) for path in staged)
            or _has_staged_symlink(worktree)
        ):
            report["status"] = "STAGING_SCOPE_REJECTED"
            return report, report_path
        commit_result = _git(
            worktree, "commit", "-m", f"Maintenance improvement {run_id}", check=False
        )
        (run_dir / "commit.log").write_text(
            commit_result.stdout + commit_result.stderr, encoding="utf-8"
        )
        if commit_result.returncode:
            report["status"] = "COMMIT_FAILED"
            return report, report_path
        candidate_sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        report["candidate_commit"] = candidate_sha

        qa_command = [
            sys.executable,
            str(root / "scripts" / "run_maintenance_qa.py"),
            "--project-root",
            str(root),
            "--base",
            base_sha,
            "--candidate",
            candidate_sha,
        ]
        with (run_dir / "qa.log").open("wb") as log:
            qa_result = subprocess.run(
                qa_command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
                check=False,
            )
        qa_text = (run_dir / "qa.log").read_text(encoding="utf-8", errors="replace").strip()
        try:
            qa_summary = json.loads(qa_text.splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            qa_summary = {"status": "INVALID_QA_REPORT"}
        report["qa_report"] = qa_summary.get("report")
        if qa_result.returncode or qa_summary.get("status") != "PASSED":
            report["status"] = "QA_FAILED"
            return report, report_path

        report["network_requested"] = True
        report["push_status"] = "RUNNING"
        _write_report(report_path, report)
        push_result = _git(
            root, "push", "--set-upstream", "origin", branch, check=False, timeout=300
        )
        (run_dir / "push.log").write_text(
            push_result.stdout + push_result.stderr, encoding="utf-8"
        )
        if push_result.returncode:
            report["push_status"] = "FAILED"
            report["status"] = "PUSH_FAILED"
            return report, report_path
        report["push_status"] = "PASSED"

        pr_body = run_dir / "pull_request.md"
        qa_report = report["qa_report"]
        pr_body.write_text(
            "Automated maintenance candidate created on an isolated worktree.\n\n"
            f"- Base: `{base_sha}`\n- Candidate: `{candidate_sha}`\n"
            f"- Changed paths: {', '.join(changed)}\n"
            f"- QA report: `{qa_report}`\n\n"
            "Review the diff and CI before merging. This workflow never merges or publishes.",
            encoding="utf-8",
        )
        pr_result = subprocess.run(
            [
                shutil.which("gh"), "pr", "create", "--base", pr_base, "--head", branch,
                "--title", f"Maintenance improvement {run_id}", "--body-file", str(pr_body),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        (run_dir / "pull_request.log").write_text(
            pr_result.stdout + pr_result.stderr, encoding="utf-8"
        )
        if pr_result.returncode:
            report["status"] = "PR_CREATION_FAILED"
            return report, report_path
        report["pull_request"] = pr_result.stdout.strip().splitlines()[-1]
        report["status"] = "PULL_REQUEST_CREATED"
        cleanup = _git(root, "worktree", "remove", str(worktree), check=False)
        report["cleanup"] = "PASSED" if cleanup.returncode == 0 else "FAILED"
        if cleanup.returncode:
            report["status"] = "CLEANUP_FAILED"
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        report["status"] = "FAILED"
        report["failure_kind"] = type(exc).__name__
        report["failure"] = str(exc)
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        _write_report(report_path, report)
    return report, report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--task-file", default="prompts/weekly_improvement.md")
    parser.add_argument("--base-ref", help="base branch/ref; defaults to origin/HEAD")
    parser.add_argument("--timeout", type=int, default=3600, help="timeout for Codex and QA")
    parser.add_argument("--dry-run", action="store_true", help="resolve inputs without starting Codex")
    args = parser.parse_args(argv)
    try:
        report, path = run(
            args.project_root,
            task_file=args.task_file,
            base_ref=args.base_ref,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "NOT_EXECUTED", "reason": str(exc)}))
        return 2
    if path is not None:
        report["report"] = str(path)
    print(json.dumps(report))
    return 0 if report["status"] in {"DRY_RUN", "NO_ACTIONABLE_CHANGE", "PULL_REQUEST_CREATED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
