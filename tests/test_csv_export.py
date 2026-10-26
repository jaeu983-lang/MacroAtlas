"""CSV export verifies saved evidence and performs no collection or normalization writes."""

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from macro_data_platform.cli import build_parser, dispatch
from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import DATA_ENDPOINT, METADATA_ENDPOINT
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.connectors.worldbank import Download
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.ingestion.csv_export import export_task
from macro_data_platform.orchestration import Orchestrator
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def _boj_download(url, document):
    return ApiDownload(
        url,
        json.dumps(document, allow_nan=False).encode(),
        200,
        NOW,
        "application/json",
        EvidenceKind.FIXTURE,
    )


class _BOJTransport:
    def fetch_metadata(self, query):
        return _boj_download(
            METADATA_ENDPOINT,
            {
                "STATUS": 200,
                "DB": "FM08",
                "DATE": "20261026",
                "RESULTSET": [
                    {
                        "SERIES_CODE": "FXERD01",
                        "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
                        "UNIT": "Yen per U.S. Dollar",
                        "FREQUENCY": "DAILY",
                        "CATEGORY": "Foreign Exchange Rates",
                        "START_OF_THE_TIME_SERIES": "19990101",
                        "END_OF_THE_TIME_SERIES": "20261022",
                        "LAST_UPDATE": "20261026",
                    }
                ],
            },
        )

    def fetch_observations(self, query):
        return _boj_download(
            DATA_ENDPOINT,
            {
                "STATUS": 200,
                "DATE": "20261026",
                "NEXTPOSITION": None,
                "RESULTSET": [
                    {
                        "SERIES_CODE": "FXERD01",
                        "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
                        "UNIT": "Yen per U.S. Dollar",
                        "FREQUENCY": "DAILY",
                        "LAST_UPDATE": 20261026,
                        "VALUES": {"SURVEY_DATES": [20260901, 20260902], "VALUES": [159.77, None]},
                    }
                ],
            },
        )


class _WorldBankTransport:
    def fetch(self, query):
        body = (Path(__file__).parent / "fixtures" / "worldbank_gdp.json").read_bytes()
        return Download(query.url, body, 200, NOW, "application/json", EvidenceKind.FIXTURE)


class CSVExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
        self.settings = Settings(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def _collect(self, provider):
        if provider == "worldbank":
            args = build_parser().parse_args(
                [
                    "--project-root",
                    str(self.root),
                    "collect",
                    "worldbank-gdp",
                    "--start-year",
                    "2020",
                    "--end-year",
                    "2022",
                    "--live",
                ]
            )
            status, summary = dispatch(args, worldbank_transport=_WorldBankTransport())
        else:
            args = build_parser().parse_args(
                [
                    "--project-root",
                    str(self.root),
                    "collect",
                    "boj-fxer",
                    "--month",
                    "202609",
                    "--live",
                ]
            )
            status, summary = dispatch(args, boj_transport=_BOJTransport())
        self.assertEqual(status, 0, summary)
        return summary["task_id"]

    def _export(self, task_id, name="result.csv"):
        args = build_parser().parse_args(
            [
                "--project-root",
                str(self.root),
                "export",
                task_id,
                "--format",
                "csv",
                "--output",
                f"data/exports/{name}",
            ]
        )
        return dispatch(args)

    def test_worldbank_csv_preserves_null_zero_and_audited_provenance_read_only(self):
        task_id = self._collect("worldbank")
        database = self.settings.database_path
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        status, result = self._export(task_id)
        self.assertEqual(status, 0)
        output = self.root / result["csv_path"]
        raw = output.read_bytes()
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        self.assertEqual([row["date"] for row in rows], ["2022", "2021", "2020"])
        self.assertEqual([row["value"] for row in rows], ["123.5", "", "0"])
        self.assertEqual(rows[1]["value_status"], "missing")
        self.assertEqual(rows[0]["unit"], "")
        self.assertEqual(rows[0]["frequency"], "")
        manifest_path = self.root / result["provenance_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["task_id"], task_id)
        self.assertEqual([row["stage_id"] for row in manifest["stages"]], ["collect", "validate"])
        self.assertEqual(
            manifest["source"]["manifest_hash_status"], "verified_against_audit_record"
        )
        self.assertEqual(manifest["export"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)

    def test_boj_csv_preserves_missing_value_and_manifest_hash_limit(self):
        task_id = self._collect("boj")
        status, result = self._export(task_id)
        self.assertEqual(status, 0)
        rows = list(
            csv.DictReader(
                io.StringIO(
                    (self.root / result["csv_path"]).read_text(encoding="utf-8"),
                )
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["value"], "")
        self.assertEqual(rows[1]["value_status"], "missing")
        manifest = json.loads((self.root / result["provenance_path"]).read_text())
        self.assertEqual(
            manifest["source"]["manifest_hash_status"],
            "fields_and_raw_hash_verified_no_capture_digest",
        )
        self.assertTrue(manifest["source"]["metadata_manifest_sha256"])

    def test_raw_tampering_is_refused_without_creating_output(self):
        task_id = self._collect("boj")
        task = HistoryStore(self.settings).get(task_id)
        raw_path = self.root / task["stages"][-1]["result"]["payload"]["raw_path"]
        raw_path.write_bytes(raw_path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "boj_request_manifest_mismatch"):
            export_task(self.settings, task_id, "data/exports/tampered.csv")
        self.assertFalse((self.root / "data/exports/tampered.csv").exists())

    def test_manifest_tampering_is_refused_without_creating_output(self):
        task_id = self._collect("boj")
        task = HistoryStore(self.settings).get(task_id)
        manifest_path = self.root / task["stages"][-1]["result"]["payload"]["manifest_path"]
        manifest_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "boj_request_manifest_mismatch"):
            export_task(self.settings, task_id, "data/exports/tampered.csv")
        self.assertFalse((self.root / "data/exports/tampered.csv").exists())

    def test_non_successful_stage_and_changed_source_are_refused(self):
        task_id = self._collect("boj")
        with sqlite3.connect(self.settings.database_path) as connection:
            raw = connection.execute(
                "SELECT document FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
            document = json.loads(raw)
            document["stages"][-1]["status"] = "NEEDS_REVIEW"
            connection.execute(
                "UPDATE tasks SET document=? WHERE task_id=?", (json.dumps(document), task_id)
            )
        with self.assertRaisesRegex(ValueError, "task_stage_not_successful"):
            export_task(self.settings, task_id, "data/exports/stage.csv")

    def test_changed_source_status_is_refused_even_when_task_status_was_forged(self):
        task_id = self._collect("boj")
        with sqlite3.connect(self.settings.database_path) as connection:
            raw = connection.execute(
                "SELECT document FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
            document = json.loads(raw)
            document["stages"][-1]["result"]["payload"]["source_change_status"] = "changed"
            connection.execute(
                "UPDATE tasks SET document=? WHERE task_id=?", (json.dumps(document), task_id)
            )
        with self.assertRaisesRegex(ValueError, "source_change_requires_review"):
            export_task(self.settings, task_id, "data/exports/changed.csv")
        self.assertFalse((self.root / "data/exports/changed.csv").exists())

    def test_quality_record_drift_is_refused(self):
        task_id = self._collect("boj")
        with sqlite3.connect(self.settings.database_path) as connection:
            raw = connection.execute(
                "SELECT document FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
            document = json.loads(raw)
            document["stages"][-1]["result"]["payload"]["quality"]["status"] = "failed"
            connection.execute(
                "UPDATE tasks SET document=? WHERE task_id=?", (json.dumps(document), task_id)
            )
        with self.assertRaisesRegex(ValueError, "boj_stored_result_mismatch"):
            export_task(self.settings, task_id, "data/exports/quality.csv")

    def test_export_refuses_overwrite_traversal_symlink_and_incomplete_tasks(self):
        task_id = self._collect("boj")
        output = self.root / "data/exports/result.csv"
        output.parent.mkdir(parents=True)
        output.write_text("keep")
        with self.assertRaisesRegex(ValueError, "output_already_exists"):
            export_task(self.settings, task_id, "data/exports/result.csv")
        with self.assertRaisesRegex(ValueError, "output_path_invalid"):
            export_task(self.settings, task_id, "data/exports/../escape.csv")
        output.unlink()
        Path(f"{output}.provenance.json").write_text("keep")
        with self.assertRaisesRegex(ValueError, "output_already_exists"):
            export_task(self.settings, task_id, "data/exports/result.csv")
        Path(f"{output}.provenance.json").unlink()
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / "data/exports/nested").symlink_to(outside, target_is_directory=True)
        except OSError:
            pass  # Symlink creation may require elevated privileges on Windows.
        else:
            with self.assertRaisesRegex(ValueError, "output_symlink"):
                export_task(self.settings, task_id, "data/exports/nested/result.csv")
        with self.assertRaisesRegex(ValueError, "unknown_task"):
            export_task(self.settings, "missing-task", "data/exports/missing.csv")

    def test_incomplete_task_is_refused(self):
        task_id = Orchestrator(HistoryStore(self.settings), {}).create("not planned").task_id
        with self.assertRaisesRegex(ValueError, "task_not_completed"):
            export_task(self.settings, task_id, "data/exports/incomplete.csv")

    def test_output_is_gitignored(self):
        ignore = (Path(__file__).parents[1] / ".gitignore").read_text()
        self.assertIn("data/exports/", ignore)


if __name__ == "__main__":
    unittest.main()
