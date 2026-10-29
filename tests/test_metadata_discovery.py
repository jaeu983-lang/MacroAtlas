"""Iteration 07 metadata adapters, normalization, preservation, and safety tests."""
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from macro_data_platform.config import Settings
from macro_data_platform.connectors.metadata import fetch_bls_catalog, fetch_census_variable
from macro_data_platform.connectors.statistical_http import ApiDownload
from macro_data_platform.contracts import EvidenceKind, StageStatus
from macro_data_platform.ingestion.metadata import (
    BLSMetadataEngine,
    CensusVariableMetadataEngine,
    CodebookMetadataEngine,
    SDMXMetadataEngine,
)
from macro_data_platform.metadata.normalize import (
    NORMALIZED_FIELDS,
    normalize_bls_catalog,
    normalize_census_variable,
    normalize_codebook_rows,
)
from macro_data_platform.metadata.sdmx import parse_sdmx_structure_xml
from macro_data_platform.orchestration.models import StageInput, StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CENSUS_URL = "https://api.census.gov/data/2022/acs/acs1/variables/B01001_001E.json"


def api_download(url, payload, kind=EvidenceKind.FIXTURE, content_type="application/json"):
    return ApiDownload(url, json.dumps(payload).encode(), 200, NOW, content_type, kind)


def bls_payload():
    return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{
        "seriesID": "CUUR0000SA0", "catalog": {
            "series_title": "All items in U.S. city average",
            "seasonality": "Not Seasonally Adjusted", "area": "U.S. city average",
            "item": "All items", "measure_data_type": "All items",
            "survey_abbreviation": "CU", "survey_name": "CPI-U",
        },
    }]}}


class NormalizationTests(unittest.TestCase):
    def test_bls_catalog_uses_only_exposed_fields(self):
        record = normalize_bls_catalog(
            bls_payload(), source_url=BLS_URL, retrieved_at=NOW.isoformat(), raw_path="raw.json",
            start_year=2024, end_year=2024, expected_series_id="CUUR0000SA0",
            series_index=2,
        )
        self.assertEqual(record["fields"]["name"]["value"], "All items in U.S. city average")
        self.assertEqual(record["fields"]["geo_coverage"]["value"], "U.S. city average")
        self.assertEqual(record["fields"]["seasonal_adjustment"]["value"],
                         "Not Seasonally Adjusted")
        for name in ("definition", "unit", "frequency", "time_coverage"):
            self.assertEqual(record["fields"][name]["state"], "unknown")
        self.assertEqual(record["identifier"]["value"], "CUUR0000SA0")
        self.assertEqual(record["raw_ref"]["json_pointer"], "/Results/series/2")
        self.assertEqual(record["fields"]["name"]["source_refs"],
                         ["/Results/series/2/catalog/series_title"])

    def test_census_variable_keeps_label_and_attributes_without_inference(self):
        payload = {"name": "B01001_001E", "label": "Estimate!!Total:",
                   "concept": "Sex by Age", "predicateType": "int", "group": None,
                   "limit": 0, "predicateOnly": True}
        record = normalize_census_variable(
            payload, source_url=CENSUS_URL, retrieved_at=NOW.isoformat(), raw_path="raw.json",
            dataset_id="acs/acs1", reference_year=2022, expected_variable_id="B01001_001E",
        )
        self.assertEqual(record["fields"]["name"]["value"], "Estimate!!Total:")
        self.assertEqual(record["source_attributes"]["concept"], "Sex by Age")
        for name in NORMALIZED_FIELDS[1:]:
            self.assertEqual(record["fields"][name]["state"], "unknown", name)

    def test_codebook_supports_languages_missing_fields_and_conflicting_aliases(self):
        rows = [
            {"code": "A", "name_en": "Total", "name_fr": "Totalité", "unit_a": "USD",
             "unit_b": "persons"},
            {"code": "B", "name_en": "Change", "name_fr": None, "unit_a": None,
             "unit_b": None},
        ]
        records = normalize_codebook_rows(
            rows, columns={"identifier": "code", "name": {"en": "name_en", "fr": "name_fr"},
                           "unit": ["unit_a", "unit_b"]},
            source_agency="Example Statistics", source_url="https://stats.example/codebook",
            retrieved_at=NOW.isoformat(), raw_path="raw.json",
        )
        self.assertEqual(records[0]["fields"]["name"]["value"], {"en": "Total", "fr": "Totalité"})
        self.assertEqual(records[0]["fields"]["unit"]["state"], "conflict")
        self.assertEqual(records[1]["fields"]["unit"]["state"], "unknown")
        self.assertEqual(records[1]["fields"]["definition"]["state"], "unknown")

    def test_duplicate_identifiers_with_disagreeing_known_values_become_conflicts(self):
        records = normalize_codebook_rows(
            [{"code": "X", "label": "First"}, {"code": "X", "label": "Second"}],
            columns={"identifier": "code", "name": "label"},
            source_agency="Example", source_url="https://stats.example/table",
            retrieved_at=NOW.isoformat(), raw_path="raw.json",
        )
        self.assertEqual([row["fields"]["name"]["state"] for row in records],
                         ["conflict", "conflict"])
        self.assertEqual(len(records[0]["fields"]["name"]["candidates"]), 2)

    def test_normalizers_require_credential_free_https_and_matching_ids(self):
        with self.assertRaises(ValueError):
            normalize_codebook_rows([], columns={"identifier": "id"}, source_agency="Example",
                                    source_url="https://stats.example/table?token=secret",
                                    retrieved_at=NOW.isoformat(), raw_path="raw.json")
        with self.assertRaises(ValueError):
            normalize_codebook_rows([], columns={"identifier": "id"}, source_agency="Example",
                                    source_url="https://stats.example/table",
                                    retrieved_at="2026-10-26T12:00:00", raw_path="raw.json")
        with self.assertRaises(ValueError):
            normalize_census_variable(
                {"name": "OTHER"}, source_url=CENSUS_URL, retrieved_at=NOW.isoformat(),
                raw_path="raw.json", dataset_id="acs/acs1", reference_year=2022,
                expected_variable_id="B01001_001E",
            )


class SDMXTests(unittest.TestCase):
    XML = b'''<?xml version="1.0" encoding="UTF-8"?>
    <mes:Structure xmlns:mes="urn:message" xmlns:str="urn:structure"
      xmlns:com="urn:common" xmlns:xml="http://www.w3.org/XML/1998/namespace">
      <mes:Structures>
        <str:Dataflows><str:Dataflow id="FLOW" agencyID="IMF" version="1.0">
          <com:Name xml:lang="en">National accounts</com:Name>
          <com:Name xml:lang="fr">Comptes nationaux</com:Name>
          <str:Structure><com:Ref id="DSD"/></str:Structure>
        </str:Dataflow></str:Dataflows>
        <str:DataStructures><str:DataStructure id="DSD" agencyID="IMF" version="1.0">
          <str:DataStructureComponents><str:DimensionList>
            <str:Dimension id="FREQ" position="1"><com:ConceptIdentity><com:Ref id="FREQ"/></com:ConceptIdentity>
              <com:Name xml:lang="en">Frequency</com:Name></str:Dimension>
          </str:DimensionList></str:DataStructureComponents>
        </str:DataStructure></str:DataStructures>
        <str:Codelists><str:Codelist id="CL_FREQ" agencyID="IMF" version="1.0">
          <com:Name xml:lang="en">Frequency codes</com:Name>
          <str:Code id="A"><com:Name xml:lang="en">Annual</com:Name>
            <com:Name xml:lang="fr">Annuel</com:Name></str:Code>
        </str:Codelist></str:Codelists>
      </mes:Structures>
    </mes:Structure>'''

    def test_extracts_dataflow_dsd_dimensions_and_multilingual_codelist(self):
        rows = parse_sdmx_structure_xml(
            self.XML, source_agency="International Monetary Fund",
            source_url="https://api.imf.org/sdmx/structure", retrieved_at=NOW,
            raw_path="raw.xml",
        )
        self.assertEqual([row["entity_type"] for row in rows],
                         ["dataflow", "datastructure", "codelist"])
        self.assertEqual(rows[0]["fields"]["name"]["value"]["fr"], "Comptes nationaux")
        self.assertEqual(rows[0]["source_attributes"]["structure_references"], ["DSD"])
        self.assertEqual(rows[1]["fields"]["dimensions"]["value"][0]["id"], "FREQ")
        self.assertEqual(rows[2]["source_attributes"]["codes"][0]["name"],
                         {"en": "Annual", "fr": "Annuel"})
        self.assertEqual(rows[1]["fields"]["unit"]["state"], "unknown")

    def test_rejects_entity_declarations_oversize_and_unsupported_messages(self):
        for value in (b"<!DOCTYPE x [<!ENTITY secret 'x'>]><x/>",
                      "<!DOCTYPE x [<!ENTITY secret 'x'>]><x/>".encode("utf-16"),
                      b" " * (2 * 1024 * 1024 + 1), b"<root/>"):
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                parse_sdmx_structure_xml(
                    value, source_agency="Example", source_url="https://stats.example/structure",
                    retrieved_at=NOW, raw_path="raw.xml",
                )


class MetadataArchiveTests(unittest.TestCase):
    def test_codebook_engine_separates_raw_normalized_and_manifest_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory))
            engine = CodebookMetadataEngine(settings)
            result = engine.run(StageInput("t", "request", "metadata", {
                "source_agency": "Example", "source_url": "https://stats.example/table",
                "rows": [{"code": "A", "label": "Total"}],
                "columns": {"identifier": "code", "name": "label"},
            }, None, ()))
            self.assertEqual(result.status, StageStatus.SUCCEEDED)
            raw = Path(directory, result.payload["raw_path"])
            normalized = Path(directory, result.payload["normalized_path"])
            manifest = json.loads(Path(directory, result.payload["manifest_path"]).read_text())
            self.assertNotEqual(raw.parent, normalized.parent)
            record = json.loads(normalized.read_text())[0]
            self.assertEqual(record["raw_ref"]["path"], result.payload["raw_path"])
            self.assertIn("sha256", manifest["raw"])
            self.assertEqual(manifest["normalized"]["record_count"], 1)

    def test_sdmx_engine_archives_source_xml_as_fixture_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory))
            result = SDMXMetadataEngine(settings).run(StageInput("t", "request", "sdmx", {
                "source_agency": "Example", "source_url": "https://stats.example/structure",
                "xml": "<Structure><Dataflow id='F'><Name>Flow</Name></Dataflow></Structure>",
            }, None, ()))
            self.assertEqual(result.status, StageStatus.SUCCEEDED)
            manifest = json.loads(Path(directory, result.payload["manifest_path"]).read_text())
            self.assertEqual(manifest["evidence_kind"], "fixture")
            self.assertTrue(result.payload["raw_path"].endswith("source.xml"))


class MetadataTransportTests(unittest.TestCase):
    def test_bls_key_is_only_in_post_body_and_returned_url_has_no_secret(self):
        with (patch("macro_data_platform.connectors.metadata.read_api_key", return_value="fake-key"),
              patch("macro_data_platform.connectors.metadata.request_json",
                    return_value=api_download(BLS_URL, {})) as send):
            result = fetch_bls_catalog("CUUR0000SA0", 2024, 2024)
        args, kwargs = send.call_args
        sent = json.loads(kwargs["body"])
        self.assertEqual(sent["registrationkey"], "fake-key")
        self.assertTrue(sent["catalog"])
        self.assertEqual(args[0], BLS_URL)
        self.assertEqual(result.source_url, BLS_URL)

    def test_census_key_is_removed_from_source_url(self):
        with (patch("macro_data_platform.connectors.metadata.read_api_key", return_value="fake-key"),
              patch("macro_data_platform.connectors.metadata.request_json",
                    return_value=api_download(CENSUS_URL, {})) as send):
            result = fetch_census_variable(2022, "acs/acs1", "B01001_001E")
        params = parse_qs(urlsplit(send.call_args.args[0]).query)
        self.assertEqual(params["key"], ["fake-key"])
        self.assertEqual(result.source_url, CENSUS_URL)
        self.assertNotIn("fake-key", result.source_url)

    def test_api_metadata_engines_require_network_setting_before_call(self):
        with tempfile.TemporaryDirectory() as directory:
            request_bls = StageInput("t", "request", "bls", {
                "series_id": "CUUR0000SA0", "start_year": 2024, "end_year": 2024,
            }, None, ())
            request_census = StageInput("t", "request", "census", {
                "year": 2022, "dataset": "acs/acs1", "variable_id": "B01001_001E",
            }, None, ())
            with patch("macro_data_platform.ingestion.metadata.fetch_bls_catalog") as bls:
                result = BLSMetadataEngine(Settings(Path(directory))).run(request_bls)
                self.assertEqual(result.status, StageStatus.NEEDS_REVIEW)
                bls.assert_not_called()
            with patch("macro_data_platform.ingestion.metadata.fetch_census_variable") as census:
                result = CensusVariableMetadataEngine(Settings(Path(directory))).run(request_census)
                self.assertEqual(result.status, StageStatus.NEEDS_REVIEW)
                census.assert_not_called()

    def test_bls_metadata_engine_runs_through_orchestrator_and_preserves_two_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            with patch("macro_data_platform.ingestion.metadata.fetch_bls_catalog",
                       return_value=api_download(BLS_URL, bls_payload())):
                runner = Orchestrator(HistoryStore(settings), {
                    ("bls_metadata", "1"): BLSMetadataEngine(settings),
                })
                task = runner.create("catalogue metadata")
                runner.plan(task.task_id, TaskPlan((StageSpec(
                    "catalogue", "bls_metadata", {
                        "series_id": "CUUR0000SA0", "start_year": 2024, "end_year": 2024,
                    },
                ),)))
                result = runner.run(task.task_id)
            self.assertEqual(result["status"], "COMPLETED")
            payload = result["stages"][0]["result"]["payload"]
            normalized = json.loads(Path(directory, payload["normalized_path"]).read_text())
            self.assertEqual(normalized[0]["fields"]["unit"]["state"], "unknown")
            self.assertTrue(Path(directory, payload["raw_path"]).is_file())

    def test_bls_schema_change_keeps_raw_response_without_claiming_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            with patch("macro_data_platform.ingestion.metadata.fetch_bls_catalog",
                       return_value=api_download(BLS_URL, {
                           "status": "REQUEST_SUCCEEDED", "Results": {"series": []},
                       })):
                result = BLSMetadataEngine(settings).run(StageInput("t", "request", "bls", {
                    "series_id": "CUUR0000SA0", "start_year": 2024, "end_year": 2024,
                }, None, ()))
            self.assertEqual(result.status, StageStatus.NEEDS_REVIEW)
            self.assertTrue(Path(directory, result.payload["raw_path"]).is_file())
            self.assertFalse(Path(directory, "data/processed/metadata/bls",
                                  result.payload["package_id"], "normalized.json").exists())


if __name__ == "__main__":
    unittest.main()
