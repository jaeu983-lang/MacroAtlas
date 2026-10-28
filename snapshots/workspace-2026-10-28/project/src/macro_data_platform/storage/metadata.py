"""Append-only raw metadata and a bounded index of the current normalized snapshots."""
import json
import sqlite3
from datetime import datetime

from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.metadata.adapters import read_metadata
from macro_data_platform.metadata.models import (
    MAX_RECORDS,
    MetadataDocument,
    MetadataRecord,
    MetadataResult,
    digest,
)
from macro_data_platform.orchestration.models import json_snapshot


class MetadataStore:
    def __init__(self, settings, *, initialize=True):
        self.settings = settings
        if not initialize:
            return
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(settings.database_path) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in {0, 2}:
                raise ValueError("unsupported history schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata_documents (
                    snapshot_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT UNIQUE NOT NULL, institution_id TEXT NOT NULL,
                    source_url TEXT NOT NULL, kind TEXT NOT NULL,
                    header TEXT NOT NULL, original_body BLOB NOT NULL, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS metadata_sources ON metadata_documents(
                    institution_id, source_url, kind, snapshot_no);
                CREATE TABLE IF NOT EXISTS metadata_records (
                    document_id TEXT NOT NULL, record_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL, concept_id TEXT,
                    payload TEXT NOT NULL, PRIMARY KEY(document_id, candidate_id));
                CREATE INDEX IF NOT EXISTS metadata_concepts ON metadata_records(concept_id);
                CREATE TRIGGER IF NOT EXISTS metadata_documents_no_update
                BEFORE UPDATE ON metadata_documents BEGIN
                    SELECT RAISE(ABORT, 'metadata is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_documents_no_delete
                BEFORE DELETE ON metadata_documents BEGIN
                    SELECT RAISE(ABORT, 'metadata is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_records_no_update
                BEFORE UPDATE ON metadata_records BEGIN
                    SELECT RAISE(ABORT, 'metadata is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_records_no_delete
                BEFORE DELETE ON metadata_records BEGIN
                    SELECT RAISE(ABORT, 'metadata is append-only'); END;
            """)

    def ingest(self, document, institution, *, language="en"):
        result = read_metadata(document, institution, language=language)
        for record in result.records:
            self.validate_structure(record)
        payload = {"document_id": result.document_id,
                   "records": [r.to_dict() for r in result.records],
                   "structures": result.structures(), "warnings": list(result.warnings)}
        payload["fingerprint"] = digest(payload)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        header = json.dumps(document.header(), sort_keys=True, ensure_ascii=False)
        with sqlite3.connect(self.settings.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO metadata_documents("
                       "document_id,institution_id,source_url,kind,header,original_body,result)"
                       " VALUES(?,?,?,?,?,?,?)",
                       (document.document_id, document.institution_id, document.source_url,
                        document.kind, header, document.body, encoded))
            row = db.execute("SELECT header,original_body,result FROM metadata_documents "
                             "WHERE document_id=?", (document.document_id,)).fetchone()
            if row != (header, document.body, encoded):
                raise ValueError("metadata identity collision or changed normalization policy")
            for record in result.records:
                data = record.to_dict()
                db.execute("INSERT OR IGNORE INTO metadata_records VALUES(?,?,?,?,?)", (
                    document.document_id, digest(data), record.candidate.candidate_id,
                    record.concept_id, json.dumps(data, sort_keys=True, ensure_ascii=False),
                ))
        return result

    def validate_structure(self, record):
        if record.structure_document_id is None:
            return
        original, result = self.get(record.structure_document_id)
        if original.kind != "sdmx_structure" or (
                original.institution_id != record.candidate.institution_id):
            raise ValueError("series structure belongs to another institution or document kind")
        with sqlite3.connect(self.settings.database_path) as db:
            current = db.execute(
                "SELECT document_id FROM metadata_documents WHERE institution_id=? "
                "AND source_url=? AND kind=? ORDER BY snapshot_no DESC LIMIT 1",
                (original.institution_id, original.source_url, original.kind),
            ).fetchone()
        if current is None or current[0] != record.structure_document_id:
            raise ValueError("series structure was superseded; rediscover metadata")
        structure = result.structures()
        flows = [flow for flow in structure["dataflows"] if flow["id"] == record.candidate.dataset_id]
        if len(flows) != 1:
            raise ValueError("series dataflow is not uniquely documented")
        ref = flows[0]["structure_ref"]
        dsds = [dsd for dsd in structure["datastructures"] if
                (dsd["agency"], dsd["id"], dsd["version"]) ==
                (ref.get("agencyID"), ref.get("id"), ref.get("version"))]
        if len(dsds) != 1:
            raise ValueError("series DSD reference is unresolved")
        dimensions = dsds[0]["dimensions"]
        keys = record.candidate.series_key
        if set(keys) != {dimension["id"] for dimension in dimensions}:
            raise ValueError("series key dimensions differ from the source DSD")
        for dimension in dimensions:
            refs = [ref for ref in dimension["references"] if ref.get("class") == "Codelist"]
            if len(refs) != 1:
                raise ValueError("series dimension needs one explicit source codelist")
            ref = refs[0]
            lists = [cl for cl in structure["codelists"] if
                     (cl["agency"], cl["id"], cl["version"]) ==
                     (ref.get("agencyID"), ref.get("id"), ref.get("version"))]
            if len(lists) != 1 or keys[dimension["id"]] not in lists[0]["codes"]:
                raise ValueError("series dimension code is not in the source codelist")

    def get(self, document_id):
        with sqlite3.connect(self.settings.database_path) as db:
            row = db.execute("SELECT header,original_body,result FROM metadata_documents "
                             "WHERE document_id=?", (document_id,)).fetchone()
        if row is None:
            raise KeyError("unknown metadata document")
        header = json.loads(row[0])
        document = MetadataDocument(
            institution_id=header["institution_id"], source_agency=header["source_agency"],
            source_url=header["source_url"], retrieved_at=datetime.fromisoformat(header["retrieved_at"]),
            evidence_kind=EvidenceKind(header["evidence_kind"]), original_ref=header["original_ref"],
            kind=header["kind"], body=bytes(row[1]), source_version=header["source_version"],
        )
        if document.content_sha256 != header["content_sha256"] or document.document_id != document_id:
            raise ValueError("metadata original hash or identity mismatch")
        data = json.loads(row[2])
        fingerprint = data.pop("fingerprint")
        if digest(data) != fingerprint:
            raise ValueError("normalized metadata hash mismatch")
        records = tuple(MetadataRecord.from_dict(v) for v in data["records"])
        if data["document_id"] != document_id or any(
            r.candidate.metadata_revision != document_id for r in records
        ):
            raise ValueError("metadata result identity mismatch")
        return document, MetadataResult(document_id, records,
                                        json.dumps(data["structures"]), tuple(data["warnings"]))

    def current_records(self, *, institution_id=None, limit=MAX_RECORDS, validate_structures=True):
        if type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
            raise ValueError("invalid metadata query limit")
        query = """
            SELECT r.document_id,r.record_id,r.payload FROM metadata_records r
            JOIN metadata_documents d ON r.document_id=d.document_id
            WHERE (? IS NULL OR d.institution_id=?)
            AND NOT EXISTS(SELECT 1 FROM metadata_documents newer
                WHERE newer.institution_id=d.institution_id AND newer.source_url=d.source_url
                AND newer.kind=d.kind AND newer.snapshot_no>d.snapshot_no)
            ORDER BY d.snapshot_no,r.candidate_id LIMIT ?
        """
        with sqlite3.connect(self.settings.database_path) as db:
            rows = db.execute(query, (institution_id, institution_id, limit + 1)).fetchall()
        if len(rows) > limit:
            raise ValueError("metadata query budget exceeded; narrow the institution scope")
        records = []
        for document_id, record_id, payload in rows:
            data = json_snapshot(json.loads(payload))
            record = MetadataRecord.from_dict(data)
            if digest(data) != record_id or record.candidate.metadata_revision != document_id:
                raise ValueError("metadata index hash or revision mismatch")
            if validate_structures:
                self.validate_structure(record)
            records.append(record)
        return tuple(records)
