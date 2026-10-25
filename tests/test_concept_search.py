"""08 correction: broad-query recall without statistical equivalence or implicit selection."""
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_metadata_discovery import AT, document, institution, json_document
from test_series_discovery import child, request
from test_series_discovery import setup as discovery_setup  # noqa: F401 - shared fixture

import macro_data_platform.mapping.concepts as concept_module
from macro_data_platform.discovery.series import parse_request
from macro_data_platform.mapping.concepts import ConceptLink, ConceptSearchPolicy
from macro_data_platform.workflow_contracts import OutputSpec
from macro_data_platform.workflow_extensions import DeliverySpec, VariantAttributes


@pytest.fixture(name="setup")
def concept_setup(request):
    return request.getfixturevalue("discovery_setup")


def gdp_data(*, different_ids=True):
    data = json.loads(document().body)
    nominal = data["datasets"][0]["series"][0]
    nominal["concept_id"] = "gdp_nominal" if different_ids else "gdp"
    real = dict(nominal, concept_id="gdp_real" if different_ids else "gdp",
                price_basis="real", label={"en":"Synthetic real GDP"},
                definition="Synthetic GDP valued at constant prices.",
                series_key={"source":"2", "country":"USA", "indicator":"FIXTURE_REAL_GDP"},
                unit="constant USD")
    data["datasets"][0]["series"] = [nominal, real]
    return data


def ingest_gdp(metadata, *, different_ids=True, data=None):
    source = replace(json_document(data or gdp_data(different_ids=different_ids)),
                     retrieved_at=AT - timedelta(seconds=1))
    metadata.ingest(source, institution())


@pytest.mark.parametrize("different_ids", [True, False])
def test_broad_us_gdp_returns_nominal_and_real_with_one_family_and_differences(setup, different_ids):
    _, _, metadata, service, _, _ = setup
    ingest_gdp(metadata, different_ids=different_ids)
    outcome = service.search(request("gdp"))
    assert len(outcome.records) == 2
    assert {r.attributes.price_basis for r in outcome.records} == {"nominal", "real"}
    assert len(outcome.proposal.groups) == 1
    assert outcome.proposal.groups[0].concept_id == "gdp"
    assert {v.concept_id for v in outcome.proposal.variants} == {"gdp"}
    assert {r.candidate.definition for r in outcome.records} == {
        "Synthetic fixture of GDP at current prices in US dollars.",
        "Synthetic GDP valued at constant prices.",
    }
    assert all(v["family_id"] == "gdp" for v in outcome.concept_matches.values())
    assert all(v["references"] for v in outcome.concept_matches.values())
    if different_ids:
        assert {r.concept_id for r in outcome.records} == {"gdp_nominal", "gdp_real"}
        assert {v["relation"] for v in outcome.concept_matches.values()} == {"subtype"}
    assert outcome.questions == ({"field":"variant.price_basis", "kind":"input",
                                  "choices":["nominal", "real"]},)


def test_broad_query_shows_candidates_without_autoselecting_or_downloading(setup):
    settings, _, metadata, service, _, wb = setup
    ingest_gdp(metadata)
    root = service.begin(
        request("gdp"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    workflow = root["workflow_request"]
    assert workflow["draft"]["candidate_id"] is None
    assert len(workflow["draft"]["proposal"]["proposal"]["candidates"]) == 2
    assert "variant.price_basis" in {q["field"] for q in workflow["questions"]}
    with pytest.raises(ValueError):
        child(service, root)
    assert not settings.raw_dir.exists() and wb.calls == []


def test_single_available_type_is_not_a_silent_default_for_broad_query(setup):
    _, _, _, service, _, wb = setup
    root = service.begin(
        request("gdp"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    assert root["workflow_request"]["draft"]["candidate_id"] is None
    assert any(q["field"] == "variant.price_basis" for q in root["workflow_request"]["questions"])
    assert wb.calls == []


def test_explicit_nominal_query_or_choice_selects_only_nominal_and_reuses_fixed_route(setup):
    _, _, metadata, service, _, wb = setup
    ingest_gdp(metadata)
    outcome = service.search(request("gdp_nominal"))
    assert len(outcome.records) == 1
    assert outcome.records[0].attributes.price_basis == "nominal"
    assert not outcome.questions
    broad = service.begin(
        request("gdp"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    revised = service.revise(broad["task_id"], expected_revision=1,
                             requirements=VariantAttributes(price_basis="nominal"),
                             confirmation_method="followup")
    assert revised["workflow_request"]["state"] == "CONFIRMED"
    assert revised["workflow_request"]["questions"] == []
    assert service.run(child(service, revised)["task_id"])["status"] == "COMPLETED"
    assert len(wb.calls) == 1


def test_real_gdp_is_discoverable_but_never_sent_to_nominal_connector(setup):
    settings, _, metadata, service, _, wb = setup
    ingest_gdp(metadata)
    outcome = service.search(request("gdp_real"))
    assert len(outcome.records) == 1 and outcome.records[0].attributes.price_basis == "real"
    assert outcome.proposal.proposal.candidates[0].support_status == "unsupported"
    root = service.begin(request("gdp_real"),
                         delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
                         confirmation_method="explicit_request")
    with pytest.raises(ValueError):
        child(service, root)
    assert not settings.raw_dir.exists() and wb.calls == []


def test_growth_per_capita_and_same_id_change_measure_are_related_not_level_gdp(setup):
    _, _, metadata, service, _, _ = setup
    data = gdp_data()
    template = data["datasets"][0]["series"][0]
    for i, (concept, measure) in enumerate((
        ("gdp_growth", "rate"), ("gdp_per_capita", "level"), ("gdp", "change"),
        ("gni", "level"), ("government_debt", "level"),
    )):
        data["datasets"][0]["series"].append(dict(
            template, concept_id=concept, measure=measure,
            label={"en":"GDP-like label"}, series_key={"indicator":f"FIXTURE_{i}"},
        ))
    data["datasets"][0]["series"].append(dict(
        template, concept_id="gdp_growth", measure="rate", countries=["JPN"],
        label={"en":"Japan GDP growth"},
        series_key={"source":"2", "country":"JPN", "indicator":"FIXTURE_JPN_GROWTH"},
    ))
    data["datasets"][0]["series"].append(dict(
        template, concept_id="gdp_growth", measure="rate", available_start="2025",
        available_end="2026", label={"en":"Out-of-period GDP growth"},
        series_key={"source":"2", "country":"USA", "indicator":"FIXTURE_LATE_GROWTH"},
    ))
    ingest_gdp(metadata, data=data)
    outcome = service.search(request("gdp"))
    assert len(outcome.records) == 2
    assert len(outcome.related_candidates) == 3
    assert all(item["concept_match"]["relation"] == "related"
               for item in outcome.related_candidates)
    assert "Japan GDP growth" not in {item["candidate"]["label"]
                                      for item in outcome.related_candidates}
    assert "Out-of-period GDP growth" not in {item["candidate"]["label"]
                                              for item in outcome.related_candidates}
    assert all(r.concept_id not in {"gni", "government_debt"} for r in outcome.records)


def test_unparsed_concept_requests_clarification_instead_of_listing_every_series(setup):
    settings, _, metadata, service, _, wb = setup
    ingest_gdp(metadata)
    outcome = service.search(request(None))
    assert outcome.records == ()
    assert outcome.related_candidates == ()
    assert any(question["field"] == "concept" and question["kind"] == "input"
               for question in outcome.questions)
    root = service.begin(
        request(None), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    workflow = root["workflow_request"]
    assert workflow["draft"]["proposal"]["proposal"]["candidates"] == []
    assert any(question["field"] == "concept" and question["kind"] == "input"
               for question in workflow["questions"])
    assert workflow["state"] == "NEEDS_INPUT"
    with pytest.raises(ValueError):
        child(service, root)
    assert not settings.raw_dir.exists() and wb.calls == []


@pytest.mark.parametrize("price", [None, "real"])
def test_source_subtype_attribute_unknown_or_conflict_remains_reviewable(setup, price):
    _, _, metadata, service, _, _ = setup
    data = gdp_data()
    data["datasets"][0]["series"] = [data["datasets"][0]["series"][0]]
    if price is None:
        data["datasets"][0]["series"][0].pop("price_basis")
    else:
        data["datasets"][0]["series"][0]["price_basis"] = price
    ingest_gdp(metadata, data=data)
    outcome = service.search(request("gdp"))
    assert len(outcome.records) == 1
    reviews = next(iter(outcome.reviews.values()))
    assert any(reason.startswith("concept_attribute_") for reason in reviews)
    selected = outcome.records[0].candidate.candidate_id
    root = service.begin(request("gdp"), candidate_id=selected,
                         delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
                         confirmation_method="explicit_request")
    assert root["workflow_request"]["state"] == "NEEDS_REVIEW"
    with pytest.raises(ValueError):
        child(service, root)


def test_natural_language_distinguishes_broad_subtypes_and_related_indicators():
    for text, concept in (
        ("미국 GDP", "gdp"), ("미국 명목 GDP", "gdp_nominal"),
        ("USA real GDP", "gdp_real"), ("명목 GDP와 실질 GDP 비교", "gdp"),
        ("미국 GDP 성장률", "gdp_growth"), ("USA GDP per capita", "gdp_per_capita"),
    ):
        assert parse_request(text)[0].concept == concept


def test_policy_change_invalidates_old_selection_before_fetch(setup, monkeypatch):
    _, _, _, service, _, wb = setup
    root = service.begin(
        request("gdp_nominal"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    work = child(service, root)
    old = concept_module.DEFAULT_CONCEPT_POLICY
    changed = ConceptSearchPolicy("changed-policy", old.links, aliases=old.aliases, facets=old.facets)
    monkeypatch.setattr(concept_module, "DEFAULT_CONCEPT_POLICY", changed)
    with pytest.raises(ValueError, match="policy changed"):
        service.run(work["task_id"])
    assert wb.calls == []


def test_direct_workflow_edits_cannot_bypass_search_conditions(setup):
    _, _, _, service, _, wb = setup
    root = service.begin(
        request("gdp_nominal"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    draft = root["workflow_request"]["draft"]
    altered = type(service.search(request("gdp_nominal")).proposal).from_dict(draft["proposal"])
    selected = altered.proposal.candidates[0]
    altered = replace(altered, proposal=replace(
        altered.proposal, candidates=(replace(selected, definition="Unrelated altered meaning"),)))
    direct = service.workflow.revise(root["task_id"], expected_revision=1, proposal=altered,
                                     confirmation_method="followup")
    with pytest.raises(ValueError, match="outside search"):
        service.workflow.create_work(direct["task_id"],
                                     expected_revision=direct["workflow_request"]["revision"])
    assert wb.calls == []


def test_relation_cycles_are_rejected_and_id_prefixes_do_not_create_membership():
    with pytest.raises(ValueError, match="cyclic"):
        ConceptSearchPolicy("cycle", (ConceptLink("a", "b", "subtype", "fixture"),
                                     ConceptLink("b", "a", "subtype", "fixture")))
    policy = concept_module.concept_search_policy()
    match = policy.match("gdp", "gdp_unreviewed_label", VariantAttributes(price_basis="nominal"))
    assert not match.primary and match.relation == "unrelated"


def test_missing_measure_does_not_turn_a_same_id_into_verified_level_gdp(setup):
    _, _, metadata, service, _, _ = setup
    data = gdp_data()
    data["datasets"][0]["series"][0].pop("measure")
    ingest_gdp(metadata, data=data)
    outcome = service.search(request("gdp"))
    assert any("gdp_measure_unknown" in reasons for reasons in outcome.reviews.values())


@pytest.mark.parametrize("changed_concept", ["gdp_real", "gdp"])
def test_changed_concept_does_not_retain_old_implied_price_or_selected_series(setup, changed_concept):
    _, history, metadata, service, _, wb = setup
    ingest_gdp(metadata)
    root = service.begin(
        request("gdp_nominal"), delivery=DeliverySpec("file", OutputSpec("raw_json", "data/raw")),
        confirmation_method="explicit_request")
    old = child(service, root)
    revised = service.revise(root["task_id"], expected_revision=1,
                             request=request(changed_concept), confirmation_method="followup")
    draft = revised["workflow_request"]["draft"]
    assert history.get(old["task_id"])["status"] == "CANCELLED"
    if changed_concept == "gdp":
        assert draft["candidate_id"] is None and draft["requirements"]["price_basis"] is None
        assert len(draft["proposal"]["proposal"]["candidates"]) == 2
    else:
        assert draft["requirements"]["price_basis"] == "real"
        assert len(draft["proposal"]["proposal"]["candidates"]) == 1
    with pytest.raises(ValueError):
        child(service, revised)
    assert wb.calls == []
