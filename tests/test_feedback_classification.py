"""Feedback classification preserves every frozen revision and never changes the ledger."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.feedback_cli import main as feedback_cli
from macro_data_platform.storage.feedback import FeedbackStore
from macro_data_platform.storage.feedback_classification import FeedbackClassificationStore
from macro_data_platform.storage.history import HistoryStore


def make_store(tmp_path):
    history = HistoryStore(Settings(tmp_path))
    with history.transaction() as connection:
        document = history.document("fixture task", datetime.now(UTC).isoformat())
        document["task_id"] = "task-a"
        history.insert(connection, document)
    feedback = FeedbackStore(history)
    return feedback, FeedbackClassificationStore(feedback)


def make_batch(snapshot):
    return {"snapshot_id": snapshot["snapshot_id"], "key_hash": snapshot["key_hash"],
            "source_hash": snapshot["source_hash"], "prompt_version": "manual-v1",
            "model_version": "model-v1", "reviewer_id": "reviewer-1",
            "privacy_cleared": True, "elapsed_ms": 120, "cost_usd": None,
            "rows": [{"feedback_id": row["feedback_id"], "revision": row["revision"],
                      "label": "unclassified", "reason": "privacy_excluded"}
                     for row in snapshot["rows"]]}


def test_snapshot_keeps_all_revisions_and_import_never_edits_feedback(tmp_path):
    feedback, classifications = make_store(tmp_path)
    first = feedback.record("task-a", text="private original")
    feedback.revise(first["feedback_id"], expected_revision=1, changes={"text": "private revision"})
    before = feedback.history_for(first["feedback_id"])
    snapshot = classifications.snapshot()
    assert snapshot["row_count"] == 2
    assert "private" not in str(snapshot)
    feedback.revise(first["feedback_id"], expected_revision=2, changes={"text": "later revision"})
    batch = classifications.import_batch(make_batch(snapshot))
    assert batch["row_count"] == 2
    assert feedback.history_for(first["feedback_id"])[:2] == before
    assert feedback.get(first["feedback_id"])["revision"] == 3
    assert classifications.batches()[0]["batch_id"] == batch["batch_id"]
    assert len(classifications.batch_rows(batch["batch_id"])) == 2


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "hash", "privacy"])
def test_invalid_batch_is_rejected_without_partial_write(tmp_path, mutation):
    feedback, classifications = make_store(tmp_path)
    feedback.record("task-a", text="a")
    feedback.record("task-a", text="b")
    snapshot = classifications.snapshot()
    batch = make_batch(snapshot)
    if mutation == "missing":
        batch["rows"].pop()
    elif mutation == "duplicate":
        batch["rows"].append(deepcopy(batch["rows"][0]))
    elif mutation == "extra":
        batch["rows"][0]["feedback_id"] = "unknown"
    elif mutation == "hash":
        batch["key_hash"] = "0" * 64
    else:
        batch["privacy_cleared"] = False
    with pytest.raises(ValueError):
        classifications.import_batch(batch)
    assert classifications.batches() == []


def test_operator_cli_snapshots_and_imports_without_changing_revision(tmp_path, capsys):
    feedback, _ = make_store(tmp_path)
    item = feedback.record("task-a", text="sensitive feedback")
    assert feedback_cli(["--project-root", str(tmp_path), "classification-snapshot"]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert "sensitive feedback" not in str(snapshot)
    path = tmp_path / "results.json"
    path.write_text(json.dumps(make_batch(snapshot)), encoding="utf-8")
    assert feedback_cli(["--project-root", str(tmp_path), "classification-import",
                         "--results", str(path), "--privacy-cleared"]) == 0
    batch = json.loads(capsys.readouterr().out)
    assert feedback_cli(["--project-root", str(tmp_path), "classification-show",
                         "--batch-id", batch["batch_id"]]) == 0
    assert json.loads(capsys.readouterr().out)[0]["feedback_id"] == item["feedback_id"]
    assert feedback.get(item["feedback_id"])["revision"] == 1


def test_tampered_original_revision_blocks_import(tmp_path):
    feedback, classifications = make_store(tmp_path)
    item = feedback.record("task-a", text="original")
    snapshot = classifications.snapshot()
    with feedback.history.transaction() as connection:
        connection.execute("UPDATE feedback_revisions SET document=? WHERE feedback_id=?",
                           ('{"altered":true}', item["feedback_id"]))
    with pytest.raises(ValueError, match="source revision mismatch"):
        classifications.import_batch(make_batch(snapshot))
    assert classifications.batches() == []
