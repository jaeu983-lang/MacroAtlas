"""Append-only guide snapshots and institution-specific strategy rules."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime

from macro_data_platform.config import Settings
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.guides import (
    GuideCategory,
    GuideChangeStatus,
    GuideSaveResult,
    GuideStrategyRule,
    SourceGuide,
)
from macro_data_platform.discovery.institution_sites import InstitutionCandidate


class GuideStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 2}:
                raise ValueError("unsupported history schema version")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_guides (
                    snapshot_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    guide_id TEXT NOT NULL UNIQUE,
                    institution_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    original_body BLOB NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    extraction_path TEXT NOT NULL,
                    extracted_text TEXT,
                    retrieved_at TEXT NOT NULL,
                    expires_at TEXT,
                    evidence_kind TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    source_version TEXT
                );
                CREATE INDEX IF NOT EXISTS guides_by_source
                    ON source_guides(institution_id, source_url, category, snapshot_no);
                CREATE TRIGGER IF NOT EXISTS source_guides_no_update
                BEFORE UPDATE ON source_guides
                BEGIN
                    SELECT RAISE(ABORT, 'source guides are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS source_guides_no_delete
                BEFORE DELETE ON source_guides
                BEGIN
                    SELECT RAISE(ABORT, 'source guides are append-only');
                END;
                CREATE TABLE IF NOT EXISTS guide_strategy_rules (
                    rule_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT NOT NULL UNIQUE,
                    institution_id TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    document TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS strategy_rules_by_institution
                    ON guide_strategy_rules(institution_id, strategy_id, rule_no);
                CREATE TRIGGER IF NOT EXISTS guide_strategy_rules_no_update
                BEFORE UPDATE ON guide_strategy_rules
                BEGIN
                    SELECT RAISE(ABORT, 'guide strategy rules are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS guide_strategy_rules_no_delete
                BEFORE DELETE ON guide_strategy_rules
                BEGIN
                    SELECT RAISE(ABORT, 'guide strategy rules are append-only');
                END;
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.settings.database_path, timeout=5)
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _guide_from_row(row: tuple) -> SourceGuide:
        guide = SourceGuide(
            institution_id=row[2],
            category=GuideCategory(row[3]),
            title=row[4],
            source_url=row[5],
            media_type=row[6],
            original_body=bytes(row[7]),
            extraction_path=tuple(json.loads(row[9])),
            extracted_text=row[10],
            retrieved_at=datetime.fromisoformat(row[11]),
            expires_at=None if row[12] is None else datetime.fromisoformat(row[12]),
            evidence_kind=EvidenceKind(row[13]),
            evidence_ref=row[14],
            source_version=row[15],
        )
        if row[1] != guide.guide_id:
            raise RuntimeError("stored guide identity does not match its metadata")
        if row[8] != guide.content_sha256:
            raise RuntimeError("stored guide content hash does not match its original body")
        return guide

    def save_guide(
        self, guide: SourceGuide, candidate: InstitutionCandidate
    ) -> GuideSaveResult:
        if guide.institution_id != candidate.institution_id:
            raise ValueError("guide and institution candidate do not match")
        canonical_url = candidate.require_official_document_url(guide.source_url)
        saved_guide = replace(guide, source_url=canonical_url)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest_row = connection.execute(
                "SELECT * FROM source_guides "
                "WHERE institution_id=? AND source_url=? AND category=? "
                "ORDER BY snapshot_no DESC LIMIT 1",
                (saved_guide.institution_id, saved_guide.source_url, saved_guide.category.value),
            ).fetchone()
            if latest_row is None:
                change_status = GuideChangeStatus.FIRST_SEEN
            elif self._guide_from_row(latest_row).revision_sha256 == saved_guide.revision_sha256:
                change_status = GuideChangeStatus.UNCHANGED
            else:
                change_status = GuideChangeStatus.CHANGED
            metadata = saved_guide.metadata()
            encoded_path = json.dumps(
                metadata["extraction_path"], ensure_ascii=False, separators=(",", ":")
            )
            connection.execute(
                "INSERT OR IGNORE INTO source_guides("
                "guide_id, institution_id, category, title, source_url, media_type, original_body, "
                "content_sha256, extraction_path, extracted_text, retrieved_at, expires_at, "
                "evidence_kind, evidence_ref, source_version"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    saved_guide.guide_id,
                    saved_guide.institution_id,
                    saved_guide.category.value,
                    saved_guide.title,
                    saved_guide.source_url,
                    saved_guide.media_type,
                    saved_guide.original_body,
                    saved_guide.content_sha256,
                    encoded_path,
                    saved_guide.extracted_text,
                    saved_guide.retrieved_at.isoformat(),
                    None if saved_guide.expires_at is None else saved_guide.expires_at.isoformat(),
                    saved_guide.evidence_kind.value,
                    saved_guide.evidence_ref,
                    saved_guide.source_version,
                ),
            )
            row = connection.execute(
                "SELECT * FROM source_guides WHERE guide_id=?", (saved_guide.guide_id,)
            ).fetchone()
            if row is None or self._guide_from_row(row) != saved_guide:
                raise RuntimeError("guide identity collision")
            connection.commit()
        return GuideSaveResult(
            guide_id=saved_guide.guide_id,
            content_sha256=saved_guide.content_sha256,
            change_status=change_status,
        )

    def get_guide(self, guide_id: str) -> SourceGuide:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_guides WHERE guide_id=?", (guide_id,)
            ).fetchone()
        if row is None:
            raise KeyError("unknown source guide")
        return self._guide_from_row(row)

    def latest_for_source(self, guide: SourceGuide) -> SourceGuide:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_guides WHERE institution_id=? AND source_url=? AND category=? "
                "ORDER BY snapshot_no DESC LIMIT 1",
                (guide.institution_id, guide.source_url, guide.category.value),
            ).fetchone()
        if row is None:
            raise KeyError("no saved snapshots for source guide")
        return self._guide_from_row(row)

    def for_institution(self, institution_id: str) -> tuple[SourceGuide, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_guides WHERE institution_id=? ORDER BY snapshot_no",
                (institution_id,),
            ).fetchall()
        return tuple(self._guide_from_row(row) for row in rows)

    def save_strategy_rule(self, rule: GuideStrategyRule) -> str:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for guide_id in rule.guide_ids:
                row = connection.execute(
                    "SELECT institution_id FROM source_guides WHERE guide_id=?", (guide_id,)
                ).fetchone()
                if row is None:
                    raise ValueError("strategy rule references an unknown guide")
                if row[0] != rule.institution_id:
                    raise ValueError("strategy rule cannot reference another institution's guide")
            document = rule.metadata()
            encoded = json.dumps(
                document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            )
            connection.execute(
                "INSERT OR IGNORE INTO guide_strategy_rules("
                "rule_id, institution_id, strategy_id, document"
                ") VALUES (?, ?, ?, ?)",
                (rule.rule_id, rule.institution_id, rule.strategy_id, encoded),
            )
            existing = connection.execute(
                "SELECT document FROM guide_strategy_rules WHERE rule_id=?", (rule.rule_id,)
            ).fetchone()
            if existing is None or existing[0] != encoded:
                raise RuntimeError("guide strategy identity collision")
            connection.commit()
        return rule.rule_id

    @staticmethod
    def _rule_from_document(document: str) -> GuideStrategyRule:
        data = json.loads(document)
        return GuideStrategyRule(
            institution_id=data["institution_id"],
            strategy_id=data["strategy_id"],
            trigger_tags=tuple(data["trigger_tags"]),
            guide_ids=tuple(data["guide_ids"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            priority=data["priority"],
        )

    def latest_strategy_rules(self, institution_id: str) -> tuple[GuideStrategyRule, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT strategy_id, document FROM guide_strategy_rules "
                "WHERE institution_id=? ORDER BY rule_no",
                (institution_id,),
            ).fetchall()
        latest: dict[str, str] = {}
        for strategy_id, document in rows:
            latest[strategy_id] = document
        return tuple(self._rule_from_document(latest[key]) for key in sorted(latest))
