"""Bounded evidence-backed candidate search and explicit collection planning."""
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.contracts import (
    ErrorCode,
    EvidenceKind,
    SourceEvidence,
    StageResult,
    StageStatus,
)
from macro_data_platform.discovery.search_policy import PROMOTED_SEARCH_POLICY
from macro_data_platform.ingestion.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    ConfirmedSelection,
    DataRequest,
)

MAX_CATALOG_PACKAGES = 100
MAX_NORMALIZED_BYTES = 2 * 1024 * 1024
MAX_SEARCH_RESULTS = 50
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOP_WORDS = {"a", "an", "and", "data", "find", "for", "from", "in", "of", "please",
               "series", "show", "the", "to", "with"}
_COUNTRY_ALIASES = {
    "USA": {"usa", "us", "united", "states", "america"},
    "JPN": {"japan", "jpn"}, "DEU": {"germany", "deu"},
}


def _worldbank_seed() -> Candidate:
    retrieved = datetime(2026, 10, 24, 15, 29, 32, tzinfo=UTC)
    data_url = (
        "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD"
        "?source=2&date=2020%3A2022&format=json&per_page=100&page=1"
    )
    evidence = (
        SourceEvidence("worldbank-wdi-guide", "World Bank",
                       "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
                       retrieved, EvidenceKind.OFFICIAL_DOCS,
                       "docs/connectors/WORLDBANK.md:indicator-reference"),
        SourceEvidence("worldbank-gate-a-run", "World Bank", data_url, retrieved,
                       EvidenceKind.LIVE_INGESTION,
                       "docs/ITERATION_04_REPORT.md:2020-2022-live-result"),
    )
    return Candidate(
        candidate_id="worldbank:2:USA:NY.GDP.MKTP.CD", institution_id="worldbank",
        label="GDP (current US$) — USA, WDI",
        definition=("Official indicator label only: GDP (current US$); the retained evidence "
                    "does not contain the full methodological definition."),
        dataset_id="2", series_key={"source": "2", "country": "USA",
                                    "indicator": "NY.GDP.MKTP.CD"},
        countries=("USA",), dimensions={}, frequency=None, unit=None,
        available_start="2020", available_end="2022", metadata_revision="gate-a-2026-10-24",
        evidence=evidence,
        rationale=("The same source, country, indicator and 2020–2022 period were collected "
                   "in the documented Gate A run."),
        uncertainties=("Full methodological definition is not in retained metadata.",
                       "Unit and frequency remain unknown; use source values without conversion.",
                       "Availability evidence covers only 2020–2022."),
        verification_status="documented", availability_status="available",
        auth_requirement="none", support_status="supported", supported_outputs=("raw_json",),
    )


def _safe_relative(settings: Settings, value: str) -> Path:
    path = settings._inside(value)
    if not path.is_file():
        raise ValueError("metadata evidence file is missing")
    return path


def _verified_archived_records(settings: Settings) -> list[tuple[str, dict, dict]]:
    root = settings._inside(f"{settings.data_dir}/raw/metadata")
    if not root.exists():
        return []
    manifests = sorted(root.glob("*/*/manifest.json"))
    if len(manifests) > MAX_CATALOG_PACKAGES:
        raise ValueError("metadata catalogue package limit exceeded")
    records = []
    for manifest_path in manifests:
        source = manifest_path.parent.parent.name
        if source not in {"bls", "census"}:
            continue
        manifest_rel = manifest_path.relative_to(settings.project_root).as_posix()
        if manifest_path.stat().st_size > 64 * 1024:
            raise ValueError("metadata manifest exceeds its size budget")
        manifest = json.loads(_safe_relative(settings, manifest_rel).read_text(encoding="utf-8"))
        raw_meta = manifest.get("raw", {})
        normalized_meta = manifest.get("normalized", {})
        raw_path = _safe_relative(settings, raw_meta.get("path", ""))
        normalized_path = _safe_relative(settings, normalized_meta.get("path", ""))
        if raw_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("metadata raw response exceeds its size budget")
        if normalized_path.stat().st_size > MAX_NORMALIZED_BYTES:
            raise ValueError("normalized metadata exceeds its size budget")
        raw = raw_path.read_bytes()
        normalized = normalized_path.read_bytes()
        if (hashlib.sha256(raw).hexdigest() != raw_meta.get("sha256")
                or hashlib.sha256(normalized).hexdigest() != normalized_meta.get("sha256")):
            raise ValueError("metadata source integrity check failed")
        parsed = urlsplit(manifest.get("source_url", ""))
        expected_host = "api.bls.gov" if source == "bls" else "api.census.gov"
        if (parsed.scheme != "https" or parsed.hostname != expected_host or parsed.query
                or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("metadata source URL is outside the official host")
        values = json.loads(normalized)
        if not isinstance(values, list) or len(values) > 10_000:
            raise ValueError("normalized metadata record count exceeds its limit")
        records.extend((source, manifest, value) for value in values if isinstance(value, dict))
        if len(records) > 5_000:
            raise ValueError("metadata catalogue record limit exceeded")
    return records


def _known(record: dict, field: str):
    value = record.get("fields", {}).get(field, {})
    return value.get("value") if value.get("state") == "known" else None


def _as_label(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values() if item not in (None, ""))[:1000]
    return ""


def _candidate_from_record(source: str, manifest: dict, record: dict) -> Candidate | None:
    entity_type = record.get("entity_type")
    if (source == "bls" and entity_type != "time_series") or (
        source == "census" and entity_type != "variable"
    ):
        return None
    identifier = record.get("identifier", {}).get("value")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z0-9_]{2,40}", identifier):
        return None
    label = _as_label(_known(record, "name")) or identifier
    attributes = record.get("source_attributes", {})
    searchable_attributes = " ".join(
        str(value) for value in attributes.values()
        if isinstance(value, (str, int, float)) and value not in (None, "")
    )[:1000]
    retrieved = datetime.fromisoformat(record["retrieved_at"])
    if retrieved.tzinfo is None or retrieved.utcoffset() is None or retrieved.utcoffset().total_seconds():
        return None
    raw_ref = record.get("raw_ref", {})
    original_ref = raw_ref.get("path")
    if not isinstance(original_ref, str):
        return None
    pointer = raw_ref.get("json_pointer", "")
    original_ref = f"{original_ref}{pointer}"
    source_url = record.get("source_url")
    if not isinstance(source_url, str):
        return None
    evidence_kind = EvidenceKind(manifest.get("evidence_kind", "fixture"))
    evidence_id = hashlib.sha256(f"{source_url}|{original_ref}".encode()).hexdigest()[:20]
    evidence = SourceEvidence(evidence_id, record.get("source_agency", source), source_url,
                              retrieved, evidence_kind, original_ref)
    dataset_value = record.get("dataset_id", {}).get("value")
    if isinstance(dataset_value, dict):
        dataset_value = None
    if dataset_value is not None and not isinstance(dataset_value, (str, int, float)):
        dataset_value = None
    dataset_id = str(dataset_value) if dataset_value is not None else None
    key = {"series_id": identifier} if source == "bls" else {
        "dataset": dataset_id or "", "variable_id": identifier,
        "year": str(record.get("source_version") or ""),
    }
    key = {name: value for name, value in key.items() if value}
    geo = _known(record, "geo_coverage")
    countries = ("USA",) if source == "bls" and geo == "U.S. city average" else ()
    verification = "documented" if evidence_kind in {
        EvidenceKind.LIVE_API, EvidenceKind.LIVE_INGESTION, EvidenceKind.OFFICIAL_DOCS,
    } else "unknown"
    uncertainties = []
    for field in ("definition", "frequency", "unit", "geo_coverage", "time_coverage"):
        if _known(record, field) is None:
            uncertainties.append(f"{field} is unknown in the source metadata")
    return Candidate(
        candidate_id=f"{source}:{dataset_id + ':' if dataset_id else ''}{identifier}",
        institution_id=source, label=label, definition=_as_label(_known(record, "definition")) or None,
        dataset_id=dataset_id, series_id=identifier, series_key=key,
        countries=countries, dimensions=None,
        frequency=_as_label(_known(record, "frequency")) or None,
        unit=_as_label(_known(record, "unit")) or None,
        available_start=None, available_end=None, metadata_revision=record.get("source_version"),
        source_version=record.get("source_version"), evidence=(evidence,),
        rationale=(f"{searchable_attributes} Source fields are candidate-generation evidence only; "
                   "they do not establish equivalence."),
        uncertainties=tuple(uncertainties), verification_status=verification,
        availability_status="unknown",
        auth_requirement="optional" if source == "bls" else "required",
        credential_env_var="BLS_API_KEY" if source == "bls" else "CENSUS_API_KEY",
        support_status="supported", supported_outputs=("raw_json",),
    )


def load_candidate_catalog(settings: Settings) -> tuple[Candidate, ...]:
    """Load one vetted WDI seed plus hash-verified local BLS/Census metadata archives."""
    candidates = [_worldbank_seed()]
    for source, manifest, record in _verified_archived_records(settings):
        candidate = _candidate_from_record(source, manifest, record)
        if candidate is not None:
            candidates.append(candidate)
    latest = {}
    for candidate in candidates:
        previous = latest.get(candidate.candidate_id)
        if (previous is None or candidate.evidence[0].retrieved_at
                > previous.evidence[0].retrieved_at):
            latest[candidate.candidate_id] = candidate
    return tuple(latest[key] for key in sorted(latest))


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in _TOKEN.findall(value) if item.casefold() not in _STOP_WORDS}


def _query_tokens(request: DataRequest) -> set[str]:
    basis = request.concept if request.concept else request.text
    tokens = _tokens(basis)
    if "us" in tokens or "u" in tokens:
        tokens.update({"usa", "united", "states"})
    if "japan" in tokens:
        tokens.add("jpn")
    if "germany" in tokens:
        tokens.add("deu")
    return tokens


def _candidate_tokens(candidate: Candidate) -> set[str]:
    content = " ".join((candidate.label, candidate.definition or "", candidate.dataset_id or "",
                        candidate.series_id or "", " ".join(candidate.series_key.values()),
                        " ".join(candidate.countries), candidate.rationale or ""))
    tokens = _tokens(content)
    for country in candidate.countries:
        tokens.update(_COUNTRY_ALIASES.get(country, {country.casefold()}))
    if candidate.available_start:
        tokens.add(candidate.available_start[:4])
    if candidate.available_end:
        tokens.add(candidate.available_end[:4])
    return tokens


def _term_present(query_term: str, candidate_terms: set[str]) -> bool:
    return query_term in candidate_terms or any(
        len(query_term) >= 3 and term.startswith(query_term) for term in candidate_terms
    )


def rank_candidates(request: DataRequest, candidates: Iterable[Candidate], *,
                    limit: int = MAX_SEARCH_RESULTS) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= MAX_SEARCH_RESULTS:
        raise ValueError("limit must be between 1 and 50")
    terms = _query_tokens(request)
    if not terms:
        return []
    ranked = []
    for candidate in candidates:
        if request.institution_hint and candidate.institution_id != request.institution_hint:
            continue
        if request.countries and candidate.countries and not set(request.countries).issubset(candidate.countries):
            continue
        if (request.frequency not in (None, "source") and candidate.frequency is not None
                and request.frequency != candidate.frequency):
            continue
        if request.period_start and candidate.available_start:
            if candidate.available_end is None:
                continue
            if (request.period_start < candidate.available_start
                    or (request.period_end is not None
                        and request.period_end > candidate.available_end)):
                continue
        if (request.dimensions and candidate.dimensions is not None
                and (set(request.dimensions) != set(candidate.dimensions)
                     or any(not set(values).issubset(candidate.dimensions[key])
                            for key, values in request.dimensions.items()))):
            continue
        candidate_terms = _candidate_tokens(candidate)
        matches = sorted(term for term in terms if _term_present(term, candidate_terms))
        if not matches:
            continue
        score = round(100 * len(matches) / len(terms), 2)
        missing = []
        if request.countries and not candidate.countries:
            missing.append("country_coverage_unknown")
        if request.period_start and not candidate.available_start:
            missing.append("period_coverage_unknown")
        if request.frequency not in (None, "source") and candidate.frequency is None:
            missing.append("frequency_unknown")
        if request.dimensions and candidate.dimensions is None:
            missing.append("dimensions_unknown")
        if candidate.definition is None:
            missing.append("definition_unknown")
        if candidate.availability_status == "unknown":
            missing.append("availability_unknown")
        if candidate.auth_requirement == "unknown":
            missing.append("authentication_requirement_unknown")
        fully_known = not missing and not candidate.uncertainties
        if score == 100 and fully_known and candidate.verification_status == "metadata_verified":
            status = "exact"
        elif candidate.verification_status == "unknown" or not fully_known:
            status = "review_required"
        elif score >= 50:
            status = "comparable"
        else:
            status = "related"
        ranked.append({
            "candidate": candidate, "score": score, "match_status": status,
            "matched_terms": matches, "missing_constraints": missing,
            "rationale": "Lexical score ranks candidates only; it does not prove statistical equivalence.",
        })
    ranked.sort(key=lambda item: (-item["score"], item["candidate"].candidate_id))
    return ranked[:limit]


class CandidateSearchEngine:
    """Register as (\"series_search\", \"1\"); no network access is performed."""
    def __init__(self, settings: Settings | None, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 candidate_loader: Callable[[Settings | None], Iterable[Candidate]] | None = None,
                 ranker: Callable[..., list[dict]] | None = None):
        self.settings, self.clock = settings, clock
        self.candidate_loader, self.ranker = candidate_loader, ranker

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) - {"request", "limit"}
                or "request" not in data):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected a structured request and optional result limit.",))
        try:
            structured = DataRequest.from_dict(data["request"])
            loader = self.candidate_loader or load_candidate_catalog
            ranker = self.ranker or PROMOTED_SEARCH_POLICY.rank
            candidates = loader(self.settings)
            ranked = ranker(structured, candidates, limit=data.get("limit", 25))
            at = self.clock()
            if at.tzinfo is None or at.utcoffset() is None or at.utcoffset().total_seconds():
                raise ValueError("clock must return UTC")
            proposal = CandidateProposal(
                f"search:{uuid4().hex}", structured.request_id, 1, at,
                tuple(item["candidate"] for item in ranked),
            )
        except (ValueError, TypeError, OSError, KeyError):
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Candidate catalogue or structured request needs review.",))
        payload = {
            "request": structured.to_dict(), "proposal": proposal.to_dict(),
            "ranking": [{key: value for key, value in item.items() if key != "candidate"}
                        | {"candidate_id": item["candidate"].candidate_id}
                        for item in ranked],
            "search_status": "candidates_found" if ranked else "unmatched",
            "selection_requires_explicit_confirmation": True,
            "ranking_policy": PROMOTED_SEARCH_POLICY.version if self.ranker is None else "injected",
            "ranking_policy_sha256": (
                PROMOTED_SEARCH_POLICY.sha256 if self.ranker is None else None
            ),
            "ranking_is_equivalence_proof": False,
        }
        refs = tuple(dict.fromkeys(e.original_ref for item in ranked
                                   for e in item["candidate"].evidence))
        warnings = () if not ranked else (
            "Rank is lexical; review source definitions, coverage and unknown fields before selection.",
        )
        if not ranked:
            warnings = ("No supported candidate matched the supplied terms.",)
        return StageResult(StageStatus.SUCCEEDED, payload, refs, warnings)


def _period_year(value: str) -> int:
    match = re.match(r"^(\d{4})(?:$|-Q[1-4]$|-\d{2}(?:-\d{2})?$)", value)
    if not match:
        raise ValueError("selected period cannot be sent to the available source connector")
    return int(match.group(1))


def _validate_output(selection: ConfirmedSelection, settings: Settings) -> None:
    if (selection.output.format != "raw_json"
            or selection.output.resolve_under(settings.project_root) != settings.raw_dir
            or selection.output.relative_dir != f"{settings.data_dir}/raw".replace("\\", "/")):
        raise ValueError("Only raw_json under the configured data/raw path is supported")


def build_confirmed_collection_plan(selection: ConfirmedSelection, settings: Settings) -> TaskPlan:
    """Turn an explicit, validated user selection into an auditable collection plan."""
    if not isinstance(selection, ConfirmedSelection):
        raise TypeError("expected an explicitly confirmed candidate selection")
    selection = ConfirmedSelection.from_dict(selection.to_dict())
    _validate_output(selection, settings)
    candidate = next(item for item in selection.proposal.candidates
                     if item.candidate_id == selection.candidate_id)
    if candidate.institution_id == "worldbank":
        from macro_data_platform.ingestion.worldbank_request import build_worldbank_plan
        collection = build_worldbank_plan(selection, settings)
    elif candidate.institution_id == "bls":
        if selection.request.dimensions or not candidate.series_id:
            raise ValueError("BLS dimension-specific discovery is not confirmed by this adapter")
        start = _period_year(selection.request.period_start)
        end = _period_year(selection.request.period_end)
        collection = TaskPlan((StageSpec("collect", "bls", {
            "series_ids": [candidate.series_id], "start_year": start, "end_year": end,
        }, engine_version="2"),))
    elif candidate.institution_id == "census":
        request = selection.request
        if (not candidate.dataset_id or not candidate.series_id or request.dimensions is None
                or set(request.dimensions) != {"for"} or len(request.dimensions["for"]) != 1):
            raise ValueError("Census collection requires a selected dataset variable and one geography")
        start, end = _period_year(request.period_start), _period_year(request.period_end)
        if start != end:
            raise ValueError("Census ACS selection requires one reference year")
        collection = TaskPlan((StageSpec("collect", "census", {
            "year": start, "dataset": candidate.dataset_id,
            "variables": ["NAME", candidate.series_id],
            "geography": request.dimensions["for"][0],
        }, engine_version="2"),))
    else:
        raise ValueError("selected institution has no registered observation connector")
    receipt = StageSpec("record_selection", "record_selection", {"selection": selection.to_dict()})
    return TaskPlan((receipt, *collection.stages))


class SelectionReceiptEngine:
    """Persist the exact candidate, evidence and user confirmation before collection."""
    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"selection"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected a confirmed-selection snapshot.",))
        try:
            selection = ConfirmedSelection.from_dict(data["selection"])
        except (ValueError, TypeError):
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SEMANTIC_AMBIGUITY,
                               warnings=("Candidate selection snapshot is invalid or changed.",))
        candidate = next(c for c in selection.proposal.candidates
                         if c.candidate_id == selection.candidate_id)
        return StageResult(StageStatus.SUCCEEDED, {
            "confirmation_fingerprint": selection.fingerprint,
            "confirmation_method": selection.confirmation_method,
            "confirmed_at": selection.confirmed_at.isoformat(),
            "proposal_revision": selection.proposal_revision,
            "candidate": candidate.to_dict(),
        }, tuple(e.original_ref for e in candidate.evidence))


def candidate_collection_engines(settings: Settings, *, worldbank_transport=None,
                                 bls_transport=None, census_transport=None,
                                 clock=lambda: datetime.now(UTC),
                                 freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY
                                 ) -> dict:
    from macro_data_platform.ingestion.bls import BLSEngine
    from macro_data_platform.ingestion.census import CensusEngine
    from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine

    return {
        ("record_selection", "1"): SelectionReceiptEngine(),
        ("worldbank_gdp", "2"): WorldBankGDPEngine(
            settings, worldbank_transport, clock=clock, freshness_policy=freshness_policy),
        ("bls", "2"): BLSEngine(
            settings, bls_transport, clock=clock, freshness_policy=freshness_policy),
        ("census", "2"): CensusEngine(
            settings, census_transport, clock=clock, freshness_policy=freshness_policy),
    }
