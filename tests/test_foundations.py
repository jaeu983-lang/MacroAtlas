"""Runs under either pytest or the standard-library unittest runner."""
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from macro_data_platform.config import Settings
from macro_data_platform.contracts import (
    Engine,
    ErrorCode,
    EvidenceKind,
    SourceEvidence,
    StageResult,
    StageStatus,
    Task,
    TaskStatus,
)


class FoundationTests(unittest.TestCase):
    def test_task_preserves_request_and_defaults(self):
        task = Task("t1", "국채 보유잔액", datetime.now(UTC))
        self.assertEqual(task.status, TaskStatus.CREATED)
        self.assertEqual(task.request, "국채 보유잔액")

    def test_task_rejects_missing_identity_and_invalid_status(self):
        for task_id, request, status in [("", "r", TaskStatus.CREATED),
                                         ("t", " ", TaskStatus.CREATED), ("t", "r", "bad")]:
            with (
                self.subTest(task_id=task_id, request=request, status=status),
                self.assertRaises(ValueError),
            ):
                Task(task_id, request, datetime.now(UTC), status)

    def test_timestamps_require_utc(self):
        for date in [datetime(2026, 1, 1),
                     datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=9)))]:
            with self.assertRaises(ValueError):
                Task("t", "request", date)

    def test_evidence_preserves_provenance_and_unknowns(self):
        for kind in EvidenceKind:
            evidence = SourceEvidence("e1", "fixture agency", "https://example.org/docs",
                                      datetime.now(UTC), kind, "fixture:original")
            self.assertIsNone(evidence.series_id)
            self.assertIsNone(evidence.source_version)
            self.assertEqual(evidence.kind, kind)
            self.assertEqual(evidence.original_ref, "fixture:original")

    def test_evidence_rejects_invalid_urls_and_kind(self):
        for url, kind in [("file:///tmp/x", EvidenceKind.FIXTURE),
                          ("https://user:secret@example.org", EvidenceKind.FIXTURE),
                          ("https://example.org", "unknown")]:
            with self.assertRaises(ValueError):
                SourceEvidence("e", "agency", url, datetime.now(UTC), kind, "ref")

    def test_results_preserve_missing_payload_and_evidence(self):
        result = StageResult(StageStatus.NEEDS_REVIEW, evidence_refs=("e1",),
                             warnings=("unit unknown",))
        self.assertIsNone(result.payload)
        self.assertEqual(result.evidence_refs, ("e1",))
        self.assertEqual(result.warnings, ("unit unknown",))

    def test_error_contract(self):
        for status in [StageStatus.FAILED_RETRYABLE, StageStatus.FAILED_TERMINAL]:
            with self.assertRaises(ValueError):
                StageResult(status)
            for code in ErrorCode:
                self.assertEqual(StageResult(status, error_code=code).error_code, code)
        for kwargs in [
            {"status": "invalid"},
            {"status": StageStatus.SUCCEEDED, "error_code": ErrorCode.INTERNAL_BUG},
            {"status": StageStatus.NEEDS_REVIEW, "error_code": "bad"},
            {"status": StageStatus.NEEDS_REVIEW, "evidence_refs": ("",)},
        ]:
            with self.assertRaises(ValueError):
                StageResult(**kwargs)

    def test_engine_is_independently_substitutable(self):
        class FixtureEngine:
            def run(self, request: str) -> StageResult[str]:
                return StageResult(StageStatus.SUCCEEDED, request, ("fixture:e1",))

        engine: Engine[str, str] = FixtureEngine()
        self.assertEqual(engine.run("request").payload, "request")

    def test_storage_defaults_are_separate_and_have_no_side_effects(self):
        with TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            settings = Settings.from_env(root, {})
            self.assertFalse(settings.network_enabled)
            self.assertEqual(settings.database_path, root / "data/catalog.sqlite")
            self.assertNotEqual(settings.raw_dir, settings.normalized_dir)
            self.assertFalse(settings.raw_dir.exists())

    def test_environment_is_explicit_and_strict(self):
        settings = Settings.from_env(Path.cwd(), {"MACROATLAS_DATA_DIR": "data/local",
                                                "MACROATLAS_NETWORK_ENABLED": "true"})
        self.assertTrue(settings.network_enabled)
        self.assertEqual(settings.raw_dir, Path.cwd() / "data/local/raw")
        with self.assertRaises(ValueError):
            Settings.from_env(Path.cwd(), {"MACROATLAS_NETWORK_ENABLED": "yes"})

    def test_storage_rejects_escapes(self):
        for path in ["../outside", str(Path.cwd().anchor), "", "."]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                Settings(Path.cwd(), path)


if __name__ == "__main__":
    unittest.main()
