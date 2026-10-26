"""Offline discovery regression and real SQLite orchestration checks."""
import json
import tempfile
import unittest
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageStatus
from macro_data_platform.discovery.institutions import (
    ADAPTERS,
    InstitutionDiscoveryEngine,
    discover_profile,
)
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore


class InstitutionDiscoveryTests(unittest.TestCase):
    def test_two_catalogue_strategies_preserve_unknown_authentication(self):
        for institution in ADAPTERS:
            with self.subTest(institution=institution):
                profile = discover_profile(institution)
                self.assertTrue(profile["links"])
                self.assertEqual(profile["auth_requirement"], "unknown")
                self.assertEqual(profile["authentication_status"], "not_tested")
                self.assertIsNone(profile["live_verified_at"])
                self.assertFalse(profile["collection_supported"])

    def test_html_relative_links_and_official_api_host(self):
        for institution, api_host in [("bls", "api.bls.gov"), ("census", "api.census.gov")]:
            with self.subTest(institution=institution):
                profile = discover_profile(institution, {
                    "source_url": ADAPTERS[institution].homepage,
                    "html": f'<a href="/data/">data</a><a href="https://{api_host}/">api</a>',
                })
                self.assertEqual(len(profile["links"]), 2)
                self.assertEqual(profile["evidence_kind"], "fixture")

    def test_deceptive_urls_and_secret_queries_rejected(self):
        adapter = ADAPTERS["bls"]
        for url in [
            "https://www.bls.gov.evil.example/", "https://evil.example/www.bls.gov",
            "https://user@www.bls.gov/", "http://www.bls.gov/",
            "https://www.bls.gov:444/", "https://api.bls.gov/?key=fake-secret",
            "https://www.census.gov/", "https://www.bls.gov:bad/",
            "https://www.bls.gov/\n", "https://www.bls.gov/\\evil",
        ]:
            with self.subTest(url=url):
                self.assertFalse(adapter.accepts(url))

    def test_limits_and_unofficial_page(self):
        for page in [
            {"source_url": "https://evil.example/", "html": ""},
            {"source_url": ADAPTERS["bls"].homepage, "html": "x" * 65537},
            {"source_url": ADAPTERS["bls"].homepage, "html": '<a href="/">x</a>' * 201},
        ]:
            with self.assertRaises(ValueError):
                discover_profile("bls", page)

    def test_invalid_and_empty_discovery_require_review(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = InstitutionDiscoveryEngine(Settings(Path(directory)))
            for data in [{"institution_id": []}, {"institution_id": "unknown"}, {
                "institution_id": "bls", "page": {
                    "source_url": ADAPTERS["bls"].homepage,
                    "html": '<a href="https://evil.example/">x</a>',
                },
            }]:
                result = engine.run(StageInput("t", "r", "s", data, None, ()))
                self.assertEqual(result.status, StageStatus.NEEDS_REVIEW)
            self.assertFalse((Path(directory) / "data").exists())

    def test_orchestrator_persists_profiles_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory))
            store = HistoryStore(settings)
            runner = Orchestrator(store, {
                ("institution_discovery", "1"): InstitutionDiscoveryEngine(settings),
            })
            refs = []
            for institution in ADAPTERS:
                task = runner.create(f"Discover {institution}")
                runner.plan(task.task_id, TaskPlan((StageSpec(
                    "institution", "institution_discovery", {"institution_id": institution},
                ),)))
                result = runner.run(task.task_id)
                self.assertEqual(result["status"], "COMPLETED")
                ref = result["stages"][0]["result"]["evidence_refs"][0]
                profile = json.loads((Path(directory) / ref).read_text())
                self.assertEqual(profile["institution_id"], institution)
                refs.append(ref)
            self.assertEqual(len(set(refs)), 2)


if __name__ == "__main__":
    unittest.main()
