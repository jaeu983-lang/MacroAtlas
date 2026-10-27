"""Validated persistence for privacy-safe numeric performance samples."""
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from macro_data_platform.performance.metrics import (
    CACHE_STATES,
    PHASES,
    SAMPLE_CLASSES,
    workload_tier,
)

_LABEL = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z", re.ASCII)
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_COUNT_FIELDS = (
    "task_attempt_no", "attempt_no", "duration_ns", "input_bytes", "input_rows",
    "input_columns", "output_bytes", "output_rows", "output_columns",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS performance_samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    execution_scope TEXT NOT NULL,
    engine TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    task_attempt_no INTEGER,
    attempt_no INTEGER,
    duration_ns INTEGER NOT NULL CHECK(duration_ns >= 0),
    input_bytes INTEGER,
    input_rows INTEGER,
    input_columns INTEGER,
    output_bytes INTEGER,
    output_rows INTEGER,
    output_columns INTEGER,
    workload_tier TEXT NOT NULL,
    sample_class TEXT NOT NULL,
    cache_status TEXT NOT NULL,
    phase_timings_json TEXT NOT NULL,
    code_sha TEXT NOT NULL,
    python_version TEXT NOT NULL,
    platform TEXT NOT NULL,
    architecture TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS performance_group_lookup
    ON performance_samples(engine, engine_version, stage, workload_tier, sample_id);
"""


def ensure_schema(connection):
    connection.executescript(SCHEMA)


def _label(value, fallback="unknown"):
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else fallback


def prepare_sample(sample):
    """Reject arbitrary text and JSON so raw prompts/URLs cannot enter this table."""
    if not isinstance(sample, dict):
        raise TypeError("performance sample must be an object")
    phases = sample.get("phase_timings_ns", {})
    if not isinstance(phases, dict) or set(phases) - PHASES:
        raise ValueError("performance phases are unsupported")
    if any(type(value) is not int or value < 0 for value in phases.values()):
        raise ValueError("performance phase times must be nonnegative integers")
    counts = {}
    for field in _COUNT_FIELDS:
        value = sample.get(field)
        if value is not None and (type(value) is not int or value < 0 or value > 10**15):
            raise ValueError("performance counts must be nonnegative integers")
        counts[field] = value
    observed_at = sample.get("observed_at")
    if not isinstance(observed_at, str) or len(observed_at) > 40:
        raise ValueError("performance timestamp must be UTC text")
    try:
        parsed = datetime.fromisoformat(observed_at)
    except ValueError:
        raise ValueError("performance timestamp must be UTC text") from None
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("performance timestamp must be UTC text")
    sample_class = sample.get("sample_class", "unspecified")
    cache_status = sample.get("cache_status", "not_applicable")
    if (not isinstance(sample_class, str) or sample_class not in SAMPLE_CLASSES or
            not isinstance(cache_status, str) or cache_status not in CACHE_STATES):
        raise ValueError("performance sample classification is unsupported")
    code_sha = sample.get("code_sha", "unknown")
    if code_sha != "unknown" and (not isinstance(code_sha, str) or not _SHA.fullmatch(code_sha)):
        raise ValueError("code SHA is invalid")
    environment = sample.get("environment", {})
    if not isinstance(environment, dict) or set(environment) != {
        "python_version", "platform", "architecture",
    }:
        raise ValueError("performance environment is unsupported")
    return {
        "observed_at": observed_at,
        "execution_scope": _label(sample.get("execution_scope")),
        "engine": _label(sample.get("engine"), "custom"),
        "engine_version": _label(sample.get("engine_version")),
        "stage": _label(sample.get("stage"), "custom"),
        "status": _label(sample.get("status")),
        **counts,
        "workload_tier": _label(sample.get("workload_tier"), "unknown"),
        "sample_class": sample_class,
        "cache_status": cache_status,
        "phase_timings_json": json.dumps(phases, sort_keys=True, separators=(",", ":")),
        "code_sha": code_sha,
        "python_version": _label(environment.get("python_version")),
        "platform": _label(environment.get("platform")),
        "architecture": _label(environment.get("architecture")),
    }


def insert_sample(connection, sample):
    row = prepare_sample(sample)
    ensure_schema(connection)
    columns = tuple(row)
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO performance_samples ({','.join(columns)}) VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def append_sample(settings, sample):
    path = settings.performance_database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
        insert_sample(connection, sample)


def build_sample(*, observed_at, execution_scope, engine, engine_version, stage, status,
                 duration_ns, task_attempt_no=None, attempt_no=None, metrics=None,
                 environment=None):
    metrics = metrics or {}
    environment = environment or {}
    input_bytes = metrics.get("input_bytes")
    input_rows = metrics.get("input_rows")
    return {
        "observed_at": observed_at,
        "execution_scope": execution_scope,
        "engine": engine,
        "engine_version": engine_version,
        "stage": stage,
        "status": status,
        "task_attempt_no": task_attempt_no,
        "attempt_no": attempt_no,
        "duration_ns": duration_ns,
        "input_bytes": input_bytes,
        "input_rows": input_rows,
        "input_columns": metrics.get("input_columns"),
        "output_bytes": metrics.get("output_bytes"),
        "output_rows": metrics.get("output_rows"),
        "output_columns": metrics.get("output_columns"),
        "workload_tier": workload_tier(input_bytes, input_rows),
        "sample_class": metrics.get("sample_class", "unspecified"),
        "cache_status": metrics.get("cache_status", "not_applicable"),
        "phase_timings_ns": metrics.get("phase_timings_ns", {}),
        "code_sha": environment.get("code_sha", "unknown"),
        "environment": {name: environment.get(name, "unknown") for name in (
            "python_version", "platform", "architecture",
        )},
    }
