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
    assert [check['name'] for check in report['checks']] == [
        'pytest', 'ruff', 'diff', 'cli', 'cli_entrypoint', 'cli_collect', 'health',
    ]
    assert calls[-1][:3] == ['git', 'worktree', 'remove']


def test_all_shared_checks_pass_and_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(qa.subprocess, 'check_output',
                        lambda args, **kw: '' if 'status' in args else 'abc123')
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(qa.subprocess, 'run', execute)
    report, path = qa.run(tmp_path)

    assert report['status'] == 'PASSED'
    assert report['cleanup'] == 'PASSED'
    assert all(check['status'] == 'PASSED' for check in report['checks'])
    assert json.loads(path.read_text())['mode'] == 'check'
    assert any(command[:3] == ['git', 'show', '--check'] for command in calls)


def test_missing_check_command_is_recorded_and_later_checks_continue(tmp_path, monkeypatch):
    monkeypatch.setattr(qa.subprocess, 'check_output',
                        lambda args, **kw: '' if 'status' in args else 'abc123')
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        if command == ['macroatlas', '--help']:
            raise FileNotFoundError('macroatlas')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(qa.subprocess, 'run', execute)
    report, _ = qa.run(tmp_path)

    assert report['status'] == 'FAILED'
    assert report['checks'][4] == {
        'name': 'cli_entrypoint',
        'exit_code': None,
        'status': 'FAILED',
        'failure_kind': 'FileNotFoundError',
    }
    assert report['checks'][-1]['name'] == 'health'
    assert report['checks'][-1]['status'] == 'PASSED'
    assert report['cleanup'] == 'PASSED'


def test_cleanup_exception_fails_run_and_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(qa.subprocess, 'check_output',
                        lambda args, **kw: '' if 'status' in args else 'abc123')

    def execute(command, **kwargs):
        if command[:3] == ['git', 'worktree', 'remove']:
            raise OSError('cleanup failed')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(qa.subprocess, 'run', execute)
    report, _ = qa.run(tmp_path)

    assert report['status'] == 'FAILED'
    assert report['cleanup'] == 'FAILED'
    assert report['cleanup_failure_kind'] == 'OSError'


def test_cli_prints_failed_check_summary(tmp_path, monkeypatch, capsys):
    report = {
        'status': 'FAILED',
        'checks': [
            {'name': 'pytest', 'status': 'FAILED', 'exit_code': 1},
            {'name': 'ruff', 'status': 'PASSED', 'exit_code': 0},
        ],
        'cleanup': 'PASSED',
    }
    monkeypatch.setattr(qa, 'run', lambda *a, **k: (report, tmp_path / 'report.json'))

    assert qa.main([]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == 'FAILED'
    assert output['checks'][0] == {
        'name': 'pytest',
        'status': 'FAILED',
        'exit_code': 1,
        'failure_kind': None,
    }
    assert output['cleanup'] == 'PASSED'
