"""Evidence-bearing metadata snapshots; source representations are never rewritten."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import ClassVar
from urllib.parse import urlsplit

from macro_data_platform.contracts import EvidenceKind, SourceEvidence, utc
from macro_data_platform.workflow_contracts import (
    Candidate,
    ValueContract,
    _check,
    _datetime,
    _strings,
    _text,
)
from macro_data_platform.workflow_extensions import VariantAttributes, _public_url

MAX_METADATA_BYTES = 1_048_576
MAX_RECORDS = 200


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode()).hexdigest()


@dataclass(frozen=True)
class MetadataDocument:
    institution_id: str
    source_agency: str
    source_url: str
    retrieved_at: datetime
    evidence_kind: EvidenceKind
    original_ref: str
    kind: str
    body: bytes
    source_version: str | None = None

    def __post_init__(self):
        for name in ("institution_id", "source_agency", "source_url", "original_ref"):
            _text(getattr(self, name))
        utc(self.retrieved_at)
        _check(self.kind in {"sdmx_structure", "api_catalogue", "sheet_codebook"},
               "unsupported metadata document kind")
        _check(isinstance(self.body, bytes) and 0 < len(self.body) <= MAX_METADATA_BYTES,
               "metadata body must be nonempty bytes within the size limit")
        _check(isinstance(self.evidence_kind, EvidenceKind) and
               self.evidence_kind in {EvidenceKind.FIXTURE, EvidenceKind.OFFICIAL_DOCS},
               "metadata needs explicit fixture or official-docs evidence")
        _text(self.source_version, optional=True)

    @property
    def content_sha256(self):
        return hashlib.sha256(self.body).hexdigest()

    def header(self):
        return {"institution_id": self.institution_id, "source_agency": self.source_agency,
                "source_url": self.source_url, "retrieved_at": self.retrieved_at.isoformat(),
                "evidence_kind": self.evidence_kind.value, "original_ref": self.original_ref,
                "kind": self.kind, "source_version": self.source_version,
                "content_sha256": self.content_sha256}

    @property
    def document_id(self):
        return digest(self.header())

    def evidence(self, path: str, dataset_id=None, series_id=None):
        return SourceEvidence(
            digest({"document": self.document_id, "path": path}), self.source_agency,
            self.source_url, self.retrieved_at, self.evidence_kind,
            self.original_ref + "#" + path, dataset_id, series_id, self.source_version,
        )


@dataclass(frozen=True, repr=False)
class SourceAccess(ValueContract):
    """A source-declared data path and exact schema, not a documentation-page substitute."""
    url: str
    format: str
    columns: Mapping[str, str] = field(default_factory=dict)
    status: str = "unknown"
    checked_at: datetime | None = None
    expires_at: datetime | None = None
    shareable: bool = False
    manual_filter_required: bool = False
    missing_values: tuple[str, ...] = ("",)
    member: str | None = None
    sheet: str | None = None
    delimiter: str | None = None
    table_index: int | None = None

    _decoders: ClassVar = {
        "checked_at": lambda v: None if v is None else _datetime(v),
        "expires_at": lambda v: None if v is None else _datetime(v),
    }

    def __post_init__(self):
        _public_url(self.url)
        _check(urlsplit(self.url).scheme == "https", "data path requires HTTPS")
        _check(self.format in {"csv", "json", "tsv", "txt", "html", "zip", "xls", "xlsx"},
               "unsupported declared source format")
        _check(self.status in {"available", "unknown", "unavailable", "blocked"},
               "invalid data access status")
        _check(type(self.shareable) is bool and type(self.manual_filter_required) is bool,
               "access flags must be booleans")
        for at in (self.checked_at, self.expires_at):
            if at is not None:
                utc(at)
        if self.checked_at is not None and self.expires_at is not None:
            _check(self.checked_at < self.expires_at, "invalid access validity range")
        _check(self.status != "available" or
               (self.checked_at is not None and self.expires_at is not None),
               "available access requires a bounded validity period")
        _check(isinstance(self.columns, Mapping) and all(
            isinstance(k, str) and isinstance(v, str) and k and v
            for k, v in self.columns.items()), "invalid source column mapping")
        _check(len(set(self.columns.values())) == len(self.columns),
               "source columns cannot alias different fields")
        object.__setattr__(self, "columns", MappingProxyType(dict(self.columns)))
        for name in ("member", "sheet"):
            value = getattr(self, name)
            _check(value is None or isinstance(value, str) and bool(value.strip()),
                   "invalid declared file member or sheet")
        _check(self.member is None or self.format == "zip",
               "a ZIP member is only valid for a ZIP source")
        _check(self.sheet is None or self.format in {"xls", "xlsx", "zip"},
               "a sheet is only valid for a spreadsheet source")
        _check(self.delimiter is None or
               (self.format in {"txt", "zip"} and isinstance(self.delimiter, str)
                and len(self.delimiter) == 1), "invalid explicit text delimiter")
        _check(self.table_index is None or
               (self.format in {"html", "zip"} and type(self.table_index) is int
                and self.table_index >= 0), "invalid declared HTML table index")
        _check(isinstance(self.missing_values, (tuple, list)) and
               all(isinstance(v, str) for v in self.missing_values), "invalid missing tokens")
        object.__setattr__(self, "missing_values", tuple(self.missing_values))


@dataclass(frozen=True, repr=False)
class ScopeRelation(ValueContract):
    """Explicit source-defined relation, never inferred from labels."""
    target: str
    relation: str
    axis: str
    version: str
    evidence_path: str
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("target", "axis", "version", "evidence_path"):
            _text(getattr(self, name))
        _check(self.relation in {"exact", "broader", "narrower", "overlap",
                                "disjoint", "unknown"}, "invalid scope relation")
        for name in ("includes", "excludes"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        _check(not set(self.includes) & set(self.excludes), "scope inclusions conflict")


@dataclass(frozen=True, repr=False)
class MetadataRecord(ValueContract):
    candidate: Candidate
    concept_id: str | None
    labels: Mapping[str, str]
    attributes: VariantAttributes = field(default_factory=VariantAttributes)
    scope: str | None = None
    scope_relations: tuple[ScopeRelation, ...] = ()
    source_fields: Mapping[str, str] = field(default_factory=dict)
    access: SourceAccess | None = None
    structure_document_id: str | None = None

    _decoders: ClassVar = {
        "candidate": Candidate.from_dict, "attributes": VariantAttributes.from_dict,
        "scope_relations": lambda values: tuple(ScopeRelation.from_dict(v) for v in values),
        "access": lambda v: None if v is None else SourceAccess.from_dict(v),
    }

    def __post_init__(self):
        _check(isinstance(self.candidate, Candidate), "expected source candidate")
        _check(isinstance(self.attributes, VariantAttributes), "expected variant metadata")
        _text(self.concept_id, optional=True)
        _text(self.scope, optional=True)
        _text(self.structure_document_id, optional=True)
        _check(self.access is None or isinstance(self.access, SourceAccess), "invalid source access")
        for name in ("labels", "source_fields"):
            value = getattr(self, name)
            _check(isinstance(value, Mapping), "expected metadata mapping")
            for key, text in value.items():
                _text(key)
                _text(text)
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        _check(isinstance(self.scope_relations, (tuple, list)) and
               all(isinstance(v, ScopeRelation) for v in self.scope_relations),
               "expected explicit scope relations")
        _check(len({v.target for v in self.scope_relations}) == len(self.scope_relations),
               "conflicting scope relation targets")
        object.__setattr__(self, "scope_relations", tuple(self.scope_relations))


@dataclass(frozen=True)
class MetadataResult:
    document_id: str
    records: tuple[MetadataRecord, ...] = ()
    structures_json: str = "{}"
    warnings: tuple[str, ...] = ()

    def __post_init__(self):
        _check(len(self.records) <= MAX_RECORDS, "metadata record limit exceeded")
        _check(len({r.candidate.candidate_id for r in self.records}) == len(self.records),
               "duplicate source series identity")
        json.loads(self.structures_json)

    def structures(self):
        return json.loads(self.structures_json)
