"""BOJ FXERD01 contract, archival and durable task tests."""
import json
import tempfile
import unittest
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from freshness_support import HISTORICAL_FIXTURE_POLICY

from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import (
    DATA_ENDPOINT,
    FREQUENCY,
    METADATA_ENDPOINT,
    SERIES_CODE,
    SERIES_NAME,
    UNIT,
    BOJQuery,
    BOJRangeQuery,
    parse_boj_metadata,
    parse_boj_observations,
    parse_boj_range_observations,
)
from macro_data_platform.connectors.statistical_http import ApiDownload, SourceFailure
from macro_data_platform.contracts import ErrorCode, EvidenceKind, StageStatus
from macro_data_platform.ingestion.boj import (
    build_boj_plan,
    build_boj_range_plan,
)
from macro_data_platform.ingestion.boj import (
    make_boj_orchestrator as _make_boj_orchestrator,
)
from macro_data_platform.ingestion.boj import (
    make_boj_range_orchestrator as _make_boj_range_orchestrator,
)
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)
QUERY = BOJQuery("202609")
RANGE_QUERY = BOJRangeQuery("202609", "202610")
make_boj_orchestrator = partial(
    _make_boj_orchestrator, clock=lambda: NOW,
    freshness_policy=HISTORICAL_FIXTURE_POLICY,
)
make_boj_range_orchestrator = partial(
    _make_boj_range_orchestrator, clock=lambda: NOW,
    freshness_policy=HISTORICAL_FIXTURE_POLICY,
)


def api_download(endpoint, document, *, retrieved_at=NOW):
    return ApiDownload(endpoint, json.dumps(document, allow_nan=False).encode(), 200,
                       retrieved_at, "application/json", EvidenceKind.FIXTURE)


def metadata_document(*, request_date="20261026"):
    return {
        "STATUS": 200, "DB": "FM08", "DATE": request_date,
        "RESULTSET": [{
            "SERIES_CODE": SERIES_CODE, "NAME_OF_TIME_SERIES": SERIES_NAME,
            "UNIT": UNIT, "FREQUENCY": FREQUENCY,
            "CATEGORY": "Foreign Exchange Rates", "START_OF_THE_TIME_SERIES": "19990101",
            "END_OF_THE_TIME_SERIES": "20261022", "LAST_UPDATE": "20261026",
        }],
    }


def observations_document(values=(159.77, None), *, request_date="20261026"):
    return {
        "STATUS": 200, "DATE": request_date, "NEXTPOSITION": None,
        "RESULTSET": [{
            "SERIES_CODE": SERIES_CODE, "NAME_OF_TIME_SERIES": SERIES_NAME,
            "UNIT": UNIT, "FREQUENCY": FREQUENCY, "LAST_UPDATE": 20261026,
            "VALUES": {"SURVEY_DATES": [20260901, 20260902], "VALUES": list(values)},
        }],
    }


def range_observations_document():
    document = observations_document((159.77, None, 150.25))
    document["RESULTSET"][0]["VALUES"]["SURVEY_DATES"] = [
        20260901, 20260902, 20261001,
    ]
    return document


class FixtureTransport:
    def __init__(self, data_outcomes=None, *, observation_body=None, metadata_body=None):
        self.data_outcomes = list(data_outcomes or [])
        self.observation_body = observation_body or observations_document()
        self.metadata_body = metadata_body or metadata_document()
        self.metadata_calls = 0
        self.observation_calls = 0

    def fetch_metadata(self, query):
        self.metadata_calls += 1
        return api_download(METADATA_ENDPOINT, self.metadata_body)

    def fetch_observations(self, query):
        self.observation_calls += 1
        if self.data_outcomes:
            outcome = self.data_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return api_download(DATA_ENDPOINT, self.observation_body)


class BOJQueryTests(unittest.TestCase):
    def test_query_is_fixed_to_verified_series_and_one_valid_month(self):
        self.assertIn("code=FXERD01", QUERY.data_url)
        self.assertIn("startDate=202609", QUERY.data_url)
        for values in [
            {"month": "202613"}, {"month": "20260"},
            {"month": "202609", "series_code": "OTHER"},
            {"month": "202609", "database": "FM09"},
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                BOJQuery(**values)


class BOJRangeQueryTests(unittest.TestCase):
    def test_range_query_is_fixed_to_one_verified_series_and_bounds_twelve_months(self):
        self.assertIn("code=FXERD01", RANGE_QUERY.data_url)
        self.assertIn("startDate=202609", RANGE_QUERY.data_url)
        self.assertIn("endDate=202610", RANGE_QUERY.data_url)
        for start, end in [
            ("202613", "202701"), ("202610", "202609"),
            ("202501", "202601"), ("20260", "202609"),
        ]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                BOJRangeQuery(start, end)

    def test_range_parser_preserves_rows_and_checks_requested_calendar_span(self):
        metadata = parse_boj_metadata(api_download(METADATA_ENDPOINT, metadata_document()),
                                      RANGE_QUERY.metadata_query)
        parsed = parse_boj_range_observations(
            api_download(DATA_ENDPOINT, range_observations_document()), RANGE_QUERY, metadata,
        )
        self.assertEqual([row["date"] for row in parsed["observations"]], [
            "2026-09-01", "2026-09-02", "2026-10-01",
        ])
        self.assertEqual([row["value"] for row in parsed["observations"]], [159.77, None, 150.25])
        self.assertEqual(parsed["period_start"], "2026-09-01")
        self.assertEqual(parsed["period_end"], "2026-10-31")
        self.assertEqual(parsed["quality"]["missing_value_count"], 1)

    def test_range_parser_rejects_out_of_range_duplicate_and_out_of_order_dates(self):
        metadata = parse_boj_metadata(api_download(METADATA_ENDPOINT, metadata_document()),
                                      RANGE_QUERY.metadata_query)
        for dates in ([20260901, 20261101], [20260901, 20260901],
                      [20261001, 20260901]):
            document = range_observations_document()
            document["RESULTSET"][0]["VALUES"]["SURVEY_DATES"] = list(dates)
            document["RESULTSET"][0]["VALUES"]["VALUES"] = [1.0] * len(dates)
            with self.subTest(dates=dates), self.assertRaises(SourceFailure):
                parse_boj_range_observations(
                    api_download(DATA_ENDPOINT, document), RANGE_QUERY, metadata,
                )

    def test_range_plan_uses_shared_registry_and_preserves_exact_month_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            transport = FixtureTransport(observation_body=range_observations_document())
            runner = make_boj_range_orchestrator(store, settings, transport)
            task = runner.create("BOJ FXERD01 two-month fixture")
            runner.plan(task.task_id, build_boj_range_plan(RANGE_QUERY))
            result = runner.run(task.task_id)
            self.assertEqual(result["status"], "COMPLETED")
            payload = result["stages"][-1]["result"]["payload"]
            self.assertEqual(len(payload["observations"]), 3)
            self.assertEqual(transport.observation_calls, 1)
            manifest = json.loads(Path(directory, payload["manifest_path"]).read_text())
            self.assertEqual(manifest["request"]["start_month"], "202609")
            self.assertEqual(manifest["request"]["end_month"], "202610")

    def test_metadata_and_observations_preserve_null_and_source_metadata(self):
        metadata = parse_boj_metadata(api_download(METADATA_ENDPOINT, metadata_document()), QUERY)
        parsed = parse_boj_observations(
            api_download(DATA_ENDPOINT, observations_document()), QUERY, metadata,
        )
        self.assertEqual(metadata["unit"], UNIT)
        self.assertEqual(metadata["frequency"], FREQUENCY)
        self.assertEqual(parsed["observations"], [
            {"date": "2026-09-01", "value": 159.77},
            {"date": "2026-09-02", "value": None},
        ])
        self.assertEqual(parsed["quality"]["missing_value_count"], 1)
        self.assertEqual(parsed["quality"]["not_checked"], [
            "economic_outliers", "revision_history", "cross_source_equivalence",
        ])

    def test_schema_mismatch_is_reviewed(self):
        metadata = parse_boj_metadata(api_download(METADATA_ENDPOINT, metadata_document()), QUERY)
        bad = observations_document()
        bad["RESULTSET"][0]["VALUES"]["SURVEY_DATES"][1] = 20261001
        with self.assertRaises(SourceFailure):
            parse_boj_observations(api_download(DATA_ENDPOINT, bad), QUERY, metadata)
        bad = observations_document()
        bad["RESULTSET"][0]["VALUES"]["VALUES"][0] = float("nan")
        with self.assertRaises(ValueError):
            api_download(DATA_ENDPOINT, bad)


class BOJOrchestrationTests(unittest.TestCase):
    def test_one_request_per_stage_and_write_once_raw_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            transport = FixtureTransport()
            runner = make_boj_orchestrator(store, settings, transport)
            task = runner.create("confirmed BOJ FXERD01 request")
            runner.plan(task.task_id, build_boj_plan(QUERY))
            result = runner.run(task.task_id)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual((transport.metadata_calls, transport.observation_calls), (1, 1))
            outputs = result["stages"][-1]["result"]["payload"]
            self.assertEqual(outputs["quality"]["status"], "passed")
            raw = Path(directory, outputs["raw_path"])
            manifest = json.loads(Path(directory, outputs["manifest_path"]).read_text())
            self.assertTrue(raw.is_file())
            self.assertEqual(manifest["request"]["month"], "202609")
            self.assertNotIn("DATE=", manifest["source_url"])

    def test_transient_data_failure_resumes_same_task_and_reuses_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            transport = FixtureTransport(data_outcomes=[
                SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                              "temporary", 503),
                api_download(DATA_ENDPOINT, observations_document()),
            ])
            runner = make_boj_orchestrator(store, settings, transport)
            task = runner.create("confirmed BOJ FXERD01 request")
            runner.plan(task.task_id, build_boj_plan(QUERY))
            first = runner.run(task.task_id)
            self.assertEqual(first["status"], "PARTIAL")
            failed_id = first["task_id"]
            resumed = runner.resume(failed_id)
            self.assertEqual(resumed["status"], "COMPLETED")
            self.assertEqual(resumed["task_id"], failed_id)
            self.assertEqual(transport.metadata_calls, 1)
            self.assertEqual(transport.observation_calls, 2)
            self.assertIn("STAGE_REUSED", [event["kind"] for event in store.events(failed_id)])
            self.assertEqual(len(resumed["attempts"]), 2)

    def test_changed_data_is_archived_but_no_observations_are_published(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            first_transport = FixtureTransport()
            first_runner = make_boj_orchestrator(store, settings, first_transport)
            first = first_runner.create("first BOJ capture")
            first_runner.plan(first.task_id, build_boj_plan(QUERY))
            self.assertEqual(first_runner.run(first.task_id)["status"], "COMPLETED")

            changed_transport = FixtureTransport(observation_body=observations_document((160.01, None)))
            changed_runner = make_boj_orchestrator(store, settings, changed_transport)
            changed = changed_runner.create("changed BOJ capture")
            changed_runner.plan(changed.task_id, build_boj_plan(QUERY))
            result = changed_runner.run(changed.task_id)
            self.assertEqual(result["status"], "NEEDS_REVIEW")
            payload = result["stages"][-1]["result"]["payload"]
            self.assertEqual(payload["source_change_status"], "changed")
            self.assertNotIn("observations", payload)
            self.assertTrue(Path(directory, payload["raw_path"]).is_file())
            self.assertTrue(Path(directory, payload["manifest_path"]).is_file())

    def test_dynamic_response_date_does_not_create_a_false_source_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            first_runner = make_boj_orchestrator(
                store, settings, FixtureTransport(
                    metadata_body=metadata_document(request_date="20261026"),
                    observation_body=observations_document(request_date="20261026"),
                ),
            )
            first = first_runner.create("first BOJ capture")
            first_runner.plan(first.task_id, build_boj_plan(QUERY))
            self.assertEqual(first_runner.run(first.task_id)["status"], "COMPLETED")

            second_runner = make_boj_orchestrator(
                store, settings, FixtureTransport(
                    metadata_body=metadata_document(request_date="20261027"),
                    observation_body=observations_document(request_date="20261027"),
                ),
            )
            second = second_runner.create("second BOJ capture")
            second_runner.plan(second.task_id, build_boj_plan(QUERY))
            result = second_runner.run(second.task_id)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["stages"][-1]["result"]["payload"]["source_change_status"],
                             "unchanged")


if __name__ == "__main__":
    unittest.main()
