"""Alignment 01 value contracts only: no workflow service, storage or collection."""
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlsplit

from macro_data_platform.contracts import EvidenceKind, SourceEvidence, utc

_CREDENTIAL_NAMES = {"key", "apikey", "token", "accesstoken", "password", "secret",
                     "authorization", "appid", "applicationid", "userid", "clientsecret",
                     "subscriptionkey"}


def _credential_name(name: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", name.lower()) in _CREDENTIAL_NAMES


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: Any, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    _check(isinstance(value, str) and bool(value.strip()), "Expected nonempty text")


def _strings(value: Any) -> tuple[str, ...]:
    _check(isinstance(value, (tuple, list)), "Expected a sequence of text")
    for item in value:
        _text(item)
    _check(len(value) == len(set(value)), "Duplicate values are not allowed")
    return tuple(value)


def _dimensions(value: Any) -> Mapping | None:
    if value is None:
        return None
    _check(isinstance(value, Mapping), "Expected dimension codes")
    result = {}
    for key, codes in value.items():
        _text(key)
        _check(not _credential_name(key), "Credentials cannot be dimension codes")
        result[key] = _strings(codes)
        _check(bool(result[key]), "Dimension selections cannot be empty")
    return MappingProxyType(result)


def _period(value: str) -> tuple:
    _text(value)
    match = re.fullmatch(r"([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?|-Q([1-4]))?", value)
    _check(match is not None, "Expected a resolved calendar period")
    year, month, day, quarter = match.groups()
    _check(int(year) > 0, "Invalid calendar period")
    if quarter:
        return ("quarter", int(year), int(quarter))
    if month:
        try:
            date(int(year), int(month), int(day or "1"))
        except ValueError:
            raise ValueError("Invalid calendar period") from None
        return ("day", int(year), int(month), int(day)) if day else ("month", int(year), int(month))
    return ("year", int(year))


def _range(start: str | None, end: str | None) -> None:
    for value in (start, end):
        if value is not None:
            _period(value)
    if start is not None and end is not None:
        first, last = _period(start), _period(end)
        _check(first[0] == last[0] and first <= last, "Inconsistent period bounds")


def _utc(value: Any) -> None:
    _check(isinstance(value, datetime), "Expected a UTC timestamp")
    utc(value)


def _datetime(value: Any) -> datetime:
    _text(value)
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid UTC timestamp") from None
    _utc(result)
    return result


def _safe_url(value: str) -> None:
    _text(value)
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and parsed.username is None and parsed.password is None)
        names = [name for name, _ in parse_qsl(parsed.query, keep_blank_values=True)]
        _check(bool(valid) and not any(_credential_name(name) for name in names),
               "Evidence URL must not contain credentials")
    except ValueError:
        raise ValueError("Invalid or credential-bearing evidence URL") from None


def _encode(value: Any) -> Any:
    if isinstance(value, ValueContract):
        return value.to_dict()
    if isinstance(value, SourceEvidence):
        return {item.name: _encode(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _json_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        _check(key not in result, "Duplicate JSON fields")
        result[key] = value
    return result


def _json_constant(value: str) -> None:
    raise ValueError("Nonstandard JSON numeric constant")


class ValueContract:
    _decoders: ClassVar[dict[str, Callable]] = {}

    def __repr__(self) -> str:
        # Requests/labels can contain arbitrary user text. Never echo it implicitly.
        return f"{type(self).__name__}(<values omitted>)"

    def to_dict(self) -> dict:
        return {"schema_version": 1,
                **{item.name: _encode(getattr(self, item.name)) for item in fields(self)}}

    def to_json(self) -> str:
        return _canonical(self)

    @classmethod
    def from_dict(cls, data: Any):
        try:
            _check(isinstance(data, dict), "Expected a contract object")
            _check(type(data.get("schema_version")) is int and data["schema_version"] == 1,
                   "Unsupported contract version")
            allowed = {item.name for item in fields(cls)} | {"schema_version"}
            _check(not set(data) - allowed, "Unknown contract fields")
            kwargs = {key: value for key, value in data.items()
                      if key != "schema_version" and key != "fingerprint"}
            for key, decoder in cls._decoders.items():
                if key in kwargs:
                    kwargs[key] = decoder(kwargs[key])
            instance = cls(**kwargs)
            if "fingerprint" in allowed:
                _check(data.get("fingerprint") == instance.fingerprint, "Snapshot mismatch")
            return instance
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise ValueError("Invalid workflow contract snapshot") from None

    @classmethod
    def from_json(cls, text: str):
        try:
            return cls.from_dict(json.loads(text, object_pairs_hook=_json_object,
                                            parse_constant=_json_constant))
        except (ValueError, TypeError, RecursionError):
            raise ValueError("Invalid workflow contract JSON") from None


@dataclass(frozen=True, repr=False)
class DataRequest(ValueContract):
    request_id: str
    text: str
    concept: str | None = None
    institution_hint: str | None = None
    countries: tuple[str, ...] = ()
    dimensions: Mapping[str, tuple[str, ...]] | None = None
    period_start: str | None = None
    period_end: str | None = None
    frequency: str | None = None
    unit_policy: str | None = None
    target_unit: str | None = None
    vintage_requirement: str | None = None

    def __post_init__(self) -> None:
        _text(self.request_id)
        _text(self.text)
        for name in ("concept", "institution_hint", "target_unit", "vintage_requirement"):
            _text(getattr(self, name), optional=True)
        object.__setattr__(self, "countries", _strings(self.countries))
        object.__setattr__(self, "dimensions", _dimensions(self.dimensions))
        _range(self.period_start, self.period_end)
        _check(self.frequency in (None, "source", "annual", "quarterly", "monthly", "daily"),
               "Unknown frequency policy")
        _check(self.unit_policy in (None, "preserve", "convert"), "Unknown unit policy")
        _check(self.unit_policy != "preserve" or self.target_unit is None,
               "Preservation cannot specify a target unit")


def _evidence_from_dict(value: Any) -> SourceEvidence:
    _check(isinstance(value, dict), "Expected evidence fields")
    data = dict(value)
    data["retrieved_at"] = _datetime(data["retrieved_at"])
    data["kind"] = EvidenceKind(data["kind"])
    _safe_url(data["source_url"])
    return SourceEvidence(**data)


def _evidence_sequence(value: Any) -> tuple[SourceEvidence, ...]:
    _check(isinstance(value, (tuple, list)), "Expected source evidence")
    result = []
    for item in value:
        _check(isinstance(item, SourceEvidence), "Expected source evidence")
        for name in ("evidence_id", "source_agency", "original_ref"):
            _text(getattr(item, name))
        for name in ("dataset_id", "series_id", "source_version"):
            _text(getattr(item, name), optional=True)
        _utc(item.retrieved_at)
        _safe_url(item.source_url)
        result.append(_evidence_from_dict(_encode(item)))
    _check(len({item.evidence_id for item in result}) == len(result), "Duplicate evidence identifiers")
    return tuple(result)


@dataclass(frozen=True, repr=False)
class Candidate(ValueContract):
    candidate_id: str
    institution_id: str
    label: str
    definition: str | None = None
    dataset_id: str | None = None
    series_id: str | None = None
    series_key: Mapping[str, str] = field(default_factory=dict)
    countries: tuple[str, ...] = ()
    dimensions: Mapping[str, tuple[str, ...]] | None = None
    frequency: str | None = None
    unit: str | None = None
    available_start: str | None = None
    available_end: str | None = None
    metadata_revision: str | None = None
    source_version: str | None = None
    evidence: tuple[SourceEvidence, ...] = ()
    rationale: str | None = None
    uncertainties: tuple[str, ...] = ()
    verification_status: str = "unknown"
    availability_status: str = "unknown"
    auth_requirement: str = "unknown"
    credential_env_var: str | None = None
    support_status: str = "unknown"
    supported_outputs: tuple[str, ...] = ()

    _decoders: ClassVar = {
        "evidence": lambda values: tuple(_evidence_from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        for name in ("candidate_id", "institution_id", "label"):
            _text(getattr(self, name))
        for name in ("definition", "dataset_id", "series_id", "frequency", "unit",
                     "metadata_revision", "source_version", "rationale", "credential_env_var"):
            _text(getattr(self, name), optional=True)
        _check(isinstance(self.series_key, Mapping), "Expected source dimension key")
        for key, value in self.series_key.items():
            _text(key)
            _text(value)
            _check(not _credential_name(key), "Credentials cannot be series keys")
        object.__setattr__(self, "series_key", MappingProxyType(dict(self.series_key)))
        for name in ("countries", "uncertainties", "supported_outputs"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        object.__setattr__(self, "dimensions", _dimensions(self.dimensions))
        object.__setattr__(self, "evidence", _evidence_sequence(self.evidence))
        _range(self.available_start, self.available_end)
        _check(self.verification_status in ("unknown", "documented", "metadata_verified"),
               "Unknown evidence verification status")
        _check(self.availability_status in ("unknown", "available", "unavailable"),
               "Unknown availability status")
        _check(self.auth_requirement in ("unknown", "none", "optional", "required"),
               "Unknown authentication requirement")
        _check(self.support_status in ("unknown", "supported", "unsupported"),
               "Unknown connector support status")
        _check(self.auth_requirement != "none" or self.credential_env_var is None,
               "Anonymous access cannot require a credential variable")
        if self.credential_env_var is not None:
            _check(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", self.credential_env_var) is not None,
                   "Expected a credential variable name, never a value")
        _check(self.auth_requirement != "required" or self.credential_env_var is not None,
               "Required authentication needs a credential variable name")


@dataclass(frozen=True, repr=False)
class CandidateProposal(ValueContract):
    proposal_id: str
    request_id: str
    revision: int
    created_at: datetime
    candidates: tuple[Candidate, ...] = ()

    _decoders: ClassVar = {
        "created_at": _datetime,
        "candidates": lambda values: tuple(Candidate.from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        _text(self.proposal_id)
        _text(self.request_id)
        _check(type(self.revision) is int and self.revision > 0, "Expected a positive revision")
        _utc(self.created_at)
        _check(isinstance(self.candidates, (list, tuple)), "Expected candidate sequence")
        _check(all(isinstance(item, Candidate) for item in self.candidates), "Expected candidates")
        _check(len({item.candidate_id for item in self.candidates}) == len(self.candidates),
               "Duplicate candidate identifiers")
        object.__setattr__(self, "candidates", tuple(self.candidates))


@dataclass(frozen=True, repr=False)
class OutputSpec(ValueContract):
    format: str
    relative_dir: str

    def __post_init__(self) -> None:
        _text(self.format)
        _text(self.relative_dir)
        _check(re.fullmatch(r"[a-z][a-z0-9_]*", self.format) is not None, "Invalid output format")
        value = self.relative_dir.replace("\\", "/")
        path = PureWindowsPath(value)
        parts = value.split("/")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}
        valid = not path.drive and not path.root and not value.startswith("/")
        for part in parts:
            valid = valid and part not in {"", ".", ".."} and part == part.rstrip(" .")
            valid = valid and not any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            valid = valid and part.split(".", 1)[0].upper() not in reserved
        _check(bool(valid), "Output directory must be a safe repository-relative path")
        object.__setattr__(self, "relative_dir", value)

    def resolve_under(self, project_root: Path) -> Path:
        root = project_root.resolve()
        path = (root / self.relative_dir).resolve()
        _check(path != root and path.is_relative_to(root), "Output path leaves the repository")
        return path


@dataclass(frozen=True, repr=False)
class ConfirmedSelection(ValueContract):
    request: DataRequest
    proposal: CandidateProposal
    candidate_id: str
    proposal_revision: int
    output: OutputSpec
    confirmed_at: datetime
    confirmation_method: str
    fingerprint: str = field(init=False)

    _decoders: ClassVar = {
        "request": DataRequest.from_dict, "proposal": CandidateProposal.from_dict,
        "output": OutputSpec.from_dict, "confirmed_at": _datetime,
    }

    def __post_init__(self) -> None:
        _check(isinstance(self.request, DataRequest) and isinstance(self.proposal, CandidateProposal)
               and isinstance(self.output, OutputSpec), "Expected typed confirmation snapshots")
        _text(self.candidate_id)
        _check(type(self.proposal_revision) is int and self.proposal_revision == self.proposal.revision,
               "Proposal revision mismatch")
        _check(self.request.request_id == self.proposal.request_id, "Request identity mismatch")
        _utc(self.confirmed_at)
        _check(self.confirmation_method in ("explicit_request", "followup"),
               "Explicit selection confirmation is required")
        _check(self.confirmed_at >= self.proposal.created_at, "Confirmation predates proposal")
        selected = [item for item in self.proposal.candidates if item.candidate_id == self.candidate_id]
        _check(len(selected) == 1, "Selected candidate does not exist")
        self._validate_selection(selected[0])
        content = self._content(self.request, self.proposal, self.output)
        object.__setattr__(self, "fingerprint", hashlib.sha256(_canonical(content).encode()).hexdigest())

    def _validate_selection(self, candidate: Candidate) -> None:
        request = self.request
        _check(request.concept is not None and bool(request.countries)
               and request.dimensions is not None and request.period_start is not None
               and request.period_end is not None and request.frequency is not None
               and request.unit_policy is not None and request.vintage_requirement is not None,
               "Required request conditions remain unknown")
        _check(candidate.definition is not None and bool(candidate.series_id or candidate.series_key)
               and bool(candidate.evidence) and candidate.verification_status != "unknown",
               "Candidate identity, definition or evidence remains unverified")
        _check(candidate.availability_status == "available" and candidate.support_status == "supported"
               and candidate.auth_requirement != "unknown", "Candidate access remains unresolved")
        _check(self.output.format in candidate.supported_outputs, "Requested output is unsupported")
        _check(set(request.countries).issubset(candidate.countries), "Country coverage mismatch")
        _check(candidate.dimensions is not None
               and set(request.dimensions) == set(candidate.dimensions), "Dimension coverage mismatch")
        for key, codes in request.dimensions.items():
            _check(set(codes).issubset(candidate.dimensions[key]), "Dimension selection mismatch")
        _check(candidate.available_start is not None and candidate.available_end is not None,
               "Available period remains unknown")
        start, end = _period(request.period_start), _period(request.period_end)
        first, last = _period(candidate.available_start), _period(candidate.available_end)
        _check(start[0] == first[0] and end[0] == last[0] and first <= start <= end <= last,
               "Requested period is not covered by the candidate")
        if request.frequency != "source":
            _check(request.frequency == candidate.frequency, "Frequency interpretation unresolved")
        if request.unit_policy == "convert":
            _check(request.target_unit is not None and candidate.unit is not None,
                   "Unit conversion conditions remain unknown")
        if request.vintage_requirement != "latest_available":
            _check(request.vintage_requirement == candidate.source_version, "Vintage is not available")
        _check(all(item.retrieved_at <= self.confirmed_at for item in candidate.evidence),
               "Confirmation predates its evidence")

    def _content(self, request: DataRequest, proposal: CandidateProposal, output: OutputSpec) -> dict:
        return {"request": request, "proposal": proposal, "candidate_id": self.candidate_id,
                "proposal_revision": self.proposal_revision, "output": output}

    def matches(self, request: DataRequest, proposal: CandidateProposal, output: OutputSpec) -> bool:
        if not (isinstance(request, DataRequest) and isinstance(proposal, CandidateProposal)
                and isinstance(output, OutputSpec)):
            return False
        digest = hashlib.sha256(_canonical(self._content(request, proposal, output)).encode()).hexdigest()
        return digest == self.fingerprint
