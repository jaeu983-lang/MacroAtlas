"""Allowlisted official guides, source-specific strategy selection and evidence capture."""
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

import requests

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import (
    MAX_BYTES,
    SourceFailure,
    parse_retry_after,
)
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration.models import StageInput

MAX_TEXT_CHARS = 250_000
MAX_LINKS = 500


@dataclass(frozen=True)
class GuideSpec:
    guide_id: str
    institution_id: str
    document_type: str
    official_url: str
    official_hosts: tuple[str, ...]
    extraction: str
    attribution: str

    def __post_init__(self):
        parsed = urlsplit(self.official_url)
        if (parsed.scheme != "https" or parsed.hostname not in self.official_hosts
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("guide URLs must use a configured official HTTPS host")


GUIDES = {
    "bls_api_v2": GuideSpec(
        "bls_api_v2", "bls", "api_guide",
        "https://www.bls.gov/developers/api_signature_v2.htm", ("www.bls.gov",),
        "html_visible_text_v1", "U.S. Bureau of Labor Statistics",
    ),
    "census_api": GuideSpec(
        "census_api", "census", "api_guide",
        "https://www.census.gov/data/developers/guidance/api-user-guide.html",
        ("www.census.gov",), "html_visible_text_v1", "U.S. Census Bureau",
    ),
    "census_api_key": GuideSpec(
        "census_api_key", "census", "authentication_guide",
        "https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html",
        ("www.census.gov",), "html_visible_text_v1", "U.S. Census Bureau",
    ),
    "census_query_limits": GuideSpec(
        "census_query_limits", "census", "query_limits_guide",
        "https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html",
        ("www.census.gov",), "html_visible_text_v1", "U.S. Census Bureau",
    ),
    "census_core_concepts": GuideSpec(
        "census_core_concepts", "census", "geography_variables_guide",
        "https://www.census.gov/data/developers/guidance/api-user-guide.Core_Concepts.html",
        ("www.census.gov",), "html_visible_text_v1", "U.S. Census Bureau",
    ),
    "census_terms": GuideSpec(
        "census_terms", "census", "terms_of_service",
        "https://www.census.gov/data/developers/about/terms-of-service.html",
        ("www.census.gov",), "html_visible_text_v1", "U.S. Census Bureau",
    ),
    "imf_api": GuideSpec(
        "imf_api", "imf", "sdmx_api_guide",
        "https://data.imf.org/en/Resource-Pages/IMF-API", ("data.imf.org",),
        "html_visible_text_v1", "International Monetary Fund",
    ),
    "bis_bulk_download": GuideSpec(
        "bis_bulk_download", "bis", "bulk_download_catalogue",
        "https://data.bis.org/bulkdownload", ("data.bis.org",),
        "html_visible_text_v1", "Bank for International Settlements",
    ),
    "boj_api_notice": GuideSpec(
        "boj_api_notice", "boj", "api_announcement",
        "https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm",
        ("www.boj.or.jp", "www.stat-search.boj.or.jp"),
        "html_visible_text_v1", "Bank of Japan",
    ),
    "boj_api_manual": GuideSpec(
        "boj_api_manual", "boj", "api_manual_pdf",
        "https://www.stat-search.boj.or.jp/info/api_manual_en.pdf",
        ("www.stat-search.boj.or.jp",), "pdf_raw_only_v1", "Bank of Japan",
    ),
    "boj_api_terms": GuideSpec(
        "boj_api_terms", "boj", "api_use_notice_pdf",
        "https://www.stat-search.boj.or.jp/info/api_notice_en.pdf",
        ("www.stat-search.boj.or.jp",), "pdf_raw_only_v1", "Bank of Japan",
    ),
    "tic_usage": GuideSpec(
        "tic_usage", "treasury_tic", "usage_guidance",
        "https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic",
        ("home.treasury.gov",), "html_visible_text_v1", "U.S. Department of the Treasury",
    ),
    "tic_portal": GuideSpec(
        "tic_portal", "treasury_tic", "statistical_portal",
        "https://home.treasury.gov/data/treasury-international-capital-tic-system",
        ("home.treasury.gov",), "html_visible_text_v1", "U.S. Department of the Treasury",
    ),
}


@dataclass(frozen=True)
class InstitutionStrategy:
    institution_id: str
    strategy_id: str
    discovery_method: str
    collection_method: str | None
    guide_ids: tuple[str, ...]
    collection_status: str
    credential_policy: str
    operating_notes: tuple[str, ...]


STRATEGIES = {
    "bls": InstitutionStrategy("bls", "bls_public_data_v2", "series_id_lookup",
                               "bls", ("bls_api_v2",), "limited_live_path",
                               "required_for_extended_query",
                               ("The API guide documents single-series retrieval for three years.",
                                "Registered multi-series requests may include up to 50 IDs for three years.",
                                "Requests up to 20 years and optional query parameters require a registration key.",
                                "This platform caps a request at 20 series IDs.")),
    "census": InstitutionStrategy("census", "census_acs_api", "dataset_variable_selection",
                                  "census", ("census_api", "census_api_key",
                                             "census_query_limits", "census_core_concepts",
                                             "census_terms"), "limited_live_path",
                                  "required",
                                  ("The 2026 Census guide requires a key for data queries.",
                                   "The guide permits up to 50 variables per query.",
                                   "Dataset-specific required variables and geographic codes need metadata review.")),
    "imf": InstitutionStrategy("imf", "imf_sdmx", "dataflow_structure_then_series",
                                None, ("imf_api",), "collection_not_implemented",
                                "unknown",
                                ("IMF documents SDMX 2.1 and 3.0 data APIs.",
                                 "The Swagger explorer page requests beta portal sign-in.")),
    "bis": InstitutionStrategy(
        "bis", "bis_sdmx_and_bulk", "official_catalogue_then_explicit_file_selection",
        None, ("bis_bulk_download",), "manual_file_intake_only", "unknown",
        ("The official bulk page links dated CSV and SDMX ZIP snapshots.",
         "No BIS-specific downloader exists; selected files use bounded local tabular intake."),
    ),
    "boj": InstitutionStrategy(
        "boj", "boj_json_csv_timeseries_api", "official_api_notice_then_series_lookup",
        None, ("boj_api_notice", "boj_api_manual", "boj_api_terms"),
        "collection_not_implemented", "unknown",
        ("BOJ's 2026 notice announces JSON and CSV access to time-series data.",
         "The official API manual is reachable and documents request parameters and limits.",
         "No BOJ observation connector or series-specific request has been implemented or tested."),
    ),
    "treasury_tic": InstitutionStrategy(
        "treasury_tic", "treasury_tic_tables", "official_table_and_usage_guidance",
        None, ("tic_portal", "tic_usage"), "collection_not_implemented", "unknown",
        ("The usage guide lists TXT, tab-delimited TXT, CSV, HTML, and PDF for most pages.",
         "It says Excel files are not used; some annual securities pages have MHT files.",
         "No TIC observation collector is implemented."),
    ),
}


def select_strategy(institution_id: str) -> dict:
    """Select only an explicit canonical institution; do not infer from request text."""
    try:
        strategy = STRATEGIES[institution_id]
    except (KeyError, TypeError):
        raise ValueError("unsupported canonical institution_id") from None
    result = asdict(strategy)
    result["guide_ids"] = list(strategy.guide_ids)
    result["operating_notes"] = list(strategy.operating_notes)
    return result


def read_strategy_guides(settings: Settings, institution_id: str, *,
                         max_age_seconds: int | None = None,
                         now: datetime | None = None) -> dict:
    """Return reusable archived evidence paths without network access or stale claims."""
    if max_age_seconds is not None and (
        type(max_age_seconds) is not int or max_age_seconds < 0
    ):
        raise ValueError("max_age_seconds must be a nonnegative integer or None")
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    strategy = select_strategy(institution_id)
    records = []
    for guide_id in strategy["guide_ids"]:
        spec = GUIDES[guide_id]
        relative = Path(settings.data_dir) / "raw" / "guides" / guide_id
        root = settings._inside(str(relative))
        attempts = []
        for manifest in root.glob("*/manifest.json") if root.exists() else ():
            try:
                manifest_path = settings._inside(manifest.relative_to(settings.project_root).as_posix())
                record = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if record.get("guide_id") != guide_id or record.get("source_url") != spec.official_url:
                continue
            attempts.append((record.get("retrieved_at", ""), record, manifest_path))
        attempts.sort(key=lambda item: (item[0], item[2].stat().st_mtime_ns))
        latest_attempt = attempts[-1] if attempts else None
        selected = None
        for _, record, manifest_path in reversed(attempts):
            if record.get("http_status") != 200 or not record.get("sha256"):
                continue
            raw_relative = record.get("original_path")
            if not isinstance(raw_relative, str):
                continue
            try:
                raw_path = settings._inside(raw_relative)
                body = raw_path.read_bytes()
            except (OSError, ValueError):
                continue
            if hashlib.sha256(body).hexdigest() != record["sha256"]:
                continue
            text_relative = record.get("extracted_text_path")
            text_path = None
            if isinstance(text_relative, str):
                try:
                    candidate = settings._inside(text_relative)
                    if candidate.is_file():
                        text_path = candidate.relative_to(settings.project_root).as_posix()
                except ValueError:
                    pass
            selected = {
                "state": "available" if text_path else "raw_only",
                "retrieved_at": record.get("retrieved_at"),
                "http_status": record.get("http_status"),
                "sha256": record["sha256"],
                "original_path": raw_path.relative_to(settings.project_root).as_posix(),
                "extracted_text_path": text_path,
                "manifest_path": manifest_path.relative_to(settings.project_root).as_posix(),
            }
            if max_age_seconds is None:
                selected["freshness"] = "unknown"
            else:
                captured = datetime.fromisoformat(record["retrieved_at"])
                age = (now - captured).total_seconds()
                selected["freshness"] = (
                    "fresh" if 0 <= age <= max_age_seconds
                    else "stale" if age > max_age_seconds else "unknown"
                )
                selected["age_seconds"] = age if age >= 0 else None
            break
        records.append({
            "guide_id": guide_id,
            "latest_attempt": None if latest_attempt is None else {
                "retrieved_at": latest_attempt[1].get("retrieved_at"),
                "http_status": latest_attempt[1].get("http_status"),
                "manifest_path": latest_attempt[2].relative_to(settings.project_root).as_posix(),
            },
            "reusable_evidence": selected,
        })
    return {"strategy": strategy, "guides": records}


class _VisibleText(HTMLParser):
    BLOCKS: ClassVar[set[str]] = {
        "address", "article", "br", "dd", "div", "dt", "h1", "h2", "h3",
        "h4", "li", "main", "p", "section", "table", "td", "th", "tr",
    }
    SKIP: ClassVar[set[str]] = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []
        self.title_parts = []
        self.in_title = False
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
            return
        if self.depth:
            return
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "a":
            href = next((value for name, value in attrs if name == "href"), None)
            if href and len(self.links) < MAX_LINKS:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
            return
        if self.depth:
            return
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth:
            return
        value = " ".join(data.split())
        if value:
            self.parts.append(value)
            if self.in_title:
                self.title_parts.append(value)


def extract_html(body: bytes, spec: GuideSpec) -> dict:
    try:
        source = body.decode("utf-8-sig")
    except UnicodeError:
        source = body.decode("windows-1252", errors="replace")
    parser = _VisibleText()
    parser.feed(source)
    text = re.sub(r"[ \t]+", " ", "\n".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    candidates = set()
    for href in parser.links:
        resolved = urlsplit(urljoin(spec.official_url, href))
        if (resolved.scheme == "https" and resolved.hostname in spec.official_hosts
                and resolved.username is None and resolved.password is None
                and resolved.port in (None, 443) and not resolved.query):
            candidates.add(urlunsplit((resolved.scheme, resolved.netloc, resolved.path, "", "")))
    return {
        "title": " ".join(parser.title_parts)[:500],
        "text": text[:MAX_TEXT_CHARS],
        "truncated": len(text) > MAX_TEXT_CHARS,
        "link_candidates": sorted(candidates)[:MAX_LINKS],
        "extraction": "html_visible_text_v1",
    }


@dataclass(frozen=True)
class GuideDownload:
    source_url: str
    body: bytes
    status_code: int
    retrieved_at: datetime
    content_type: str


class OfficialGuideFetcher:
    """Fetch predeclared official pages using the configured HTTP proxy and CA."""

    def fetch(self, spec: GuideSpec) -> GuideDownload:
        deadline = time.monotonic() + 30
        try:
            # requests uses the environment proxy and configured CA bundle.
            with requests.get(
                spec.official_url, timeout=(5, 20), stream=True, allow_redirects=False,
                headers={"Accept": "text/html,application/json,application/pdf",
                         "User-Agent": "MacroAtlas/0.1"},
            ) as response:
                status = response.status_code
                if status == 403 or status == 401:
                    raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                        "Official guide access was denied.", status)
                if status == 429 or 500 <= status < 600:
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                        "Official guide server returned a temporary error.",
                                        status, retry_after)
                if 300 <= status < 400:
                    raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                        "Official guide redirect requires review.", status)
                if status == 404:
                    raise SourceFailure(StageStatus.FAILED_TERMINAL, ErrorCode.SITE_CHANGED,
                                        "Official guide was not found.", status)
                if status != 200:
                    raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                        "Official guide returned an unexpected status.", status)
                length = response.headers.get("Content-Length", "")
                if length.isdecimal() and int(length) > MAX_BYTES:
                    raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                        "Official guide exceeded the two MiB size limit.", status)
                chunks, size = [], 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES or time.monotonic() > deadline:
                        raise SourceFailure(StageStatus.NEEDS_REVIEW,
                                            ErrorCode.SCHEMA_CHANGED,
                                            "Official guide exceeded its size or time limit.",
                                            status)
                    chunks.append(chunk)
                return GuideDownload(spec.official_url, b"".join(chunks), status,
                                     datetime.now(UTC),
                                     response.headers.get("Content-Type", ""))
        except SourceFailure:
            raise
        except requests.exceptions.SSLError:
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                "Official guide TLS verification failed.") from None
        except requests.RequestException:
            raise SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                                "Official guide transport failed.") from None


def _save_guide(settings: Settings, spec: GuideSpec, download: GuideDownload | None,
                extraction: dict | None, *, status_code: int | None,
                fetch_error: str | None = None,
                retry_after_seconds: int | None = None) -> dict:
    if download is not None:
        parsed = urlsplit(download.source_url)
        if (parsed.scheme != "https" or parsed.hostname not in spec.official_hosts
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("guide response source is outside its official allowlist")
        if len(download.body) > MAX_BYTES:
            raise ValueError("guide response exceeds the two MiB limit")
    previous = None
    if download is not None:
        prior = read_strategy_guides(settings, spec.institution_id)
        previous = next((guide["reusable_evidence"]["sha256"]
                         for guide in prior["guides"]
                         if guide["guide_id"] == spec.guide_id
                         and guide["reusable_evidence"] is not None), None)
    relative = Path(settings.data_dir) / "raw" / "guides" / spec.guide_id / uuid4().hex
    directory = settings._inside(str(relative))
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(parents=True, exist_ok=False)
    original_path = text_path = None
    content_hash = None
    content_type = "" if download is None else download.content_type
    byte_count = 0 if download is None else len(download.body)
    if download is not None:
        content_hash = hashlib.sha256(download.body).hexdigest()
        media = content_type.split(";", 1)[0].lower().strip()
        extension = {"text/html": "html", "application/json": "json",
                     "application/pdf": "pdf"}.get(media, "bin")
        raw = settings._inside(str(relative / f"source.{extension}"))
        with raw.open("xb") as stream:
            stream.write(download.body)
        original_path = raw.relative_to(settings.project_root).as_posix()
        if extraction is not None and extraction.get("text"):
            extracted = settings._inside(str(relative / "extracted.txt"))
            with extracted.open("x", encoding="utf-8") as stream:
                stream.write(extraction["text"])
            text_path = extracted.relative_to(settings.project_root).as_posix()
    manifest = settings._inside(str(relative / "manifest.json"))
    record = {
        "guide_id": spec.guide_id, "institution_id": spec.institution_id,
        "document_type": spec.document_type, "source_agency": spec.attribution,
        "source_url": spec.official_url,
        "retrieved_at": (download.retrieved_at.isoformat() if download else datetime.now(UTC).isoformat()),
        "http_status": status_code, "content_type": content_type, "byte_count": byte_count,
        "sha256": content_hash, "original_path": original_path, "extracted_text_path": text_path,
        "representation": "HTTP response body after requests content decoding",
        "extraction": None if extraction is None else {
            "method": extraction["extraction"], "title": extraction["title"],
            "text_truncated": extraction["truncated"],
            "candidate_links": [
                {"url": link, "state": "candidate_unverified"}
                for link in extraction["link_candidates"]
            ],
            "state": "extracted",
        },
        "auth_requirement": "unknown", "license_status": "not_assessed",
        "retry_after_seconds": retry_after_seconds,
        "content_comparison": (
            "unavailable" if download is None else
            "baseline_unavailable" if previous is None else
            "unchanged" if content_hash == previous else "changed"
        ),
        "previous_sha256": previous,
        "fetch_error": fetch_error,
    }
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2)
    record["manifest_path"] = manifest.relative_to(settings.project_root).as_posix()
    return record


class InstitutionGuideEngine:
    """Fetch and archive a curated official guide; register as guide_documentation/1."""

    def __init__(self, settings: Settings, fetcher: OfficialGuideFetcher | None = None):
        self.settings = settings
        self.fetcher = fetcher if fetcher is not None else OfficialGuideFetcher()

    def run(self, request: StageInput) -> StageResult[dict]:
        data = request.input_data
        if (not isinstance(data, dict) or set(data) != {"guide_id"}
                or not isinstance(data.get("guide_id"), str)
                or data["guide_id"] not in GUIDES):
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected a curated guide_id.",))
        spec = GUIDES[data["guide_id"]]
        if self.settings.network_enabled is not True:
            return StageResult(StageStatus.NEEDS_REVIEW, error_code=ErrorCode.LICENSE_SECURITY,
                               warnings=("Network guide retrieval is disabled in settings.",))
        try:
            download = self.fetcher.fetch(spec)
        except SourceFailure as failure:
            record = _save_guide(
                self.settings, spec, None, None,
                status_code=failure.status_code, fetch_error=str(failure),
                retry_after_seconds=failure.retry_after_seconds,
            )
            retry_hint = None
            if failure.status == StageStatus.FAILED_RETRYABLE:
                if failure.retry_after_seconds is None:
                    retry_hint = ("Manual resume is available after the temporary source "
                                  "condition clears; no automatic retry was sent.")
                else:
                    retry_hint = (f"Wait at least {failure.retry_after_seconds} seconds before "
                                  "manual resume; no automatic retry was sent.")
            return StageResult(failure.status, record, (record["manifest_path"],),
                               (str(failure),), failure.code, retry_hint,
                               failure.retry_after_seconds)
        media_type = download.content_type.split(";", 1)[0].strip().lower()
        extraction = None
        if media_type == "text/html":
            extraction = extract_html(download.body, spec)
        elif media_type == "application/json":
            try:
                content = json.loads(download.body)
                extraction = {"title": "", "text": json.dumps(content, ensure_ascii=False,
                                                                  indent=2)[:MAX_TEXT_CHARS],
                              "truncated": False, "link_candidates": [],
                              "extraction": "json_pretty_v1"}
            except (ValueError, UnicodeError, RecursionError):
                extraction = None
        record = _save_guide(self.settings, spec, download, extraction,
                             status_code=download.status_code)
        if extraction is None:
            return StageResult(StageStatus.NEEDS_REVIEW, record, (record["manifest_path"],),
                               ("Original guide saved, but no safe text extractor matched its media type.",),
                               ErrorCode.SCHEMA_CHANGED)
        if not extraction["text"].strip():
            return StageResult(StageStatus.NEEDS_REVIEW, record,
                               (record["manifest_path"], record["original_path"]),
                               ("Original guide saved but yielded no extractable text.",),
                               ErrorCode.SCHEMA_CHANGED)
        evidence = tuple(path for path in (
            record["original_path"], record["extracted_text_path"], record["manifest_path"],
        ) if path)
        return StageResult(StageStatus.SUCCEEDED, record, evidence,
                           ("Guide is archived; content interpretation and licensing remain unreviewed.",))
