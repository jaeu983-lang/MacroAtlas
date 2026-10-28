import hashlib
import json
import tarfile
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from macro_data_platform.ingestion.freshness import (
    DEFAULT_FRESHNESS_POLICY,
    FreshnessEvidence,
    FreshnessPolicy,
    FreshnessStatus,
    assess_freshness,
    series_key_override_key,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "docs/evidence/freshness_policy_candidate_20261028.json"


def _load_candidate():
    return json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))


def _freshness_evidence(record, *, approve_for_test=False):
    captured_at = datetime.fromisoformat(record["captured_at"])
    return FreshnessEvidence(
        evidence_id=record["evidence_id"],
        source_url=record["source_url"],
        source_sha256=record["source_sha256"],
        captured_at=captured_at,
        evidence_type=record["evidence_type"],
        citation=record["citation"],
        review_status="approved" if approve_for_test else record["review_status"],
        reviewer_id="synthetic-test-reviewer" if approve_for_test else record["reviewer_id"],
        reviewed_at=(captured_at + timedelta(seconds=1) if approve_for_test else
                     datetime.fromisoformat(record["reviewed_at"])
                     if record["reviewed_at"] else None),
    )


class _VisibleHtml(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def test_freshness_source_capture_archive_matches_candidate_hashes():
    candidate = _load_candidate()
    archive_path = ROOT / candidate["source_capture_archive"]
    archive_bytes = archive_path.read_bytes()
    assert hashlib.sha256(archive_bytes).hexdigest() == candidate[
        "source_capture_archive_sha256"
    ]

    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
    manifest = json.loads(members["manifest.json"])
    assert manifest["schema_version"] == "freshness-source-capture-v1"
    records = {item["archive_member"]: item for item in manifest["sources"]}
    for proposed in candidate["candidates"]:
        evidence = proposed["evidence"]
        content = members[evidence["archive_member"]]
        source = records[evidence["archive_member"]]
        assert hashlib.sha256(content).hexdigest() == evidence["source_sha256"]
        assert source["source_url"] == evidence["source_url"]
        assert source["captured_at"] == evidence["captured_at"]


def test_captured_release_calendar_fixtures_match_the_citations():
    candidate = _load_candidate()
    with tarfile.open(ROOT / candidate["source_capture_archive"], mode="r:gz") as archive:
        pages = {
            item.name: archive.extractfile(item).read().decode("utf-8", "replace")
            for item in archive.getmembers() if item.name.endswith(".html")
        }
    visible = {}
    for name, page in pages.items():
        parser = _VisibleHtml()
        parser.feed(page)
        visible[name] = " ".join(parser.parts)

    bls = visible["bls_cpi_release_schedule.html"]
    assert "October 2026 Nov. 10, 2026 08:30 AM" in bls
    assert "November 2026 Dec. 10, 2026 08:30 AM" in bls
    census = visible["census_acs_release_dates.html"]
    assert "2025 American Community Survey 1-year Estimates October 14, 2026" in census


def test_freshness_override_candidates_are_not_activated_or_reviewed():
    candidate = _load_candidate()
    assert candidate["enabled"] is False
    assert candidate["review_status"] == "pending_independent_review"
    assert candidate["activation_rule"].startswith("Do not load")
    assert DEFAULT_FRESHNESS_POLICY.series_overrides == {}

    overrides = {row["override_key"]: row["proposed_max_age_days"]
                 for row in candidate["candidates"]}
    evidence = {row["override_key"]: _freshness_evidence(row["evidence"])
                for row in candidate["candidates"]}
    policy = FreshnessPolicy(
        policy_id="review-only-" + candidate["candidate_id"],
        series_overrides=overrides,
        series_evidence=evidence,
    )

    bls_result = assess_freshness(
        ["2026-09"], frequency="monthly", series_id="CUUR0000SA0",
        as_of=date(2026, 10, 28), policy=policy,
    )
    assert bls_result["status"] == FreshnessStatus.FRESHNESS_UNVERIFIED
    assert bls_result["policy_evidence_status"] == "pending_review"

    census = next(row for row in candidate["candidates"]
                  if row["series_scope"]["source_agency"] == "U.S. Census Bureau")
    census_key = series_key_override_key({
        "dataset": "acs/acs1", "variable": "B01001_001E", "geography": "state:06",
    })
    assert census["override_key"] == census_key
    census_result = assess_freshness(
        ["2025"], frequency=None, period_format="YYYY",
        series_key={"dataset": "acs/acs1", "variable": "B01001_001E",
                    "geography": "state:06"},
        as_of=date(2026, 10, 28), policy=policy,
    )
    assert census_result["status"] == FreshnessStatus.FRESHNESS_UNVERIFIED
    assert census_result["policy_evidence_status"] == "pending_review"


def test_proposed_series_threshold_boundaries_are_local_only():
    candidate = _load_candidate()
    # This synthetic approval exercises the proposed boundaries; it does not alter the
    # pending review status or load the candidate into production policy.
    overrides = {row["override_key"]: row["proposed_max_age_days"]
                 for row in candidate["candidates"]}
    evidence = {row["override_key"]: _freshness_evidence(
        row["evidence"], approve_for_test=True,
    ) for row in candidate["candidates"]}
    policy = FreshnessPolicy(
        policy_id="boundary-test-only-" + candidate["candidate_id"],
        series_overrides=overrides,
        series_evidence=evidence,
    )

    bls_at_limit = assess_freshness(
        ["2026-09"], frequency="monthly", series_id="CUUR0000SA0",
        as_of=date(2026, 11, 29), policy=policy,
    )
    bls_past_limit = assess_freshness(
        ["2026-09"], frequency="monthly", series_id="CUUR0000SA0",
        as_of=date(2026, 11, 30), policy=policy,
    )
    assert bls_at_limit["age_days"] == 60
    assert bls_at_limit["status"] == FreshnessStatus.FRESH
    assert bls_past_limit["age_days"] == 61
    assert bls_past_limit["status"] == FreshnessStatus.STALE

    census_key = {
        "dataset": "acs/acs1", "variable": "B01001_001E", "geography": "state:06",
    }
    census_at_limit = assess_freshness(
        ["2025"], frequency=None, period_format="YYYY", series_key=census_key,
        as_of=date(2027, 2, 4), policy=policy,
    )
    census_past_limit = assess_freshness(
        ["2025"], frequency=None, period_format="YYYY", series_key=census_key,
        as_of=date(2027, 2, 5), policy=policy,
    )
    assert census_at_limit["age_days"] == 400
    assert census_at_limit["status"] == FreshnessStatus.FRESH
    assert census_past_limit["age_days"] == 401
    assert census_past_limit["status"] == FreshnessStatus.STALE
