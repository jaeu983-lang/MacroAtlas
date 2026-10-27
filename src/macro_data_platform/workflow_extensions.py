"""Additive alignment 01 contracts. No link discovery, questions, I/O or task execution."""
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
from types import MappingProxyType
from typing import ClassVar
from urllib.parse import parse_qsl, urlsplit

from macro_data_platform.contracts import SourceEvidence
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    ConfirmedSelection,
    DataRequest,
    OutputSpec,
    ValueContract,
    _canonical,
    _check,
    _credential_name,
    _datetime,
    _evidence_from_dict,
    _evidence_sequence,
    _period,
    _safe_url,
    _strings,
    _text,
    _utc,
)


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _sequence(values, model) -> tuple:
    _check(isinstance(values, (tuple, list)), "Expected a contract sequence")
    _check(all(isinstance(item, model) for item in values), "Unexpected contract sequence item")
    return tuple(values)


def _public_url(value: str, *, evidence_reference: bool = False) -> None:
    _safe_url(value)
    parsed = urlsplit(value)
    try:
        port = parsed.port
        _check(port is None or port > 0, "Invalid public data URL")
    except ValueError:
        raise ValueError("Invalid public data URL") from None
    # Sharing a signed/capability URL is not made safe by labelling it 'blocked'.
    names = [key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    fragment_keys = [key for key, _ in parse_qsl(parsed.fragment, keep_blank_values=True)]
    _check(not any(_credential_name(name) for name in names)
           and (not parsed.fragment or (evidence_reference
                and not any(_credential_name(key) for key in fragment_keys))),
           "Data URL may contain credentials or an opaque fragment")


@dataclass(frozen=True, repr=False)
class DeliverySpec(ValueContract):
    mode: str | None = None
    file: OutputSpec | None = None
    link_ids: tuple[str, ...] = ()

    _decoders: ClassVar = {"file": lambda value: None if value is None else OutputSpec.from_dict(value)}

    def __post_init__(self) -> None:
        _check(self.mode in (None, "file", "link", "both"), "Unknown delivery mode")
        _check(self.file is None or isinstance(self.file, OutputSpec), "Expected file output settings")
        object.__setattr__(self, "link_ids", _strings(self.link_ids))
        _check(self.mode != "link" or self.file is None, "Link-only delivery cannot request a file")
        _check(self.mode != "file" or not self.link_ids, "File-only delivery cannot select links")
        if self.file is not None:
            _check(self.file.format not in {"file", "link", "both"},
                   "Delivery mode is not a file format")

    @property
    def requires_choice(self) -> bool:
        return self.mode is None


@dataclass(frozen=True, repr=False)
class VariantAttributes(ValueContract):
    seasonal_adjustment: str | None = None
    price_basis: str | None = None
    base_period: str | None = None
    stock_flow: str | None = None
    measure: str | None = None
    frequency: str | None = None
    unit: str | None = None
    scale: str | None = None
    revision_status: str | None = None
    methodology: str | None = None
    population: str | None = None
    source_codes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for item in fields(self):
            if item.name != "source_codes":
                _text(getattr(self, item.name), optional=True)
        _check(self.stock_flow in (None, "stock", "flow", "not_applicable"), "Unknown stock/flow code")
        _check(self.measure in (None, "level", "index", "rate", "change"), "Unknown measure code")
        _check(isinstance(self.source_codes, Mapping), "Expected original source codes")
        copied = {}
        for key, value in self.source_codes.items():
            _text(key)
            _text(value)
            _check(not _credential_name(key), "Credentials cannot be variant source codes")
            copied[key] = value
        object.__setattr__(self, "source_codes", MappingProxyType(copied))


@dataclass(frozen=True, repr=False)
class CandidateVariant(ValueContract):
    candidate_id: str
    concept_id: str
    attributes: VariantAttributes = field(default_factory=VariantAttributes)
    evidence: tuple[SourceEvidence, ...] = ()

    _decoders: ClassVar = {
        "attributes": VariantAttributes.from_dict,
        "evidence": lambda values: tuple(_evidence_from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        _text(self.candidate_id)
        _text(self.concept_id)
        _check(isinstance(self.attributes, VariantAttributes), "Expected variant attributes")
        object.__setattr__(self, "evidence", _evidence_sequence(self.evidence))
        has_attributes = any(getattr(self.attributes, item.name) is not None
                             for item in fields(self.attributes) if item.name != "source_codes")
        _check(not (has_attributes or self.attributes.source_codes) or bool(self.evidence),
               "Variant attributes require source evidence")


@dataclass(frozen=True, repr=False)
class CandidateGroup(ValueContract):
    group_id: str
    concept_id: str
    candidate_ids: tuple[str, ...]
    rationale: str
    evidence: tuple[SourceEvidence, ...]

    _decoders: ClassVar = {
        "evidence": lambda values: tuple(_evidence_from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        for name in ("group_id", "concept_id", "rationale"):
            _text(getattr(self, name))
        object.__setattr__(self, "candidate_ids", _strings(self.candidate_ids))
        object.__setattr__(self, "evidence", _evidence_sequence(self.evidence))
        _check(bool(self.candidate_ids) and bool(self.evidence), "Groups need members and evidence")


@dataclass(frozen=True, repr=False)
class GroupedProposal(ValueContract):
    proposal: CandidateProposal
    variants: tuple[CandidateVariant, ...] = ()
    groups: tuple[CandidateGroup, ...] = ()

    _decoders: ClassVar = {
        "proposal": CandidateProposal.from_dict,
        "variants": lambda values: tuple(CandidateVariant.from_dict(item) for item in values),
        "groups": lambda values: tuple(CandidateGroup.from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        _check(isinstance(self.proposal, CandidateProposal), "Expected an original candidate proposal")
        object.__setattr__(self, "variants", _sequence(self.variants, CandidateVariant))
        object.__setattr__(self, "groups", _sequence(self.groups, CandidateGroup))
        known = {item.candidate_id for item in self.proposal.candidates}
        variants = {item.candidate_id: item for item in self.variants}
        _check(len(variants) == len(self.variants) and set(variants).issubset(known),
               "Unknown or repeated variant candidate")
        _check(len({item.group_id for item in self.groups}) == len(self.groups), "Duplicate group IDs")
        originals = {item.candidate_id: item for item in self.proposal.candidates}
        for key, variant in variants.items():
            for name in ("frequency", "unit"):
                stated, original = getattr(variant.attributes, name), getattr(originals[key], name)
                _check(stated is None or original is None or stated == original,
                       "Variant attributes contradict the original candidate")
        grouped = set()
        for group in self.groups:
            members = set(group.candidate_ids)
            _check(members.issubset(variants) and not members.intersection(grouped),
                   "Unknown, unclassified or multiply grouped candidate")
            _check(all(variants[key].concept_id == group.concept_id for key in members),
                   "Different concepts cannot form one variant group")
            for name in ("stock_flow", "measure"):
                values = {getattr(variants[key].attributes, name) for key in members}
                values.discard(None)
                _check(len(values) <= 1, "Conflicting statistical concepts require separate groups")
            grouped.update(members)


@dataclass(frozen=True, repr=False)
class DataLink(ValueContract):
    link_id: str
    candidate_id: str
    proposal_id: str
    proposal_revision: int
    target_fingerprint: str
    status: str = "unknown"
    url: str | None = None
    kind: str | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None
    official: bool | None = None
    shareable: bool | None = None
    access_requirement: str = "unknown"
    manual_filter_required: bool | None = None
    reason: str | None = None
    restrictions: tuple[str, ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()

    _decoders: ClassVar = {
        "checked_at": lambda value: None if value is None else _datetime(value),
        "expires_at": lambda value: None if value is None else _datetime(value),
        "evidence": lambda values: tuple(_evidence_from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        for name in ("link_id", "candidate_id", "proposal_id", "target_fingerprint"):
            _text(getattr(self, name))
        _check(type(self.proposal_revision) is int and self.proposal_revision > 0,
               "Expected a positive proposal revision")
        _check(re.fullmatch(r"[0-9a-f]{64}", self.target_fingerprint) is not None,
               "Expected a target fingerprint")
        _check(self.status in ("available", "unavailable", "unknown", "blocked"),
               "Unknown data link status")
        _check(self.kind in (None, "download", "api", "viewer", "reference"), "Unknown link type")
        _check(self.access_requirement in ("unknown", "public", "authentication_required",
                                           "permission_required"), "Unknown link access requirement")
        for name in ("official", "shareable", "manual_filter_required"):
            value = getattr(self, name)
            _check(value is None or type(value) is bool, "Expected an explicit boolean or unknown")
        _text(self.reason, optional=True)
        object.__setattr__(self, "restrictions", _strings(self.restrictions))
        object.__setattr__(self, "evidence", _evidence_sequence(self.evidence))
        if self.url is not None:
            _public_url(self.url)
        for item in self.evidence:
            _public_url(item.source_url, evidence_reference=True)
        for stamp in (self.checked_at, self.expires_at):
            if stamp is not None:
                _utc(stamp)
        if self.expires_at is not None and self.status == "available":
            _check(self.checked_at is not None and self.expires_at > self.checked_at,
                   "Link expiry must follow verification time")
        if self.status in ("unavailable", "blocked"):
            _check(self.reason is not None and self.checked_at is not None and bool(self.evidence),
                   "Unavailable links require a scoped reason and verification time")
        if self.status == "available":
            _check(self.url is not None and self.kind in ("download", "api", "viewer")
                   and self.checked_at is not None and self.official is True and self.shareable is True
                   and self.access_requirement == "public"
                   and self.manual_filter_required is not None and bool(self.evidence),
                   "Available data links require verified public data access and evidence")
        if self.checked_at is not None:
            _check(all(item.retrieved_at <= self.checked_at for item in self.evidence),
                   "Link verification predates its evidence")

    def usable_at(self, at: datetime) -> bool:
        _utc(at)
        return (self.status == "available" and self.checked_at <= at
                and (self.expires_at is None or at < self.expires_at))


def link_target_fingerprint(request: DataRequest, proposal: GroupedProposal, candidate_id: str,
                            requirements: VariantAttributes | None = None) -> str:
    _check(isinstance(request, DataRequest) and isinstance(proposal, GroupedProposal),
           "Expected request and grouped proposal")
    _check(request.request_id == proposal.proposal.request_id, "Request identity mismatch")
    _check(candidate_id in {item.candidate_id for item in proposal.proposal.candidates},
           "Unknown target candidate")
    requirements = VariantAttributes() if requirements is None else requirements
    _check(isinstance(requirements, VariantAttributes), "Expected variant requirements")
    return _digest({"contract": "link_target_v1", "request": request, "proposal": proposal,
                    "candidate_id": candidate_id, "requirements": requirements})


@dataclass(frozen=True, repr=False)
class DeliveryOffer(ValueContract):
    request: DataRequest
    proposal: GroupedProposal
    candidate_id: str
    requirements: VariantAttributes = field(default_factory=VariantAttributes)
    links: tuple[DataLink, ...] = ()

    _decoders: ClassVar = {
        "request": DataRequest.from_dict, "proposal": GroupedProposal.from_dict,
        "requirements": VariantAttributes.from_dict,
        "links": lambda values: tuple(DataLink.from_dict(item) for item in values),
    }

    def __post_init__(self) -> None:
        digest = link_target_fingerprint(self.request, self.proposal, self.candidate_id, self.requirements)
        object.__setattr__(self, "links", _sequence(self.links, DataLink))
        _check(len({item.link_id for item in self.links}) == len(self.links), "Duplicate link IDs")
        source = self.proposal.proposal
        for link in self.links:
            _check(link.candidate_id == self.candidate_id and link.proposal_id == source.proposal_id
                   and link.proposal_revision == source.revision and link.target_fingerprint == digest,
                   "Data link belongs to different candidate, conditions or metadata revision")

    @property
    def candidate(self) -> Candidate:
        return next(item for item in self.proposal.proposal.candidates
                    if item.candidate_id == self.candidate_id)

    @property
    def file_formats(self) -> tuple[str, ...]:
        candidate = self.candidate
        if candidate.support_status != "supported" or candidate.availability_status != "available":
            return ()
        return tuple(item for item in candidate.supported_outputs if item not in {"file", "link", "both"})

    def available_modes(self, at: datetime) -> tuple[str, ...]:
        _utc(at)
        file, link = bool(self.file_formats), any(item.usable_at(at) for item in self.links)
        return (("file",) if file else ()) + (("link",) if link else ()) + (("both",) if file and link else ())


def _validate_link_target(request: DataRequest, candidate: Candidate, at: datetime) -> None:
    # Link delivery does not require a local collector/exporter or its API credential setting.
    _check(request.concept is not None and bool(request.countries) and request.dimensions is not None
           and request.period_start is not None and request.period_end is not None
           and request.frequency is not None and request.unit_policy is not None
           and request.vintage_requirement is not None, "Required request conditions remain unknown")
    _check(candidate.definition is not None and bool(candidate.series_id or candidate.series_key)
           and bool(candidate.evidence) and candidate.verification_status != "unknown"
           and candidate.availability_status == "available", "Candidate metadata remains unresolved")
    _check(set(request.countries).issubset(candidate.countries), "Country coverage mismatch")
    _check(candidate.dimensions is not None and set(request.dimensions) == set(candidate.dimensions),
           "Dimension coverage mismatch")
    for key, values in request.dimensions.items():
        _check(set(values).issubset(candidate.dimensions[key]), "Dimension selection mismatch")
    _check(candidate.available_start is not None and candidate.available_end is not None,
           "Available period remains unknown")
    start, end = _period(request.period_start), _period(request.period_end)
    first, last = _period(candidate.available_start), _period(candidate.available_end)
    _check(first[0] == start[0] and end[0] == last[0] and first <= start <= end <= last,
           "Requested period is not covered by the candidate")
    _check(request.frequency == "source" or request.frequency == candidate.frequency,
           "Link cannot perform a frequency transformation")
    _check(request.unit_policy == "preserve", "Link-only delivery cannot promise a unit conversion")
    _check(request.vintage_requirement == "latest_available"
           or request.vintage_requirement == candidate.source_version, "Vintage is not available")
    _check(all(item.retrieved_at <= at for item in candidate.evidence),
           "Confirmation predates its evidence")


@dataclass(frozen=True, repr=False)
class ConfirmedDelivery(ValueContract):
    offer: DeliveryOffer
    delivery: DeliverySpec
    confirmed_at: datetime
    confirmation_method: str
    fingerprint: str = field(init=False)

    _decoders: ClassVar = {"offer": DeliveryOffer.from_dict, "delivery": DeliverySpec.from_dict,
                           "confirmed_at": _datetime}

    def __post_init__(self) -> None:
        _check(isinstance(self.offer, DeliveryOffer) and isinstance(self.delivery, DeliverySpec),
               "Expected delivery contracts")
        _utc(self.confirmed_at)
        _check(self.confirmation_method in ("explicit_request", "followup"),
               "Explicit delivery confirmation is required")
        _check(not self.delivery.requires_choice, "Delivery mode must be selected")
        offer, delivery = self.offer, self.delivery
        source = offer.proposal.proposal
        _check(self.confirmed_at >= source.created_at, "Confirmation predates proposal")
        _check(delivery.mode in offer.available_modes(self.confirmed_at),
               "Requested delivery mode is unavailable; no automatic fallback")
        if delivery.mode in ("file", "both"):
            _check(delivery.file is not None and delivery.file.format in offer.file_formats,
                   "Supported file settings are required")
            ConfirmedSelection(offer.request, source, offer.candidate_id, source.revision,
                               delivery.file, self.confirmed_at, self.confirmation_method)
        else:
            _validate_link_target(offer.request, offer.candidate, self.confirmed_at)
        if delivery.mode in ("link", "both"):
            _check(bool(delivery.link_ids), "Data links must be explicitly selected")
            selected = {item.link_id: item for item in offer.links}
            _check(all(key in selected and selected[key].usable_at(self.confirmed_at)
                       for key in delivery.link_ids), "Selected link is unknown, blocked or expired")
        actual = next((item for item in offer.proposal.variants
                       if item.candidate_id == offer.candidate_id), None)
        for item in fields(offer.requirements):
            expected = getattr(offer.requirements, item.name)
            if item.name == "source_codes":
                if expected:
                    _check(actual is not None and all(actual.attributes.source_codes.get(key) == value
                           for key, value in expected.items()), "Variant source codes do not match")
            elif expected is not None:
                _check(actual is not None and getattr(actual.attributes, item.name) == expected,
                       "Variant attribute is unknown or differs from the request")
        if actual is not None:
            _check(all(item.retrieved_at <= self.confirmed_at for item in actual.evidence),
                   "Confirmation predates variant evidence")
        for group in offer.proposal.groups:
            if offer.candidate_id in group.candidate_ids:
                _check(all(item.retrieved_at <= self.confirmed_at for item in group.evidence),
                       "Confirmation predates group evidence")
        object.__setattr__(self, "fingerprint", self._fingerprint(offer, delivery))

    @staticmethod
    def _fingerprint(offer: DeliveryOffer, delivery: DeliverySpec) -> str:
        return _digest({"contract": "confirmed_delivery_v1", "offer": offer, "delivery": delivery})

    def matches(self, offer: DeliveryOffer, delivery: DeliverySpec) -> bool:
        return (isinstance(offer, DeliveryOffer) and isinstance(delivery, DeliverySpec)
                and self._fingerprint(offer, delivery) == self.fingerprint)
