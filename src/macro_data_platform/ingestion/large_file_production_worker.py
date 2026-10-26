"""Standalone bounded BIS flat CSV worker; it never infers economic meaning."""

import csv
import hashlib
import io
import json
import os
import re
import resource
import sqlite3
import stat
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath


class StopJob(Exception):
    def __init__(self, reason, *, retryable=False):
        self.reason = reason
        self.retryable = retryable


MAX_ROW_CHARS = 8 * 1024 * 1024


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, document):
    temporary = path.with_name(path.name + ".pending")
    if temporary.exists() or temporary.is_symlink():
        raise StopJob("manifest_write_collision")
    encoded = json.dumps(document, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cancelled(database, task_id):
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        row = connection.execute("SELECT document FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise StopJob("task_disappeared")
        return bool(json.loads(row[0]).get("cancel_requested"))
    finally:
        connection.close()


def _validate_archive(archive, expected_member):
    infos = archive.infolist()
    if not infos or len(infos) >= 1000:
        raise StopJob("archive_entries")
    names = set()
    for item in infos:
        name = item.filename
        if (name in names or "\\" in name or name.startswith("/")
                or ".." in PurePosixPath(name).parts or ":" in name
                or item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16)):
            raise StopJob("archive_security")
        names.add(name)
        if item.file_size / max(1, item.compress_size) >= 200:
            raise StopJob("archive_ratio")
        if item.file_size > 256 * 1024 * 1024:
            raise StopJob("archive_budget")
    matches = [item for item in infos if item.filename == expected_member]
    if len(matches) != 1:
        raise StopJob("archive_member_changed")
    item = matches[0]
    if PurePosixPath(item.filename).suffix.lower() != ".csv":
        raise StopJob("unsupported_member")
    if item.file_size >= 128 * 1024 * 1024:
        raise StopJob("member_budget")
    return item


def _binding(job):
    return {
        "task_id": job["task_id"],
        "deferral_id": job["deferral_id"],
        "deferral_event_seq": job["deferral_event_seq"],
        "raw_sha256": job["raw_sha256"],
        "request_manifest_sha256": job["request_manifest_sha256"],
        "zip_member": job["zip_member"],
        "engine_fingerprint": job["engine_fingerprint"],
        "budget": job["budget"],
    }


def _load_checkpoint(path, binding):
    if not path.exists():
        return {
            "version": 1, "binding": binding, "headers": None, "header_row": 1,
            "next_data_row": 0, "rows": 0, "cells": 0, "empty_fields": 0,
            "zero_fields": 0, "output_bytes": 0, "chunks": [],
        }
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise StopJob("checkpoint_integrity")
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise StopJob("checkpoint_integrity") from None
    if not isinstance(checkpoint, dict) or checkpoint.get("version") != 1:
        raise StopJob("checkpoint_version")
    if checkpoint.get("binding") != binding:
        raise StopJob("checkpoint_binding_changed")
    chunks = checkpoint.get("chunks")
    if not isinstance(chunks, list) or len(chunks) > 200:
        raise StopJob("checkpoint_integrity")
    expected_files = set()
    for number, chunk in enumerate(chunks, 1):
        name = f"chunk-{number:04d}.jsonl"
        if (not isinstance(chunk, dict) or chunk.get("path") != name
                or type(chunk.get("rows")) is not int or chunk["rows"] < 1
                or type(chunk.get("bytes")) is not int or chunk["bytes"] < 1
                or not isinstance(chunk.get("sha256"), str)):
            raise StopJob("checkpoint_integrity")
        file_path = path.parent / name
        if file_path.is_symlink() or not file_path.is_file():
            raise StopJob("checkpoint_chunk_missing")
        if file_path.stat().st_size != chunk.get("bytes") or _sha256(file_path) != chunk.get("sha256"):
            raise StopJob("checkpoint_chunk_changed")
        expected_files.add(name)
    if checkpoint.get("next_data_row") != checkpoint.get("rows"):
        raise StopJob("checkpoint_integrity")
    if (sum(chunk["rows"] for chunk in chunks) != checkpoint.get("rows")
            or sum(chunk["bytes"] for chunk in chunks) != checkpoint.get("output_bytes")
            or checkpoint.get("cells") != checkpoint.get("rows") * len(checkpoint.get("headers") or [])):
        raise StopJob("checkpoint_integrity")
    for candidate in path.parent.iterdir():
        if candidate.name.endswith(".pending"):
            if candidate.is_symlink() or not candidate.is_file():
                raise StopJob("checkpoint_integrity")
            if (candidate.name not in {"checkpoint.json.pending", "output_manifest.json.pending"}
                    and not re.fullmatch(r"chunk-\d{4}\.jsonl\.pending", candidate.name)):
                raise StopJob("unexpected_artifact")
            candidate.unlink()
        elif candidate.name.startswith("chunk-") and candidate.name.endswith(".jsonl"):
            if candidate.is_symlink() or not candidate.is_file():
                raise StopJob("checkpoint_integrity")
            if candidate.name not in expected_files:
                # A process may have died between chunk rename and checkpoint commit.
                expected_next = f"chunk-{len(chunks) + 1:04d}.jsonl"
                if candidate.name != expected_next:
                    raise StopJob("checkpoint_orphan_chunk")
                candidate.unlink()
        elif candidate.name not in {"checkpoint.json", "output_manifest.json", "job.json"}:
            raise StopJob("unexpected_artifact")
    return checkpoint


def run(job):
    limits = job["budget"]
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_bytes"], limits["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"], limits["output_bytes"]))
    started = time.monotonic()
    raw_path = Path(job["raw_path"])
    request_path = Path(job["request_manifest_path"])
    artifact_root = Path(job["artifact_root"])
    database_path = Path(job["database_path"])
    for path in (raw_path, request_path, artifact_root, database_path):
        if path.is_symlink() or any(part.is_symlink() for part in path.parents):
            raise StopJob("symbolic_link")
    if not raw_path.is_file() or not request_path.is_file() or not artifact_root.is_dir():
        raise StopJob("artifact_missing")
    if raw_path.stat().st_size > limits["input_bytes"]:
        raise StopJob("input_budget")
    if _sha256(raw_path) != job["raw_sha256"]:
        raise StopJob("source_changed_since_binding")
    if _sha256(request_path) != job["request_manifest_sha256"]:
        raise StopJob("request_manifest_changed")

    checkpoint_path = artifact_root / "checkpoint.json"
    output_manifest_path = artifact_root / "output_manifest.json"
    binding = _binding(job)
    if output_manifest_path.exists():
        if (output_manifest_path.is_symlink() or not output_manifest_path.is_file()
                or output_manifest_path.stat().st_size > 1024 * 1024):
            raise StopJob("output_manifest_integrity")
        manifest = json.loads(output_manifest_path.read_text(encoding="utf-8"))
        if manifest.get("binding") != binding:
            raise StopJob("output_manifest_binding_changed")
        checkpoint = manifest.get("checkpoint")
        checkpoint_path = artifact_root / "checkpoint.json"
        if (not isinstance(checkpoint, dict) or checkpoint.get("path") != "checkpoint.json"
                or checkpoint_path.is_symlink() or not checkpoint_path.is_file()
                or checkpoint_path.stat().st_size != checkpoint.get("bytes")
                or _sha256(checkpoint_path) != checkpoint.get("sha256")):
            raise StopJob("checkpoint_integrity")
        if not isinstance(manifest.get("chunks"), list) or len(manifest["chunks"]) > 200:
            raise StopJob("output_manifest_integrity")
        if (sum(chunk.get("rows", -1) for chunk in manifest["chunks"])
                != manifest.get("rows")
                or sum(chunk.get("bytes", -1) for chunk in manifest["chunks"])
                != manifest.get("output_bytes")
                or manifest.get("cells") != manifest.get("rows") * manifest.get("columns")):
            raise StopJob("output_manifest_integrity")
        for number, chunk in enumerate(manifest.get("chunks", []), 1):
            expected_name = f"chunk-{number:04d}.jsonl"
            if not isinstance(chunk, dict) or chunk.get("path") != expected_name:
                raise StopJob("output_manifest_integrity")
            file_path = artifact_root / chunk["path"]
            if (file_path.is_symlink() or not file_path.is_file()
                    or file_path.stat().st_size != chunk["bytes"]
                    or _sha256(file_path) != chunk["sha256"]):
                raise StopJob("output_chunk_changed")
        return {"execution_state": "COMPLETED", **manifest,
                "elapsed_seconds": time.monotonic() - started}

    checkpoint = _load_checkpoint(checkpoint_path, binding)
    csv.field_size_limit(1024 * 1024)
    with raw_path.open("rb") as raw_stream:
        archive = zipfile.ZipFile(raw_stream)
        info = _validate_archive(archive, job["zip_member"])
        stream = archive.open(info)
        text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        reader = csv.reader(text, delimiter=",", strict=True)
        header = next(reader, None)
        if (not header or len(header) > 32 or any(not value.strip() for value in header)
                or sum(map(len, header)) > 64 * 1024 or len(set(header)) != len(header)):
            raise StopJob("header_invalid")
        if checkpoint["headers"] is not None and checkpoint["headers"] != header:
            raise StopJob("checkpoint_header_changed")
        checkpoint["headers"] = header
        for _ in range(checkpoint["rows"]):
            row = next(reader, None)
            if row is None or len(row) != len(header):
                raise StopJob("checkpoint_source_mismatch")
        rows_in_chunk = 0
        chunk_number = len(checkpoint["chunks"]) + 1
        chunk_path = artifact_root / f"chunk-{chunk_number:04d}.jsonl.pending"
        chunk_stream = None
        try:
            for row in reader:
                if checkpoint["rows"] % 1000 == 0 and _cancelled(database_path, job["task_id"]):
                    raise StopJob("cancelled")
                if len(row) != len(header):
                    raise StopJob("ragged_rows")
                if sum(map(len, row)) > MAX_ROW_CHARS:
                    raise StopJob("row_budget")
                if checkpoint["rows"] >= 2_000_000:
                    raise StopJob("row_budget")
                if checkpoint["cells"] + len(row) > 20_000_000:
                    raise StopJob("cell_budget")
                encoded = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                if checkpoint["output_bytes"] + len(encoded) > limits["output_bytes"]:
                    raise StopJob("output_budget")
                if chunk_stream is None:
                    chunk_stream = chunk_path.open("xb")
                chunk_stream.write(encoded)
                checkpoint["output_bytes"] += len(encoded)
                checkpoint["rows"] += 1
                checkpoint["cells"] += len(row)
                checkpoint["empty_fields"] += sum(value == "" for value in row)
                checkpoint["zero_fields"] += sum(value == "0" for value in row)
                rows_in_chunk += 1
                if rows_in_chunk == 10_000:
                    _finish_chunk(chunk_stream, chunk_path, artifact_root, checkpoint)
                    chunk_stream = None
                    chunk_number += 1
                    rows_in_chunk = 0
                    checkpoint["next_data_row"] = checkpoint["rows"]
                    _atomic_json(checkpoint_path, checkpoint)
                    chunk_path = artifact_root / f"chunk-{chunk_number:04d}.jsonl.pending"
            if chunk_stream is not None:
                _finish_chunk(chunk_stream, chunk_path, artifact_root, checkpoint)
                chunk_stream = None
        finally:
            if chunk_stream is not None:
                chunk_stream.close()
            text.close()
            archive.close()
    if checkpoint["rows"] == 0:
        raise StopJob("no_observations")
    if _sha256(raw_path) != job["raw_sha256"]:
        raise StopJob("source_changed_during_processing")
    checkpoint["next_data_row"] = checkpoint["rows"]
    _atomic_json(checkpoint_path, checkpoint)
    manifest = {
        "schema_version": 1,
        "binding": binding,
        "source": {
            "url": job["source_url"], "agency": job["source_agency"],
            "captured_at": job.get("source_captured_at"),
            "http_status": job.get("source_http_status"),
            "content_type": job.get("source_content_type"),
            "last_modified": job.get("source_last_modified"),
            "raw_path": job["raw_relative_path"], "raw_sha256": job["raw_sha256"],
            "request_manifest_path": job["request_manifest_relative_path"],
            "request_manifest_sha256": job["request_manifest_sha256"],
            "zip_member": job["zip_member"],
        },
        "representation": "UTF-8 JSON Lines rows; all source fields preserved as strings",
        "headers": checkpoint["headers"], "rows": checkpoint["rows"],
        "columns": len(checkpoint["headers"]), "cells": checkpoint["cells"],
        "empty_fields": checkpoint["empty_fields"], "zero_fields": checkpoint["zero_fields"],
        "output_bytes": checkpoint["output_bytes"], "chunks": checkpoint["chunks"],
        "checkpoint": {"path": "checkpoint.json", "bytes": checkpoint_path.stat().st_size,
                       "sha256": _sha256(checkpoint_path)},
        "quality_scope": "rectangular CSV structure only; no economic meaning or units inferred",
        "completed_at_epoch": time.time(),
    }
    _atomic_json(output_manifest_path, manifest)
    return {"execution_state": "COMPLETED", **manifest,
            "elapsed_seconds": time.monotonic() - started}


def _finish_chunk(stream, pending_path, artifact_root, checkpoint):
    stream.flush()
    os.fsync(stream.fileno())
    stream.close()
    number = len(checkpoint["chunks"]) + 1
    name = f"chunk-{number:04d}.jsonl"
    final_path = artifact_root / name
    if final_path.exists() or final_path.is_symlink():
        raise StopJob("output_collision")
    try:
        os.link(pending_path, final_path, follow_symlinks=False)
        pending_path.unlink()
        _fsync_directory(artifact_root)
    except FileExistsError:
        raise StopJob("output_collision") from None
    with final_path.open("rb") as completed:
        chunk_rows = sum(1 for _ in completed)
    checkpoint["chunks"].append({
        "path": name, "sha256": _sha256(final_path), "bytes": final_path.stat().st_size,
        "first_data_row": sum(chunk["rows"] for chunk in checkpoint["chunks"]),
        "rows": chunk_rows,
    })


if __name__ == "__main__":
    try:
        job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = run(job)
        result["worker_status"] = "SUCCEEDED"
    except StopJob as error:
        result = {"worker_status": "STOPPED", "reason": error.reason,
                  "retryable": error.retryable}
    except MemoryError:
        result = {"worker_status": "STOPPED", "reason": "memory_budget", "retryable": True}
    except Exception:  # noqa: BLE001 - never emit source rows or diagnostic details
        result = {"worker_status": "STOPPED", "reason": "format_or_worker_error",
                  "retryable": False}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
