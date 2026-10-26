"""Offline guide-capture and institution-strategy tests."""
import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from macro_data_platform.config import Settings
from macro_data_platform.connectors.statistical_http import SourceFailure
from macro_data_platform.contracts import ErrorCode, StageStatus
from macro_data_platform.discovery.institution_guides import (
    GUIDES,
    GuideDownload,
    InstitutionGuideEngine,
    extract_html,
    read_strategy_guides,
    select_strategy,
)
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore


class FixtureFetcher:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def fetch(self, spec):
        self.calls.append(spec.guide_id)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class GuideTests(unittest.TestCase):
    def test_strategy_selection_is_canonical_and_reports_support(self):
        expected = {
            "bls": ("bls_public_data_v2", "bls", ["bls_api_v2"]),
            "census": ("census_acs_api", "census", [
                "census_api", "census_api_key", "census_query_limits",
                "census_core_concepts", "census_terms",
            ]),
            "imf": ("imf_sdmx", None, ["imf_api"]),
            "bis": ("bis_sdmx_and_bulk", None, ["bis_bulk_download"]),
            "boj": ("boj_json_csv_timeseries_api", None, [
                "boj_api_notice", "boj_api_manual", "boj_api_terms",
            ]),
            "treasury_tic": ("treasury_tic_tables", None, ["tic_portal", "tic_usage"]),
        }
        for institution, (strategy_id, collection, guides) in expected.items():
            with self.subTest(institution=institution):
                strategy = select_strategy(institution)
                self.assertEqual(strategy["strategy_id"], strategy_id)
                self.assertEqual(strategy["collection_method"], collection)
                self.assertEqual(strategy["guide_ids"], guides)
                self.assertTrue(strategy["operating_notes"])
        with self.assertRaises(ValueError):
            select_strategy("Treasury TIC")
        self.assertEqual(select_strategy("boj")["collection_status"], "blocked_manual_access")

    def test_bis_bulk_guide_accepts_only_official_archive_candidates(self):
        spec = GUIDES["bis_bulk_download"]
        source = b"""<html><body>
        <a href='/static/bulk/WS_GLI_PUB_csv_col.zip'>Global liquidity indicators (CSV)</a>
        <a href='https://outside.example/other.zip'>unofficial</a>
        <a href='/static/bulk/download.zip?token=private'>query</a>
        </body></html>"""

        parsed = extract_html(source, spec)

        self.assertEqual(parsed["link_candidates"], [
            "https://data.bis.org/static/bulk/WS_GLI_PUB_csv_col.zip",
        ])

    def test_html_extraction_omits_scripts_and_unapproved_links(self):
        spec = GUIDES["tic_usage"]
        source = b"""<html><head><title>TIC guide</title><script>secret()</script></head>
        <body><h1>Use data</h1><p>Read CSV guidance.</p>
        <a href='/data/'>portal</a><a href='https://evil.example/'>offsite</a>
        <a href='/download?token=private'>query</a></body></html>"""
        parsed = extract_html(source, spec)
        self.assertIn("Read CSV guidance.", parsed["text"])
        self.assertNotIn("secret()", parsed["text"])
        self.assertEqual(parsed["title"], "TIC guide")
        self.assertEqual(parsed["link_candidates"], [
            "https://home.treasury.gov/data/",
        ])

    def test_success_preserves_original_text_manifest_and_hash(self):
        body = b"<html><title>BLS guide</title><p>API usage rules.</p></html>"
        download = GuideDownload(GUIDES["bls_api_v2"].official_url, body, 200,
                                 datetime(2026, 10, 26, tzinfo=UTC), "text/html; charset=utf-8")
        fetcher = FixtureFetcher(download)
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            result = InstitutionGuideEngine(settings, fetcher).run(StageInput(
                "task", "guide", "guide", {"guide_id": "bls_api_v2"}, None, (),
            ))
            self.assertEqual(result.status, StageStatus.SUCCEEDED)
            record = result.payload
            raw = Path(directory, record["original_path"])
            text = Path(directory, record["extracted_text_path"])
            manifest = Path(directory, record["manifest_path"])
            self.assertEqual(raw.read_bytes(), body)
            self.assertIn("API usage rules.", text.read_text())
            self.assertEqual(json.loads(manifest.read_text())["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(fetcher.calls, ["bls_api_v2"])
            reusable = read_strategy_guides(settings, "bls")["guides"][0]["reusable_evidence"]
            self.assertEqual(reusable["state"], "available")
            self.assertEqual(reusable["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(reusable["freshness"], "unknown")
            checked = read_strategy_guides(
                settings, "bls", max_age_seconds=3600, now=datetime(2026, 10, 26, 1, tzinfo=UTC),
            )["guides"][0]["reusable_evidence"]
            self.assertEqual(checked["freshness"], "fresh")

    def test_refresh_tracks_change_without_overwriting_prior_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            for body in (b"<html><p>First guide.</p></html>",
                         b"<html><p>Updated guide.</p></html>"):
                download = GuideDownload(GUIDES["tic_usage"].official_url, body, 200,
                                         datetime(2026, 10, 26, tzinfo=UTC), "text/html")
                result = InstitutionGuideEngine(settings, FixtureFetcher(download)).run(
                    StageInput("task", "guide", "guide",
                               {"guide_id": "tic_usage"}, None, ()),
                )
                self.assertEqual(result.status, StageStatus.SUCCEEDED)
            latest = read_strategy_guides(settings, "treasury_tic")["guides"]
            usage = next(item for item in latest if item["guide_id"] == "tic_usage")
            self.assertEqual(usage["reusable_evidence"]["state"], "available")
            manifest = Path(directory, usage["reusable_evidence"]["manifest_path"])
            record = json.loads(manifest.read_text())
            self.assertEqual(record["content_comparison"], "changed")
            self.assertIsNotNone(record["previous_sha256"])

    def test_403_is_recorded_as_review_without_archiving_page_body(self):
        failure = SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                "Official guide access was denied.", 403)
        fetcher = FixtureFetcher(failure)
        with tempfile.TemporaryDirectory() as directory:
            result = InstitutionGuideEngine(Settings(Path(directory), network_enabled=True), fetcher).run(
                StageInput("task", "guide", "guide", {"guide_id": "imf_api"}, None, ()),
            )
            self.assertEqual(result.status, StageStatus.NEEDS_REVIEW)
            record = result.payload
            self.assertEqual(record["http_status"], 403)
            self.assertIsNone(record["original_path"])
            self.assertIsNone(record["sha256"])
            self.assertTrue(Path(directory, record["manifest_path"]).exists())

    def test_bis_bulk_503_preserves_retry_after_without_automatic_retry(self):
        class Response:
            def __init__(self):
                self.status_code = 503
                self.headers = {"Retry-After": "17", "Content-Type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with tempfile.TemporaryDirectory() as directory, patch(
                "macro_data_platform.discovery.institution_guides.requests.get",
                return_value=Response()) as get:
            result = InstitutionGuideEngine(Settings(Path(directory), network_enabled=True)).run(
                StageInput("task", "BIS bulk catalogue", "guide",
                           {"guide_id": "bis_bulk_download"}, None, ()),
            )
            self.assertEqual(result.status, StageStatus.FAILED_RETRYABLE)
            self.assertEqual(result.retry_after_seconds, 17)
            self.assertIn("Wait at least 17 seconds", result.retry_hint)
            self.assertEqual(get.call_count, 1)
            record = result.payload
            self.assertEqual(record["http_status"], 503)
            self.assertEqual(record["retry_after_seconds"], 17)
            self.assertIsNone(record["original_path"])
            self.assertIsNone(record["sha256"])

    def test_invalid_guide_id_does_not_call_fetcher(self):
        fetcher = FixtureFetcher(None)
        with tempfile.TemporaryDirectory() as directory:
            engine = InstitutionGuideEngine(Settings(Path(directory)), fetcher)
            result = engine.run(StageInput("task", "guide", "guide",
                                           {"guide_id": "https://evil.example"}, None, ()))
            self.assertEqual(result.status, StageStatus.FAILED_TERMINAL)
            self.assertFalse(fetcher.calls)

    def test_orchestrator_can_run_guide_capture_stage(self):
        body = b"<html><title>API guide</title><p>Versioned evidence.</p></html>"
        download = GuideDownload(GUIDES["census_api"].official_url, body, 200,
                                 datetime(2026, 10, 26, tzinfo=UTC), "text/html")
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            runner = Orchestrator(HistoryStore(settings), {
                ("guide_documentation", "1"): InstitutionGuideEngine(
                    settings, FixtureFetcher(download),
                ),
            })
            task = runner.create("capture Census API guide")
            runner.plan(task.task_id, TaskPlan((StageSpec(
                "guide", "guide_documentation", {"guide_id": "census_api"},
            ),)))
            result = runner.run(task.task_id)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["stages"][0]["engine"], "guide_documentation")


if __name__ == "__main__":
    unittest.main()
