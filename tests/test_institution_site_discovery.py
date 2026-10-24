"""Fixture-only institution site discovery and append-only profile storage."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.institution_sites import (
    InstitutionCandidate,
    InstitutionSiteDiscovery,
    LinkKind,
    OfficialDomainEvidence,
    SiteDocument,
    SiteDocumentKind,
    SitemapXmlStrategy,
)
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.institution_profiles import InstitutionProfileStore

FIXTURES = Path(__file__).parent / "fixtures" / "site_discovery"
CHECKED_AT = datetime(2026, 10, 24, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 10, 25, 1, tzinfo=UTC)


def bis_candidate() -> InstitutionCandidate:
    return InstitutionCandidate(
        institution_id="INT-02",
        name="BIS",
        jurisdiction="international",
        official_domains=(
            OfficialDomainEvidence("data.bis.org", "https://data.bis.org/bulkdownload", CHECKED_AT),
            OfficialDomainEvidence("stats.bis.org", "https://stats.bis.org/api-doc/v1/", CHECKED_AT),
        ),
    )


def treasury_candidate() -> InstitutionCandidate:
    return InstitutionCandidate(
        institution_id="US-03",
        name="Treasury TIC",
        jurisdiction="United States",
        official_domains=(
            OfficialDomainEvidence(
                "home.treasury.gov",
                "https://home.treasury.gov/data/treasury-international-capital-tic-system",
                CHECKED_AT,
            ),
        ),
    )


def site_document(
    source_url: str,
    body: bytes,
    kind: SiteDocumentKind,
    evidence_ref: str,
) -> SiteDocument:
    return SiteDocument(
        source_url=source_url,
        body=body,
        kind=kind,
        evidence_kind=EvidenceKind.FIXTURE,
        evidence_ref=evidence_ref,
        retrieved_at=RETRIEVED_AT,
    )


def bis_document(body: bytes | None = None) -> SiteDocument:
    return site_document(
        "https://stats.bis.org/api-doc/v1/",
        body if body is not None else (FIXTURES / "bis_navigation.html").read_bytes(),
        SiteDocumentKind.HTML,
        "fixture:tests/fixtures/site_discovery/bis_navigation.html",
    )


def treasury_document(body: bytes | None = None) -> SiteDocument:
    return site_document(
        "https://home.treasury.gov/data/treasury-international-capital-tic-system",
        body if body is not None else (FIXTURES / "treasury_sitemap.xml").read_bytes(),
        SiteDocumentKind.SITEMAP_XML,
        "fixture:tests/fixtures/site_discovery/treasury_sitemap.xml",
    )


def test_html_navigation_discovers_bis_portal_and_docs_without_promoting_external_links():
    profile = InstitutionSiteDiscovery().discover(bis_candidate(), (bis_document(),))

    assert profile["status"] == "docs_verified"
    assert profile["verified_at"] == CHECKED_AT.isoformat()
    assert profile["discovery_mode"] == "fixture"
    assert profile["strategy_ids"] == ["html_navigation_v1"]
    assert profile["site_live_tested"] is False
    assert profile["links_live_tested"] is False
    assert profile["raw_documents_stored"] is False
    links = {row["url"]: row for row in profile["official_links"]}
    assert links["https://data.bis.org/"]["kind"] == LinkKind.STATISTICS_PORTAL.value
    assert links["https://stats.bis.org/api-doc/v1/"]["kind"] == LinkKind.DOCUMENTATION.value
    assert all(
        "attacker.example" not in row["url"] and "community.example.org" not in row["url"]
        for row in profile["official_links"]
    )
    assert {
        row["hostname"] for row in profile["external_link_findings"]
    } == {"community.example.org", "data.bis.org.attacker.example"}
    assert all(row["source_documents"] for row in profile["external_link_findings"])
    assert profile["rejected_link_count"] == 2
    assert "view=summary" not in str(profile)
    assert all(
        source["evidence_kind"] == EvidenceKind.FIXTURE.value
        for row in profile["official_links"]
        for source in row["source_documents"]
    )


def test_sitemap_strategy_discovers_tic_pages_and_keeps_external_host_untrusted():
    profile = InstitutionSiteDiscovery().discover(treasury_candidate(), (treasury_document(),))

    assert profile["strategy_ids"] == ["sitemap_xml_v1"]
    assert [row["kind"] for row in profile["official_links"]] == [
        LinkKind.STATISTICS_PORTAL.value,
        LinkKind.OFFICIAL_OTHER.value,
    ]
    assert profile["external_link_findings"][0]["hostname"] == "example.org"
    assert profile["external_link_findings"][0]["classification"] == "external_candidate"
    assert profile["external_link_findings"][0]["source_documents"][0]["evidence_ref"] == (
        "fixture:tests/fixtures/site_discovery/treasury_sitemap.xml"
    )
    assert profile["site_live_tested"] is False
    assert profile["discovery_mode"] == "fixture"


def test_official_host_matching_uses_dns_label_boundaries():
    body = b"""
    <a href="https://home.treasury.gov.attacker.example/data">spoof</a>
    <a href="https://evilhome.treasury.gov/data">subdomain</a>
    <a href="https://home.treasury.gov.evil/data">suffix</a>
    """
    document = site_document(
        "https://home.treasury.gov/data/treasury-international-capital-tic-system",
        body,
        SiteDocumentKind.HTML,
        "fixture:domain-boundaries",
    )
    profile = InstitutionSiteDiscovery().discover(treasury_candidate(), (document,))

    assert profile["official_links"] == []
    assert {row["hostname"] for row in profile["external_link_findings"]} == {
        "evilhome.treasury.gov",
        "home.treasury.gov.attacker.example",
        "home.treasury.gov.evil",
    }


def test_nonofficial_source_document_is_rejected_before_parsing():
    document = site_document(
        "https://home.treasury.gov.attacker.example/page",
        b"<a href='https://home.treasury.gov/data'>Stats</a>",
        SiteDocumentKind.HTML,
        "fixture:external-page",
    )

    with pytest.raises(ValueError, match="outside the documented official domains"):
        InstitutionSiteDiscovery().discover(treasury_candidate(), (document,))


@pytest.mark.parametrize(
    "url",
    [
        "http://home.treasury.gov/page",
        "https://user:password@home.treasury.gov/page",
        "https://home.treasury.gov:8443/page",
        "https://home.treasury.gov/page?key=value",
    ],
)
def test_official_domain_evidence_rejects_insecure_or_credentialed_urls(url):
    with pytest.raises(ValueError):
        OfficialDomainEvidence("home.treasury.gov", url, CHECKED_AT)


def test_sitemap_rejects_dtd_and_entity_declarations():
    bodies = (
        b'<!DOCTYPE urlset [<!ENTITY x "https://home.treasury.gov/">]><urlset/>',
        '<!DOCTYPE urlset [<!ENTITY x "safe">]><urlset/>'.encode("utf-16"),
    )
    with pytest.raises(ValueError, match="DTD and entity"):
        SitemapXmlStrategy().extract(treasury_document(bodies[0]))
    with pytest.raises(ValueError, match="valid UTF-8"):
        SitemapXmlStrategy().extract(treasury_document(bodies[1]))


def test_conflicting_strategy_classification_is_retained_as_official_other():
    html = site_document(
        "https://stats.bis.org/api-doc/v1/",
        b'<a href="https://data.bis.org/">API documentation</a>',
        SiteDocumentKind.HTML,
        "fixture:html-classification",
    )
    sitemap = site_document(
        "https://stats.bis.org/api-doc/v1/",
        b"<urlset><url><loc>https://data.bis.org/</loc></url></urlset>",
        SiteDocumentKind.SITEMAP_XML,
        "fixture:sitemap-classification",
    )
    profile = InstitutionSiteDiscovery().discover(bis_candidate(), (html, sitemap))

    assert profile["official_links"][0]["kind"] == LinkKind.OFFICIAL_OTHER.value
    assert profile["official_links"][0]["classification_conflict"] is True
    assert {
        row["classification"] for row in profile["official_links"][0]["source_documents"]
    } == {LinkKind.DOCUMENTATION.value, LinkKind.OFFICIAL_OTHER.value}


def test_documents_are_bounded_and_timestamps_must_be_utc():
    with pytest.raises(ValueError, match="size limit"):
        bis_document(b"x" * (1_048_576 + 1))
    with pytest.raises(ValueError, match="UTC"):
        SiteDocument(
            source_url="https://stats.bis.org/api-doc/v1/",
            body=b"",
            kind=SiteDocumentKind.HTML,
            evidence_kind=EvidenceKind.FIXTURE,
            evidence_ref="fixture:naive-time",
            retrieved_at=datetime(2026, 10, 25),
        )
    with pytest.raises(TypeError, match="EvidenceKind"):
        SiteDocument(
            source_url="https://stats.bis.org/api-doc/v1/",
            body=b"",
            kind=SiteDocumentKind.HTML,
            evidence_kind="fixture",
            evidence_ref="fixture:wrong-kind",
            retrieved_at=RETRIEVED_AT,
        )


def test_profile_store_is_append_only_and_does_not_change_history_schema_version(tmp_path):
    settings = Settings(tmp_path)
    HistoryStore(settings)
    store = InstitutionProfileStore(settings)
    profile = InstitutionSiteDiscovery().discover(bis_candidate(), (bis_document(),))

    profile_id = store.save(profile)
    assert store.save(profile) == profile_id
    with pytest.raises(ValueError, match="UTC"):
        store.save({**profile, "verified_at": "2026-10-24T00:00:00"})
    assert store.get(profile_id)["profile_id"] == profile_id
    assert len(store.for_institution("INT-02")) == 1

    revised_profile = {**profile, "discovery_run_at": "2026-10-26T00:00:00+00:00"}
    revised_id = store.save(revised_profile)
    assert revised_id != profile_id
    assert len(store.for_institution("INT-02")) == 2

    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE institution_profiles SET document='{}' WHERE profile_id=?", (profile_id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM institution_profiles WHERE profile_id=?", (profile_id,))
