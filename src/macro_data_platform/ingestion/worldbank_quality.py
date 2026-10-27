"""Gate A: hash captured bytes, verify raw files, normalize losslessly, persist quality evidence."""
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from macro_data_platform.connectors.worldbank import (
    MAX_BYTES,
    ConnectorFailure,
    Download,
    GDPQuery,
    WorldBankTransport,
    parse_gdp,
)
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageResult, StageStatus
from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine

NORMALIZATION_VERSION = "worldbank_gate_a_v2"
PARSER_VERSION = "worldbank_gdp_parser_v2"


def _read(settings, relative, limit):
    path = settings._inside(relative)
    if not path.is_relative_to(settings.raw_dir / "worldbank"):
        raise ValueError("artifact must remain in the World Bank raw directory")
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("artifact exceeds verification read budget")
    return value


def verified_download(audit, artifact):
    raw_path, manifest_path = artifact["raw_path"], artifact["manifest_path"]
    if (Path(raw_path).name != "response.json" or Path(manifest_path).name != "request.json"
            or Path(raw_path).parent != Path(manifest_path).parent):
        raise ValueError("raw and manifest paths do not form an artifact")
    raw = _read(audit.settings, raw_path, MAX_BYTES)
    manifest = _read(audit.settings, manifest_path, 65536)
    if (hashlib.sha256(raw).hexdigest() != artifact["raw_sha256"]
            or hashlib.sha256(manifest).hexdigest() != artifact["manifest_sha256"]):
        raise ValueError("raw or manifest hash mismatch")
    metadata = json.loads(manifest)
    expected = {key: artifact[key] for key in (
        "source_url", "retrieved_at", "http_status", "content_type", "mode", "byte_count",
        "raw_path",
    )}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("artifact manifest does not match captured response")
    if len(raw) != artifact["byte_count"]:
        raise ValueError("artifact length mismatch")
    return Download(artifact["source_url"], raw, artifact["http_status"],
                    datetime.fromisoformat(artifact["retrieved_at"]),
                    artifact["content_type"], EvidenceKind(artifact["mode"]))


def comparison_fingerprint(source_url, query):
    canonical = json.dumps({"source_url": source_url, "query": query}, sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_payload_digest(body):
    """Ignore JSON formatting and key order; retain exact bytes for non-JSON sources."""
    try:
        parsed = json.loads(body)
        canonical = json.dumps(parsed, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        canonical = body
        method = "worldbank_raw_bytes_v1"
    else:
        method = "worldbank_json_canonical_v1"
    return hashlib.sha256(canonical).hexdigest(), method


def _compare_prior_artifact(audit, artifact):
    download = verified_download(audit, artifact)
    calculated, method = source_payload_digest(download.body)
    stored = artifact.get("comparison_sha256")
    stored_method = artifact.get("comparison_method")
    if stored is not None and (stored != calculated or stored_method != method):
        raise ValueError("prior source comparison metadata does not match verified raw")
    return calculated, method


def normalize_worldbank(parsed, query, source_change_status="first_observation"):
    """Minimal deterministic checks; no inferred units, imputation or economic corrections."""
    rows = parsed["observations"]
    counts = Counter(row["date"] for row in rows)
    expected = {str(year) for year in range(query.start_year, query.end_year + 1)}
    issues, warnings = [], []
    if any(count > 1 for count in counts.values()):
        issues.append("duplicate_periods")
    missing = sorted(expected - counts.keys())
    if missing:
        issues.append("missing_periods")
    units = {row.get("unit") for row in rows if isinstance(row.get("unit"), str) and row["unit"]}
    if len(units) > 1:
        issues.append("inconsistent_source_units")
    if any(row.get("unit") is not None and not isinstance(row["unit"], str) for row in rows):
        issues.append("invalid_source_unit")
    nulls = sum(row["value"] is None for row in rows)
    negative_values = sum(row["value"] is not None and row["value"] < 0 for row in rows)
    if negative_values:
        issues.append("negative_gdp_values")
    if nulls:
        warnings.append("missing_values_preserved")
    if any(row.get("obs_status") for row in rows):
        warnings.append("source_observation_status_preserved")
    if parsed["unit"] is None or parsed["frequency"] is None:
        warnings.append("normalized_unit_or_frequency_unknown")
    if source_change_status == "changed":
        issues.append("source_payload_changed_since_prior_request")
    elif source_change_status not in {"first_observation", "unchanged"}:
        warnings.append("prior_response_comparison_unavailable")
    normalized = []
    if not issues:
        for position, row in enumerate(rows):
            normalized.append({
                "period": row["date"], "value": row["value"],
                "value_status": "missing" if row["value"] is None else "reported",
                "country": row["countryiso3code"], "indicator_id": row["indicator"]["id"],
                "series_key": parsed["series_key"], "series_id": parsed["series_id"],
                "source_agency": parsed["source_agency"], "dataset_id": parsed["dataset_id"],
                "frequency": parsed["frequency"], "unit": row.get("unit") or parsed["unit"],
                "source_unit": row.get("unit"), "observation_status": row.get("obs_status"),
                "source_version": parsed["source_version"],
                "source_last_updated": parsed["source_last_updated"],
                "retrieved_at": parsed["retrieved_at"], "source_url": parsed["source_url"],
                "source_row_index": position, "original_row": row,
            })
    report = {
        "status": "failed" if issues else "passed", "issues": issues, "warnings": warnings,
        "requested_periods": sorted(expected), "observed_periods": sorted(counts),
        "missing_periods": missing, "row_count": len(rows), "missing_value_count": nulls,
        "negative_gdp_value_count": negative_values,
        "source_change_status": source_change_status,
        "normalization_version": NORMALIZATION_VERSION, "parser_version": PARSER_VERSION,
        "page_metadata": parsed["page_metadata"],
        "scope": "raw integrity, identity, period coverage, duplicates, finite numbers, unit consistency, and nonnegative GDP values",
        "not_checked": ["economic_outliers_beyond_nonnegative_check", "revision_history",
                        "cross_source_equivalence", "unit_frequency_metadata_resolution"],
    }
    return report, normalized


def _incident(audit, request, owner, result):
    if result.status != StageStatus.SUCCEEDED:
        audit.record_stage("incident", request, owner, {
            "stage_status": result.status, "error_code": result.error_code,
            "warnings": list(result.warnings), "evidence_refs": list(result.evidence_refs),
        })
    return result


class _CapturedTransport:
    def __init__(self, transport):
        self.transport, self.download, self.sha256 = transport, None, None

    def fetch(self, query):
        self.download = self.transport.fetch(query)
        self.sha256 = hashlib.sha256(self.download.body).hexdigest()
        return self.download


class WorldBankAuditedCollection:
    def __init__(self, audit, transport=None, *, settings=None):
        self.audit = audit
        self.transport = transport if transport is not None else WorldBankTransport(
            settings if settings is not None else audit.settings)

    def run(self, request):
        audit = self.audit
        owner = audit.active(request)
        captured = _CapturedTransport(self.transport)
        result = WorldBankGDPEngine(audit.settings, captured).run(request)
        payload = result.payload or {}
        try:
            if "raw_path" in payload and "manifest_path" in payload:
                download = captured.download
                manifest = _read(audit.settings, payload["manifest_path"], 65536)
                context = audit.history.get(request.task_id).get("workflow_context", {})
                artifact = {
                    "raw_path": payload["raw_path"], "manifest_path": payload["manifest_path"],
                    "raw_sha256": captured.sha256,
                    "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                    "byte_count": len(download.body), "http_status": download.status_code,
                    "source_url": download.source_url, "retrieved_at": download.retrieved_at.isoformat(),
                    "content_type": download.content_type, "mode": download.kind.value,
                    "query": request.input_data, "collection_status": result.status,
                    "confirmation_fingerprint": context.get("confirmation", {}).get("fingerprint"),
                }
                verified_download(audit, artifact)
                comparison_sha256, comparison_method = source_payload_digest(download.body)
                scope_fingerprint = comparison_fingerprint(download.source_url, request.input_data)
                saved = audit.record_source_artifact(
                    request, owner, artifact, scope_fingerprint=scope_fingerprint,
                    comparison_sha256=comparison_sha256, comparison_method=comparison_method,
                    compare_prior=lambda prior: _compare_prior_artifact(audit, prior),
                )
                result = replace(result, payload={**payload, "artifact_id": saved["record_id"],
                                                  "raw_sha256": artifact["raw_sha256"],
                                                  "comparison_sha256": comparison_sha256,
                                                  "comparison_method": comparison_method,
                                                  "source_change_status": saved["source_change_status"]})
            return _incident(audit, request, owner, result)
        except (ValueError, OSError, sqlite3.Error):
            failed = StageResult(StageStatus.NEEDS_REVIEW,
                {key: payload[key] for key in ("raw_path", "manifest_path") if key in payload},
                result.evidence_refs, ("Raw preservation or audit integrity requires review.",),
                ErrorCode.QUALITY_FAILURE)
            # If SQLite itself is unavailable, the runner still persists its safe failure result.
            return _incident(audit, request, owner, failed)


class WorldBankValidation:
    def __init__(self, audit):
        self.audit = audit

    def run(self, request):
        audit, upstream = self.audit, request.upstream or {}
        owner = audit.active(request)
        artifact = audit.get(upstream["artifact_id"], kind="artifact")
        if artifact["task_id"] != request.task_id or artifact["query"] != request.input_data:
            return _incident(audit, request, owner, StageResult(
                StageStatus.NEEDS_REVIEW, error_code=ErrorCode.QUALITY_FAILURE,
                warnings=("Artifact is outside the confirmed task or query.",)))
        try:
            download = verified_download(audit, artifact)
            query = GDPQuery(**request.input_data)
            parsed = parse_gdp(download, query)
            report, observations = normalize_worldbank(
                parsed, query, artifact.get("source_change_status", "first_observation"),
            )
            code = ErrorCode.QUALITY_FAILURE if report["status"] == "failed" else None
        except ConnectorFailure as failure:
            report, observations, code = {
                "status": "failed", "issues": ["source_schema_changed"], "warnings": [],
            }, [], failure.code
        except (ValueError, OSError):
            report, observations, code = {
                "status": "failed", "issues": ["raw_integrity_failed"], "warnings": [],
            }, [], ErrorCode.QUALITY_FAILURE
        saved = audit.record_stage("validation", request, owner, {
            **report, "artifact_id": artifact["record_id"], "raw_sha256": artifact["raw_sha256"],
            "mode": artifact["mode"],
        }, observations=observations)
        result = StageResult(
            StageStatus.SUCCEEDED if code is None else StageStatus.NEEDS_REVIEW,
            {**upstream, "validation_id": saved["record_id"], "quality": report,
             "normalized_ref": "sqlite:gate_a_observations/" + saved["record_id"]
             if code is None else None},
            (*request.input_refs, "sqlite:gate_a_records/" + saved["record_id"]),
            tuple(report["warnings"] + report["issues"]), code,
        )
        return _incident(audit, request, owner, result)


def reusable(audit, spec, stage):
    payload = stage["result"]["payload"]
    if spec.engine not in {"worldbank_collect_audit", "worldbank_validate"}:
        return False
    artifact = audit.get(payload["artifact_id"], kind="artifact")
    verified_download(audit, artifact)
    if artifact["query"] != spec.input_data:
        return False
    reports = audit.for_task(artifact["task_id"], kind="validation")
    related = [report for report in reports if report["artifact_id"] == artifact["record_id"]]
    if related and related[-1]["status"] != "passed":
        return False
    if spec.engine == "worldbank_validate":
        report = audit.get(payload["validation_id"], kind="validation")
        if report["artifact_id"] != artifact["record_id"] or report["status"] != "passed":
            return False
        if report.get("normalization_version") != NORMALIZATION_VERSION:
            return False
        if report.get("parser_version") != PARSER_VERSION:
            return False
        audit.observations(report["record_id"])
    return True


def verify_completed(audit, doc):
    stage = next(row for row in reversed(doc["stages"]) if row["stage_id"] == "validate")
    payload = stage["result"]["payload"]
    artifact = audit.get(payload["artifact_id"], kind="artifact")
    verified_download(audit, artifact)
    report = audit.get(payload["validation_id"], kind="validation")
    if report["status"] != "passed" or report["artifact_id"] != artifact["record_id"]:
        raise ValueError("completed validation does not match artifact")
    audit.observations(report["record_id"])
