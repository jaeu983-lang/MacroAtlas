"""Run shared offline maintenance checks in an immutable detached checkout."""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import sysconfig
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_COMMIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def run(root, *, timeout=600, candidate=None, base=None):
    root = Path(root).resolve()
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    if candidate is None and base is not None:
        raise ValueError('--base requires --candidate')
    if candidate is not None:
        if base is None:
            raise ValueError('--base is required with --candidate')
        candidate, base = candidate.lower(), base.lower()
        if not _COMMIT_SHA.fullmatch(candidate) or not _COMMIT_SHA.fullmatch(base):
            raise ValueError('candidate and base must be full commit SHA values')

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

    source_head = git('rev-parse', 'HEAD')
    source_clean = not git('status', '--porcelain')
    if candidate is None:
        if not source_clean:
            raise ValueError('working tree must be clean; commit changes before QA')
        mode = 'check'
        base_commit = source_head
        candidate_commit = source_head
        changed_paths = []
    else:
        candidate_commit = git('rev-parse', '--verify', f'{candidate}^{{commit}}')
        base_commit = git('rev-parse', '--verify', f'{base}^{{commit}}')
        if candidate_commit != candidate or base_commit != base:
            raise ValueError('candidate and base must resolve to the supplied full commit SHA')
        if git('merge-base', base_commit, candidate_commit) != base_commit:
            raise ValueError('base commit must be an ancestor of candidate commit')
        changed_paths = git('diff', '--name-only', f'{base_commit}..{candidate_commit}')
        changed_paths = changed_paths.splitlines() if changed_paths else []
        mode = 'qa_candidate'
    commit = candidate_commit
    run_id = uuid4().hex
    run_dir = root / "reports" / ("maintenance_qa_" + run_id)
    run_dir.mkdir(parents=True)
    worktree = run_dir / "checkout"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "mode": mode,
        "commit": commit,
        "source_head": source_head,
        "source_checkout_clean": source_clean,
        "base_commit": base_commit,
        "candidate_commit": candidate_commit,
        "changed_paths": changed_paths,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "started_at": datetime.now(UTC).isoformat(),
        "status": "FAILED",
        "checks": [],
        "network_requested": False,
    }
    attached = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        attached = True
        scripts_dir = sysconfig.get_path("scripts")
        env = dict(
            os.environ,
            PYTHONPATH=str(worktree / "src"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        if scripts_dir:
            env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
        diff_check = (
            ["git", "show", "--check", "--oneline", commit]
            if mode == 'check'
            else ["git", "diff", "--check", f"{base_commit}..{candidate_commit}"]
        )
        commands = [
            ("pytest", [sys.executable, "-m", "pytest"]),
            ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
            ("diff", diff_check),
            ("cli", [sys.executable, "-m", "macro_data_platform.cli", "--help"]),
            ("cli_entrypoint", ["macroatlas", "--help"]),
            ("cli_collect", ["macroatlas", "collect", "--help"]),
            ("health", [sys.executable, "-m", "macro_data_platform.health"]),
        ]
        for name, command in commands:
            with (run_dir / (name + ".log")).open("w", encoding="utf-8") as log:
                try:
                    result = subprocess.run(
                        command,
                        check=False,
                        cwd=worktree,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                    )
                    check = {
                        "name": name,
                        "exit_code": result.returncode,
                        "status": "PASSED" if result.returncode == 0 else "FAILED",
                    }
                except subprocess.TimeoutExpired:
                    check = {"name": name, "exit_code": None, "status": "TIMED_OUT"}
                except OSError as exc:
                    check = {
                        "name": name,
                        "exit_code": None,
                        "status": "FAILED",
                        "failure_kind": type(exc).__name__,
                    }
            report['checks'].append(check)
        report["status"] = (
            "PASSED"
            if all(check["status"] == "PASSED" for check in report["checks"])
            else "FAILED"
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report["failure_kind"] = type(exc).__name__
    finally:
        if attached:
            try:
                cleanup = subprocess.run(
                    ["git", "worktree", "remove", str(worktree)],
                    check=False,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                report["cleanup"] = "PASSED" if cleanup.returncode == 0 else "FAILED"
                if cleanup.returncode:
                    report["cleanup_failure_kind"] = "WorktreeRemoveFailed"
            except (OSError, subprocess.SubprocessError) as exc:
                report["status"] = "FAILED"
                report["cleanup"] = "FAILED"
                report["cleanup_failure_kind"] = type(exc).__name__
            if report["cleanup"] != "PASSED":
                report["status"] = "FAILED"
        else:
            report["cleanup"] = "NOT_NEEDED"
        report["finished_at"] = datetime.now(UTC).isoformat()
        (run_dir / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    return report, run_dir / "report.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=int, default=600, help="timeout per check in seconds")
    parser.add_argument("--candidate", help="full immutable candidate commit SHA to verify")
    parser.add_argument("--base", help="full base commit SHA; required with --candidate")
    args = parser.parse_args(argv)
    try:
        report, path = run(args.project_root, timeout=args.timeout,
                           candidate=args.candidate, base=args.base)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "NOT_EXECUTED", "reason": str(exc)}))
        return 2
    summary = {
        "status": report["status"],
        "mode": report["mode"],
        "base_commit": report["base_commit"],
        "candidate_commit": report["candidate_commit"],
        "changed_paths": report["changed_paths"],
        "report": str(path),
        "checks": [
            {
                "name": check["name"],
                "status": check["status"],
                "exit_code": check.get("exit_code"),
                "failure_kind": check.get("failure_kind"),
            }
            for check in report["checks"]
        ],
        "cleanup": report["cleanup"],
    }
    print(json.dumps(summary))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == '__main__':
    raise SystemExit(main())
