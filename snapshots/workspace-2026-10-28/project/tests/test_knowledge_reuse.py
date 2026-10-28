"""Iteration 12 Gate D: scoped retrieval, invalidation, conflicts, and safe reuse boundaries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import count
from threading import Event

import pytest

import macro_data_platform.storage.knowledge as knowledge_module
from macro_data_platform.config import Settings
from macro_data_platform.mapping.concepts import ConceptLink, ConceptSearchPolicy
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore
from macro_data_platform.storage.knowledge import KnowledgeStore

AS_OF = "2026-10-25T12:00:00+00:00"


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 25, 12, tzinfo=UTC)

    def __call__(self):
        return self.value


@pytest.fixture
def stores(tmp_path):
    settings = Settings(tmp_path)
    history = HistoryStore(settings)
    clock = Clock()
    task = Orchestrator(history, {}, clock=clock).create("knowledge reuse fixture task")
    return history, KnowledgeStore(settings, clock=clock), task


def accepted_official(store, statement, *, institution="worldbank", dataset="WDI",
                      concept="GDP", axis="price_basis", **kwargs):
    record = store.register(
        statement, provenance="official_evidence", validation_status="verified",
        evidence_refs=("fixture:official-source-snapshot",), institution_id=institution,
        dataset_id=dataset, concept_id=concept, classification_axis=axis, **kwargs,
    )
    store.review(record["record_id"], status="accepted", reviewer="fixture-review")
    return record


def test_same_institution_reuse_is_scoped_and_explicit_input_wins(stores):
    _, store, task = stores
    feedback = store.audit.add_feedback(
        task.task_id, text="Offer CSV first, but let me choose.", category="correction",
        institution_id="worldbank", correction_type="output_preference",
    )
    store.audit.review_feedback(feedback["record_id"], expected_revision=1,
                                review_status="accepted", reviewer="user")
    preference = store.register(
        provenance="user_statement", feedback_id=feedback["record_id"],
    )
    store.review(preference["record_id"], status="accepted", reviewer="user")

    other = store.register(
        "For IMF, prefer an XLSX option.", provenance="user_statement",
        institution_id="imf", correction_type="output_preference",
    )
    store.review(other["record_id"], status="accepted", reviewer="user")
    global_source = accepted_official(
        store, "Unscoped official statement must not apply to a named institution.",
        institution=None, concept="GDP",
    )
    result = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    by_id = {record["record_id"]: record for record in result["records"]}
    assert set(by_id) == {preference["record_id"], global_source["record_id"]}
    assert by_id[preference["record_id"]]["reusable"] is True
    assert by_id[preference["record_id"]]["requires_confirmation"] is True
    assert by_id[preference["record_id"]]["provenance"] == "user_statement"
    assert by_id[global_source["record_id"]]["reusable"] is False
    overridden = store.query(
        institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
        explicit_correction_types=("output_preference",),
    )
    by_id = {record["record_id"]: record for record in overridden["records"]}
    assert by_id[preference["record_id"]]["reusable"] is False
    assert "overrides" in by_id[preference["record_id"]]["reason"]


def test_only_reviewed_verified_source_evidence_is_reusable_and_inference_stays_quarantined(stores):
    _, store, _ = stores
    official = store.register(
        "Fixture evidence with explicit scope.", provenance="official_evidence",
        validation_status="verified", evidence_refs=("fixture:source",),
        institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
        classification_axis="price_basis",
    )
    inference = store.register(
        "Possible relation inferred from repeated labels.", provenance="inference",
        institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
        classification_axis="price_basis",
    )
    result = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    by_id = {item["record_id"]: item for item in result["records"]}
    assert by_id[official["record_id"]]["reusable"] is False
    assert by_id[inference["record_id"]]["quarantined"] is True
    assert by_id[inference["record_id"]]["reusable"] is False

    store.review(official["record_id"], status="accepted", reviewer="fixture-review")
    refreshed = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    by_id = {item["record_id"]: item for item in refreshed["records"]}
    assert by_id[official["record_id"]]["reusable"] is False  # unresolved active-scope conflict
    assert refreshed["conflict_groups"] == 1
    with pytest.raises(ValueError, match="cannot be approved"):
        store.review(inference["record_id"], status="accepted", reviewer="fixture-review")


def test_broader_official_scope_is_a_candidate_but_not_reusable_for_a_narrow_query(stores):
    _, store, _ = stores
    no_concept_scope = accepted_official(store, "Institution-level GDP note.", concept=None)
    no_dataset_scope = accepted_official(
        store, "GDP note without a dataset scope.", dataset=None, concept="GDP",
    )
    result = store.query(institution_id="worldbank", dataset_id="WDI", concept_id="GDP",
                         as_of=AS_OF)
    by_id = {item["record_id"]: item for item in result["records"]}
    assert set(by_id) == {no_concept_scope["record_id"], no_dataset_scope["record_id"]}
    assert all(not item["reusable"] for item in by_id.values())


def test_conflicts_return_all_claims_and_cancel_invalidates_the_projection(stores):
    _, store, _ = stores
    first = accepted_official(store, "Source says nominal GDP is current-price output.")
    second = accepted_official(store, "Another source snapshot describes current-price output.")
    result = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert len(result["records"]) == 2
    assert result["conflict_groups"] == 1
    assert all(item["conflict"] and not item["reusable"] for item in result["records"])
    limited = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                          max_rows=1)
    assert limited["status"] == "partial" and limited["conflict_groups"] == 1
    assert "potential_conflicts_unchecked_due_to_row_budget" in limited["uncertainties"]
    assert limited["records"][0]["conflict"] is True
    assert limited["records"][0]["reusable"] is False

    store.cancel(second["record_id"], reason="fixture contradiction resolved", actor="reviewer")
    after = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert [item["record_id"] for item in after["records"]] == [first["record_id"]]
    assert after["conflict_groups"] == 0
    assert after["records"][0]["reusable"] is True


def test_row_and_byte_budgets_report_incomplete_results_without_reuse(stores):
    _, store, _ = stores
    for index in range(3):
        accepted_official(store, f"Fixture scope {index}.", concept=f"C{index}")
    limited_rows = store.query(institution_id="worldbank", as_of=AS_OF, max_rows=1)
    assert limited_rows["status"] == "partial"
    assert "row_budget_exhausted" in limited_rows["uncertainties"]
    assert len(limited_rows["records"]) == 1
    assert limited_rows["records"][0]["reusable"] is False

    limited_bytes = store.query(institution_id="worldbank", as_of=AS_OF,
                                max_bytes=1, max_rows=10)
    assert limited_bytes["status"] == "partial"
    assert "evidence_byte_budget_exhausted" in limited_bytes["uncertainties"]
    assert limited_bytes["records"] == []
    with pytest.raises(ValueError, match="bounded task"):
        store.query(as_of=AS_OF)
        with pytest.raises(ValueError, match="concept_id"):
            store.query(institution_id="worldbank", max_depth=1)


def test_effective_period_and_source_version_are_part_of_query_scope(stores):
    _, store, _ = stores
    record = accepted_official(
        store, "Time-bounded source snapshot.", source_version="source-v2",
        effective_from="2027-01-01T00:00:00Z", effective_to="2028-01-01T00:00:00Z",
    )
    before = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    current = store.query(institution_id="worldbank", concept_id="GDP",
                          source_version="source-v2", as_of="2027-06-01T00:00:00Z")
    after = store.query(institution_id="worldbank", concept_id="GDP",
                        source_version="source-v2", as_of="2028-01-01T00:00:00Z")
    assert before["records"] == []
    assert [item["record_id"] for item in current["records"]] == [record["record_id"]]
    assert current["records"][0]["reusable"] is True
    assert after["records"] == []


def test_cache_is_bounded_warm_and_invalidated_after_review_cancel_or_refresh(stores):
    _, store, _ = stores
    record = store.register(
        "Cache fixture claim.", provenance="official_evidence", validation_status="verified",
        evidence_refs=("fixture:source",), institution_id="worldbank", dataset_id="WDI",
        concept_id="GDP", classification_axis="price_basis",
    )
    first = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    warm = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert first["metrics"]["cache_hit"] is False
    assert warm["metrics"]["cache_hit"] is True
    assert warm["metrics"]["evidence_bytes_read"] == 0
    assert store.cache_info()["entries"] == 1
    assert store.cache_info()["bytes"] <= store.cache_info()["max_bytes"]

    store.review(record["record_id"], status="accepted", reviewer="reviewer")
    after_review = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert after_review["metrics"]["cache_hit"] is False
    assert after_review["records"][0]["reusable"] is True
    store.cancel(record["record_id"], reason="withdraw fixture", actor="reviewer")
    after_cancel = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert after_cancel["records"] == []
    assert after_cancel["metrics"]["cache_hit"] is False

    other_store = KnowledgeStore(store.settings, clock=store.clock)
    external = accepted_official(other_store, "Written by a second store instance.")
    after_external_write = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF)
    assert after_external_write["metrics"]["cache_hit"] is False
    assert [item["record_id"] for item in after_external_write["records"]] == [
        external["record_id"]
    ]


def test_query_cache_entry_and_byte_limits_are_enforced(stores):
    _, store, _ = stores
    store.register(
        "Large but bounded benchmark statement. " + "x" * 14_000,
        provenance="user_statement", institution_id="worldbank", concept_id="GDP",
    )
    for index in range(140):
        store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                    policy_version=f"cache-test-{index}")
    cache = store.cache_info()
    assert cache["entries"] <= cache["max_entries"]
    assert cache["bytes"] <= cache["max_bytes"]
    assert cache["entries"] < 140  # byte budget evicts old large result snapshots


def test_separate_index_refresh_is_bounded_and_withholds_reuse_until_complete(stores):
    _, store, _ = stores
    first = accepted_official(store, "Refresh record one.", concept="C1")
    second = accepted_official(store, "Refresh record two.", concept="C2")
    batch1 = store.refresh_index(batch_size=1, restart=True)
    assert batch1["processed"] == 1 and batch1["refresh_pending"] is True
    during = store.query(institution_id="worldbank", as_of=AS_OF)
    assert during["status"] == "partial" and during["refresh_pending"] is True
    assert all(not item["reusable"] for item in during["records"])
    batch2 = store.refresh_index(batch_size=1)
    assert batch2["processed"] == 1 and batch2["refresh_pending"] is False
    after = store.query(institution_id="worldbank", as_of=AS_OF)
    assert after["status"] == "complete"
    assert {item["record_id"] for item in after["records"]} == {
        first["record_id"], second["record_id"],
    }
    assert all(item["reusable"] for item in after["records"])


def test_index_query_plan_uses_institution_scope_index(stores):
    _, store, _ = stores
    accepted_official(store, "Query plan fixture.")
    plan = store.explain_query_plan(institution_id="worldbank", concept_id="GDP")
    assert any("knowledge_current_scope" in item for item in plan), plan


def test_reviewed_subtype_expansion_returns_search_candidates_without_equivalence(stores):
    _, store, _ = stores
    nominal = accepted_official(store, "Current-price GDP definition.", concept="gdp_nominal")
    real = accepted_official(store, "Constant-price GDP definition.", concept="gdp_real")
    policy = ConceptSearchPolicy("fixture-gdp-v1", (
        ConceptLink("GDP", "gdp_nominal", "subtype", "fixture:nominal-definition"),
        ConceptLink("GDP", "gdp_real", "subtype", "fixture:real-definition"),
        ConceptLink("GDP", "gdp_growth", "related", "fixture:growth-is-related"),
    ))

    broad = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                        concept_policy=policy, max_depth=1)
    by_id = {item["record_id"]: item for item in broad["records"]}
    assert set(by_id) == {nominal["record_id"], real["record_id"]}
    assert all(item["search_concept_match"] == "search_subtype" for item in by_id.values())
    assert all(item["search_concept_depth"] == 1 for item in by_id.values())
    assert by_id[nominal["record_id"]]["search_concept_path"] == ["GDP", "gdp_nominal"]
    assert by_id[nominal["record_id"]]["search_concept_evidence_refs"] == [
        "fixture:nominal-definition"
    ]
    assert all(not item["reusable"] and item["requires_confirmation"]
               for item in by_id.values())
    assert all("not statistical equivalence" in item["reason"] for item in by_id.values())
    assert "subtype_search_candidates_require_semantic_choice" in broad["uncertainties"]
    assert broad["metrics"]["expansion_depth"] == 1
    assert broad["metrics"]["expansion_candidates"] == 2

    narrow = store.query(institution_id="worldbank", concept_id="gdp_nominal", as_of=AS_OF,
                         concept_policy=policy, max_depth=1)
    assert [item["record_id"] for item in narrow["records"]] == [nominal["record_id"]]
    assert narrow["records"][0]["search_concept_match"] == "exact_concept"

    exact_only = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                             concept_policy=policy, max_depth=0)
    assert exact_only["records"] == []


def test_concept_policy_fingerprint_partitions_query_cache(stores):
    _, store, _ = stores
    accepted_official(store, "Nominal GDP.", concept="gdp_nominal")
    accepted_official(store, "Real GDP.", concept="gdp_real")
    first_policy = ConceptSearchPolicy("gdp-v1", (
        ConceptLink("GDP", "gdp_nominal", "subtype", "fixture:nominal"),
        ConceptLink("GDP", "gdp_real", "subtype", "fixture:real"),
    ))
    second_policy = ConceptSearchPolicy("gdp-v2", (
        ConceptLink("GDP", "gdp_nominal", "subtype", "fixture:nominal"),
    ))

    first = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                        concept_policy=first_policy, max_depth=1)
    second = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                         concept_policy=second_policy, max_depth=1)
    assert len(first["records"]) == 2 and first["metrics"]["cache_hit"] is False
    assert len(second["records"]) == 1 and second["metrics"]["cache_hit"] is False
    assert second["scope"]["concept_search"]["policy_version"] == "gdp-v2"


def test_concept_expansion_rejects_unbounded_or_unreviewed_requests(stores):
    _, store, _ = stores
    with pytest.raises(ValueError, match="depth must be between"):
        store.query(institution_id="worldbank", concept_id="GDP", max_depth=5)
    with pytest.raises(ValueError, match="requires a versioned"):
        store.query(institution_id="worldbank", concept_id="GDP", max_depth=1)
    with pytest.raises(ValueError, match="requires a concept_id"):
        store.query(institution_id="worldbank", max_depth=1)
    related_only = ConceptSearchPolicy("related-only", (
        ConceptLink("GDP", "gdp_growth", "related", "fixture:related"),
    ))
    exact = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                        concept_policy=related_only, max_depth=4)
    assert exact["metrics"]["expansion_candidates"] == 0


def test_query_snapshot_does_not_mix_an_inflight_cross_store_update(stores):
    _, store, _ = stores
    other_store = KnowledgeStore(store.settings, clock=store.clock)
    snapshot_read = Event()
    resume_reader = Event()
    writer_started = Event()
    paused = False
    original_state_reader = store._current_index_state
    original_writer_transaction = other_store.history.transaction

    @contextmanager
    def signal_writer_transaction():
        with original_writer_transaction() as connection:
            writer_started.set()
            yield connection

    other_store.history.transaction = signal_writer_transaction

    def pause_after_snapshot(connection):
        nonlocal paused
        state = original_state_reader(connection)
        if connection.in_transaction and not paused:
            paused = True
            snapshot_read.set()
            if not resume_reader.wait(5):
                raise TimeoutError("query snapshot synchronization timed out")
        return state

    store._current_index_state = pause_after_snapshot
    with ThreadPoolExecutor(max_workers=2) as executor:
        reader = executor.submit(
            store.query, institution_id="worldbank", as_of=AS_OF, max_time_ms=2_000,
        )
        assert snapshot_read.wait(5)
        writer = executor.submit(
            accepted_official, other_store, "Concurrent writer fixture.",
            concept="NEW_EVIDENCE",
        )
        try:
            assert writer_started.wait(5)
        finally:
            resume_reader.set()
        before_write = reader.result(timeout=5)
        record = writer.result(timeout=5)
    assert before_write["records"] == []

    after_write = store.query(institution_id="worldbank", as_of=AS_OF)
    assert [item["record_id"] for item in after_write["records"]] == [
        record["record_id"]
    ]
    assert after_write["metrics"]["cache_hit"] is False


def test_time_budget_exhaustion_returns_partial_and_withholds_reuse(stores, monkeypatch):
    _, store, _ = stores
    accepted_official(store, "Time budget fixture.")
    ticks = count()

    def exhausted_clock():
        return 0.0 if next(ticks) < 2 else 10.0

    monkeypatch.setattr(knowledge_module.time, "perf_counter", exhausted_clock)
    result = store.query(institution_id="worldbank", concept_id="GDP", as_of=AS_OF,
                         max_time_ms=1)
    assert result["status"] == "partial"
    assert "time_budget_exhausted" in result["uncertainties"]
    assert all(item["reusable"] is False for item in result["records"])
