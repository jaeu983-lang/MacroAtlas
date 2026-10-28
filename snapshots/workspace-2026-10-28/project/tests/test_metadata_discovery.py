"""Iteration 07: source preservation and explicit normalization, entirely offline."""
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.institution_sites import (
    InstitutionCandidate,
    OfficialDomainEvidence,
)
from macro_data_platform.metadata.adapters import read_metadata
from macro_data_platform.metadata.models import MetadataDocument
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.metadata import MetadataStore

AT = datetime(2026, 10, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "metadata"


def institution(identifier="worldbank", host="datahelpdesk.worldbank.org"):
    return InstitutionCandidate(identifier, identifier, "test",
                                (OfficialDomainEvidence(host, f"https://{host}/docs", AT),))


def document(file="catalogue.json", *, identifier="worldbank",
             host="datahelpdesk.worldbank.org", kind="api_catalogue"):
    return MetadataDocument(identifier, identifier, f"https://{host}/docs", AT,
                            EvidenceKind.FIXTURE, "fixture:" + file, kind,
                            (FIXTURES / file).read_bytes(), "fixture-v1")


def json_document(data, **kwargs):
    return replace(document(**kwargs), body=json.dumps(data).encode())


def test_sdmx_references_codes_and_multilingual_labels_without_inventing_series():
    doc = document("imf_structure.xml", identifier="imf", host="data.imf.org",
                   kind="sdmx_structure")
    result = read_metadata(doc, institution("imf", "data.imf.org"))
    assert result.records == () and result.warnings == ()
    structures = result.structures()
    assert structures["dataflows"][0]["structure_ref"]["id"] == "TEST_DSD"
    assert structures["codelists"][0]["codes"]["Q"]["ko"] == "분기"
    assert structures["datastructures"][0]["dimensions"][0]["id"] == "FREQ"


def test_sdmx_missing_references_are_unknown_not_guessed():
    doc = document("imf_structure.xml", identifier="imf", host="data.imf.org",
                   kind="sdmx_structure")
    doc = replace(doc, body=doc.body.replace(b'id="TEST_FREQ" version="1.0" class',
                                            b'id="MISSING" version="1.0" class'))
    result = read_metadata(doc, institution("imf", "data.imf.org"))
    assert result.warnings == ("unresolved_codelist:FREQ",)
    assert result.records == ()


@pytest.mark.parametrize("body", [b'<!DOCTYPE x [<!ENTITY a "x">]><x/>',
                                b'<!ENTITY a "x"><x/>'])
def test_sdmx_forbids_entity_documents(body):
    doc = replace(document(), kind="sdmx_structure", body=body)
    with pytest.raises(ValueError, match="forbidden"):
        read_metadata(doc, institution())


def test_missing_units_and_frequency_stay_unknown_source_is_preserved(tmp_path):
    doc = document()
    settings = Settings(tmp_path)
    HistoryStore(settings)
    store = MetadataStore(settings)
    result = store.ingest(doc, institution(), language="ko")
    record = result.records[0]
    assert record.candidate.unit is None and record.candidate.frequency is None
    assert record.attributes.seasonal_adjustment is None
    assert record.candidate.label == "국내총생산"
    assert record.candidate.series_id is None
    assert record.candidate.series_key["indicator"] == "NY.GDP.MKTP.CD"
    assert record.candidate.support_status == "unknown"
    assert record.candidate.evidence[0].kind is EvidenceKind.FIXTURE
    restored_doc, restored_result = MetadataStore(settings).get(doc.document_id)
    assert restored_doc.body == doc.body
    assert restored_result.records == result.records
    assert store.current_records() == result.records
    assert store.ingest(doc, institution(), language="ko") == result
    with sqlite3.connect(settings.database_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM metadata_documents")


def test_codebook_keeps_sheet_codes_variants_and_source_cell():
    doc = document("tic_codebook.json", identifier="tic", host="home.treasury.gov",
                   kind="sheet_codebook")
    result = read_metadata(doc, institution("tic", "home.treasury.gov"))
    record = result.records[0]
    assert record.candidate.unit == "billion USD"
    assert record.candidate.frequency == "monthly"
    assert record.attributes.source_codes["unit"] == "BUSD"
    assert record.attributes.stock_flow == "stock"
    assert record.source_fields["definition"].endswith("/Notes")
    assert record.scope == "foreign_holders"


def test_unknown_and_conflicting_codes_do_not_turn_into_normalized_facts():
    data = json.loads(document().body)
    row = data["datasets"][0]["series"][0]
    row.update(unit="EUR", unit_code="USD", frequency_code="UNRECOGNIZED")
    record = read_metadata(json_document(data), institution()).records[0]
    assert record.candidate.unit is None and record.candidate.frequency is None
    assert "conflict:unit" in record.candidate.uncertainties
    assert "unknown_code:frequency:UNRECOGNIZED" in record.candidate.uncertainties
    assert record.attributes.source_codes["unit"] == "USD"


def test_explicit_scope_relations_keep_axis_version_inclusions_and_exclusions():
    data = json.loads(document().body)
    data["datasets"][0]["series"][0].update(scope="public_sector", scope_relations=[{
        "target":"central_bank", "relation":"broader", "axis":"institutional_sector",
        "version":"fixture-v1", "includes":["central_bank"], "excludes":["private_banks"],
    }])
    record = read_metadata(json_document(data), institution()).records[0]
    relation = record.scope_relations[0]
    assert relation.relation == "broader"
    assert relation.version == "fixture-v1"
    assert relation.excludes == ("private_banks",)
    assert relation.evidence_path.endswith("/scope_relations/0")


def test_metadata_updates_replace_current_index_without_overwriting_raw(tmp_path):
    store = MetadataStore(Settings(tmp_path))
    old = document()
    store.ingest(old, institution())
    new_data = json.loads(old.body)
    new_data["datasets"][0]["series"][0]["definition"] = "revised fixture definition"
    updated = replace(json_document(new_data), retrieved_at=AT + timedelta(days=1))
    store.ingest(updated, institution())
    assert store.current_records()[0].candidate.definition == "revised fixture definition"
    assert store.get(old.document_id)[0].body == old.body
    assert store.get(updated.document_id)[0].body == updated.body


def test_duplicate_series_and_external_source_are_rejected():
    data = json.loads(document().body)
    data["datasets"][0]["series"] *= 2
    with pytest.raises(ValueError, match="duplicate source series"):
        read_metadata(json_document(data), institution())
    with pytest.raises(ValueError, match="outside"):
        read_metadata(replace(document(), source_url="https://example.org/docs"), institution())


@pytest.mark.parametrize("column", ["original_body", "result"])
def test_corrupt_original_or_normalized_metadata_is_not_reused(tmp_path, column):
    settings = Settings(tmp_path)
    store = MetadataStore(settings)
    doc = document()
    store.ingest(doc, institution())
    replacement = b"corrupt raw" if column == "original_body" else json.dumps({
        "document_id": doc.document_id, "fingerprint": "0" * 64,
    })
    with sqlite3.connect(settings.database_path) as db:
        db.execute("DROP TRIGGER metadata_documents_no_update")
        db.execute(f"UPDATE metadata_documents SET {column}=?", (replacement,))
    with pytest.raises(ValueError, match="hash"):
        store.get(doc.document_id)
