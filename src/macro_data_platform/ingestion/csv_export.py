"""Read-only export of verified World Bank and BOJ task results."""

import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import (
    DATA_ENDPOINT,
    METADATA_ENDPOINT,
    BOJQuery,
    parse_boj_metadata,
    parse_boj_observations,
)
from macro_data_platform.connectors.statistical_http import MAX_BYTES, ApiDownload
from macro_data_platform.connectors.worldbank import Download, GDPQuery, parse_gdp
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
)
from macro_data_platform.ingestion.worldbank_quality import (
    normalize_worldbank,
    source_payload_digest,
)
from macro_data_platform.storage.audit import digest as _audit_digest
from macro_data_platform.storage.statistical_downloads import (
    _comparison_fingerprint_for_source,
    _request_fingerprint,
)

MAX_MANIFEST_BYTES = 64 * 1024
PACKAGE_ID = re.compile(r"^[a-f0-9]{32}$")
CSV_COLUMNS = (
    "date",
    "value",
    "value_status",
    "source_agency",
    "dataset_id",
    "series_id",
    "series_name",
    "indicator_id",
    "series_key_json",
    "unit",
    "frequency",
    "source_version",
    "retrieved_at",
    "source_url",
    "raw_path",
    "raw_sha256",
    "request_manifest_path",
    "request_manifest_sha256",
    "source_change_status",
    "observation_status",
    "freshness_status",
    "freshness_frequency",
    "freshness_frequency_basis",
    "freshness_latest_period",
    "freshness_evaluated_at",
    "freshness_age_days",
    "freshness_max_age_days",
    "freshness_policy_id",
)


@dataclass(frozen=True)
class VerifiedDataset:
    task_id: str
    provider: str
    source: dict
    quality: dict
    observations: tuple[dict, ...]
    stages: tuple[dict, ...]


def _state(value):
    return value.value if hasattr(value, "value") else value


def _stable_quality(value):
    """Ignore only clock-dependent freshness fields when checking saved evidence."""
    if not isinstance(value, dict):
        return value
    result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    freshness = result.get("freshness")
    values = freshness if isinstance(freshness, list) else [freshness]
    for item in values:
        if isinstance(item, dict):
            item.pop("evaluated_at", None)
            item.pop("age_days", None)
    return result


def _quality_record_matches(validation, current_quality):
    saved = {key: validation.get(key) for key in current_quality}
    return _stable_quality(saved) == _stable_quality(current_quality)


def _readonly_connection(settings):
    uri = settings.database_path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _load_task(connection, task_id):
    row = connection.execute(
        "SELECT document FROM tasks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    if row is None:
        raise ValueError("unknown_task")
    try:
        document = json.loads(row["document"])
    except (ValueError, RecursionError):
        raise ValueError("task_history_integrity") from None
    if not isinstance(document, dict) or document.get("task_id") != task_id:
        raise ValueError("task_history_integrity")
    if _state(document.get("status")) != "COMPLETED":
        raise ValueError("task_not_completed")
    return document


def _plan_by_engine(document, engines):
    plan = document.get("plan")
    if (
        not isinstance(plan, list)
        or any(not isinstance(row, dict) for row in plan)
        or [row.get("engine") for row in plan] != list(engines)
    ):
        raise ValueError("unsupported_task_plan")
    expected_stage_ids = {
        "worldbank_collect_audit": "collect",
        "worldbank_validate": "validate",
        "boj_metadata": "metadata",
        "boj_observations": "collect",
    }
    if [row.get("stage_id") for row in plan] != [expected_stage_ids[engine] for engine in engines]:
        raise ValueError("unsupported_task_plan")
    expected_engine_versions = {
        "worldbank_collect_audit": "1", "worldbank_validate": "2",
        "boj_metadata": "1", "boj_observations": "2",
    }
    if any(row.get("engine_version") != expected_engine_versions.get(row.get("engine"))
           for row in plan):
        raise ValueError("unsupported_engine_version")
    stages = document.get("stages")
    if not isinstance(stages, list) or len(stages) != len(plan):
        raise ValueError("task_stage_history_incomplete")
    indexed = {}
    for plan_row, stage in zip(plan, stages, strict=True):
        if (
            not isinstance(stage, dict)
            or stage.get("stage_id") != plan_row.get("stage_id")
            or stage.get("engine") != plan_row.get("engine")
            or stage.get("engine_version") != plan_row.get("engine_version")
            or not isinstance(stage.get("stage_run_id"), str)
            or type(stage.get("attempt_no")) is not int
            or type(stage.get("task_attempt_no")) is not int
            or _state(stage.get("status")) != "SUCCEEDED"
        ):
            raise ValueError("task_stage_not_successful")
        indexed[stage["stage_id"]] = stage
    return plan, indexed


def _payload(stage):
    result = stage.get("result")
    payload = result.get("payload") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or _state(result.get("status")) != "SUCCEEDED"
        or not isinstance(payload, dict)
    ):
        raise ValueError("successful_stage_payload_missing")
    return payload


def _record(connection, record_id, kind, task_id, stage_run_id):
    row = connection.execute(
        "SELECT kind,task_id,stage_run_id,document FROM gate_a_records WHERE record_id=?",
        (record_id,),
    ).fetchone()
    if (
        row is None
        or row["kind"] != kind
        or row["task_id"] != task_id
        or row["stage_run_id"] != stage_run_id
    ):
        raise ValueError("audit_record_scope_mismatch")
    try:
        document = json.loads(row["document"])
    except (ValueError, RecursionError):
        raise ValueError("audit_record_integrity") from None
    if (
        not isinstance(document, dict)
        or document.get("record_id") != record_id
        or document.get("kind") != kind
        or document.get("task_id") != task_id
        or document.get("stage_run_id") != stage_run_id
    ):
        raise ValueError("audit_record_integrity")
    return document


def _audit_observations(connection, validation_id):
    rows = connection.execute(
        "SELECT document FROM gate_a_observations WHERE validation_id=? ORDER BY position",
        (validation_id,),
    ).fetchall()
    try:
        return [json.loads(row["document"]) for row in rows]
    except (TypeError, ValueError, RecursionError):
        raise ValueError("normalized_observations_invalid") from None


def _stage_provenance(document):
    return tuple(
        {
            "stage_id": stage["stage_id"],
            "engine": stage["engine"],
            "engine_version": stage["engine_version"],
            "stage_run_id": stage["stage_run_id"],
            "status": _state(stage["status"]),
            "attempt_no": stage["attempt_no"],
            "task_attempt_no": stage["task_attempt_no"],
        }
        for stage in document["stages"]
    )


def _safe_raw_file(settings, relative, provider, filename, limit):
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("source_path_invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ValueError("source_path_invalid")
    raw_root = PurePosixPath(settings.data_dir) / "raw" / provider
    if not pure.is_relative_to(raw_root) or pure.name != filename:
        raise ValueError("source_path_scope_mismatch")
    package = pure.parent.relative_to(raw_root)
    if len(package.parts) != 1 or not PACKAGE_ID.fullmatch(package.name):
        raise ValueError("source_path_scope_mismatch")

    candidate = settings.project_root.joinpath(*pure.parts)
    current = settings.project_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("source_symlink")
    resolved = settings._inside(relative)
    if resolved != candidate or not candidate.is_file():
        raise ValueError("source_file_missing")
    if candidate.stat().st_size > limit:
        raise ValueError("source_file_budget")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError:
        raise ValueError("source_file_unreadable") from None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("source_file_not_regular")
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("source_file_budget")
    return body


def _provider_files(settings, source, payload):
    raw_path, manifest_path = payload.get("raw_path"), payload.get("manifest_path")
    if not isinstance(raw_path, str) or not isinstance(manifest_path, str):
        raise TypeError("source_provenance_missing")
    if Path(raw_path).parent != Path(manifest_path).parent:
        raise ValueError("source_provenance_scope_mismatch")
    raw_bytes = _safe_raw_file(settings, raw_path, source, "response.json", MAX_BYTES)
    manifest_bytes = _safe_raw_file(
        settings, manifest_path, source, "request.json", MAX_MANIFEST_BYTES
    )
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("request_manifest_invalid") from None
    if not isinstance(manifest, dict):
        raise TypeError("request_manifest_invalid")
    return raw_bytes, manifest_bytes, manifest


def _worldbank(connection, settings, task_id, document, *, freshness_policy,
               as_of):
    plans, stages = _plan_by_engine(document, ("worldbank_collect_audit", "worldbank_validate"))
    query_data = plans[0].get("input_data")
    if not isinstance(query_data, dict) or set(query_data) != {"start_year", "end_year"}:
        raise ValueError("unsupported_worldbank_query")
    try:
        query = GDPQuery(**query_data)
    except (TypeError, ValueError):
        raise ValueError("unsupported_worldbank_query") from None
    collected, validated = _payload(stages["collect"]), _payload(stages["validate"])
    if (
        collected.get("dataset_id") != "2"
        or collected.get("source_agency") != "World Bank"
        or collected.get("indicator_id") != "NY.GDP.MKTP.CD"
        or collected.get("series_key")
        != {
            "source": "2",
            "country": "USA",
            "indicator": "NY.GDP.MKTP.CD",
        }
    ):
        raise ValueError("unsupported_worldbank_series")
    if collected.get("artifact_id") != validated.get("artifact_id"):
        raise ValueError("artifact_validation_mismatch")
    artifact = _record(
        connection,
        collected.get("artifact_id"),
        "artifact",
        task_id,
        stages["collect"]["stage_run_id"],
    )
    validation = _record(
        connection,
        validated.get("validation_id"),
        "validation",
        task_id,
        stages["validate"]["stage_run_id"],
    )
    if (
        artifact.get("collection_status") != "SUCCEEDED"
        or artifact.get("http_status") != 200
        or artifact.get("query") != query_data
        or validation.get("artifact_id") != artifact["record_id"]
        or validation.get("status") != "passed"
    ):
        raise ValueError("worldbank_quality_not_passed")
    source_change = artifact.get("source_change_status")
    if source_change not in {"unchanged", "first_observation"}:
        raise ValueError("source_change_requires_review")
    if (
        collected.get("source_change_status") != source_change
        or validated.get("source_change_status") != source_change
        or validated.get("quality", {}).get("status") != "passed"
    ):
        raise ValueError("worldbank_quality_scope_mismatch")

    raw, manifest_bytes, manifest = _provider_files(settings, "worldbank", artifact)
    raw_sha = hashlib.sha256(raw).hexdigest()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if (
        raw_sha != artifact.get("raw_sha256")
        or raw_sha != collected.get("raw_sha256")
        or manifest_sha != artifact.get("manifest_sha256")
    ):
        raise ValueError("worldbank_source_hash_mismatch")
    expected_manifest = {
        "source_url": artifact.get("source_url"),
        "retrieved_at": artifact.get("retrieved_at"),
        "http_status": artifact.get("http_status"),
        "content_type": artifact.get("content_type"),
        "mode": artifact.get("mode"),
        "byte_count": artifact.get("byte_count"),
        "raw_path": artifact.get("raw_path"),
    }
    if (
        any(manifest.get(key) != value for key, value in expected_manifest.items())
        or artifact.get("source_url") != query.url
    ):
        raise ValueError("worldbank_manifest_scope_mismatch")
    comparison_sha, comparison_method = source_payload_digest(raw)
    if comparison_sha != artifact.get("comparison_sha256") or comparison_method != artifact.get(
        "comparison_method"
    ):
        raise ValueError("worldbank_comparison_hash_mismatch")

    from datetime import datetime

    download = Download(
        artifact["source_url"],
        raw,
        artifact["http_status"],
        datetime.fromisoformat(artifact["retrieved_at"]),
        artifact["content_type"],
        EvidenceKind(artifact["mode"]),
    )
    parsed = parse_gdp(download, query)
    quality, expected_observations = normalize_worldbank(
        parsed, query, source_change, as_of=as_of, freshness_policy=freshness_policy,
    )
    if quality.get("freshness", {}).get("status") != FreshnessStatus.FRESH:
        raise ValueError("freshness_requires_review")
    if quality.get("status") != "passed":
        raise ValueError("worldbank_revalidation_failed")
    if not _quality_record_matches(validation, quality):
        raise ValueError("worldbank_validation_record_mismatch")
    observations = _audit_observations(connection, validation["record_id"])
    if (
        _audit_digest(observations) != validation.get("normalized_sha256")
        or _audit_digest(observations) != _audit_digest(expected_observations)
        or len(observations) != quality.get("row_count")
    ):
        raise ValueError("worldbank_normalized_integrity_mismatch")

    first = parsed["observations"][0]
    source = {
        "source_agency": "World Bank",
        "dataset_id": "2",
        "series_id": None,
        "series_name": first["indicator"]["value"],
        "indicator_id": "NY.GDP.MKTP.CD",
        "series_key": parsed["series_key"],
        "unit": parsed.get("unit"),
        "frequency": parsed.get("frequency"),
        "source_version": parsed.get("source_version"),
        "source_last_updated": parsed.get("source_last_updated"),
        "retrieved_at": parsed["retrieved_at"],
        "source_url": parsed["source_url"],
        "api_documentation_url": parsed["api_documentation_url"],
        "attribution": parsed["attribution"],
        "license_note": parsed["license_note"],
        "terms_url": parsed["terms_url"],
        "raw_path": artifact["raw_path"],
        "raw_sha256": raw_sha,
        "manifest_path": artifact["manifest_path"],
        "manifest_sha256": manifest_sha,
        "source_change_status": source_change,
        "manifest_hash_status": "verified_against_audit_record",
        "quality_warnings": quality.get("warnings", []),
        "freshness": quality.get("freshness"),
    }
    rows = []
    for row in observations:
        original = row.get("original_row")
        if not isinstance(original, dict):
            raise TypeError("worldbank_original_row_missing")
        rows.append(
            {
                "date": row.get("period"),
                "value": original.get("value"),
                "value_status": row.get("value_status"),
                "observation_status": original.get("obs_status"),
            }
        )
    return VerifiedDataset(
        task_id, "worldbank", source, quality, tuple(rows), _stage_provenance(document)
    )


def _verified_download(
    settings,
    source,
    payload,
    request,
    endpoint,
    *,
    mode=None,
    source_change_status=None,
    retrieved_at=None,
):
    raw, manifest_bytes, manifest = _provider_files(settings, source, payload)
    raw_sha = hashlib.sha256(raw).hexdigest()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if (
        manifest.get("source_agency") != "Bank of Japan"
        or manifest.get("source_url") != endpoint
        or manifest.get("request") != request
        or manifest.get("raw_path") != payload.get("raw_path")
        or manifest.get("raw_sha256") != raw_sha
        or payload.get("raw_sha256") != raw_sha
        or manifest.get("byte_count") != len(raw)
        or manifest.get("http_status") != 200
        or manifest.get("mode") not in {"live_api", "fixture"}
        or (mode is not None and manifest.get("mode") != mode)
        or (
            source_change_status is not None
            and manifest.get("source_change_status") != source_change_status
        )
        or (retrieved_at is not None and manifest.get("retrieved_at") != retrieved_at)
    ):
        raise ValueError("boj_request_manifest_mismatch")
    content_type = manifest.get("content_type")
    if (
        not isinstance(content_type, str)
        or content_type.split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise ValueError("boj_content_type_mismatch")
    request_fingerprint = _request_fingerprint(endpoint, request)
    if manifest.get("request_fingerprint") != request_fingerprint:
        raise ValueError("boj_request_fingerprint_mismatch")
    comparison_sha, comparison_method = _comparison_fingerprint_for_source("boj", raw)
    if (
        manifest.get("comparison_sha256") != comparison_sha
        or manifest.get("comparison_method") != comparison_method
    ):
        raise ValueError("boj_comparison_hash_mismatch")
    return raw, manifest_bytes, manifest, raw_sha, manifest_sha


def _boj(connection, settings, task_id, document, *, freshness_policy, as_of):
    plans, stages = _plan_by_engine(document, ("boj_metadata", "boj_observations"))
    metadata_request = plans[0].get("input_data")
    observation_request = plans[1].get("input_data")
    if (
        metadata_request != {"database": "FM08", "series_code": "FXERD01"}
        or not isinstance(observation_request, dict)
        or set(observation_request) != {"database", "series_code", "month"}
        or observation_request.get("database") != "FM08"
        or observation_request.get("series_code") != "FXERD01"
    ):
        raise ValueError("unsupported_boj_query")
    try:
        query = BOJQuery(observation_request["month"])
    except (TypeError, ValueError):
        raise ValueError("unsupported_boj_query") from None
    metadata_payload, data_payload = _payload(stages["metadata"]), _payload(stages["collect"])
    if (
        metadata_payload.get("metadata_status") != "verified"
        or metadata_payload.get("database") != query.database
        or metadata_payload.get("series_code") != query.series_code
        or data_payload.get("source_agency") != "Bank of Japan"
        or data_payload.get("dataset_id") != query.database
        or data_payload.get("series_id") != query.series_code
        or data_payload.get("source_url") != DATA_ENDPOINT
    ):
        raise ValueError("boj_series_identity_mismatch")
    source_change = data_payload.get("source_change_status")
    metadata_change = metadata_payload.get("source_change_status")
    if source_change not in {"unchanged", "first_observation"} or metadata_change not in {
        "unchanged",
        "first_observation",
    }:
        raise ValueError("source_change_requires_review")

    meta_request = {**metadata_request, "request_kind": "metadata"}
    metadata_raw, _, metadata_manifest, metadata_sha, _ = _verified_download(
        settings,
        "boj",
        metadata_payload,
        meta_request,
        METADATA_ENDPOINT,
        source_change_status=metadata_change,
    )
    from datetime import datetime

    try:
        metadata_document = json.loads(metadata_raw)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("boj_metadata_document_invalid") from None
    metadata_download = ApiDownload(
        METADATA_ENDPOINT,
        metadata_raw,
        200,
        datetime.fromisoformat(metadata_manifest["retrieved_at"]),
        metadata_manifest["content_type"],
        EvidenceKind(metadata_manifest["mode"]),
    )
    metadata = parse_boj_metadata(metadata_download, query)
    if any(
        metadata_payload.get(key) != metadata.get(key)
        for key in (
            "source_agency",
            "database",
            "series_code",
            "series_name",
            "unit",
            "frequency",
            "source_url",
            "metadata_status",
        )
    ):
        raise ValueError("boj_metadata_record_mismatch")
    if metadata_document.get("DB") != query.database:
        raise ValueError("boj_metadata_database_mismatch")

    data_request = {**observation_request, "request_kind": "observations"}
    raw, _, manifest, raw_sha, manifest_sha = _verified_download(
        settings,
        "boj",
        data_payload,
        data_request,
        DATA_ENDPOINT,
        mode=data_payload.get("mode"),
        source_change_status=source_change,
        retrieved_at=data_payload.get("retrieved_at"),
    )
    data_download = ApiDownload(
        DATA_ENDPOINT,
        raw,
        200,
        datetime.fromisoformat(manifest["retrieved_at"]),
        manifest["content_type"],
        EvidenceKind(manifest["mode"]),
    )
    parsed = parse_boj_observations(data_download, query, metadata)
    freshness = assess_freshness(
        [row["date"] for row in parsed["observations"]],
        frequency=metadata.get("frequency"), series_id=query.series_code,
        series_key={"database": query.database, "series_code": query.series_code},
        as_of=as_of, policy=freshness_policy,
    )
    freshness_issue = (
        "stale_observations" if freshness["status"] == FreshnessStatus.STALE else
        "freshness_unverified" if freshness["status"] != FreshnessStatus.FRESH else None
    )
    parsed["quality"] = {
        **parsed["quality"], "freshness": freshness,
        "issues": [freshness_issue] if freshness_issue else [],
        "status": "failed" if freshness_issue else "passed",
    }
    if freshness_issue:
        raise ValueError("freshness_requires_review")
    if (
        data_payload.get("quality", {}).get("status") != "passed"
        or not _quality_record_matches(data_payload.get("quality"), parsed.get("quality"))
        or data_payload.get("observations") != parsed.get("observations")
        or any(
            data_payload.get(key) != parsed.get(key)
            for key in (
                "source_agency",
                "dataset_id",
                "series_id",
                "series_name",
                "unit",
                "frequency",
                "period_start",
                "period_end",
                "retrieved_at",
                "source_url",
            )
        )
    ):
        raise ValueError("boj_stored_result_mismatch")
    source = {
        "source_agency": "Bank of Japan",
        "dataset_id": query.database,
        "series_id": query.series_code,
        "series_name": metadata["series_name"],
        "indicator_id": None,
        "series_key": {
            "database": query.database,
            "series_code": query.series_code,
            "month": query.month,
        },
        "unit": metadata["unit"],
        "frequency": metadata["frequency"],
        "source_version": None,
        "source_last_updated": parsed.get("source_last_updated"),
        "retrieved_at": parsed["retrieved_at"],
        "source_url": parsed["source_url"],
        "api_documentation_url": metadata["api_documentation_url"],
        "raw_path": data_payload["raw_path"],
        "raw_sha256": raw_sha,
        "manifest_path": data_payload["manifest_path"],
        "manifest_sha256": manifest_sha,
        "source_change_status": source_change,
        "manifest_hash_status": "fields_and_raw_hash_verified_no_capture_digest",
        "metadata_raw_path": metadata_payload["raw_path"],
        "metadata_raw_sha256": metadata_sha,
        "metadata_manifest_path": metadata_payload["manifest_path"],
        "metadata_manifest_sha256": hashlib.sha256(
            _safe_raw_file(
                settings,
                metadata_payload["manifest_path"],
                "boj",
                "request.json",
                MAX_MANIFEST_BYTES,
            )
        ).hexdigest(),
        "quality_warnings": [],
        "freshness": parsed["quality"]["freshness"],
    }
    rows = tuple(
        {
            "date": row["date"],
            "value": row["value"],
            "value_status": "missing" if row["value"] is None else "reported",
            "observation_status": None,
        }
        for row in parsed["observations"]
    )
    return VerifiedDataset(
        task_id, "boj", source, parsed["quality"], rows, _stage_provenance(document)
    )


def _value_text(value):
    if value is None:
        return ""
    if type(value) not in {int, float} or (type(value) is float and not math.isfinite(value)):
        raise ValueError("observation_value_invalid")
    return str(value)


def _csv_bytes(dataset):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_COLUMNS, extrasaction="raise", lineterminator="\n"
    )
    writer.writeheader()
    for observation in dataset.observations:
        source = dataset.source
        freshness = dataset.quality.get("freshness")
        if isinstance(freshness, list):
            freshness = freshness[0] if len(freshness) == 1 else {}
        freshness = freshness if isinstance(freshness, dict) else {}
        series_key = json.dumps(
            source["series_key"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        writer.writerow(
            {
                "date": observation["date"],
                "value": _value_text(observation["value"]),
                "value_status": observation["value_status"],
                "source_agency": source["source_agency"],
                "dataset_id": source["dataset_id"],
                "series_id": source.get("series_id"),
                "series_name": source.get("series_name"),
                "indicator_id": source.get("indicator_id"),
                "series_key_json": series_key,
                "unit": source.get("unit"),
                "frequency": source.get("frequency"),
                "source_version": source.get("source_version"),
                "retrieved_at": source["retrieved_at"],
                "source_url": source["source_url"],
                "raw_path": source["raw_path"],
                "raw_sha256": source["raw_sha256"],
                "request_manifest_path": source["manifest_path"],
                "request_manifest_sha256": source["manifest_sha256"],
                "source_change_status": source["source_change_status"],
                "observation_status": observation.get("observation_status"),
                "freshness_status": freshness.get("status"),
                "freshness_frequency": freshness.get("frequency"),
                "freshness_frequency_basis": freshness.get("frequency_basis"),
                "freshness_latest_period": freshness.get("latest_period"),
                "freshness_evaluated_at": freshness.get("evaluated_at"),
                "freshness_age_days": freshness.get("age_days"),
                "freshness_max_age_days": freshness.get("max_age_days"),
                "freshness_policy_id": freshness.get("policy_id"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _output_paths(settings, output):
    if not isinstance(output, (str, Path)):
        raise TypeError("output_path_invalid")
    text = str(output)
    if not text or "\x00" in text:
        raise ValueError("output_path_invalid")
    relative = Path(text)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("output_path_invalid")
    export_root = Path(settings.data_dir) / "exports"
    if (
        len(relative.parts) <= len(export_root.parts)
        or relative.parts[: len(export_root.parts)] != export_root.parts
        or relative.suffix.lower() != ".csv"
    ):
        raise ValueError("output_must_be_csv_under_data_exports")
    target = settings.project_root / relative
    sidecar = Path(str(target) + ".provenance.json")
    for candidate in (target, sidecar):
        current = settings.project_root
        for part in candidate.relative_to(settings.project_root).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("output_symlink")
    if target.exists() or sidecar.exists():
        raise ValueError("output_already_exists")
    if not target.parent.resolve().is_relative_to(settings._inside(str(export_root))):
        raise ValueError("output_path_escape")
    return relative.as_posix(), target, sidecar, settings._inside(str(export_root))


def _mkdir_export_parent(settings, target, export_root):
    current = settings.project_root
    for part in target.parent.relative_to(settings.project_root).parts:
        current = current / part
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise ValueError("output_parent_invalid")
        else:
            current.mkdir()
    if not target.parent.resolve().is_relative_to(export_root):
        raise ValueError("output_path_escape")


def _publish_pair(target, sidecar, csv_body, manifest_body):
    temp_csv = temp_manifest = None
    published_csv = published_manifest = False
    try:
        fd, temp_csv_name = tempfile.mkstemp(
            prefix=".macroatlas-export-", suffix=".csv.tmp", dir=target.parent
        )
        temp_csv = Path(temp_csv_name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(csv_body)
            stream.flush()
            os.fsync(stream.fileno())
        fd, temp_manifest_name = tempfile.mkstemp(
            prefix=".macroatlas-export-", suffix=".json.tmp", dir=target.parent
        )
        temp_manifest = Path(temp_manifest_name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(manifest_body)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists() or target.is_symlink() or sidecar.exists() or sidecar.is_symlink():
            raise ValueError("output_already_exists")
        os.link(temp_csv, target)
        published_csv = True
        os.link(temp_manifest, sidecar)
        published_manifest = True
        if os.name != "nt":
            descriptor = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception:
        for published, destination, temporary in (
            (published_manifest, sidecar, temp_manifest),
            (published_csv, target, temp_csv),
        ):
            if published and temporary is not None:
                try:
                    if destination.stat().st_ino == temporary.stat().st_ino:
                        destination.unlink()
                except OSError:
                    pass
        raise
    finally:
        for path in (temp_csv, temp_manifest):
            if path is not None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass


def export_task(settings: Settings, task_id: str, output, *, format="csv",
                freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
                as_of: datetime | None = None) -> dict:
    if format != "csv":
        raise ValueError("unsupported_export_format")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id_invalid")
    evaluation_time = datetime.now(UTC) if as_of is None else as_of
    if not isinstance(freshness_policy, FreshnessPolicy):
        raise TypeError("freshness_policy_invalid")
    with closing(_readonly_connection(settings)) as connection:
        document = _load_task(connection, task_id)
        plan = document.get("plan")
        if isinstance(plan, list) and any(not isinstance(row, dict) for row in plan):
            raise ValueError("unsupported_task_plan")
        engines = [row.get("engine") for row in plan] if isinstance(plan, list) else []
        if engines == ["worldbank_collect_audit", "worldbank_validate"]:
            dataset = _worldbank(connection, settings, task_id, document,
                                 freshness_policy=freshness_policy, as_of=evaluation_time)
        elif engines == ["boj_metadata", "boj_observations"]:
            dataset = _boj(connection, settings, task_id, document,
                            freshness_policy=freshness_policy, as_of=evaluation_time)
        else:
            raise ValueError("unsupported_provider_task")

    relative, target, sidecar, export_root = _output_paths(settings, output)
    csv_body = _csv_bytes(dataset)
    missing_count = sum(row["value"] is None for row in dataset.observations)
    manifest = {
        "schema_version": 1,
        "export_format": "csv",
        "encoding": "utf-8",
        "null_encoding": "empty CSV value with value_status=missing",
        "task_id": task_id,
        "provider": dataset.provider,
        "stages": list(dataset.stages),
        "row_count": len(dataset.observations),
        "missing_value_count": missing_count,
        "columns": list(CSV_COLUMNS),
        "quality": dataset.quality,
        "source": dataset.source,
        "export": {
            "path": relative,
            "sha256": hashlib.sha256(csv_body).hexdigest(),
            "bytes": len(csv_body),
            "provenance_path": (relative + ".provenance.json"),
        },
    }
    manifest_body = (
        json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _mkdir_export_parent(settings, target, export_root)
    _publish_pair(target, sidecar, csv_body, manifest_body)
    return {
        "status": "COMPLETED",
        "task_id": task_id,
        "provider": dataset.provider,
        "csv_path": relative,
        "csv_sha256": hashlib.sha256(csv_body).hexdigest(),
        "provenance_path": relative + ".provenance.json",
        "provenance_sha256": hashlib.sha256(manifest_body).hexdigest(),
        "row_count": len(dataset.observations),
        "missing_value_count": missing_count,
    }
