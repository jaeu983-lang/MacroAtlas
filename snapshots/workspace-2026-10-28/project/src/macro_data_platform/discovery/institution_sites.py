"""Offline institution-site discovery from supplied HTML and sitemap documents."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from macro_data_platform.contracts import EvidenceKind, utc

MAX_DOCUMENT_BYTES = 1_048_576
MAX_DISCOVERED_LINKS = 5_000
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SiteDocumentKind(str, Enum):
    HTML = "html"
    SITEMAP_XML = "sitemap_xml"


class LinkKind(str, Enum):
    STATISTICS_PORTAL = "statistics_portal"
    DOCUMENTATION = "documentation"
    OFFICIAL_OTHER = "official_other"


def _normalise_host(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("host must be a nonempty hostname")
    if any(char in value for char in "/:@?#\\") or any(ord(char) < 33 for char in value):
        raise ValueError("host must not include URL components")
    try:
        host = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("host is not a valid IDNA hostname") from exc
    labels = host.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise ValueError("host must be a valid DNS hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses are not accepted as official domains")
    return host


def _url_parts(raw_url: str, base_url: str | None = None) -> tuple[str, str, bool]:
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > 2_048:
        raise ValueError("URL is empty or too long")
    if any(ord(char) < 32 or char == "\\" for char in raw_url):
        raise ValueError("URL contains a control character or backslash")
    resolved = urljoin(base_url, raw_url) if base_url else raw_url
    try:
        parsed = urlsplit(resolved)
        host_raw = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL is malformed") from exc
    if parsed.scheme.lower() != "https" or not host_raw:
        raise ValueError("only absolute HTTPS URLs are accepted")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not accepted")
    if port not in {None, 443}:
        raise ValueError("nonstandard URL ports are not accepted")
    host = _normalise_host(host_raw)
    path = parsed.path or "/"
    netloc = host
    canonical = urlunsplit(("https", netloc, path, "", ""))
    return host, canonical, bool(parsed.query)


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


@dataclass(frozen=True)
class OfficialDomainEvidence:
    hostname: str
    evidence_url: str
    verified_at: datetime

    def __post_init__(self) -> None:
        host = _normalise_host(self.hostname)
        object.__setattr__(self, "hostname", host)
        source_host, _, has_query = _url_parts(self.evidence_url)
        if has_query or not _host_matches(source_host, host):
            raise ValueError("domain evidence URL must be an HTTPS URL on the documented domain")
        utc(self.verified_at)


@dataclass(frozen=True)
class InstitutionCandidate:
    institution_id: str
    name: str
    jurisdiction: str
    official_domains: tuple[OfficialDomainEvidence, ...]

    def __post_init__(self) -> None:
        for field_name in ("institution_id", "name", "jurisdiction"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be nonempty")
        if not self.official_domains:
            raise ValueError("at least one documented official domain is required")
        if len({row.hostname for row in self.official_domains}) != len(self.official_domains):
            raise ValueError("official domains must be unique")

    def matches_official_host(self, host: str) -> bool:
        return any(_host_matches(host, row.hostname) for row in self.official_domains)

    def require_official_document_url(self, url: str) -> str:
        host, canonical, has_query = _url_parts(url)
        if has_query:
            raise ValueError("source document URL must not contain a query")
        if not self.matches_official_host(host):
            raise ValueError("source document is outside the documented official domains")
        return canonical


@dataclass(frozen=True)
class SiteDocument:
    source_url: str
    body: bytes
    kind: SiteDocumentKind
    evidence_kind: EvidenceKind
    evidence_ref: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.body, bytes):
            raise TypeError("document body must be bytes")
        if len(self.body) > MAX_DOCUMENT_BYTES:
            raise ValueError("site document exceeds the configured size limit")
        if not isinstance(self.kind, SiteDocumentKind):
            raise TypeError("unsupported site document kind")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise TypeError("evidence_kind must be an EvidenceKind")
        if self.evidence_kind not in {EvidenceKind.FIXTURE, EvidenceKind.OFFICIAL_DOCS}:
            raise ValueError("site discovery accepts fixture or official documentation evidence only")
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
            raise ValueError("evidence_ref must be nonempty")
        _url_parts(self.source_url)
        utc(self.retrieved_at)


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    label: str


class SiteDiscoveryStrategy(Protocol):
    strategy_id: str
    document_kind: SiteDocumentKind

    def extract(self, document: SiteDocument) -> tuple[LinkCandidate, ...]: ...


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[LinkCandidate] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        values = dict(attrs)
        href = values.get("href")
        if href is not None:
            self._href = href
            self._text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() == "a" and self._href is not None:
            self._finish_anchor()

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self._finish_anchor()

    def _finish_anchor(self) -> None:
        self.rows.append(LinkCandidate(self._href or "", " ".join(" ".join(self._text).split())))
        self._href = None
        self._text = []
        if len(self.rows) > MAX_DISCOVERED_LINKS:
            raise ValueError("HTML document exceeds the discovered-link limit")


class HtmlNavigationStrategy:
    strategy_id = "html_navigation_v1"
    document_kind = SiteDocumentKind.HTML

    def extract(self, document: SiteDocument) -> tuple[LinkCandidate, ...]:
        if document.kind != self.document_kind:
            raise ValueError("HTML navigation strategy received a different document kind")
        try:
            source = document.body.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("HTML fixture must be valid UTF-8") from exc
        parser = _AnchorParser()
        parser.feed(source)
        parser.close()
        return tuple(parser.rows)


class SitemapXmlStrategy:
    strategy_id = "sitemap_xml_v1"
    document_kind = SiteDocumentKind.SITEMAP_XML

    def extract(self, document: SiteDocument) -> tuple[LinkCandidate, ...]:
        if document.kind != self.document_kind:
            raise ValueError("sitemap strategy received a different document kind")
        body = document.body
        try:
            source = body.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("sitemap XML must be valid UTF-8") from exc
        if "<!doctype" in source.lower() or "<!entity" in source.lower():
            raise ValueError("DTD and entity declarations are not accepted in sitemap XML")
        try:
            root = ElementTree.fromstring(source)
        except ElementTree.ParseError as exc:
            raise ValueError("sitemap XML is malformed") from exc
        rows: list[LinkCandidate] = []
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text:
                rows.append(LinkCandidate(element.text.strip(), ""))
                if len(rows) > MAX_DISCOVERED_LINKS:
                    raise ValueError("sitemap exceeds the discovered-link limit")
        return tuple(rows)


def _classify(url: str, label: str) -> LinkKind:
    path_parts = [part for part in urlsplit(url).path.lower().split("/") if part]
    words = set(re.findall(r"[a-z0-9]+", f"{label.lower()} {' '.join(path_parts)}"))
    if words & {"documentation", "developer", "guide", "help", "docs", "doc"}:
        return LinkKind.DOCUMENTATION
    if words & {"statistics", "statistical", "sdmx", "dataflow", "dataset", "datasets", "portal"}:
        return LinkKind.STATISTICS_PORTAL
    if path_parts and path_parts[0] == "data" and len(path_parts) <= 2:
        return LinkKind.STATISTICS_PORTAL
    return LinkKind.OFFICIAL_OTHER


def _evidence_name(value: EvidenceKind) -> str:
    return value.value


class InstitutionSiteDiscovery:
    """Parse supplied documents only; this class has no network client."""

    def __init__(self, strategies: tuple[SiteDiscoveryStrategy, ...] | None = None) -> None:
        self.strategies = strategies or (HtmlNavigationStrategy(), SitemapXmlStrategy())
        if len({row.strategy_id for row in self.strategies}) != len(self.strategies):
            raise ValueError("strategy identifiers must be unique")

    def discover(
        self, candidate: InstitutionCandidate, documents: tuple[SiteDocument, ...]
    ) -> dict:
        if not documents:
            raise ValueError("at least one site document is required")
        by_kind = {strategy.document_kind: strategy for strategy in self.strategies}
        official_links: dict[str, dict] = {}
        external_hosts: dict[str, list[dict]] = {}
        rejected_link_count = 0
        used_strategies: set[str] = set()
        document_records: list[dict] = []
        evidence_kinds: set[str] = set()

        for document in documents:
            source_url = candidate.require_official_document_url(document.source_url)
            strategy = by_kind.get(document.kind)
            if strategy is None:
                raise ValueError("no discovery strategy is configured for this document kind")
            used_strategies.add(strategy.strategy_id)
            evidence_kinds.add(_evidence_name(document.evidence_kind))
            document_records.append({
                "source_url": source_url,
                "evidence_ref": document.evidence_ref,
                "evidence_kind": _evidence_name(document.evidence_kind),
                "retrieved_at": document.retrieved_at.isoformat(),
                "strategy_id": strategy.strategy_id,
            })
            for item in strategy.extract(document):
                try:
                    host, canonical_url, has_query = _url_parts(item.url, source_url)
                except ValueError:
                    rejected_link_count += 1
                    continue
                if not candidate.matches_official_host(host):
                    source_record = {
                        "source_url": source_url,
                        "evidence_ref": document.evidence_ref,
                        "evidence_kind": _evidence_name(document.evidence_kind),
                        "strategy_id": strategy.strategy_id,
                    }
                    external_hosts.setdefault(host, [])
                    if source_record not in external_hosts[host]:
                        external_hosts[host].append(source_record)
                    continue
                if has_query:
                    rejected_link_count += 1
                    continue
                kind = _classify(canonical_url, item.label)
                existing = official_links.get(canonical_url)
                if existing is None:
                    existing = {
                        "url": canonical_url,
                        "kind": kind.value,
                        "label": item.label,
                        "classification_conflict": False,
                        "source_documents": [],
                    }
                    official_links[canonical_url] = existing
                elif existing["kind"] != kind.value:
                    existing["kind"] = LinkKind.OFFICIAL_OTHER.value
                    existing["classification_conflict"] = True
                source_record = {
                    "source_url": source_url,
                    "evidence_ref": document.evidence_ref,
                    "evidence_kind": _evidence_name(document.evidence_kind),
                    "strategy_id": strategy.strategy_id,
                    "label": item.label,
                    "classification": kind.value,
                }
                if source_record not in existing["source_documents"]:
                    existing["source_documents"].append(source_record)

        verified_at = max(row.verified_at for row in candidate.official_domains)
        discovery_run_at = max(row.retrieved_at for row in documents)
        mode = "fixture" if evidence_kinds == {EvidenceKind.FIXTURE.value} else (
            "official_docs" if evidence_kinds == {EvidenceKind.OFFICIAL_DOCS.value} else "mixed"
        )
        return {
            "institution_id": candidate.institution_id,
            "name": candidate.name,
            "jurisdiction": candidate.jurisdiction,
            "status": "docs_verified",
            "verified_at": verified_at.isoformat(),
            "official_domain_evidence": [
                {
                    "hostname": row.hostname,
                    "evidence_url": row.evidence_url,
                    "verified_at": row.verified_at.isoformat(),
                    "evidence_kind": EvidenceKind.OFFICIAL_DOCS.value,
                }
                for row in candidate.official_domains
            ],
            "discovery_mode": mode,
            "discovery_run_at": discovery_run_at.isoformat(),
            "strategy_ids": sorted(used_strategies),
            "documents": sorted(document_records, key=lambda row: (row["source_url"], row["strategy_id"])),
            "official_links": [
                official_links[key]
                for key in sorted(official_links)
            ],
            "external_link_findings": [
                {
                    "hostname": host,
                    "classification": "external_candidate",
                    "source_documents": external_hosts[host],
                }
                for host in sorted(external_hosts)
            ],
            "rejected_link_count": rejected_link_count,
            "site_live_tested": False,
            "links_live_tested": False,
            "raw_documents_stored": False,
        }


def profile_fingerprint(profile: dict) -> str:
    """Return a deterministic profile identity without mutating the input."""
    canonical = json.dumps(
        profile, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
