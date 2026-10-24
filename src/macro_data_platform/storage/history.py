"""Atomic SQLite task snapshots plus append-only events; no observation storage."""
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from macro_data_platform.config import Settings


class HistoryStore:
    @staticmethod
    def document(request: str, created_at: str) -> dict:
        return {
            "task_id": str(uuid4()), "request": request, "created_at": created_at,
            "status": "CREATED", "plan": None, "attempts": [], "stages": [],
            "active_token": None, "cancel_requested": False,
        }

    @staticmethod
    def insert(connection, document: dict, idempotency_key: str | None = None) -> None:
        connection.execute(
            "INSERT INTO tasks(task_id, idempotency_key, document) VALUES (?, ?, ?)",
            (document["task_id"], idempotency_key,
             json.dumps(document, ensure_ascii=False, allow_nan=False)),
        )

    @staticmethod
    def by_key(connection, key: str | None) -> dict | None:
        if key is None:
            return None
        row = connection.execute(
            "SELECT document FROM tasks WHERE idempotency_key=?", (key,),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def __init__(self, settings: Settings):
        self.settings = settings
        path = settings.database_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 2}:
                raise ValueError("unsupported history schema version")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    body TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_by_task ON task_events(task_id, event_id);
                PRAGMA user_version=2;
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Re-evaluate containment for every open, including after a symlink change.
        connection = sqlite3.connect(self.settings.database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def load(connection: sqlite3.Connection, task_id: str) -> dict:
        row = connection.execute("SELECT document FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("unknown task identifier")
        return json.loads(row[0])

    @staticmethod
    def save(connection: sqlite3.Connection, document: dict) -> None:
        connection.execute(
            "UPDATE tasks SET document=? WHERE task_id=?",
            (json.dumps(document, ensure_ascii=False, allow_nan=False), document["task_id"]),
        )

    @staticmethod
    def event(connection: sqlite3.Connection, task_id: str, body: dict) -> None:
        connection.execute(
            "INSERT INTO task_events(task_id, body) VALUES (?, ?)",
            (task_id, json.dumps(body, ensure_ascii=False, allow_nan=False)),
        )

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self.load(connection, task_id)

    def events(self, task_id: str) -> list[dict]:
        with self._connect() as connection:
            self.load(connection, task_id)
            rows = connection.execute(
                "SELECT event_id, body FROM task_events WHERE task_id=? ORDER BY event_id",
                (task_id,),
            ).fetchall()
            return [{"event_id": row[0], **json.loads(row[1])} for row in rows]
