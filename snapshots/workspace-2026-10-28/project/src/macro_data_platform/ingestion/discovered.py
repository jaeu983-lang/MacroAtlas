"""Evidence-bound source routes; one declared CSV schema plus the existing WDI path."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from requests.exceptions import RequestException

from macro_data_platform.contracts import (
    ErrorCode,
    EvidenceKind,
    StageResult,
    StageStatus,
    TaskStatus,
    utc,
)
from macro_data_platform.ingestion.formats import MAX_SOURCE_BYTES, parse_table
from macro_data_platform.ingestion.retry import retry_delay
from macro_data_platform.ingestion.worldbank_request import WorldBankRequestDispatcher
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan
from macro_data_platform.orchestration.workflow import validate_workflow_task
from macro_data_platform.workflow_extensions import ConfirmedDelivery


def _confirmed(history, task_id, at):
    with history.transaction() as db:
        child = history.load(db, task_id)
        validate_workflow_task(history, db, child, at, allow_link=True)
        return ConfirmedDelivery.from_dict(child["workflow_context"]["confirmation"])


def _selected_links(confirmed):
    selected = set(confirmed.delivery.link_ids)
    return [link.to_dict() for link in confirmed.offer.links if link.link_id in selected]


def deliver_links(history, task_id, at):
    _confirmed(history, task_id, at)
    with history.transaction() as db:
        child = history.load(db, task_id)
        validate_workflow_task(history, db, child, at, allow_link=True)
        confirmed = ConfirmedDelivery.from_dict(child["workflow_context"]["confirmation"])
        if confirmed.delivery.mode != "link":
            raise ValueError("link delivery requires link-only conditions")
        if child["status"] == TaskStatus.COMPLETED:
            return child
        if child["status"] != TaskStatus.CREATED or child["cancel_requested"]:
            raise ValueError("link delivery requires an uncancelled created task")
        child["delivery_result"] = {
            "mode": "link", "links": _selected_links(confirmed),
            "verification": "supplied metadata evidence; no HTTP, parser or data file",
        }
        child["status"] = TaskStatus.COMPLETED
        child["attempts"].append({
            "attempt_no": 1, "token": uuid4().hex, "started_at": at.isoformat(),
            "finished_at": at.isoformat(), "status": TaskStatus.COMPLETED,
        })
        history.save(db, child)
        history.event(db, task_id, {"kind": "DISCOVERED_LINK_DELIVERED", "at": at.isoformat()})
        return child


class WorldBankRoute:
    formats = ("raw_json",)

    def __init__(self, transport=None):
        self.transport = transport

    def supports(self, record):
        candidate = record.candidate
        return (candidate.institution_id in {"worldbank", "INT-04"} and candidate.dataset_id == "2"
                and candidate.series_id is None and dict(candidate.series_key) == {
                    "source": "2", "country": "USA", "indicator": "NY.GDP.MKTP.CD",
                })

    def available(self, record, at):
        return record.candidate.auth_requirement == "none"

    def dispatcher(self, settings, history, record, clock):
        return WorldBankRequestDispatcher(settings, history, transport=self.transport,
                                          clock=clock, gate_a=True)


@dataclass(frozen=True)
class SourceDownload:
    source_url: str
    body: bytes
    retrieved_at: datetime
    kind: EvidenceKind
    status_code: int = 200
    retry_after_seconds: float | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    retry_after_exceeds_limit: bool = False

    def __post_init__(self):
        utc(self.retrieved_at)
        if not isinstance(self.body, bytes) or not 0 < len(self.body) <= MAX_SOURCE_BYTES:
            raise ValueError("source response body exceeds the collection limit")
        if not isinstance(self.kind, EvidenceKind) or self.kind not in {
            EvidenceKind.FIXTURE, EvidenceKind.LIVE_INGESTION
        }:
            raise ValueError("source response requires explicit ingestion evidence")
        if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
            raise ValueError("source response requires a valid HTTP status")
        if type(self.retry_after_exceeds_limit) is not bool:
            raise ValueError("source response retry policy marker must be boolean")
        if self.retry_after_seconds is not None and (
            type(self.retry_after_seconds) not in {int, float}
            or not math.isfinite(self.retry_after_seconds)
            or not 0 <= self.retry_after_seconds <= 86_400
        ):
            raise ValueError("source response Retry-After exceeds the supported bound")
        for header in (self.content_type, self.etag, self.last_modified):
            if header is not None and (not isinstance(header, str) or len(header) > 512):
                raise ValueError("source response header metadata is invalid")


class DeclaredTableRoute:
    """Register one institution's source-declared tabular formats and column mapping."""
    source_formats = frozenset({"csv", "tsv", "txt", "html", "zip", "xls", "xlsx"})

    def __init__(self, institution_id, transport=None):
        self.institution_id, self.transport = institution_id, transport

    def supports(self, record):
        access = record.access
        if (record.candidate.institution_id != self.institution_id or access is None
                or access.format not in self.source_formats
                or set(access.columns) != {"period", "country", "value"}):
            return False
        if access.format == "zip":
            if access.member is None:
                return False
            suffix = Path(access.member).suffix.lower()
            if suffix == ".xls" and importlib.util.find_spec("xlrd") is None:
                return False
        if access.format == "xls" and importlib.util.find_spec("xlrd") is None:
            return False
        if access.format == "txt" and access.delimiter is None:
            return False
        return not (access.format == "zip" and Path(access.member).suffix.lower() == ".txt"
                    and access.delimiter is None)

    def formats_for(self, record):
        return ("raw_" + record.access.format,) if self.supports(record) else ()

    def available(self, record, at):
        access = record.access
        return (self.transport is not None and access.status == "available"
                and access.checked_at <= at < access.expires_at
                and not access.manual_filter_required
                and record.candidate.auth_requirement == "none"
                and record.candidate.frequency in {"monthly", "annual"})

    def dispatcher(self, settings, history, record, clock):
        return _TableDispatcher(settings, history, record, self.transport, clock)


class DeclaredCSVRoute(DeclaredTableRoute):
    """Compatibility route restricted to CSV source declarations."""
    def supports(self, record):
        return super().supports(record) and record.access.format == "csv"


_SOURCE_MEDIA_TYPES = {
    "csv": {"text/csv", "application/csv", "text/plain", "application/octet-stream"},
    "tsv": {"text/tab-separated-values", "text/csv", "text/plain", "application/octet-stream"},
    "txt": {"text/plain", "application/octet-stream"},
    "html": {"text/html", "application/xhtml+xml", "application/octet-stream"},
    "zip": {"application/zip", "application/x-zip-compressed", "application/octet-stream"},
    "xls": {"application/vnd.ms-excel", "application/octet-stream"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "application/octet-stream"},
}


def _periods(start, end, frequency):
    if frequency == "annual":
        if len(start) != 4 or len(end) != 4:
            raise ValueError("annual source requires annual periods")
        values = [str(year) for year in range(int(start), int(end) + 1)]
    elif frequency == "monthly":
        if len(start) != 7 or len(end) != 7:
            raise ValueError("monthly source requires monthly periods")
        first = int(start[:4]) * 12 + int(start[5:]) - 1
        last = int(end[:4]) * 12 + int(end[5:]) - 1
        values = [f"{index // 12:04}-{index % 12 + 1:02}" for index in range(first, last + 1)]
    else:
        raise ValueError("only declared annual/monthly CSV periods are supported")
    if not 1 <= len(values) <= 120:
        raise ValueError("CSV collection requires 1 to 120 periods")
    return values


class _TableDispatcher:
    def __init__(self, settings, history, record, transport, clock):
        self.settings, self.history, self.record = settings, history, record
        self.transport, self.clock = transport, clock

    def _runner(self, task_id, confirmed):
        candidate, request = confirmed.offer.candidate, confirmed.offer.request
        if (candidate.candidate_id != self.record.candidate.candidate_id or
                candidate.metadata_revision != self.record.candidate.metadata_revision):
            raise ValueError("CSV route belongs to another candidate revision")
        if confirmed.delivery.mode == "link":
            return deliver_links(self.history, task_id, self.clock())
        access = self.record.access
        if (access is None or access.status != "available" or
                not access.checked_at <= self.clock() < access.expires_at):
            raise ValueError("CSV source access expired or unavailable")
        output_format = "raw_" + access.format
        if confirmed.delivery.file.format != output_format:
            raise ValueError("file output must preserve the declared source format")
        if confirmed.delivery.file.resolve_under(self.settings.project_root) != self.settings.raw_dir:
            raise ValueError("only the configured raw directory is supported")
        if (request.unit_policy != "preserve" or request.vintage_requirement != "latest_available"
                or request.target_unit is not None or candidate.auth_requirement != "none"
                or dict(request.dimensions) or dict(candidate.dimensions)):
            raise ValueError("CSV route supports preserved units, latest data and no extra dimensions")
        if request.frequency not in {None, "source", candidate.frequency}:
            raise ValueError("requested frequency differs from the selected source frequency")
        if not 1 <= len(request.countries) <= 10:
            raise ValueError("CSV collection country budget is 1 to 10")
        if confirmed.delivery.mode == "both" and any(
            link["url"] != access.url for link in _selected_links(confirmed)
        ):
            raise ValueError("CSV data link differs from the selected source path")
        _periods(request.period_start, request.period_end, candidate.frequency)
        runner = Orchestrator(
            self.history, {("declared_table", "1"): _TableEngine(self, confirmed)}, clock=self.clock)
        plan = TaskPlan((StageSpec("collect", "declared_table", {
            "candidate_id": candidate.candidate_id, "metadata_revision": candidate.metadata_revision,
            "confirmation_fingerprint": confirmed.fingerprint,
        }, max_attempts=3, reuse_ttl_seconds=0),))
        existing = self.history.get(task_id)
        if existing["status"] == TaskStatus.COMPLETED:
            payload = existing["stages"][0]["result"]["payload"]
            raw_filename = "response." + self.record.access.format
            for name, filename, checksum in (
                ("raw_path", raw_filename, "raw_sha256"),
                ("manifest_path", "request.json", "manifest_sha256"),
            ):
                file = self.settings._inside(payload[name])
                if (not file.is_relative_to(self.settings.raw_dir / "discovered") or
                        file.name != filename or
                        hashlib.sha256(file.read_bytes()).hexdigest() != payload[checksum]):
                    raise ValueError("completed table artifact integrity check failed")
        if existing["plan"] is not None and existing["plan"] != plan.snapshot():
            raise ValueError("saved table plan differs from the confirmed discovery")
        runner.plan(task_id, plan)
        return runner

    def run(self, task_id):
        confirmed = _confirmed(self.history, task_id, self.clock())
        return self._runner(task_id, confirmed).run(task_id)

    def resume(self, task_id, *, approved=False):
        confirmed = _confirmed(self.history, task_id, self.clock())
        return self._runner(task_id, confirmed).resume(task_id, approved=approved)


class _TableEngine:
    def __init__(self, dispatcher, confirmed):
        self.dispatcher, self.confirmed = dispatcher, confirmed

    def run(self, stage):
        d, confirmed = self.dispatcher, self.confirmed
        access = d.record.access
        transport_kind = getattr(d.transport, "kind", None)
        if not isinstance(transport_kind, EvidenceKind) or transport_kind not in {
            EvidenceKind.FIXTURE, EvidenceKind.LIVE_INGESTION
        }:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.AUTH_ACCESS,
                               warnings=("An explicitly classified source transport is required.",))
        if transport_kind != EvidenceKind.FIXTURE and not d.settings.network_enabled:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.AUTH_ACCESS,
                               warnings=("Network access is disabled.",))
        paths, refs = {}, ()
        try:
            response = d.transport.fetch(access.url)
            if not isinstance(response, SourceDownload):
                raise ValueError("unclassified source response")  # noqa: TRY004 - source value boundary
            if response.kind != transport_kind or response.source_url != access.url:
                return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                                   warnings=("Response identity differs from the confirmed source.",))
            relative = Path(d.settings.data_dir) / "raw" / "discovered" / uuid4().hex
            folder = d.settings._inside(str(relative))
            folder.mkdir(parents=True, exist_ok=False)
            raw_name = "response." + access.format
            raw = folder / raw_name
            with raw.open("xb") as stream:
                stream.write(response.body)
            raw_hash = hashlib.sha256(response.body).hexdigest()
            manifest = folder / "request.json"
            candidate = confirmed.offer.candidate
            metadata = {
                "source_agency": candidate.institution_id, "source_url": access.url,
                "retrieved_at": response.retrieved_at.isoformat(), "http_status": response.status_code,
                "mode": response.kind.value, "raw_sha256": raw_hash,
                "metadata_revision": candidate.metadata_revision,
                "source_version": candidate.source_version,
                "raw_filename": raw_name, "source_format": access.format,
                "content_type": response.content_type, "etag": response.etag,
                "last_modified": response.last_modified,
                "retry_after_seconds": response.retry_after_seconds,
                "retry_after_exceeds_limit": response.retry_after_exceeds_limit,
                "parser_version": 1, "parse_selection": {
                    "member": access.member, "sheet": access.sheet,
                    "delimiter": access.delimiter, "table_index": access.table_index,
                },
                "candidate": candidate.to_dict(), "request": confirmed.offer.request.to_dict(),
                "confirmation_fingerprint": confirmed.fingerprint,
                "license_note": "Source-specific terms require separate review; no blanket grant.",
            }
            with manifest.open("x", encoding="utf-8") as stream:
                json.dump(metadata, stream, ensure_ascii=False, allow_nan=False)
            paths = {"raw_path": raw.relative_to(d.settings.project_root).as_posix(),
                     "manifest_path": manifest.relative_to(d.settings.project_root).as_posix()}
            refs = tuple(paths.values())
            if response.retrieved_at < access.checked_at or response.retrieved_at > d.clock():
                return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                   ("Response timestamp is outside confirmed source-access evidence.",),
                                   ErrorCode.SEMANTIC_AMBIGUITY)
            try:
                fresh_confirmation = _confirmed(d.history, stage.task_id, d.clock())
            except ValueError:
                fresh_confirmation = None
            if (fresh_confirmation is None or
                    fresh_confirmation.fingerprint != confirmed.fingerprint):
                return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                   ("Source metadata or confirmation changed during collection; re-search required.",),
                                   ErrorCode.SEMANTIC_AMBIGUITY)
            if response.status_code in {408, 429} or 500 <= response.status_code <= 599:
                if response.status_code == 429 and response.retry_after_exceeds_limit:
                    return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                       ("Source Retry-After exceeds the supported wait policy.",),
                                       ErrorCode.TRANSIENT)
                delay = retry_delay(stage.attempt_no, response.retry_after_seconds)
                return StageResult(
                    StageStatus.FAILED_RETRYABLE, paths, refs,
                    ("Source returned a temporary HTTP failure; no observations were accepted.",),
                    ErrorCode.TRANSIENT, "Resume is delayed by the recorded bounded backoff.", delay)
            if response.status_code in {401, 403}:
                return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                   ("Source access was denied; no authentication bypass attempted.",),
                                   ErrorCode.AUTH_ACCESS)
            if 300 <= response.status_code < 400:
                return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                   ("Redirect refused; source route requires review.",),
                                   ErrorCode.LICENSE_SECURITY)
            if response.status_code in {404, 410}:
                return StageResult(StageStatus.FAILED_TERMINAL, paths, refs,
                                   ("Declared source path no longer exists.",), ErrorCode.SITE_CHANGED)
            if response.status_code != 200:
                return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                   ("Source returned an unexpected HTTP response; raw retained.",),
                                   ErrorCode.SCHEMA_CHANGED)
            if response.content_type:
                media_type = response.content_type.split(";", 1)[0].strip().lower()
                if media_type not in _SOURCE_MEDIA_TYPES[access.format]:
                    return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                                       ("Response media type differs from the declared source format.",),
                                       ErrorCode.SCHEMA_CHANGED)
            parsed = parse_table(
                response.body, access.format, delimiter=access.delimiter,
                member=access.member, sheet=access.sheet, table_index=access.table_index,
            )
            if (not parsed.rows or len(parsed.rows[0]) != len(set(parsed.rows[0]))
                    or set(parsed.rows[0]) != set(access.columns.values())):
                raise ValueError("source CSV columns changed")
            requested = confirmed.offer.request
            periods = _periods(requested.period_start, requested.period_end, candidate.frequency)
            rows, seen = [], set()
            for values in parsed.rows[1:]:
                if len(values) != len(parsed.rows[0]):
                    raise ValueError("source CSV row shape changed")
                source = dict(zip(parsed.rows[0], values, strict=True))
                period, country, value = (source[access.columns[k]] for k in
                                          ("period", "country", "value"))
                if period not in periods or country not in requested.countries:
                    continue
                key = (period, country)
                if key in seen:
                    raise ValueError("duplicate requested observation")
                seen.add(key)
                if value in access.missing_values:
                    normalized = None
                else:
                    number = Decimal(value)
                    if not number.is_finite():
                        raise ValueError("nonfinite source observation")
                    normalized = str(number)
                rows.append({"period": period, "country": country, "value": normalized,
                             "source_value": value, "unit": candidate.unit,
                             "frequency": candidate.frequency})
            if seen != {(p, c) for p in periods for c in requested.countries}:
                raise ValueError("requested observation coverage is incomplete")
            return StageResult(
                StageStatus.SUCCEEDED, {**paths, "raw_sha256": raw_hash,
                                       "raw_filename": raw_name, "source_format": access.format,
                                       "source_member": parsed.source_member,
                                       "sheet_name": parsed.sheet_name,
                                       "mode": response.kind.value, "observations": rows,
                                       "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                                       "links": _selected_links(confirmed)}, refs,
                parsed.warnings
                + (("source_unit_unknown_preserved",) if candidate.unit is None else ())
                + (("source_content_type_unreported",) if not response.content_type else ()))
        except (TimeoutError, ConnectionError, RequestException):
            delay = retry_delay(stage.attempt_no)
            return StageResult(StageStatus.FAILED_RETRYABLE, paths, refs,
                               ("Source transport timed out or disconnected; no partial response accepted.",),
                               ErrorCode.TRANSIENT,
                               "Resume is delayed by the recorded bounded backoff.", delay)
        except (ValueError, InvalidOperation, UnicodeError):
            return StageResult(StageStatus.NEEDS_REVIEW, paths, refs,
                               ("Source identity/schema/values require review; saved raw is retained.",),
                               ErrorCode.SCHEMA_CHANGED)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, paths, refs,
                               ("Local source preservation failed; existing files retained.",),
                               ErrorCode.INTERNAL_BUG)
