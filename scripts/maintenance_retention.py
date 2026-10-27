"""Conservative retention for completed, non-candidate maintenance reports."""
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

_IMPROVEMENT_DIR = re.compile(r"improvement_(\d{8}T\d{6}Z-[0-9a-f]{8})\Z")
_BRANCH = re.compile(r"agent/improvement-\d{8}T\d{6}Z-[0-9a-f]{8}\Z")
_QA_DIR = re.compile(r"maintenance_qa_([0-9a-f]{32})\Z")


def _git(root, *args):
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=False, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _worktree_registered(root, checkout):
    result = _git(root, "worktree", "list", "--porcelain")
    if result is None or result.returncode or not isinstance(result.stdout, str):
        return None
    target = str(checkout.resolve()).casefold()
    return any(
        str(Path(line.removeprefix("worktree ")).resolve()).casefold() == target
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    )


def _branch_exists(root, branch):
    result = _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    if result is None or result.returncode not in (0, 1):
        return None
    return result.returncode == 0


def _old_enough(report, cutoff):
    finished_at = report.get("finished_at")
    if not isinstance(finished_at, str):
        return False
    try:
        timestamp = datetime.fromisoformat(finished_at)
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        return False
    return timestamp.astimezone(UTC) <= cutoff


def _safe_report_directory(run_dir, allowed_names):
    try:
        entries = list(run_dir.iterdir())
    except OSError:
        return False
    return all(
        not entry.is_symlink()
        and entry.name in allowed_names
        and entry.is_file()
        for entry in entries
    )


def prune_reports(root, *, report_type, retention_days=90, now=None):
    """Prune only old successful routine reports with no remaining worktree/branch."""
    if report_type not in {"improvement", "maintenance_qa"}:
        raise ValueError("report_type must be 'improvement' or 'maintenance_qa'")
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    root = Path(root).resolve()
    reports = root / "reports"
    summary = {"policy_days": retention_days, "scanned": 0, "removed": [], "preserved": 0}
    if reports.is_symlink() or not reports.is_dir():
        return summary
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must include a timezone")
    cutoff = current_time.astimezone(UTC) - timedelta(days=retention_days)

    for run_dir in sorted(reports.iterdir()):
        match = (
            _IMPROVEMENT_DIR.fullmatch(run_dir.name)
            if report_type == "improvement"
            else _QA_DIR.fullmatch(run_dir.name)
        )
        if not match or run_dir.is_symlink() or not run_dir.is_dir():
            continue
        summary["scanned"] += 1
        report_path = run_dir / "report.json"
        if report_path.is_symlink() or not report_path.is_file():
            summary["preserved"] += 1
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary["preserved"] += 1
            continue
        if not isinstance(report, dict) or not _old_enough(report, cutoff):
            summary["preserved"] += 1
            continue

        checkout = run_dir / "checkout"
        registered = _worktree_registered(root, checkout)
        if registered is not False or checkout.exists():
            summary["preserved"] += 1
            continue

        if report_type == "improvement":
            run_id = match.group(1)
            branch = report.get("branch")
            logged_worktree = report.get("worktree")
            if (
                report.get("run_id") != run_id
                or not isinstance(logged_worktree, str)
                or Path(logged_worktree).resolve() != checkout.resolve()
                or branch != f"agent/improvement-{run_id}"
                or not _BRANCH.fullmatch(str(branch))
                or report.get("status") != "NO_ACTIONABLE_CHANGE"
                or report.get("cleanup") != "PASSED"
            ):
                summary["preserved"] += 1
                continue
            if _branch_exists(root, branch) is not False:
                summary["preserved"] += 1
                continue
            allowed_names = {
                "report.json", "codex.log", "commit.log", "qa.log", "push.log",
                "pull_request.log", "pull_request.md",
            }
        else:
            if (
                report.get("run_id") != match.group(1)
                or report.get("mode") != "check"
                or report.get("status") != "PASSED"
                or report.get("cleanup") not in {"PASSED", "NOT_NEEDED"}
            ):
                summary["preserved"] += 1
                continue
            allowed_names = {
                "report.json", "pytest.log", "ruff.log", "diff.log", "cli.log",
                "cli_entrypoint.log", "cli_collect.log", "health.log",
            }

        if not _safe_report_directory(run_dir, allowed_names):
            summary["preserved"] += 1
            continue
        try:
            shutil.rmtree(run_dir)
        except OSError:
            summary["preserved"] += 1
            continue
        summary["removed"].append(run_dir.name)
    return summary
