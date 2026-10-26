import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from macro_data_platform.cli import build_parser, dispatch
from macro_data_platform.config import Settings
from macro_data_platform.ingestion.large_file_duration import (
    MODEL_VERSION,
    _sample_profile,
    estimate_duration,
    profile_artifact,
    remaining_production_profile,
)
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, decision


def _successful_trial(task_id, baseline, empirical):
    start = datetime(2026, 10, 26, tzinfo=UTC)
    finish = start + timedelta(seconds=1)
    return {
        "task_id": task_id,
        "status": "COMPLETED",
        "plan": [{
            "engine": "large_file_trial",
            "input_data": {
                "duration_profile": {
                    "format": "csv", "source_bytes": 1200, "rows": 10,
                    "columns": 2, "cells": 20, "output_bytes": 1000,
                },
                "duration_estimate": {
                    "model_version": MODEL_VERSION,
                    "candidate_models": {
                        "baseline": {"seconds": baseline},
                        "empirical": {"seconds": empirical},
                    },
                },
            },
        }],
        "stages": [{
            "status": "SUCCEEDED",
            "started_at": start.isoformat(),
            "finished_at": finish.isoformat(),
            "result": {"payload": {
                "execution_state": "TRIAL_PASSED", "rows": 10, "columns": 2,
                "cells": 20, "output_bytes": 1000,
            }},
        }],
    }


def test_profile_keeps_last_row_and_never_retains_sample_values():
    content = b"period,value\n2026Q1,0\n2026Q2,secret\n"
    profile = _sample_profile(content, len(content), ".csv", {"header_row": 1})

    assert profile["rows"] == 2
    assert profile["profile_confidence"] == "high"
    assert "secret" not in json.dumps(profile)
    assert "2026Q1" not in json.dumps(profile)


def test_shadow_comparison_selects_the_candidate_with_lower_paired_error():
    history = [_successful_trial(f"task-{index}", 100.0, 1.0) for index in range(3)]
    estimate = estimate_duration(
        "qualification",
        {"format": "csv", "source_bytes": 1200, "rows": 10, "columns": 2,
         "cells": 20, "output_bytes": 1000, "profile_confidence": "low"},
        history,
        wall_seconds=20,
    )

    assert estimate["selected_model"] == "empirical"
    assert estimate["shadow_comparison_count"] == 3
    assert estimate["median_absolute_percentage_error"]["empirical"] == 0.0
    assert estimate["range_seconds"]["lower"] <= estimate["estimated_seconds"] / 2
    assert estimate["range_seconds"]["upper"] >= estimate["estimated_seconds"] * 2


def test_qualification_history_does_not_train_production_forecast():
    estimate = estimate_duration(
        "production",
        {"format": "csv", "source_bytes": 1200, "rows": 10, "columns": 2,
         "cells": 20, "output_bytes": 1000, "profile_confidence": "high"},
        [_successful_trial(f"trial-{index}", 100.0, 1.0) for index in range(3)],
        wall_seconds=60,
    )

    assert estimate["history_sample_count"] == 0
    assert estimate["selected_model"] == "baseline"


def test_estimate_command_reads_catalog_without_creating_or_changing_tasks(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\n')
    settings = Settings(tmp_path)
    source = tmp_path / "data/inbox/sample.csv"
    source.parent.mkdir(parents=True)
    source.write_text("period,value\n2026Q1,0\n", encoding="utf-8")
    record = DeferredNonAPIStore(settings).register(
        {"relative_path": "data/inbox/sample.csv", "format": "csv"},
        "origin-task", "inspect", decision("input_bytes", 200),
    )
    before = hashlib.sha256(settings.database_path.read_bytes()).hexdigest()
    args = build_parser().parse_args([
        "--project-root", str(tmp_path), "large-estimate", "qualification", record["id"],
    ])

    status, result = dispatch(args)

    after = hashlib.sha256(settings.database_path.read_bytes()).hexdigest()
    assert status == 0
    assert result["estimate_only"] is True
    assert result["execution_started"] is False
    assert result["profile"]["rows"] == 1
    assert before == after
    with sqlite3.connect(settings.database_path.as_uri() + "?mode=ro", uri=True) as connection:
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone()


def test_profile_artifact_is_bounded_and_stores_only_aggregate_metadata(tmp_path):
    settings = Settings(tmp_path)
    source = tmp_path / "data/inbox/sample.csv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"period,value\n" + b"2026Q1,secret\n" * 30000)

    profile = profile_artifact(settings, {
        "relative_path": "data/inbox/sample.csv", "format": "csv",
    })

    assert profile["sample_bytes"] <= 256 * 1024
    assert "secret" not in json.dumps(profile)


def test_profile_rejects_parent_traversal_before_path_walk(tmp_path):
    profile = profile_artifact(Settings(tmp_path), {
        "relative_path": "../outside.csv", "format": "csv",
    })

    assert profile["profile_method"] == "size_only"
    assert profile["profile_reason"] == "invalid_source_path"


def test_resume_profile_scales_remaining_rows_but_retains_source_validation_work():
    remaining = remaining_production_profile(
        {"rows": 100, "cells": 400, "output_bytes": 1000, "source_bytes": 256},
        {"rows": 25},
    )

    assert remaining["rows"] == 75
    assert remaining["cells"] == 300
    assert remaining["output_bytes"] == 750
    assert remaining["source_bytes"] == 256
    assert remaining["profile_method"] == "checkpoint_remaining_work"
