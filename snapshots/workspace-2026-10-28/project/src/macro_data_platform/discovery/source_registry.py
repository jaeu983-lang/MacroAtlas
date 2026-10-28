"""Offline, evidence-backed API-first coverage registry for catalog sources."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType
from urllib.parse import urlsplit


class ApiAvailability(str, Enum):
    DOCUMENTED = "documented"
    UNCONFIRMED = "unconfirmed"
    NOT_OFFERED = "not_offered"


class AuthRequirement(str, Enum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"
    UNKNOWN = "unknown"


class AccessPriority(str, Enum):
    API_FIRST = "api_first"
    API_AUDIT_FIRST = "api_audit_first"
    OFFICIAL_ONLY = "official_only"


class AdapterStatus(str, Enum):
    PARTIAL = "partial"
    FIXTURES_ONLY = "fixtures_only"
    NOT_IMPLEMENTED = "not_implemented"


class FixtureScope(str, Enum):
    SOURCE_SPECIFIC = "source_specific"
    GENERIC = "generic"
    SCENARIO_ONLY = "scenario_only"
    NONE = "none"


class LiveValidation(str, Enum):
    NOT_RUN = "not_run"
    PARTIAL = "partial"
    FAILED = "failed"


def _validate_urls(urls: tuple[str, ...], field_name: str) -> None:
    if len(urls) != len(set(urls)):
        raise ValueError(f"{field_name} must be unique")
    for value in urls:
        if not isinstance(value, str) or not value or len(value) > 2_048:
            raise ValueError(f"{field_name} must contain bounded URLs")
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError as exc:
            raise ValueError(f"{field_name} contains a malformed URL") from exc
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or port not in {None, 443}):
            raise ValueError(f"{field_name} accepts official HTTPS URLs without credentials")


@dataclass(frozen=True)
class SourceAccessProfile:
    institution_id: str
    name: str
    scenario_ids: tuple[str, ...]
    api_availability: ApiAvailability
    access_priority: AccessPriority
    api_families: tuple[str, ...]
    api_documentation_urls: tuple[str, ...]
    official_source_urls: tuple[str, ...]
    authentication: AuthRequirement
    credential_env_var: str | None
    non_api_methods: tuple[str, ...]
    adapter_status: AdapterStatus
    fixture_scope: FixtureScope
    live_validation: LiveValidation
    live_scope: str | None
    docs_checked_on: date
    status_note: str
    api_provider: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("institution_id", "name", "status_note"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be nonempty")
        if len(self.institution_id) > 64 or len(self.name) > 160:
            raise ValueError("institution identity exceeds the configured size limit")
        if (any(
            not isinstance(value, str) or len(value) != 1 or value not in "ABCDEFGH"
            for value in self.scenario_ids
        )):
            raise ValueError("scenario_ids may contain only A-H labels")
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        if type(self.docs_checked_on) is not date:
            raise TypeError("docs_checked_on must be a date")
        enum_fields = {
            "api_availability": ApiAvailability,
            "access_priority": AccessPriority,
            "authentication": AuthRequirement,
            "adapter_status": AdapterStatus,
            "fixture_scope": FixtureScope,
            "live_validation": LiveValidation,
        }
        for field_name, enum_type in enum_fields.items():
            if not isinstance(getattr(self, field_name), enum_type):
                raise TypeError(f"{field_name} must use its declared enum")
        for field_name in ("api_families", "non_api_methods"):
            values = getattr(self, field_name)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain nonempty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        _validate_urls(self.api_documentation_urls, "api_documentation_urls")
        _validate_urls(self.official_source_urls, "official_source_urls")

        if self.api_availability == ApiAvailability.DOCUMENTED:
            if (not self.api_families or not self.api_documentation_urls
                    or self.access_priority != AccessPriority.API_FIRST):
                raise ValueError("documented APIs require a documented API family and API-first priority")
        elif self.api_availability == ApiAvailability.UNCONFIRMED:
            if (self.api_families or self.api_documentation_urls
                    or self.access_priority != AccessPriority.API_AUDIT_FIRST
                    or self.authentication != AuthRequirement.UNKNOWN):
                raise ValueError("unconfirmed APIs cannot claim API docs, a protocol or auth policy")
        else:
            if (self.api_families or self.api_documentation_urls
                    or self.access_priority != AccessPriority.OFFICIAL_ONLY):
                raise ValueError("not-offered APIs require an official-only access policy")
        if not self.official_source_urls:
            raise ValueError("each source requires official source evidence")
        if (self.api_availability == ApiAvailability.NOT_OFFERED
                and (self.authentication != AuthRequirement.UNKNOWN
                     or not self.status_note.startswith("Official documentation explicitly states no API"))):
            raise ValueError("not_offered requires explicit official documentation and unknown API auth")

        if self.authentication in {AuthRequirement.REQUIRED, AuthRequirement.OPTIONAL}:
            if self.authentication == AuthRequirement.REQUIRED and not self.credential_env_var:
                raise ValueError("required authentication must name an environment variable")
            if self.credential_env_var is not None and (
                not self.credential_env_var.isascii()
                or not self.credential_env_var.replace("_", "").isalnum()
                or not self.credential_env_var.isupper()
            ):
                raise ValueError("credential_env_var must be an uppercase environment variable name")
        elif self.credential_env_var is not None:
            raise ValueError("credential_env_var requires optional or required authentication")
        if self.api_provider is not None and (
            not isinstance(self.api_provider, str)
            or not self.api_provider.strip()
            or len(self.api_provider) > 160
            or self.api_availability != ApiAvailability.DOCUMENTED
        ):
            raise ValueError("API provider must be set only for a documented API")
        if self.live_validation in {LiveValidation.PARTIAL, LiveValidation.FAILED}:
            if not isinstance(self.live_scope, str) or not self.live_scope.strip():
                raise ValueError("tested live validation requires its exact scope")
        elif self.live_scope is not None:
            raise ValueError("unrun live validation cannot claim a tested scope")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready view containing names, never credential values."""
        return {
            "institution_id": self.institution_id,
            "name": self.name,
            "scenario_ids": list(self.scenario_ids),
            "api_availability": self.api_availability.value,
            "access_priority": self.access_priority.value,
            "api_families": list(self.api_families),
            "api_documentation_urls": list(self.api_documentation_urls),
            "official_source_urls": list(self.official_source_urls),
            "authentication": self.authentication.value,
            "credential_env_var": self.credential_env_var,
            "non_api_methods": list(self.non_api_methods),
            "adapter_status": self.adapter_status.value,
            "fixture_scope": self.fixture_scope.value,
            "live_validation": self.live_validation.value,
            "live_scope": self.live_scope,
            "docs_checked_on": self.docs_checked_on.isoformat(),
            "status_note": self.status_note,
            "api_provider": self.api_provider,
        }


_CHECKED = date(2026, 10, 25)


def _profile(
    institution_id: str,
    name: str,
    scenario: str | None,
    *,
    api_families: tuple[str, ...] = (),
    api_docs: tuple[str, ...] = (),
    official_sources: tuple[str, ...],
    authentication: AuthRequirement = AuthRequirement.UNKNOWN,
    credential_env_var: str | None = None,
    non_api_methods: tuple[str, ...] = (),
    adapter_status: AdapterStatus = AdapterStatus.NOT_IMPLEMENTED,
    fixture_scope: FixtureScope = FixtureScope.NONE,
    live_validation: LiveValidation = LiveValidation.NOT_RUN,
    live_scope: str | None = None,
    api_provider: str | None = None,
    status_note: str,
) -> SourceAccessProfile:
    if api_docs:
        availability = ApiAvailability.DOCUMENTED
        priority = AccessPriority.API_FIRST
    else:
        availability = ApiAvailability.UNCONFIRMED
        priority = AccessPriority.API_AUDIT_FIRST
    return SourceAccessProfile(
        institution_id=institution_id,
        name=name,
        scenario_ids=(scenario,) if scenario else (),
        api_availability=availability,
        access_priority=priority,
        api_families=api_families,
        api_documentation_urls=api_docs,
        official_source_urls=official_sources,
        authentication=authentication,
        credential_env_var=credential_env_var,
        non_api_methods=non_api_methods,
        adapter_status=adapter_status,
        fixture_scope=fixture_scope,
        live_validation=live_validation,
        live_scope=live_scope,
        docs_checked_on=_CHECKED,
        status_note=status_note,
        api_provider=api_provider,
    )


_ROWS = (
    _profile(
        "INT-01", "IMF", "A",
        api_families=("SDMX 2.1", "SDMX 3.0"),
        api_docs=("https://data.imf.org/en/Resource-Pages/IMF-API",),
        official_sources=("https://data.imf.org/en/Resource-Pages/IMF-API",),
        authentication=AuthRequirement.NONE,
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 34: public IMF.STA CPI dataflow metadata only, latest returned 5.0.0; one uncredentialed HTTP 200 request, source contract and archive/hash read-back. No observation ingestion or private API validation.",
        status_note="Public IMF_DATA 2.1 metadata-only client, synthetic/recorded fixtures and mocked route tests. Official MATLAB/R guides distinguish public access from elevated authentication. One CPI metadata live request validated; referenced DSD unresolved, observations/private access/general workflow unverified. Swagger login is not needed for this selected public request.",
    ),
    _profile(
        "INT-02", "BIS", "B",
        api_families=("SDMX REST 2.1",),
        api_docs=("https://stats.bis.org/api-doc/v2/",),
        official_sources=("https://stats.bis.org/api-doc/v2/", "https://data.bis.org/bulkdownload"),
        authentication=AuthRequirement.NONE,
        non_api_methods=("official CSV/SDMX ZIP bulk download",),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 32: BIS WS_TC 2.0 dataflow metadata only; one HTTP 200 request, source contract and archive/hash read-back. No observation ingestion.",
        status_note="SDMX mocked route tests plus synthetic/recorded metadata fixtures. Iteration 32 selected metadata validated; referenced DSD remains unresolved, no general workflow or observation validation.",
    ),
    _profile(
        "US-03", "Treasury TIC", "C",
        official_sources=(
            "https://home.treasury.gov/data/treasury-international-capital-tic-system",
            "https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic",
        ),
        non_api_methods=("official CSV", "official TSV/TXT", "official HTML tables", "official PDF releases"),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        status_note="Two registered official CSV downloads (MFH history and January 2023 Table 3D), synthetic layout contracts and raw archive/read-back; no live ingestion or normalized observations. API specification remains unconfirmed; not proof that no API exists.",
    ),
    _profile(
        "US-04", "BEA", "D",
        api_families=("BEA REST API; JSON/XML; dataset and parameter discovery",),
        api_docs=("https://apps.bea.gov/API/docs/index.htm", "https://apps.bea.gov/API/swagger/index.htm"),
        official_sources=("https://apps.bea.gov/API/docs/index.htm",),
        authentication=AuthRequirement.REQUIRED,
        credential_env_var="BEA_API_KEY",
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="2026-10-25 GetDataSetList metadata only: 13 dataset entries, archived and hash-read-back; no observation ingestion or general workflow validation.",
        status_note="BEA JSON GET client, synthetic/recorded catalogue fixtures and source envelope checks. Iteration 31 verified one live metadata request and sanitized archive/read-back; observation parsing and general workflow integration remain unverified.",
    ),
    _profile(
        "EU-01", "ECB", "E",
        api_families=("SDMX REST 2.1",),
        api_docs=("https://data.ecb.europa.eu/help/api/overview",),
        official_sources=("https://data.ecb.europa.eu/help/api/overview",),
        authentication=AuthRequirement.NONE,
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 32: ECB ECB_EXR1 1.0 DSD metadata only; one HTTP 200 archive, six dimensions validated after parser fix by offline hash read-back, no new HTTP. No observation ingestion.",
        status_note="SDMX mocked route tests plus synthetic/recorded metadata fixtures. Initial duplicate-dimension parser failure retained in canary report; AttributeRelationship references excluded from definitions and same saved bytes revalidated separately. No general workflow validation.",
    ),
    _profile(
        "EU-02", "Eurostat", "E",
        api_families=("Catalogue API", "SDMX 2.1", "SDMX 3.0", "Statistics API JSON-stat"),
        api_docs=("https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction",),
        official_sources=("https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction",),
        authentication=AuthRequirement.NONE,
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 32: ESTAT NAMA_10_GDP 1.0 dataflow metadata only; one HTTP 200 request, source contract and archive/hash read-back. No observation ingestion.",
        status_note="SDMX mocked route tests plus synthetic/recorded metadata fixtures. Selected dataflow metadata validated; referenced DSD, workflow and observations remain unverified. API returns current values without historical observation versions.",
    ),
    _profile(
        "JP-02", "Japan MOF", "F",
        official_sources=(
            "https://www.mof.go.jp/english/statistics/index.html",
            "https://www.mof.go.jp/policy/international_policy/reference/official_reserve_assets/data/index.htm",
        ),
        non_api_methods=("official CSV downloads", "official SDMX downloads", "official statistics pages"),
        status_note="No general MOF API specification located in reviewed official documentation; downloadable SDMX files are not classified as an API.",
    ),
    _profile(
        "JP-01", "Bank of Japan", "F",
        api_families=("Time-Series Data Search REST API; JSON/CSV",),
        api_docs=("https://www.stat-search.boj.or.jp/info/api_manual_en.pdf",),
        official_sources=("https://www.stat-search.boj.or.jp/info/api_manual_en.pdf",),
        authentication=AuthRequirement.NONE,
        non_api_methods=("official flat-file downloads for selected statistics",),
        status_note="Public API methods are documented; no BOJ-specific connector or live API request has been run.",
    ),
    _profile(
        "JP-03", "e-Stat", "F",
        api_families=("e-Stat REST API v3.0; XML/JSON/CSV",),
        api_docs=("https://www.e-stat.go.jp/api/en/api-info", "https://www.e-stat.go.jp/api/en/api-info/api-spec"),
        official_sources=("https://www.e-stat.go.jp/api/en/api-info",),
        authentication=AuthRequirement.REQUIRED,
        credential_env_var="ESTAT_APP_ID",
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="2026-10-25 getStatsList(lang=E, limit=1) metadata only: one table entry, archived and hash-read-back; no observation ingestion or general workflow validation.",
        status_note="e-Stat v3.0 JSON GET client, synthetic/recorded catalogue fixtures and source envelope checks. Iteration 31 verified one live metadata request and sanitized archive/read-back; observation parsing and general workflow integration remain unverified.",
    ),
    _profile(
        "CN-01", "PBOC", "G",
        official_sources=("https://www.pbc.gov.cn/en/", "https://www.pbc.gov.cn/en/3688253/3689009/3788456/2025092319414130565/index.html"),
        non_api_methods=("official statistical release pages; format requires per-series review",),
        adapter_status=AdapterStatus.FIXTURES_ONLY,
        fixture_scope=FixtureScope.SCENARIO_ONLY,
        status_note="No public data API specification located in reviewed official sources; site-discovery fixture is not an API connector.",
    ),
    _profile(
        "CN-02", "SAFE", "G",
        official_sources=("https://www.safe.gov.cn/en/", "https://www.safe.gov.cn/en/ForexReserves/index.html"),
        non_api_methods=("official statistics/release pages; file formats require per-series review",),
        adapter_status=AdapterStatus.FIXTURES_ONLY,
        fixture_scope=FixtureScope.SCENARIO_ONLY,
        status_note="No public data API specification located in reviewed official sources; site-discovery fixture is not a SAFE data adapter.",
    ),
    _profile(
        "CN-03", "NBS China", "G",
        official_sources=("https://data.stats.gov.cn/", "https://www.stats.gov.cn/xw/tjxw/tzgg/202603/t20260325_1962844.html"),
        non_api_methods=("official national data portal; automated format requires per-table review",),
        adapter_status=AdapterStatus.FIXTURES_ONLY,
        fixture_scope=FixtureScope.SCENARIO_ONLY,
        status_note="No public data API specification located in reviewed official sources; the 2026 portal upgrade requires a stability review.",
    ),
    _profile(
        "INT-03", "OECD", "H",
        api_families=("OECD SDMX REST API",),
        api_docs=("https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1",),
        official_sources=("https://sdmx.oecd.org/public/",),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 32: OECD.SDD.NAD DSD_NAMAIN1@DF_QNA 1.1 dataflow metadata only; one uncredentialed HTTP 200 request, contract and archive/hash read-back. No observation ingestion.",
        status_note="SDMX mocked route tests plus synthetic/recorded metadata fixtures. Selected public metadata route succeeded without credentials; global authentication/coverage is not inferred. Referenced DSD, observations and general workflow remain unverified.",
    ),
    _profile(
        "INT-04", "World Bank", "H",
        api_families=("Indicators API v2", "SDMX API"),
        api_docs=("https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",),
        official_sources=("https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",),
        authentication=AuthRequirement.NONE,
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="USA / WDI source 2 / NY.GDP.MKTP.CD fixed route only; see Gate A and iteration 14 reports.",
        status_note="A documented no-key API exists; the current live connector covers one fixed GDP route and saves its raw response to files, not a general Indicators API client.",
    ),
    _profile(
        "US-01", "Federal Reserve Board", None,
        api_families=("FRED API for Federal Reserve Board DDP series",),
        api_docs=(
            "https://fred.stlouisfed.org/docs/api/fred/",
            "https://www.federalreserve.gov/data/data-download-fred-information.htm",
        ),
        official_sources=(
            "https://www.federalreserve.gov/data/data-download-fred-information.htm",
            "https://fred.stlouisfed.org/docs/api/fred/",
            "https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html",
        ),
        authentication=AuthRequirement.REQUIRED,
        credential_env_var="FRED_API_KEY",
        api_provider="Federal Reserve Bank of St. Louis (FRED)",
        non_api_methods=("Board DDP XML statistical-release downloads",),
        status_note=(
            "The Board's July 2026 notice documents FRED API access to DDP series. "
            "The API provider is FRED, not the Board; DDP is transitioning, and series-level "
            "coverage/crosswalk still needs confirmation. A limited FRED v1 client exists, "
            "but Board-specific crosswalk/workflow and live requests remain unverified."
        ),
    ),
    _profile(
        "US-02", "St. Louis Fed FRED/ALFRED", None,
        api_families=("FRED API v1/v2; FRED and ALFRED series/observation services",),
        api_docs=(
            "https://fred.stlouisfed.org/docs/api/fred/",
            "https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html",
        ),
        official_sources=(
            "https://fred.stlouisfed.org/docs/api/fred/",
            "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
        ),
        authentication=AuthRequirement.REQUIRED,
        credential_env_var="FRED_API_KEY",
        api_provider="Federal Reserve Bank of St. Louis (FRED)",
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        status_note=(
            "Official API documentation covers both FRED and ALFRED. API key is required; "
            "third-party series can carry separate rights, and terms permit limits to change. "
            "Iteration 28 adds limited FRED v1 metadata/search/observation page and release/source "
            "clients with synthetic fixture file round-trips; original agency is not inferred "
            "from the FRED provider. Workflow/live authentication remain unverified; no v2 client."
        ),
    ),
    _profile(
        "US-05", "Bureau of Labor Statistics", None,
        api_families=("BLS Public Data API v1/v2; REST JSON/XLSX",),
        api_docs=(
            "https://www.bls.gov/developers/home.htm",
            "https://www.bls.gov/developers/api_faqs.htm",
        ),
        official_sources=(
            "https://www.bls.gov/audience/developers.htm",
            "https://www.bls.gov/developers/api_faqs.htm",
        ),
        authentication=AuthRequirement.OPTIONAL,
        credential_env_var="BLS_API_KEY",
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        non_api_methods=("official downloadable time-series files for selected programs",),
        status_note=(
            "Version 1 is documented for public use without registration; version 2 registration "
            "provides expanded access. Query and series limits vary by version and request. "
            "Iteration 28 implements only keyless v1 POST (up to 25 series and 10 years) "
            "with synthetic fixture parsing and file round-trips. It never sends BLS_API_KEY "
            "and has no v2 fallback. Workflow/live API requests remain unverified."
        ),
    ),
    _profile(
        "US-06", "U.S. Census Bureau", None,
        api_families=("Census Data API; dataset-specific REST queries",),
        api_docs=(
            "https://www.census.gov/data/developers.html",
            "https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html",
            "https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html",
        ),
        official_sources=(
            "https://www.census.gov/data/developers.html",
            "https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html",
            "https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html",
        ),
        authentication=AuthRequirement.REQUIRED,
        credential_env_var="CENSUS_API_KEY",
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        status_note=(
            "The Census API user guide revised May 2026 requires an API key on data queries "
            "and documents up to 50 variables per query. Available datasets and fields vary "
            "by program. Iteration 28 adds keyless metadata and keyed header/row JSON clients "
            "with synthetic fixture file round-trips. Numeric strings/nulls/sentinels are "
            "preserved; workflow/live authentication and payloads remain unverified."
        ),
    ),
    _profile(
        "EU-03", "Deutsche Bundesbank", None,
        api_families=("Bundesbank SDMX REST API; SDMX-ML 2.1/JSON/CSV/ZIP",),
        api_docs=(
            "https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448",
            "https://api.statistiken.bundesbank.de/doc/index.html?urls.primaryName=English+REST+API+Documentation",
        ),
        official_sources=(
            "https://www.bundesbank.de/en/statistics/time-series-and-real-time-data",
            "https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448",
        ),
        non_api_methods=("official CSV and SDMX downloads",),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 32: BBK BBEX3 dataflow metadata only, returned version 1.0; one uncredentialed HTTP 200 request, contract and archive/hash read-back. No observation ingestion.",
        status_note=(
            "Bundesbank SDMX mocked route tests plus synthetic/recorded metadata fixtures. "
            "Selected public metadata route succeeded without credentials; global authentication "
            "remains unknown. Referenced DSD, observations and general workflow remain unverified."
        ),
    ),
    _profile(
        "EU-04", "Bank of England", None,
        official_sources=(
            "https://www.bankofengland.co.uk/boeapps/database/",
            "https://www.bankofengland.co.uk/statistics/faqs",
        ),
        non_api_methods=("official database exports in HTML, Excel, XML, and CSV",),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        status_note=(
            "Registered IUDBEDR CSVF=TN official CSV download, synthetic native-date contract and raw "
            "archive/read-back; no live ingestion or normalized observations. General public statistics "
            "API specification remains unconfirmed, not officially absent."
        ),
    ),
    _profile(
        "EU-05", "INSEE", None,
        api_families=("INSEE SDMX 2.1 REST web service; BDM/idbank series access",),
        api_docs=("https://www.insee.fr/en/information/2868055",),
        official_sources=(
            "https://www.insee.fr/en/information/2868055",
            "https://www.insee.fr/fr/information/2862759",
        ),
        adapter_status=AdapterStatus.PARTIAL,
        fixture_scope=FixtureScope.SOURCE_SPECIFIC,
        live_validation=LiveValidation.PARTIAL,
        live_scope="Iteration 33: direct BDM codelist/FR1/CL_NATURE/1.0, one HTTP 200 request, metadata contract and archive/hash read-back only. Prior Iteration 32 IPC-2015-COICOP DSD HTTP 404 remains failed; no observation ingestion.",
        status_note=(
            "INSEE BDM data and metadata methods, mocked route tests and synthetic/recorded metadata fixtures. "
            "Official user guide distinguishes direct HTTPS from signed-in API portal. "
            "CL_NATURE codelist metadata validated in Iteration 33. Prior DSD 404 retained; "
            "that DSD, observations and general workflow remain unverified."
        ),
    ),
)


def _make_registry(rows: tuple[SourceAccessProfile, ...]) -> Mapping[str, SourceAccessProfile]:
    ids = [row.institution_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("source registry contains duplicate institution IDs")
    return MappingProxyType({row.institution_id: row for row in rows})


SOURCE_REGISTRY: Mapping[str, SourceAccessProfile] = _make_registry(_ROWS)


def all_source_profiles() -> tuple[SourceAccessProfile, ...]:
    return tuple(SOURCE_REGISTRY.values())


def get_source_profile(institution_id: str) -> SourceAccessProfile:
    try:
        return SOURCE_REGISTRY[institution_id]
    except KeyError:
        raise KeyError(f"unknown institution ID: {institution_id}") from None


def profiles_by_api_availability(
    availability: ApiAvailability,
) -> tuple[SourceAccessProfile, ...]:
    if not isinstance(availability, ApiAvailability):
        raise TypeError("availability must be an ApiAvailability")
    return tuple(row for row in SOURCE_REGISTRY.values() if row.api_availability == availability)


def profiles_by_scenario(scenario_id: str) -> tuple[SourceAccessProfile, ...]:
    if scenario_id not in "ABCDEFGH" or len(scenario_id) != 1:
        raise ValueError("scenario_id must be one of A-H")
    return tuple(row for row in SOURCE_REGISTRY.values() if scenario_id in row.scenario_ids)
