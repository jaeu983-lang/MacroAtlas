"""Store GPT-authored test interactions separately from real user feedback."""

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from macro_data_platform.config import Settings

_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_FIELDS = {"case_id", "question", "observed_answer", "answer_origin", "outcome", "feedback",
           "generator", "engine_version", "catalog_sha256"}


def _validate(case):
    if not isinstance(case, dict) or set(case) != _FIELDS:
        raise ValueError("invalid synthetic case fields")
    for name in ("case_id", "generator", "engine_version"):
        if not isinstance(case[name], str) or not _ID.fullmatch(case[name]):
            raise ValueError(f"invalid {name}")
    if not isinstance(case["question"], str) or not 1 <= len(case["question"].strip()) <= 2000:
        raise ValueError("invalid question")
    if not isinstance(case["observed_answer"], dict):
        raise TypeError("observed answer must be structured")
    if case["answer_origin"] not in {"engine", "synthetic"}:
        raise ValueError("invalid answer origin")
    if case["outcome"] not in {"answered", "needs_correction", "unresolved"}:
        raise ValueError("invalid outcome")
    feedback = case["feedback"]
    if case["outcome"] in {"answered", "unresolved"} and feedback is not None:
        raise ValueError("answered or unresolved cases must not invent feedback")
    if case["outcome"] == "needs_correction" and (
            not isinstance(feedback, str) or not feedback.strip()):
        raise ValueError("correction needs specific feedback")
    if feedback is not None and (not isinstance(feedback, str) or len(feedback) > 2000):
        raise ValueError("invalid feedback")
    if not isinstance(case["catalog_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", case["catalog_sha256"]):
        raise ValueError("invalid catalog hash")
    encoded = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False)
    if len(encoded.encode("utf-8")) > 16000:
        raise ValueError("synthetic case exceeds size limit")
    return encoded


class SyntheticFeedbackStore:
    """A separate database; imported examples never become user feedback or evaluation cases."""

    def __init__(self, settings: Settings):
        self.settings = settings
        requested = settings.project_root / settings.data_dir / "synthetic_feedback.sqlite"
        if requested.is_symlink():
            raise ValueError("synthetic database must not be a symlink")
        self.path = settings._inside(f"{settings.data_dir}/synthetic_feedback.sqlite")
        if self.path == settings.database_path:
            raise ValueError("synthetic and user feedback databases must be separate")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS synthetic_interactions (
                case_id TEXT PRIMARY KEY, origin TEXT NOT NULL CHECK(origin='gpt_synthetic'),
                recorded_at TEXT NOT NULL, document TEXT NOT NULL, sha256 TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS synthetic_runs (
                run_id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, model TEXT NOT NULL,
                prompt_sha256 TEXT NOT NULL, elapsed_ms INTEGER NOT NULL,
                input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, case_count INTEGER NOT NULL,
                local_elapsed_ms INTEGER NOT NULL DEFAULT 0)""")
            if "local_elapsed_ms" not in {row[1] for row in db.execute("PRAGMA table_info(synthetic_runs)")}:
                db.execute("ALTER TABLE synthetic_runs ADD COLUMN local_elapsed_ms INTEGER NOT NULL DEFAULT 0")

    def import_cases(self, cases, *, run=None):
        if not isinstance(cases, list) or not cases or len(cases) > 500:
            raise ValueError("expected 1 to 500 synthetic cases")
        prepared = [(case["case_id"], _validate(case)) for case in cases]
        if len({key for key, _ in prepared}) != len(prepared):
            raise ValueError("duplicate synthetic case ID")
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            inserted = 0
            for case_id, document in prepared:
                digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
                existing = db.execute("SELECT sha256 FROM synthetic_interactions WHERE case_id=?",
                                      (case_id,)).fetchone()
                if existing:
                    if existing[0] != digest:
                        raise ValueError("synthetic case ID conflicts with existing record")
                    continue
                db.execute("INSERT INTO synthetic_interactions VALUES (?, ?, ?, ?, ?)",
                           (case_id, "gpt_synthetic", datetime.now(UTC).isoformat(), document, digest))
                inserted += 1
            if run is not None:
                db.execute("INSERT INTO synthetic_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (run["run_id"], datetime.now(UTC).isoformat(), run["model"],
                            run["prompt_sha256"], run["elapsed_ms"], run["input_tokens"],
                            run["output_tokens"], None, len(cases), run["local_elapsed_ms"]))
        return {"origin": "gpt_synthetic", "submitted": len(cases), "inserted": inserted}

    def list_cases(self):
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT document FROM synthetic_interactions ORDER BY rowid").fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_runs(self):
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT run_id, recorded_at, model, prompt_sha256, elapsed_ms, "
                              "local_elapsed_ms, input_tokens, output_tokens, cost_usd, case_count "
                              "FROM synthetic_runs ORDER BY rowid").fetchall()
        keys = ("run_id", "recorded_at", "model", "prompt_sha256", "model_elapsed_ms",
                "local_elapsed_ms", "input_tokens", "output_tokens", "cost_usd", "case_count")
        return [dict(zip(keys, row, strict=True)) for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("import", help="import explicitly synthetic GPT-authored examples")
    add.add_argument("--file", type=Path, required=True)
    commands.add_parser("list", help="list synthetic interactions")
    commands.add_parser("runs", help="list synthetic GPT execution metadata")
    args = parser.parse_args(argv)
    store = SyntheticFeedbackStore(Settings(args.project_root))
    if args.command == "import":
        result = store.import_cases(json.loads(args.file.read_text(encoding="utf-8")))
    elif args.command == "list":
        result = store.list_cases()
    else:
        result = store.list_runs()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
