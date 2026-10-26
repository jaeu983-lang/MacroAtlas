"""QA runner must preserve failure and refuse dirty source trees."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'maintenance_qa', Path(__file__).parents[1] / 'scripts/run_maintenance_qa.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def test_dirty_checkout_never_creates_worktree(tmp_path, monkeypatch):
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda *a, **k: ' M source.py')
    with pytest.raises(ValueError, match='clean'):
        qa.run(tmp_path)
    assert not (tmp_path / 'reports').exists()


@pytest.mark.parametrize('timeout', [False, True])
def test_failed_check_is_reported_and_cleanup_runs(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(qa.subprocess, 'check_output',
                        lambda args, **kw: '' if 'status' in args else 'abc123')
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        if 'pytest' in command:
            if timeout:
                raise subprocess.TimeoutExpired(command, 1)
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(qa.subprocess, 'run', execute)
    report, path = qa.run(tmp_path)
    assert report['status'] == 'FAILED'
    assert report['checks'][0]['status'] == ('TIMED_OUT' if timeout else 'FAILED')
    assert report['cleanup'] == 'PASSED'
    assert json.loads(path.read_text())['commit'] == 'abc123'
    assert calls[-1][:3] == ['git', 'worktree', 'remove']
