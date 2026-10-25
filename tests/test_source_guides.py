"""Offline guide snapshot, expiry, change and strategy-reuse tests."""
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.guides import (
    GuideCategory,
    GuideChangeStatus,
    GuideStrategyRule,
    GuideStrategySelector,
    SourceGuide,
    StrategySelectionStatus,
)
from macro_data_platform.discovery.institution_sites import (
    InstitutionCandidate,
    OfficialDomainEvidence,
)
from macro_data_platform.storage.guides import GuideStore
from macro_data_platform.storage.history import HistoryStore

FIXTURES = Path(__file__).parent / "fixtures" / "guide_documents"
DOCS_CHECKED_AT = datetime(2026, 10, 24, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 10, 25, tzinfo=UTC)
FUTURE_EXPIRY = datetime(2027, 10, 24, tzinfo=UTC)


def imf_candidate() -> InstitutionCandidate:
    return InstitutionCandidate(
        institution_id="INT-01",
        name="IMF",
        jurisdiction="international",
        official_domains=(
            OfficialDomainEvidence(
                "data.imf.org",
                "https://data.imf.org/en/Resource-Pages/IMF-API",
                DOCS_CHECKED_AT,
            ),
        ),
    )


def tic_candidate() -> InstitutionCandidate:
    return InstitutionCandidate(
        institution_id="US-03",
        name="Treasury TIC",
        jurisdiction="United States",
        official_domains=(
            OfficialDomainEvidence(
                "home.treasury.gov",
                "https://home.treasury.gov/data/treasury-international-capital-tic-system",
                DOCS_CHECKED_AT,
            ),
        ),
    )


def make_guide(
    institution_id: str,
    *,
    body: bytes | None = None,
    retrieved_at: datetime = RETRIEVED_AT,
    expires_at: datetime | None = FUTURE_EXPIRY,
) -> SourceGuide:
    if institution_id == "INT-01":
        fixture = FIXTURES / "imf_sdmx_api_guide.txt"
        category = GuideCategory.API_GUIDE
        source_url = "https://data.imf.org/en/Resource-Pages/IMF-API"
        extraction_path = ("fixture:IMF API resource page", "fixture:SDMX API guide section")
    elif institution_id == "US-03":
        fixture = FIXTURES / "tic_usage_policy.txt"
        category = GuideCategory.USAGE_POLICY
        source_url = (
            "https://home.treasury.gov/data/treasury-international-capital-tic-system/"
            "contact-tic-using-tic"
        )
        extraction_path = ("fixture:TIC index", "fixture:using TIC guidance")
    else:
        raise ValueError("unknown test institution")
    original = body if body is not None else fixture.read_bytes()
    return SourceGuide(
        institution_id=institution_id,
        category=category,
        title=f"Synthetic {category.value} fixture",
        source_url=source_url,
        media_type="text/plain; charset=utf-8",
        original_body=original,
        extraction_path=extraction_path,
        retrieved_at=retrieved_at,
        evidence_kind=EvidenceKind.FIXTURE,
        evidence_ref=f"fixture:tests/fixtures/guide_documents/{fixture.name}",
        extracted_text=original.decode("utf-8"),
        expires_at=expires_at,
    )


def rule(
    institution_id: str,
    strategy_id: str,
    tags: tuple[str, ...],
    guide_id: str,
    created_at: datetime = RETRIEVED_AT,
    priority: int = 0,
) -> GuideStrategyRule:
    return GuideStrategyRule(
        institution_id=institution_id,
        strategy_id=strategy_id,
        trigger_tags=tags,
        guide_ids=(guide_id,),
        created_at=created_at,
        priority=priority,
    )


def test_imf_and_tic_guides_keep_distinct_category_source_and_original(tmp_path):
    settings = Settings(tmp_path)
    HistoryStore(settings)
    store = GuideStore(settings)
    imf = make_guide("INT-01")
    tic = make_guide("US-03")

    imf_saved = store.save_guide(imf, imf_candidate())
    tic_saved = store.save_guide(tic, tic_candidate())
    reopened = GuideStore(settings)
    saved_imf = reopened.get_guide(imf_saved.guide_id)
    saved_tic = reopened.get_guide(tic_saved.guide_id)

    assert imf_saved.change_status is GuideChangeStatus.FIRST_SEEN
    assert tic_saved.change_status is GuideChangeStatus.FIRST_SEEN
    assert saved_imf.category is GuideCategory.API_GUIDE
    assert saved_tic.category is GuideCategory.USAGE_POLICY
    assert saved_imf.original_body == imf.original_body
    assert saved_imf.extracted_text == imf.extracted_text
    assert saved_imf.extraction_path == imf.extraction_path
    assert saved_imf.content_sha256 == imf.content_sha256
    assert saved_imf.evidence_kind is EvidenceKind.FIXTURE
    assert "SYNTHETIC FIXTURE" in saved_tic.original_body.decode("utf-8")
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE source_guides SET title='replacement' WHERE guide_id=?",
                (imf_saved.guide_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM source_guides WHERE guide_id=?", (imf_saved.guide_id,)
            )


@pytest.mark.parametrize(
    ("column", "replacement", "message"),
    (
        ("guide_id", "corrupt-guide-id", "identity"),
        ("content_sha256", "0" * 64, "content hash"),
    ),
)
def test_guide_reads_reject_corrupted_persisted_identity_or_hash(
    tmp_path, column, replacement, message
):
    settings = Settings(tmp_path)
    store = GuideStore(settings)
    guide_id = store.save_guide(make_guide("INT-01"), imf_candidate()).guide_id
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("DROP TRIGGER source_guides_no_update")
        connection.execute(
            f"UPDATE source_guides SET {column}=? WHERE guide_id=?",
            (replacement, guide_id),
        )

    with pytest.raises(RuntimeError, match=message):
        store.for_institution("INT-01")


def test_guide_changes_append_snapshots_without_replacing_original(tmp_path):
    store = GuideStore(Settings(tmp_path))
    candidate = imf_candidate()
    original = make_guide("INT-01")
    first = store.save_guide(original, candidate)
    unchanged = store.save_guide(
        make_guide("INT-01", retrieved_at=RETRIEVED_AT + timedelta(days=1)), candidate
    )
    changed_body = original.original_body + b"\nfixture revision\n"
    changed = store.save_guide(
        make_guide(
            "INT-01",
            body=changed_body,
            retrieved_at=RETRIEVED_AT + timedelta(days=2),
        ),
        candidate,
    )

    assert unchanged.change_status is GuideChangeStatus.UNCHANGED
    assert changed.change_status is GuideChangeStatus.CHANGED
    assert changed.guide_id != first.guide_id
    assert [row.content_sha256 for row in store.for_institution("INT-01")] == [
        original.content_sha256,
        original.content_sha256,
        changed.content_sha256,
    ]
    assert store.get_guide(first.guide_id).original_body == original.original_body


@pytest.mark.parametrize(
    "category",
    (GuideCategory.CODEBOOK, GuideCategory.STATISTICAL_EXPLANATION),
)
def test_codebook_and_statistical_explanation_categories_round_trip(tmp_path, category):
    store = GuideStore(Settings(tmp_path))
    base = make_guide("INT-01")
    guide = replace(
        base,
        category=category,
        title=f"Synthetic {category.value} fixture",
    )

    saved = store.save_guide(guide, imf_candidate())

    assert store.get_guide(saved.guide_id) == guide


def test_strategy_rules_are_reused_only_for_the_matching_institution(tmp_path):
    store = GuideStore(Settings(tmp_path))
    imf_guide = make_guide("INT-01")
    tic_guide = make_guide("US-03")
    imf_id = store.save_guide(imf_guide, imf_candidate()).guide_id
    tic_id = store.save_guide(tic_guide, tic_candidate()).guide_id
    store.save_strategy_rule(rule("INT-01", "imf_sdmx", ("sdmx",), imf_id))
    store.save_strategy_rule(rule("US-03", "tic_web_table", ("web_table",), tic_id))
    selector = GuideStrategySelector()

    imf_selection = selector.select(
        store, "INT-01", ("SDMX", "bop"), RETRIEVED_AT + timedelta(days=1)
    )
    tic_selection = selector.select(
        store, "US-03", ("web_table", "holdings"), RETRIEVED_AT + timedelta(days=1)
    )
    repeated = selector.select(
        store, "INT-01", ("sdmx", "bop"), RETRIEVED_AT + timedelta(days=1)
    )
    cross_match = selector.select(
        store, "INT-01", ("web_table",), RETRIEVED_AT + timedelta(days=1)
    )

    assert imf_selection.status is StrategySelectionStatus.SELECTED
    assert imf_selection.strategy_id == "imf_sdmx"
    assert imf_selection.guide_ids == (imf_id,)
    assert tic_selection.strategy_id == "tic_web_table"
    assert tic_selection.guide_ids == (tic_id,)
    assert repeated == imf_selection
    assert cross_match.status is StrategySelectionStatus.NO_MATCH


def test_expired_guide_is_not_reused(tmp_path):
    store = GuideStore(Settings(tmp_path))
    expired_guide = make_guide(
        "US-03",
        expires_at=datetime(2026, 10, 26, tzinfo=UTC),
    )
    guide_id = store.save_guide(expired_guide, tic_candidate()).guide_id
    store.save_strategy_rule(rule("US-03", "tic_web_table", ("web_table",), guide_id))

    selection = GuideStrategySelector().select(
        store, "US-03", ("web_table",), datetime(2026, 10, 26, tzinfo=UTC)
    )

    assert selection.status is StrategySelectionStatus.GUIDE_EXPIRED
    assert selection.guide_ids == (guide_id,)


def test_changed_guide_requires_review_until_rule_references_new_snapshot(tmp_path):
    store = GuideStore(Settings(tmp_path))
    candidate = imf_candidate()
    original = make_guide("INT-01")
    old_id = store.save_guide(original, candidate).guide_id
    first_rule = rule("INT-01", "imf_sdmx", ("sdmx",), old_id)
    store.save_strategy_rule(first_rule)
    updated = make_guide(
        "INT-01",
        body=original.original_body + b"\nnew fixture revision\n",
        retrieved_at=RETRIEVED_AT + timedelta(days=1),
    )
    new_id = store.save_guide(updated, candidate).guide_id
    selector = GuideStrategySelector()

    stale_selection = selector.select(
        store, "INT-01", ("sdmx",), RETRIEVED_AT + timedelta(days=2)
    )
    new_rule = rule(
        "INT-01",
        "imf_sdmx",
        ("sdmx",),
        new_id,
        created_at=RETRIEVED_AT + timedelta(days=2),
    )
    store.save_strategy_rule(new_rule)
    reviewed_selection = selector.select(
        store, "INT-01", ("sdmx",), RETRIEVED_AT + timedelta(days=3)
    )

    assert stale_selection.status is StrategySelectionStatus.GUIDE_CHANGED
    assert stale_selection.guide_ids == (old_id,)
    assert reviewed_selection.status is StrategySelectionStatus.SELECTED
    assert reviewed_selection.rule_id == new_rule.rule_id
    assert reviewed_selection.guide_ids == (new_id,)


def test_changed_expiry_metadata_requires_review_even_when_body_is_unchanged(tmp_path):
    store = GuideStore(Settings(tmp_path))
    candidate = tic_candidate()
    original = make_guide("US-03")
    old_id = store.save_guide(original, candidate).guide_id
    store.save_strategy_rule(rule("US-03", "tic_web_table", ("web_table",), old_id))
    revised_expiry = make_guide(
        "US-03",
        retrieved_at=RETRIEVED_AT + timedelta(days=1),
        expires_at=RETRIEVED_AT + timedelta(hours=1),
    )
    saved_revision = store.save_guide(revised_expiry, candidate)

    selection = GuideStrategySelector().select(
        store, "US-03", ("web_table",), RETRIEVED_AT + timedelta(days=2)
    )

    assert saved_revision.change_status is GuideChangeStatus.CHANGED
    assert revised_expiry.content_sha256 == original.content_sha256
    assert selection.status is StrategySelectionStatus.GUIDE_CHANGED
    assert selection.guide_ids == (old_id,)


def test_ambiguous_strategy_matches_require_review(tmp_path):
    store = GuideStore(Settings(tmp_path))
    guide_id = store.save_guide(make_guide("INT-01"), imf_candidate()).guide_id
    store.save_strategy_rule(rule("INT-01", "imf_sdmx", ("sdmx",), guide_id))
    store.save_strategy_rule(rule("INT-01", "imf_sdmx_search", ("sdmx",), guide_id))

    selection = GuideStrategySelector().select(
        store, "INT-01", ("sdmx",), RETRIEVED_AT + timedelta(days=1)
    )

    assert selection.status is StrategySelectionStatus.NEEDS_REVIEW
    assert selection.candidate_strategy_ids == ("imf_sdmx", "imf_sdmx_search")


def test_strategy_rule_rejects_cross_institution_guides_and_nonofficial_guide_url(tmp_path):
    store = GuideStore(Settings(tmp_path))
    tic_id = store.save_guide(make_guide("US-03"), tic_candidate()).guide_id
    with pytest.raises(ValueError, match="another institution"):
        store.save_strategy_rule(rule("INT-01", "wrong_institution", ("sdmx",), tic_id))

    external = make_guide("INT-01")
    with pytest.raises(ValueError, match="outside the documented official domains"):
        store.save_guide(
            replace(external, source_url="https://example.org/imf-guide"),
            imf_candidate(),
        )


def test_unknown_guide_expiry_is_reported_instead_of_assumed_current(tmp_path):
    store = GuideStore(Settings(tmp_path))
    guide_id = store.save_guide(
        make_guide("INT-01", expires_at=None), imf_candidate()
    ).guide_id
    store.save_strategy_rule(rule("INT-01", "imf_sdmx", ("sdmx",), guide_id))

    selection = GuideStrategySelector().select(
        store, "INT-01", ("sdmx",), RETRIEVED_AT + timedelta(days=1)
    )

    assert selection.status is StrategySelectionStatus.SELECTED
    assert selection.warnings == (f"guide_expiry_unknown:{guide_id}",)
