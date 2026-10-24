import os
import subprocess
import sys
from pathlib import Path

import pytest

from macro_data_platform.health import check_project_layout


def test_project_layout_detects_missing_items(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("rules", encoding="utf-8")
    missing = check_project_layout(tmp_path)
    assert "AGENTS.md" not in missing
    assert "GUIDELINES.md" in missing


def test_project_layout_passes_when_required_items_exist(tmp_path: Path):
    for item in ["AGENTS.md", "GUIDELINES.md", "pyproject.toml", "src", "tests"]:
        path = tmp_path / item
        if item in {"src", "tests"}:
            path.mkdir()
        else:
            path.write_text("placeholder", encoding="utf-8")
    assert check_project_layout(tmp_path) == []


@pytest.mark.parametrize("encoding", ["cp949", "utf-8", "ascii"])
def test_health_cli_handles_unicode_paths(encoding):
    # Use a synthetic module path so the regression remains portable even when
    # the checkout itself has only ASCII characters. No files need to exist.
    code = (
        "import macro_data_platform.health as h; "
        "h.__file__ = '/workspace/문档/프로젝트/src/macro_data_platform/health.py'; "
        "h.check_project_layout = lambda root: []; "
        "raise SystemExit(h.main())"
    )
    env = {**os.environ, "PYTHONIOENCODING": f"{encoding}:strict"}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr.decode(encoding)
    output = result.stdout.decode(encoding)
    assert "OK: project layout verified" in output
    if encoding == "utf-8":
        assert "문档" in output
        assert "프로젝트" in output
    else:
        assert r"\u6863" in output
