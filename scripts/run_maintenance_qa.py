"""Run the shared offline maintenance checks in a clean, detached checkout."""
import argparse
import json
import os
import platform
import subprocess
import sys
import sysconfig
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def run(root, *, timeout=600):
    root = Path(root).resolve()
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    if git('status', '--porcelain'):
        raise ValueError('working tree must be clean; commit changes before QA')
    commit = git('rev-parse', 'HEAD')
    run_id = uuid4().hex
    run_dir = root / "reports" / ("maintenance_qa_" + run_id)
    run_dir.mkdir(parents=True)
    worktree = run_dir / "checkout"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "mode": "check",
        "commit": commit,
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
        commands = [
            ("pytest", [sys.executable, "-m", "pytest", "-q"]),
            ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
            ("diff", ["git", "show", "--check", "--oneline", commit]),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=int, default=600, help="timeout per check in seconds")
    args = parser.parse_args()
    try:
        report, path = run(args.project_root, timeout=args.timeout)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "NOT_EXECUTED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": report["status"], "report": str(path)}))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == '__main__':
    raise SystemExit(main())
