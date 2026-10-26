"""Read-only workload profiling and adaptive duration estimates for large-file jobs."""

import csv
import io
import json
import math
import os
import sqlite3
import stat
import statistics
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

MODEL_VERSION = "large-duration-v1"
MAX_HISTORY_ROWS = 500
MAX_PROFILE_BYTES = 256 * 1024
MAX_PROFILE_ROWS = 500
_MIB = 1024 * 1024
_ENGINES = {
    "qualification": "large_file_trial",
    "production": "large_file_production",
}


@contextmanager
def read_only_connection(database_path):
    """Open an existing task database without creating or modifying it."""
    path = Path(database_path)
    if not path.is_file():
        yield None
        return
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.execute("PRAGMA query_only=ON")
    try:
        yield connection
    finally:
        connection.close()


def history_documents(connection):
    if connection is None:
        return []
    tables = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    if not tables:
        return []
    rows = connection.execute(
        "SELECT document FROM tasks ORDER BY rowid DESC LIMIT ?", (MAX_HISTORY_ROWS,),
    ).fetchall()
    documents = []
    for (encoded,) in rows:
        try:
            value = json.loads(encoded)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            documents.append(value)
    return documents


def _safe_local_path(settings, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("source_artifact_missing")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("invalid_source_path")
    original = settings.project_root / candidate
    current = original
    while current != settings.project_root:
        if current.is_symlink():
            raise ValueError("symbolic_link")
        current = current.parent
    path = settings._inside(relative)
    allowed = [settings._inside(f"{settings.data_dir}/{name}") for name in ("inbox", "raw")]
    if not any(path.is_relative_to(root) for root in allowed):
        raise ValueError("invalid_source_path")
    if not path.is_file():
        raise ValueError("source_artifact_missing")
    return path


def _sample_profile(sample, content_bytes, suffix, scope):
    """Estimate rows/output from a bounded prefix; never retain source cell values."""
    full_sample = content_bytes <= len(sample)
    complete = sample if full_sample else sample.rsplit(b"\n", 1)[0]
    if not complete:
        raise ValueError("sample_empty")
    text = complete.decode("utf-8-sig")
    delimiter = scope.get("delimiter")
    if delimiter is None:
        if suffix == ".csv":
            delimiter = ","
        elif suffix == ".tsv":
            delimiter = "\t"
        else:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",\t;|").delimiter
    if delimiter not in {",", "\t", ";", "|"}:
        raise ValueError("unsupported_delimiter")
    header_row = scope.get("header_row", 1)
    if type(header_row) is not int or not 1 <= header_row <= 100:
        raise ValueError("header_scope")
    stream = io.StringIO(text)
    reader = csv.reader(stream, delimiter=delimiter, strict=True)
    rows = []
    row_limit = MAX_PROFILE_ROWS + header_row
    for _, row in zip(range(row_limit), reader):
        rows.append(row)
    extra_row = next(reader, None) if len(rows) == row_limit else None
    rows_truncated = extra_row is not None
    if len(rows) <= header_row:
        raise ValueError("sample_has_no_data_rows")
    header = rows[header_row - 1]
    if not header:
        raise ValueError("header_invalid")
    data_rows = [row for row in rows[header_row:] if row]
    if not data_rows:
        raise ValueError("sample_has_no_data_rows")

    observed_data_rows = len(data_rows) + int(bool(extra_row))
    sampled_bytes = len(text[:stream.tell()].encode("utf-8"))
    bytes_per_record = max(1.0, sampled_bytes / max(1, observed_data_rows))
    output_sizes = [
        len((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        for row in data_rows
    ]
    output_per_record = max(1.0, statistics.mean(output_sizes))
    exact_sample = full_sample and not rows_truncated
    estimated_rows = len(data_rows) if exact_sample else max(
        len(data_rows), math.ceil(content_bytes / bytes_per_record),
    )
    estimated_rows = min(2_000_000, estimated_rows)
    columns = len(header)
    output_bytes = min(192 * _MIB, math.ceil(estimated_rows * output_per_record))
    sample_confidence = "medium" if len(data_rows) >= 30 else "low"
    if exact_sample:
        sample_confidence = "high"
    if estimated_rows > len(data_rows) * 20:
        sample_confidence = "low"
    return {
        "rows": estimated_rows,
        "columns": columns,
        "cells": estimated_rows * columns,
        "output_bytes": output_bytes,
        "sample_rows": observed_data_rows,
        "sample_bytes": len(sample),
        "profile_method": "bounded_prefix",
        "profile_confidence": sample_confidence,
    }


def profile_artifact(settings, scope):
    """Read file metadata plus at most 256 KiB of table content for a forecast."""
    profile = {
        "format": str(scope.get("format", "unknown")).lower(),
        "profile_method": "size_only",
        "profile_confidence": "low",
    }
    try:
        path = _safe_local_path(settings, scope.get("relative_path"))
        file_stat = path.stat()
        profile["source_bytes"] = file_stat.st_size
        if file_stat.st_size >= 128 * _MIB:
            raise ValueError("input_budget")
        suffix = path.suffix.lower()
        content_bytes = file_stat.st_size
        if suffix == ".zip":
            with path.open("rb") as archive_stream, zipfile.ZipFile(archive_stream) as archive:
                entries = archive.infolist()
                if not entries or len(entries) >= 1000:
                    raise ValueError("archive_entries")
                members = []
                names = set()
                for item in entries:
                    name = item.filename
                    if (name in names or "\\" in name or name.startswith("/")
                            or ".." in PurePosixPath(name).parts or ":" in name
                            or item.flag_bits & 1
                            or stat.S_ISLNK(item.external_attr >> 16)):
                        raise ValueError("archive_security")
                    names.add(name)
                    if item.file_size / max(1, item.compress_size) >= 200:
                        raise ValueError("archive_ratio")
                    if not item.is_dir() and PurePosixPath(name).suffix.lower() in {
                        ".csv", ".tsv", ".txt",
                    }:
                        members.append(item)
                selected = scope.get("zip_member")
                if selected is not None:
                    members = [item for item in members if item.filename == selected]
                if len(members) != 1:
                    raise ValueError("archive_selection")
                member = members[0]
                if member.file_size >= 128 * _MIB:
                    raise ValueError("member_budget")
                suffix = PurePosixPath(member.filename).suffix.lower()
                content_bytes = member.file_size
                with archive.open(member) as source:
                    sample = source.read(MAX_PROFILE_BYTES)
        else:
            if suffix not in {".csv", ".tsv", ".txt"}:
                raise ValueError("unsupported_trial_format")
            if file_stat.st_size >= 128 * _MIB:
                raise ValueError("input_budget")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as source:
                sample = source.read(MAX_PROFILE_BYTES)
        profile["content_bytes"] = content_bytes
        profile["format"] = suffix.lstrip(".")
        profile.update(_sample_profile(sample, content_bytes, suffix, scope))
    except (OSError, ValueError, UnicodeError, csv.Error, zipfile.BadZipFile,
            RuntimeError, EOFError) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        profile["profile_reason"] = reason[:80] or "profile_unavailable"
    return profile


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _stage_duration(doc, stage):
    started = _parse_timestamp(stage.get("started_at"))
    finished = _parse_timestamp(stage.get("finished_at"))
    if started is not None and finished is not None:
        seconds = (finished - started).total_seconds()
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    result = stage.get("result") or {}
    payload = result.get("payload") if isinstance(result, dict) else None
    seconds = payload.get("elapsed_seconds") if isinstance(payload, dict) else None
    return seconds if isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds >= 0 else None


def _engine_for(operation):
    if operation not in _ENGINES:
        raise ValueError("unsupported_duration_operation")
    return _ENGINES[operation]


def _profile_from_task(inputs, payload, operation):
    saved = inputs.get("duration_profile")
    if isinstance(saved, dict):
        return saved
    scope = inputs.get("scope") if isinstance(inputs.get("scope"), dict) else {}
    stat_data = inputs.get("source_stat") if isinstance(inputs.get("source_stat"), dict) else {}
    source_bytes = stat_data.get("st_size", inputs.get("raw_size"))
    rows = payload.get("rows")
    columns = payload.get("columns")
    cells = payload.get("cells")
    if cells is None and isinstance(rows, int) and isinstance(columns, int):
        cells = rows * columns
    return {
        "format": str(scope.get("format", "zip" if operation == "production" else "unknown")).lower(),
        "source_bytes": source_bytes,
        "rows": rows,
        "columns": columns,
        "cells": cells,
        "output_bytes": payload.get("output_bytes"),
        "content_bytes": inputs.get("member_bytes"),
        "profile_method": "saved_execution_metrics",
        "profile_confidence": "medium" if rows and columns else "low",
    }


def _successful_samples(documents, operation):
    expected_engine = _engine_for(operation)
    samples = []
    for doc in documents:
        plan = doc.get("plan")
        stages = doc.get("stages")
        if (doc.get("status") != "COMPLETED" or not isinstance(plan, list) or not plan
                or not isinstance(stages, list) or not stages):
            continue
        stage_plan = plan[0]
        if not isinstance(stage_plan, dict) or stage_plan.get("engine") != expected_engine:
            continue
        stage = stages[-1]
        result = stage.get("result") if isinstance(stage, dict) else None
        payload = result.get("payload") if isinstance(result, dict) else None
        if (not isinstance(payload, dict) or stage.get("status") != "SUCCEEDED"
                or payload.get("execution_state") not in {
                    "TRIAL_PASSED", "COMPLETED",
                }):
            continue
        actual = _stage_duration(doc, stage)
        if actual is None:
            continue
        inputs = stage_plan.get("input_data")
        if not isinstance(inputs, dict):
            continue
        profile = _profile_from_task(inputs, payload, operation)
        samples.append({
            "profile": profile,
            "seconds": max(0.01, actual),
            "estimate": inputs.get("duration_estimate"),
        })
    return samples


def _positive(profile, name):
    value = profile.get(name)
    return value if type(value) is int and value > 0 else None


def _work_units(profile):
    output_bytes = _positive(profile, "output_bytes") or 0
    cells = _positive(profile, "cells") or 0
    source_bytes = _positive(profile, "source_bytes") or 0
    return max(1, output_bytes + cells * 8 + source_bytes)


def _distance(left, right):
    score = 0.0
    weight = 0
    for name, factor in (("output_bytes", 1.0), ("cells", 1.0), ("columns", 0.75),
                         ("content_bytes", 0.5)):
        a, b = _positive(left, name), _positive(right, name)
        if a is None or b is None:
            continue
        score += abs(math.log(a / b)) * factor
        weight += factor
    if not weight:
        a, b = _positive(left, "source_bytes"), _positive(right, "source_bytes")
        if a is not None and b is not None:
            score += abs(math.log(a / b))
            weight = 1
    if not weight:
        return 10.0
    if left.get("format") and right.get("format") and left["format"] != right["format"]:
        score += 1.5
    return score / weight


def _percentile(values, quantile):
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _ape_by_task(documents, operation, model):
    expected_engine = _engine_for(operation)
    errors = {}
    for doc in documents:
        plan, stages = doc.get("plan"), doc.get("stages")
        if (doc.get("status") != "COMPLETED" or not isinstance(plan, list) or not plan
                or not isinstance(stages, list) or not stages
                or not isinstance(plan[0], dict) or plan[0].get("engine") != expected_engine):
            continue
        inputs = plan[0].get("input_data")
        estimate = inputs.get("duration_estimate") if isinstance(inputs, dict) else None
        if not isinstance(estimate, dict) or estimate.get("model_version") != MODEL_VERSION:
            continue
        candidates = estimate.get("candidate_models") if isinstance(estimate, dict) else None
        prediction = candidates.get(model) if isinstance(candidates, dict) else None
        predicted_seconds = prediction.get("seconds") if isinstance(prediction, dict) else None
        stage = stages[-1]
        if not isinstance(stage, dict):
            continue
        result = stage.get("result") or {}
        payload = result.get("payload") if isinstance(result, dict) else None
        if (not isinstance(predicted_seconds, (int, float)) or predicted_seconds <= 0
                or not isinstance(payload, dict) or stage.get("status") != "SUCCEEDED"
                or payload.get("execution_state") not in {"TRIAL_PASSED", "COMPLETED"}):
            continue
        actual = _stage_duration(doc, stage)
        if actual is not None and isinstance(doc.get("task_id"), str):
            errors[doc["task_id"]] = abs(predicted_seconds - actual) / max(0.01, actual)
    return errors


def _weighted_median(values):
    if not values:
        return None
    ordered = sorted(values, key=lambda pair: pair[0])
    total = sum(weight for _, weight in ordered)
    cursor = 0.0
    for value, weight in ordered:
        cursor += weight
        if cursor >= total / 2:
            return value
    return ordered[-1][0]


def estimate_duration(operation, profile, documents, *, wall_seconds):
    """Return two shadow forecasts, a selected estimate, and evidence-based confidence."""
    engine = _engine_for(operation)
    profile = dict(profile)
    samples = _successful_samples(documents, operation)
    work = _work_units(profile)
    rates = [sample["seconds"] / _work_units(sample["profile"]) for sample in samples]
    prior_rate = 0.020 / _MIB
    observed_rate = statistics.median(rates) if rates else prior_rate
    # A three-sample prior damps a handful of unusually small or cached executions.
    blended_rate = (prior_rate * 3 + observed_rate * len(rates)) / (3 + len(rates))
    baseline_seconds = max(0.1, 0.12 + blended_rate * work)

    neighbors = sorted(
        (( _distance(profile, sample["profile"]), sample) for sample in samples),
        key=lambda item: item[0],
    )[:5]
    empirical_values = []
    for distance, sample in neighbors:
        sample_work = _work_units(sample["profile"])
        scaled = max(0.05, (sample["seconds"] - 0.12) * work / sample_work + 0.12)
        empirical_values.append((scaled, 1 / (0.25 + distance)))
    empirical_seconds = _weighted_median(empirical_values) or baseline_seconds

    baseline_errors = _ape_by_task(documents, operation, "baseline")
    empirical_errors = _ape_by_task(documents, operation, "empirical")
    paired_tasks = baseline_errors.keys() & empirical_errors.keys()
    comparisons = len(paired_tasks)
    if comparisons >= 3:
        baseline_mape = statistics.median(baseline_errors[task] for task in paired_tasks)
        empirical_mape = statistics.median(empirical_errors[task] for task in paired_tasks)
        selected = "baseline" if baseline_mape <= empirical_mape else "empirical"
        selection_reason = "lower_median_absolute_percentage_error"
    elif len(neighbors) >= 3:
        selected = "empirical"
        selection_reason = "three_or_more_similar_successful_runs"
    else:
        selected = "baseline"
        selection_reason = "shadow_comparison_warming_up"

    point = baseline_seconds if selected == "baseline" else empirical_seconds
    nearest_distance = neighbors[0][0] if neighbors else None
    if len(neighbors) >= 3:
        adjusted = [
            max(0.05, (sample["seconds"] - 0.12) * work / _work_units(sample["profile"]) + 0.12)
            for _, sample in neighbors
        ]
        lower = _percentile(adjusted, 0.2)
        upper = _percentile(adjusted, 0.8)
    else:
        lower, upper = point * 0.5, point * 2.0
    profile_confidence = profile.get("profile_confidence", "low")
    if profile_confidence == "low":
        lower = min(lower, point * 0.5)
        upper = max(upper, point * 2.0)
    lower = max(0.1, min(point, lower))
    upper = max(point, upper, lower)

    if len(neighbors) >= 10 and nearest_distance is not None and nearest_distance < 0.35:
        confidence = "high" if profile_confidence == "high" else "medium"
    elif len(neighbors) >= 3 and nearest_distance is not None and nearest_distance < 1.0:
        confidence = "medium" if profile_confidence != "low" else "low"
    else:
        confidence = "low"
    baseline_mape = (
        statistics.median(baseline_errors[task] for task in paired_tasks) if comparisons else None
    )
    empirical_mape = (
        statistics.median(empirical_errors[task] for task in paired_tasks) if comparisons else None
    )
    profile_reason = profile.get("profile_reason")
    return {
        "model_version": MODEL_VERSION,
        "operation": operation,
        "engine": engine,
        "duration_scope": "engine stage wall time; excludes human review and unrelated setup",
        "estimated_seconds": round(point, 3),
        "range_seconds": {"lower": round(lower, 3), "upper": round(upper, 3)},
        "confidence": confidence,
        "history_sample_count": len(samples),
        "similar_sample_count": len(neighbors),
        "shadow_comparison_count": comparisons,
        "selected_model": selected,
        "selection_reason": selection_reason,
        "candidate_models": {
            "baseline": {"seconds": round(baseline_seconds, 3)},
            "empirical": {"seconds": round(empirical_seconds, 3)},
        },
        "median_absolute_percentage_error": {
            "baseline": round(baseline_mape, 4) if baseline_mape is not None else None,
            "empirical": round(empirical_mape, 4) if empirical_mape is not None else None,
        },
        "wall_budget_seconds": wall_seconds,
        "upper_estimate_reaches_wall_budget": upper >= wall_seconds,
        "profile_method": profile.get("profile_method", "unknown"),
        "profile_confidence": profile_confidence,
        "profile_reason": profile_reason,
        "profile": profile,
    }


def actual_stage_seconds(doc):
    stages = doc.get("stages")
    if not isinstance(stages, list) or not stages:
        return None
    value = _stage_duration(doc, stages[-1])
    return round(value, 3) if value is not None else None


def remaining_production_profile(profile, checkpoint):
    """Scale the production workload to unprocessed rows; retain source revalidation cost."""
    remaining = dict(profile)
    total_rows = _positive(profile, "rows")
    if total_rows is None or not isinstance(checkpoint, dict):
        remaining["profile_method"] = "resume_full_run_fallback"
        remaining["profile_confidence"] = "low"
        return remaining
    done_rows = checkpoint.get("rows", 0)
    if type(done_rows) is not int or done_rows < 0:
        done_rows = 0
    remaining_rows = max(0, total_rows - done_rows)
    ratio = remaining_rows / total_rows
    remaining["rows"] = remaining_rows
    for name in ("cells", "output_bytes"):
        value = _positive(profile, name)
        if value is not None:
            remaining[name] = math.ceil(value * ratio)
    remaining["profile_method"] = "checkpoint_remaining_work"
    if ratio < 0.1:
        remaining["profile_confidence"] = "low"
    return remaining


def read_checkpoint(settings, task_input):
    artifact_root = task_input.get("artifact_root")
    if (not isinstance(artifact_root, str)
            or not artifact_root.startswith(f"{settings.data_dir}/large_artifacts/")):
        return None
    relative_root = Path(artifact_root)
    if relative_root.is_absolute() or ".." in relative_root.parts:
        return None
    try:
        original = settings.project_root / artifact_root / "checkpoint.json"
        current = original
        while current != settings.project_root:
            if current.is_symlink():
                return None
            current = current.parent
        path = settings._inside(f"{artifact_root}/checkpoint.json")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None
