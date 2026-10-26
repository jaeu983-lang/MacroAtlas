"""Bounded offline institution/link discovery; no claim of live availability."""
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration.models import StageInput


@dataclass(frozen=True)
class InstitutionAdapter:
    institution_id: str
    homepage: str
    official_hosts: tuple[str, ...]
    seed_links: tuple[str, ...]
    credential_env_var: str
    api_destination: str

    def accepts(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            return (
                parsed.scheme == "https" and parsed.hostname in self.official_hosts
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None and not parsed.query and not parsed.fragment
                and not any(c.isspace() or ord(c) < 32 for c in url)
                and "\\" not in url
            )
        except ValueError:
            return False


ADAPTERS = {
    "bls": InstitutionAdapter(
        "bls", "https://www.bls.gov/", ("www.bls.gov", "api.bls.gov"),
        ("https://www.bls.gov/audience/developers.htm",),
        "BLS_API_KEY", "api.bls.gov",
    ),
    "census": InstitutionAdapter(
        "census", "https://www.census.gov/", ("www.census.gov", "api.census.gov"),
        ("https://www.census.gov/data.html",),
        "CENSUS_API_KEY", "api.census.gov",
    ),
}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value is not None:
                    if len(self.links) >= 200:
                        raise ValueError("link budget exceeded")
                    self.links.append(value)


def discover_profile(institution_id: str, page: dict | None = None) -> dict:
    """Seeds use the repository catalogue; supplied HTML is fixture evidence only.

    Exact-host validation establishes domain membership, not current HTTP status,
    documentation content, permission to collect, or API authentication success.
    """
    adapter = ADAPTERS[institution_id]
    links = list(adapter.seed_links)
    strategy = "catalogue_seeds"
    source_url = adapter.homepage
    if page is not None:
        if not isinstance(page, dict) or set(page) != {"source_url", "html"}:
            raise ValueError("expected source_url and html")
        source_url = page["source_url"]
        html = page["html"]
        if not isinstance(source_url, str) or not adapter.accepts(source_url):
            raise ValueError("page must have an approved official URL")
        if not isinstance(html, str) or len(html.encode()) > 65536:
            raise ValueError("HTML fixture budget exceeded")
        parser = _Links()
        parser.feed(html)
        links = [urljoin(source_url, href) for href in parser.links]
        strategy = "html_fixture_links"
    accepted = sorted({url for url in links if adapter.accepts(url)})
    return {
        "institution_id": institution_id, "homepage": adapter.homepage,
        "strategy": strategy, "source_url": source_url,
        "evidence_kind": "fixture" if page is not None else "repository_catalogue",
        "evidence_ref": None if page is not None else "docs/INSTITUTION_CATALOG.md",
        "checked_at": datetime.now(UTC).isoformat(),
        "validation_scope": "exact_official_host_only", "live_verified_at": None,
        "links": accepted, "rejected_link_count": len(links) - sum(
            adapter.accepts(url) for url in links
        ),
        "credential_env_var": adapter.credential_env_var,
        "api_destination": adapter.api_destination,
        "authentication_status": "not_tested", "auth_requirement": "unknown",
        "collection_supported": False,
    }


class InstitutionDiscoveryEngine:
    """Register as ('institution_discovery', '1') in the existing Orchestrator."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) - {"institution_id", "page"}
                or not isinstance(data.get("institution_id"), str)
                or data["institution_id"] not in ADAPTERS):
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected supported institution_id and optional page.",))
        try:
            profile = discover_profile(data["institution_id"], data.get("page"))
        except ValueError:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Invalid page evidence or discovery budget exceeded.",))
        if not profile["links"]:
            return StageResult(StageStatus.NEEDS_REVIEW, profile,
                               error_code=ErrorCode.SITE_CHANGED,
                               warnings=("No approved official links found.",))
        try:
            relative = f"{self.settings.data_dir}/discovery/{uuid4().hex}/profile.json"
            path = self.settings._inside(relative)
            path.parent.mkdir(parents=True, exist_ok=False)
            with path.open("x", encoding="utf-8") as stream:
                json.dump(profile, stream, ensure_ascii=False, allow_nan=False, indent=2)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.INTERNAL_BUG,
                               warnings=("Profile preservation failed.",))
        return StageResult(StageStatus.SUCCEEDED, profile, (relative,),
                           ("Offline domain validation only; collection is not implemented.",))
