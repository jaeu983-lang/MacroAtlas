"""Structured CLI tests use only fixture transports unless a live flag is explicit."""
import io
import json
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from freshness_support import HISTORICAL_FIXTURE_POLICY

from macro_data_platform.cli import _worldbank_task, build_parser, dispatch, main
from macro_data_platform.config import Settings
from macro_data_platform.connectors.boj import DATA_ENDPOINT, METADATA_ENDPOINT
from macro_data_platform.connectors.official_files import PROFILES, OfficialFileDownload
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.connectors.worldbank import Download
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.orchestration import Orchestrator
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def boj_download(endpoint, body):
    return ApiDownload(endpoint, json.dumps(body, allow_nan=False).encode(), 200, NOW,
                       "application/json", EvidenceKind.FIXTURE)


def metadata_body():
    return {"STATUS": 200, "DB": "FM08", "DATE": "20261026", "RESULTSET": [{
        "SERIES_CODE": "FXERD01",
        "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
        "UNIT": "Yen per U.S. Dollar", "FREQUENCY": "DAILY",
        "CATEGORY": "Foreign Exchange Rates", "LAST_UPDATE": "20261026",
    }]}


def data_body():
    return {"STATUS": 200, "DATE": "20261026", "NEXTPOSITION": None, "RESULTSET": [{
        "SERIES_CODE": "FXERD01",
        "NAME_OF_TIME_SERIES": "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market",
        "UNIT": "Yen per U.S. Dollar", "FREQUENCY": "DAILY", "LAST_UPDATE": 20261026,
        "VALUES": {"SURVEY_DATES": [20260901], "VALUES": [159.77]},
    }]}


class BOJFixture:
    def fetch_metadata(self, query):
        return boj_download(METADATA_ENDPOINT, metadata_body())

    def fetch_observations(self, query):
        return boj_download(DATA_ENDPOINT, data_body())


class FileFixture:
    def fetch(self, source_id):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("WS_GLI_csv_col.csv", "period,value\n2026Q1,1\n")
        return OfficialFileDownload(source_id, PROFILES[source_id]["url"], content.getvalue(),
                                    200, NOW, "application/zip", None)


class WorldBankFixture:
    def fetch(self, query):
        body = Path(__file__).parent / "fixtures" / "worldbank_gdp.json"
        return Download(query.url, body.read_bytes(), 200, NOW, "application/json",
                        EvidenceKind.FIXTURE)


class WorldBankSeriesFixture:
    def fetch(self, query):
        body = [{"page": 1, "pages": 1, "per_page": 100, "total": 1,
                 "sourceid": query.source_id, "lastupdated": "2026-10-08"},
                [{"indicator": {"id": query.indicator_id, "value": "Fixture series"},
                  "country": {"id": query.country_iso3, "value": "Fixture country"},
                  "countryiso3code": query.country_iso3, "date": str(query.end_year),
                  "value": 12.5, "unit": "", "obs_status": "", "decimal": 1}]]
        return Download(query.url, json.dumps(body).encode(), 200, NOW, "application/json",
                        EvidenceKind.FIXTURE)


class BLSFixture:
    def fetch(self, query):
        body = {"status": "REQUEST_SUCCEEDED", "messageCodes": [], "Results": {"series": [
            {"seriesID": series_id, "data": [{
                "year": str(query.end_year), "period": "M09", "value": "1.2",
            }]} for series_id in query.series_ids
        ]}}
        return ApiDownload(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            json.dumps(body).encode(), 200, NOW, "application/json", EvidenceKind.FIXTURE,
        )


class CensusFixture:
    def fetch(self, query):
        geography = query.geography.split(":", 1)[0]
        body = [list(query.variables) + [geography],
                ["United States" if query.geography == "us:1" else "California"
                 for _ in query.variables] + [query.geography.split(":", 1)[1]]]
        endpoint = f"https://api.census.gov/data/{query.year}/{query.dataset}"
        return ApiDownload(endpoint, json.dumps(body).encode(), 200, NOW,
                           "application/json", EvidenceKind.FIXTURE)


class StructuredCLITests(unittest.TestCase):
    def test_boj_cli_runs_fixed_scoped_request_and_prints_task_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "collect", "boj-fxer", "--month", "202609", "--live",
            ])
            status, result = dispatch(
                args, boj_transport=BOJFixture(),
                freshness_policy=HISTORICAL_FIXTURE_POLICY,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["observation_count"], 1)
            self.assertEqual(len(result["stages"]), 2)

    def test_worldbank_task_is_an_explicit_confirmed_fixed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
            settings = Settings(root)
            store = HistoryStore(settings)
            task_id = _worldbank_task(store, settings, 2020, 2022)
            task = store.get(task_id)
            self.assertEqual(task["workflow_context"]["confirmation"]["confirmation_method"],
                             "explicit_request")
            candidate = task["workflow_context"]["confirmation"]["offer"]["proposal"][
                "proposal"]["candidates"][0]
            self.assertEqual(candidate["series_key"]["indicator"], "NY.GDP.MKTP.CD")

    def test_worldbank_cli_executes_the_confirmed_workflow_with_fixture_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "collect", "worldbank-gdp",
                "--start-year", "2020", "--end-year", "2022", "--live",
            ])
            status, result = dispatch(
                args, worldbank_transport=WorldBankFixture(),
                freshness_policy=HISTORICAL_FIXTURE_POLICY,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual([stage["status"] for stage in result["stages"]],
                             ["SUCCEEDED", "SUCCEEDED"])

    def test_worldbank_series_cli_runs_explicit_selection_through_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "collect", "worldbank-series",
                "--country", "CAN", "--indicator", "SP.POP.TOTL", "--source-id", "2",
                "--start-year", "2025", "--end-year", "2025", "--live",
            ])
            status, result = dispatch(
                args, worldbank_transport=WorldBankSeriesFixture(), clock=lambda: NOW,
                freshness_policy=HISTORICAL_FIXTURE_POLICY,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["source_id"], "2")
            self.assertEqual(result["country"], "CAN")
            self.assertEqual(result["indicator_id"], "SP.POP.TOTL")
            self.assertEqual(result["observation_count"], 1)
            self.assertTrue(result["raw_path"].startswith("data/raw/worldbank/"))

    def test_bls_cli_runs_selected_series_through_shared_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "collect", "bls",
                "--series-id", "CUUR0000SA0", "--series-id", "CUUR0000SA1",
                "--start-year", "2026", "--end-year", "2026", "--live",
            ])
            status, result = dispatch(
                args, bls_transport=BLSFixture(), clock=lambda: NOW,
                freshness_policy=HISTORICAL_FIXTURE_POLICY,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["series_ids"], ["CUUR0000SA0", "CUUR0000SA1"])
            self.assertEqual(result["series_count"], 2)
            self.assertEqual(result["observation_count"], 2)

    def test_census_cli_runs_selected_acs_query_through_shared_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "collect", "census", "--year", "2024",
                "--dataset", "acs/acs1", "--variable", "NAME", "--variable", "B01001_001E",
                "--geography", "state:06", "--live",
            ])
            status, result = dispatch(
                args, census_transport=CensusFixture(), clock=lambda: NOW,
                freshness_policy=HISTORICAL_FIXTURE_POLICY,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["dataset"], "acs/acs1")
            self.assertEqual(result["geography"], "state:06")
            self.assertEqual(result["observation_count"], 1)

    def test_local_search_cli_uses_verified_catalog_without_network_and_preserves_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "search", "GDP USA",
                "--institution", "worldbank", "--country", "USA",
                "--period-start", "2020", "--period-end", "2022",
            ])
            with (patch("macro_data_platform.connectors.bls.request_json") as bls_request,
                  patch("macro_data_platform.connectors.census.request_json") as census_request):
                status, result = dispatch(args, clock=lambda: NOW)
            bls_request.assert_not_called()
            census_request.assert_not_called()
            self.assertEqual(status, 0)
            self.assertEqual(result["search_status"], "candidates_found")
            self.assertTrue(result["selection_requires_explicit_confirmation"])
            self.assertEqual(result["candidates"][0]["candidate"]["candidate_id"],
                             "worldbank:2:USA:NY.GDP.MKTP.CD")
            self.assertEqual(result["candidates"][0]["match_status"], "review_required")

            status_args = build_parser().parse_args([
                "--project-root", directory, "status", result["task_id"],
            ])
            status_code, saved = dispatch(status_args)
            self.assertEqual(status_code, 0)
            self.assertEqual(saved["search_status"], "candidates_found")
            self.assertEqual(saved["candidates"], result["candidates"])

    def test_bls_and_census_collect_require_explicit_live_flag(self):
        commands = [
            ["collect", "bls", "--series-id", "CUUR0000SA0",
             "--start-year", "2024", "--end-year", "2024"],
            ["collect", "census", "--year", "2024", "--dataset", "acs/acs1",
             "--variable", "NAME", "--geography", "us:1"],
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(SystemExit) as caught:
                build_parser().parse_args(command)
            self.assertEqual(caught.exception.code, 2)

    def test_search_cli_rejects_oversized_query_and_result_limit(self):
        for command in (["search", "x" * 501], ["search", "GDP", "--limit", "51"]):
            with self.subTest(command=command), self.assertRaises(SystemExit) as caught:
                build_parser().parse_args(command)
            self.assertEqual(caught.exception.code, 2)

    def test_status_command_is_local_and_does_not_make_network_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            settings = Settings(Path(directory))
            store = HistoryStore(settings)
            task_id = Orchestrator(store, {}).create("local status fixture").task_id
            task = store.get(task_id)
            args = build_parser().parse_args([
                "--project-root", directory, "status", task["task_id"],
            ])
            status, result = dispatch(args)
            self.assertEqual(status, 0)
            self.assertEqual(result["task_id"], task["task_id"])
            self.assertEqual(result["status"], "CREATED")

    def test_gate_c_watch_cli_uses_the_fixed_source_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project]\nname='fixture'\n")
            args = build_parser().parse_args([
                "--project-root", directory, "watch", "bis", "--live",
            ])
            status, result = dispatch(args, file_transport=FileFixture())
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["watch_source_id"], "bis")
            self.assertEqual(result["source_change_status"], "first_observation")

    def test_live_request_requires_explicit_flag(self):
        with self.assertRaises(SystemExit) as caught:
            main(["collect", "boj-fxer", "--month", "202609"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
