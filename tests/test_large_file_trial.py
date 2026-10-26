import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageStatus
from macro_data_platform.ingestion.large_file_trial import (
    DEFAULT_BUDGET,
    LargeFileTrialEngine,
    create_trial,
    make_trial_orchestrator,
)
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, decision
from macro_data_platform.orchestration import StageInput
from macro_data_platform.storage.history import HistoryStore


def setup_candidate(tmp_path, body=b"a,b\n0,\n", suffix="csv"):
    settings = Settings(tmp_path)
    source = tmp_path / f"data/inbox/source.{suffix}"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    store = HistoryStore(settings)
    runner = make_trial_orchestrator(store, settings)
    parent = runner.create("candidate")
    record = DeferredNonAPIStore(settings).register(
        {"relative_path": source.relative_to(tmp_path).as_posix(), "format": suffix},
        parent.task_id,
        "candidate",
        decision("qualification_candidate", status="inspection_required"),
    )
    return settings, store, runner, record, source


def test_trial_idempotently_binds_immutable_event(tmp_path):
    settings, store, _runner, record, source = setup_candidate(tmp_path)
    first = create_trial(store, settings, record["id"])
    assert create_trial(store, settings, record["id"]) == first
    snapshot = store.get(first)
    DeferredNonAPIStore(settings).register(
        {"relative_path": source.relative_to(tmp_path).as_posix(), "format": "csv"},
        record["task_id"],
        "candidate",
        decision("input_bytes", 100),
    )
    assert store.get(first)["plan"] == snapshot["plan"]
    assert create_trial(store, settings, record["id"]) != first
    assert store.get(record["task_id"])["status"] == "CREATED"


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited worker is Linux only")
def test_streaming_trial_preserves_source_zero_and_empty_and_discards_scratch(tmp_path):
    settings, store, runner, record, source = setup_candidate(tmp_path)
    original = source.read_bytes()
    doc = runner.run(create_trial(store, settings, record["id"]))
    result = doc["stages"][-1]["result"]["payload"]
    assert result["execution_state"] == "TRIAL_PASSED"
    assert (result["zero_fields"], result["empty_fields"], result["rows"]) == (1, 1, 1)
    assert result["production_execution"] == "NOT_EXECUTED"
    assert result["eligible_for_production"] is False
    assert source.read_bytes() == original
    assert [p.name for p in (tmp_path / "data/large_trials").iterdir()] == ["worker.lock"]
    assert len(runner.run(doc["task_id"])["attempts"]) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited worker is Linux only")
@pytest.mark.parametrize(
    "body,suffix,budget,reason",
    [
        (b"a,b\n1\n", "csv", DEFAULT_BUDGET, "ragged_rows"),
        (b"a,b\n" + b"1,2\n" * 20, "csv", replace(DEFAULT_BUDGET, output_bytes=8), "output_budget"),
    ],
)
def test_failed_trial_reports_not_executed_and_removes_partial_output(
    tmp_path, body, suffix, budget, reason
):
    settings, store, runner, record, source = setup_candidate(tmp_path, body, suffix)
    result = runner.run(create_trial(store, settings, record["id"], budget=budget))
    payload = result["stages"][-1]["result"]["payload"]
    assert payload["execution_state"] == "NOT_EXECUTED"
    assert payload["reason"] == reason
    assert result["status"] == "NEEDS_REVIEW"
    assert source.read_bytes() == body
    assert [p.name for p in (tmp_path / "data/large_trials").iterdir()] == ["worker.lock"]


def test_unsupported_platform_stops_before_worker(tmp_path):
    settings, store, runner, record, _ = setup_candidate(tmp_path)
    with patch("macro_data_platform.ingestion.large_file_trial.sys.platform", "win32"):
        doc = runner.run(create_trial(store, settings, record["id"]))
    assert doc["stages"][-1]["result"]["payload"]["reason"] == "resource_isolation_unavailable"


def test_large_source_is_not_opened_for_trial(tmp_path):
    settings, store, _runner, record, _source = setup_candidate(tmp_path)
    task_id = create_trial(
        store, settings, record["id"], budget=replace(DEFAULT_BUDGET, input_bytes=1)
    )
    data = store.get(task_id)["plan"][0]["input_data"]
    with patch.object(Path, "open", side_effect=AssertionError("must not read")):
        result = LargeFileTrialEngine(settings).run(
            StageInput(task_id, "trial", "qualify", data, None, ())
        )
    assert result.status == StageStatus.NEEDS_REVIEW
    assert result.payload["reason"] == "input_budget"


@pytest.mark.skipif(sys.platform != "linux", reason="resource-limited worker is Linux only")
def test_ambiguous_delimiter_is_tested_without_production_approval(tmp_path):
    settings, store, runner, record, _ = setup_candidate(tmp_path, b"a|b\n0|\n", "txt")
    result = runner.run(create_trial(store, settings, record["id"]))["stages"][-1]["result"][
        "payload"
    ]
    assert result["delimiter_inferred"] is True
    assert result["production_execution"] == "NOT_EXECUTED"
    json.dumps(result)


def test_changed_source_cannot_retarget_bound_trial(tmp_path):
    settings, store, runner, record, source = setup_candidate(tmp_path)
    task_id = create_trial(store, settings, record["id"])
    source.write_bytes(b"a,b\nchanged,source\n")
    result = runner.run(task_id)["stages"][-1]["result"]["payload"]
    assert result["execution_state"] == "NOT_EXECUTED"
    assert result["reason"] == "source_changed_since_binding"


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX resource isolation")
def test_busy_worker_is_not_run(tmp_path):
    from macro_data_platform.ingestion.large_file_trial import worker_slot

    settings, store, runner, record, _ = setup_candidate(tmp_path)
    root = tmp_path / "data/large_trials"
    root.mkdir()
    with worker_slot(root):
        result = runner.run(create_trial(store, settings, record["id"]))["stages"][-1]["result"][
            "payload"
        ]
    assert result["reason"] == "engine_busy"
    assert result["trial_attempted"] is False


def test_existing_trial_cannot_be_reused_after_source_replacement(tmp_path):
    settings, store, _runner, record, source = setup_candidate(tmp_path)
    create_trial(store, settings, record["id"])
    source.write_bytes(b"a,b\nchanged,original\n")
    with pytest.raises(ValueError, match="source_changed_since_binding"):
        create_trial(store, settings, record["id"])


def test_cli_failed_candidate_is_not_implicitly_retried(tmp_path):
    from macro_data_platform.cli import build_parser, dispatch

    _settings, store, _runner, record, _ = setup_candidate(tmp_path, b"not a workbook", "xlsx")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\n')
    args = build_parser().parse_args(["--project-root", str(tmp_path), "large-check", record["id"]])
    first_code, first = dispatch(args)
    second_code, second = dispatch(args)
    assert first_code == second_code == 1
    assert first["execution_state"] == second["execution_state"] == "NOT_EXECUTED"
    assert first["task_id"] == second["task_id"]
    assert len(store.get(first["task_id"])["attempts"]) == 1


def test_history_failure_returns_safe_not_executed(tmp_path,monkeypatch,capsys):
    import sqlite3

    from macro_data_platform.cli import main
    (tmp_path/'pyproject.toml').write_text('[project]\nname="fixture"\n')
    def unavailable(*args,**kwargs):
        raise sqlite3.OperationalError('private database diagnostic')
    monkeypatch.setattr('macro_data_platform.cli.HistoryStore',unavailable)
    code=main(['--project-root',str(tmp_path),'large-check','unknown'])
    output=capsys.readouterr().out
    assert code==1
    assert json.loads(output)['execution_state']=='NOT_EXECUTED'
    assert 'private database diagnostic' not in output


def test_absolute_candidate_is_rejected_before_external_path_inspection(tmp_path):
    settings=Settings(tmp_path)
    data={'budget':asdict(DEFAULT_BUDGET),'scope':{'relative_path':'/outside.csv'}}
    with patch.object(Path,'is_symlink',side_effect=AssertionError('no outside inspection')):
        result=LargeFileTrialEngine(settings).run(StageInput('t','trial','qualify',data,None,()))
    assert result.payload['execution_state']=='NOT_EXECUTED'


def test_ambiguous_txt_automatically_enters_catalog_then_explicit_trial(tmp_path):
    from macro_data_platform.ingestion.tabular_files import TabularFileEngine
    from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan
    settings=Settings(tmp_path);store=HistoryStore(settings)
    source=tmp_path/'data/inbox/ambiguous.txt';source.parent.mkdir(parents=True)
    source.write_bytes(b'a|b\n0|\n')
    parent_runner=Orchestrator(store,{('tabular_file','1'):TabularFileEngine(settings)})
    parent=parent_runner.create('ambiguous text')
    parent_runner.plan(parent.task_id,TaskPlan((StageSpec('inspect','tabular_file',{
        'relative_path':'data/inbox/ambiguous.txt','format':'txt'}),)))
    doc=parent_runner.run(parent.task_id)
    record=doc['stages'][-1]['result']['payload']['non_api_deferral']
    assert record['reason']=='delimiter_unknown'
    trial=make_trial_orchestrator(store,settings).run(create_trial(store,settings,record['id']))
    payload=trial['stages'][-1]['result']['payload']
    if sys.platform=='linux':
        assert payload['execution_state']=='TRIAL_PASSED'
        assert payload['delimiter_inferred'] is True
    else:
        assert payload['execution_state']=='NOT_EXECUTED'
    assert store.get(parent.task_id)['status']=='NEEDS_REVIEW'
    assert payload['production_execution']=='NOT_EXECUTED'
