"""Value-only extension tests with declared fixture evidence; never verifies real URLs."""
import json
import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from test_workflow_contracts import AT, candidate, confirmation, data_request, evidence, proposal

from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    ConfirmedSelection,
    DataRequest,
    OutputSpec,
)
from macro_data_platform.workflow_extensions import (
    CandidateGroup,
    CandidateVariant,
    ConfirmedDelivery,
    DataLink,
    DeliveryOffer,
    DeliverySpec,
    GroupedProposal,
    VariantAttributes,
    link_target_fingerprint,
)


def grouped(*, second=False, original=None):
    items = (candidate(), candidate(candidate_id="c2")) if second else (candidate(),)
    source = original if original is not None else proposal(candidates=items)
    variants = tuple(CandidateVariant(
        item.candidate_id, "fixture-gdp", VariantAttributes(
            seasonal_adjustment="adjusted" if item.candidate_id == "c1" else "unadjusted",
            stock_flow="flow", measure="level", price_basis="real", base_period="2020",
            source_codes={"ADJUSTMENT": "SA" if item.candidate_id == "c1" else "NSA"},
        ), (evidence(),),
    ) for item in source.candidates)
    groups = (CandidateGroup("g1", "fixture-gdp", tuple(item.candidate_id for item in items),
                             "Declared fixture definition grouping, not automatic equivalence.",
                             (evidence(),)),)
    # Single custom candidate proposals retain their own identifiers.
    if original is not None:
        groups = (replace(groups[0], candidate_ids=tuple(item.candidate_id for item in source.candidates)),)
    return GroupedProposal(source, variants, groups)


def data_link(base=None, **changes):
    base = base if base is not None else DeliveryOffer(data_request(), grouped(), "c1")
    source = base.proposal.proposal
    values = {
        "link_id": "l1", "candidate_id": base.candidate_id, "proposal_id": source.proposal_id,
        "proposal_revision": source.revision,
        "target_fingerprint": link_target_fingerprint(base.request, base.proposal,
                                                       base.candidate_id, base.requirements),
        "status": "available", "url": "https://example.org/data?country=USA&start=2020&end=2022",
        "kind": "api", "checked_at": AT, "expires_at": AT + timedelta(hours=1),
        "official": True, "shareable": True, "access_requirement": "public",
        "manual_filter_required": False,
        "evidence": (evidence(evidence_id="fixture:link"),),
    }
    return DataLink(**{**values, **changes})


def offer(*, request=None, suggested=None, requirements=None, links=None):
    base = DeliveryOffer(request if request is not None else data_request(),
                         suggested if suggested is not None else grouped(), "c1",
                         requirements if requirements is not None else VariantAttributes())
    return replace(base, links=(data_link(base),) if links is None else links)


def selected(mode="both", *, offered=None):
    spec = DeliverySpec(mode,
                        OutputSpec("raw_json", "data/raw") if mode in ("file", "both") else None,
                        ("l1",) if mode in ("link", "both") else ())
    return ConfirmedDelivery(offered if offered is not None else offer(), spec, AT, "explicit_request")


@pytest.mark.parametrize("name,cls", [
    ("DataRequest", DataRequest), ("Candidate", Candidate), ("CandidateProposal", CandidateProposal),
    ("OutputSpec", OutputSpec), ("ConfirmedSelection", ConfirmedSelection),
])
def test_original_v1_json_is_byte_identical_to_pre_extension_golden(name, cls):
    golden = json.loads((Path(__file__).parent / "fixtures/workflow_v1_golden.json").read_text("utf-8"))
    restored = cls.from_json(golden[name])
    assert restored.to_json() == golden[name]
    if name == "ConfirmedSelection":
        assert restored.fingerprint == "92b82d2b99402fba6a7704aed19e10db20dceb4345c1146f8a3d54d2cd8b7d96"
        assert restored.matches(restored.request, restored.proposal, restored.output)


def test_original_constructors_fingerprints_and_validation_errors_are_unchanged():
    assert confirmation().fingerprint == "92b82d2b99402fba6a7704aed19e10db20dceb4345c1146f8a3d54d2cd8b7d96"
    with pytest.raises(ValueError, match="^Unknown frequency policy$"):
        data_request(frequency="unsupported")
    old_output = OutputSpec("link", "data/export")
    assert old_output.format == "link"  # It was merely a string, never a delivery mode.
    with pytest.raises(ValueError, match="not a file format"):
        DeliverySpec("file", old_output)
    changed = data_request().to_dict()
    changed["delivery_mode"] = "link"
    with pytest.raises(ValueError, match="snapshot"):
        DataRequest.from_dict(changed)


@pytest.mark.parametrize("mode", ["file", "link", "both"])
def test_three_explicit_delivery_modes_can_be_confirmed(mode):
    result = selected(mode)
    assert result.delivery.mode == mode
    assert result.matches(result.offer, result.delivery)
    assert result.fingerprint != confirmation().fingerprint
    if mode == "link":
        assert result.delivery.file is None


def test_unspecified_mode_stays_unknown_even_with_a_file_preference():
    draft = DeliverySpec(file=OutputSpec("csv", "data/export"))
    assert draft.mode is None
    assert draft.requires_choice is True
    assert DeliverySpec.from_json(draft.to_json()).mode is None
    with pytest.raises(ValueError, match="must be selected"):
        ConfirmedDelivery(offer(), draft, AT, "explicit_request")
    assert not selected("file").delivery.requires_choice


@pytest.mark.parametrize("spec", [DeliverySpec("file"), DeliverySpec("link"),
                                  DeliverySpec("both", OutputSpec("raw_json", "data/raw")),
                                  DeliverySpec("both", link_ids=("l1",))])
def test_explicit_mode_does_not_fill_missing_file_or_link_selection(spec):
    with pytest.raises(ValueError):
        ConfirmedDelivery(offer(), spec, AT, "explicit_request")


def test_cross_mode_settings_are_rejected_not_silently_discarded():
    with pytest.raises(ValueError, match="cannot request a file"):
        DeliverySpec("link", OutputSpec("csv", "data/export"))
    with pytest.raises(ValueError, match="cannot select links"):
        DeliverySpec("file", link_ids=("l1",))
    with pytest.raises(ValueError):
        DeliverySpec(True)
    with pytest.raises(ValueError):
        DeliverySpec("excel")


@pytest.mark.parametrize("status", ["unknown", "unavailable", "blocked"])
def test_non_available_link_states_are_preserved_and_excluded_from_choices(status):
    base = DeliveryOffer(data_request(), grouped(), "c1")
    link = data_link(base, status=status, url=None, kind=None, expires_at=None,
                     checked_at=None if status == "unknown" else AT,
                     official=None, shareable=None, manual_filter_required=None,
                     reason=None if status == "unknown" else "Checked only the selected fixture route.")
    value = replace(base, links=(link,))
    assert value.available_modes(AT) == ("file",)
    assert DataLink.from_json(link.to_json()).status == status
    for mode in ("link", "both"):
        with pytest.raises(ValueError, match="no automatic fallback"):
            selected(mode, offered=value)


@pytest.mark.parametrize("status", ["blocked", "unavailable"])
def test_absence_or_restriction_requires_reason_and_scope_verification(status):
    with pytest.raises(ValueError, match="scoped reason"):
        data_link(status=status, reason=None)


def test_link_only_can_exist_without_a_local_collector_exporter_or_api_key_setting():
    original = proposal(candidates=(candidate(support_status="unsupported", supported_outputs=(),
                                              auth_requirement="unknown"),))
    value = offer(suggested=grouped(original=original))
    assert value.available_modes(AT) == ("link",)
    assert selected("link", offered=value).delivery.file is None
    with pytest.raises(ValueError):
        selected("file", offered=value)


def test_both_and_file_modes_do_not_fall_back_to_links_for_an_unsupported_format():
    spec = DeliverySpec("both", OutputSpec("xlsx", "data/export"), ("l1",))
    with pytest.raises(ValueError, match="file settings"):
        ConfirmedDelivery(offer(), spec, AT, "explicit_request")
    assert spec.mode == "both"
    assert spec.file.format == "xlsx"


@pytest.mark.parametrize("changes", [
    {"url": None}, {"kind": "reference"}, {"official": None}, {"official": False},
    {"shareable": None}, {"shareable": False}, {"checked_at": None, "expires_at": None},
    {"manual_filter_required": None}, {"evidence": ()},
    {"access_requirement": "unknown"}, {"access_requirement": "authentication_required"},
])
def test_available_link_needs_actual_data_type_and_explicit_verification_fields(changes):
    with pytest.raises(ValueError):
        data_link(**changes)


def test_reference_page_can_be_recorded_as_unknown_but_never_selected_as_data():
    base = DeliveryOffer(data_request(), grouped(), "c1")
    reference = data_link(base, kind="reference", status="unknown", expires_at=None)
    value = replace(base, links=(reference,))
    assert value.available_modes(AT) == ("file",)


def test_viewer_manual_filter_and_restrictions_remain_visible_in_snapshot():
    base = DeliveryOffer(data_request(), grouped(), "c1")
    viewer = data_link(base, kind="viewer", manual_filter_required=True,
                       restrictions=("User must select the stated period in the viewer.",))
    result = selected("link", offered=replace(base, links=(viewer,)))
    assert result.offer.links[0].manual_filter_required is True
    assert result.offer.links[0].restrictions


def test_expired_future_or_unselected_link_does_not_get_silently_substituted():
    value = offer()
    link = value.links[0]
    assert link.usable_at(AT)
    assert not link.usable_at(AT - timedelta(seconds=1))
    assert not link.usable_at(link.expires_at)
    for mode in ("link", "both"):
        original = selected(mode)
        with pytest.raises(ValueError, match="unavailable"):
            replace(original, confirmed_at=link.expires_at)
    # File-only confirmation can ignore an expired, unselected link.
    assert replace(selected("file"), confirmed_at=link.expires_at).delivery.mode == "file"
    with pytest.raises(ValueError, match="Selected link"):
        ConfirmedDelivery(value, DeliverySpec("link", link_ids=("missing",)), AT, "explicit_request")


def test_already_expired_link_can_be_recorded_as_blocked_without_becoming_an_option():
    value = data_link(status="blocked", reason="Expired at the checked fixture route.",
                       expires_at=AT - timedelta(seconds=1))
    assert not value.usable_at(AT)


def test_absence_status_needs_inspection_evidence_and_document_anchors_remain_usable():
    with pytest.raises(ValueError, match="scoped reason"):
        data_link(status="unavailable", reason="No data URL at this checked route.", evidence=())
    value = data_link(evidence=(evidence(source_url="https://example.org/docs#data"),))
    assert value.usable_at(AT)


def test_public_statistical_code_query_is_not_mistaken_for_an_api_credential():
    value = data_link(url="https://example.org/data?code=GDP&year=2020")
    assert value.usable_at(AT)


@pytest.mark.parametrize("changes", [
    {"candidate_id": "c2"}, {"proposal_id": "different"}, {"proposal_revision": 2},
    {"target_fingerprint": "0" * 64},
])
def test_links_from_other_candidates_conditions_or_revisions_cannot_be_merged(changes):
    base = DeliveryOffer(data_request(), grouped(), "c1")
    with pytest.raises(ValueError, match="different candidate"):
        replace(base, links=(data_link(base, **changes),))


def test_sa_nsa_are_distinct_variants_inside_a_group_not_duplicate_data_or_auto_selection():
    value = grouped(second=True)
    original = value.proposal.to_json()
    assert value.groups[0].candidate_ids == ("c1", "c2")
    assert [item.attributes.seasonal_adjustment for item in value.variants] == ["adjusted", "unadjusted"]
    assert value.proposal.to_json() == original
    assert CandidateVariant("c1", "fixture-gdp").attributes.seasonal_adjustment is None
    assert DeliverySpec().requires_choice


@pytest.mark.parametrize("attribute,other", [("stock_flow", "stock"), ("measure", "rate")])
def test_contradictory_stock_flow_or_level_rate_cannot_form_one_variant_group(attribute, other):
    value = grouped(second=True)
    changed = replace(value.variants[1], attributes=replace(value.variants[1].attributes,
                                                          **{attribute: other}))
    with pytest.raises(ValueError, match="separate groups"):
        replace(value, variants=(value.variants[0], changed))
    separate = replace(value, variants=(value.variants[0], changed), groups=(
        replace(value.groups[0], group_id="g1", candidate_ids=("c1",)),
        replace(value.groups[0], group_id="g2", candidate_ids=("c2",)),
    ))
    assert len(separate.groups) == 2


def test_different_concepts_and_unknown_group_members_are_rejected():
    value = grouped(second=True)
    with pytest.raises(ValueError, match="Different concepts"):
        replace(value, variants=(value.variants[0], replace(value.variants[1], concept_id="other")))
    with pytest.raises(ValueError, match="Unknown"):
        replace(value, groups=(replace(value.groups[0], candidate_ids=("missing",)),))
    with pytest.raises(ValueError, match="multiply grouped"):
        replace(value, groups=(value.groups[0], replace(value.groups[0], group_id="g2")))
    with pytest.raises(ValueError, match="Unknown or repeated"):
        replace(value, variants=(value.variants[0], value.variants[0]))


def test_groups_and_known_variants_need_evidence_and_cannot_contradict_original_fields():
    with pytest.raises(ValueError, match="require source evidence"):
        CandidateVariant("c1", "GDP", VariantAttributes(seasonal_adjustment="adjusted"))
    with pytest.raises(ValueError, match="members and evidence"):
        CandidateGroup("g1", "GDP", ("c1",), "reason", ())
    value = grouped()
    with pytest.raises(ValueError, match="contradict"):
        replace(value, variants=(replace(value.variants[0], attributes=VariantAttributes(
            frequency="monthly",
        )),))


def test_requested_variants_must_match_without_assuming_unknown_is_unadjusted():
    value = offer(requirements=VariantAttributes(seasonal_adjustment="adjusted"))
    assert selected("link", offered=value).offer.requirements.seasonal_adjustment == "adjusted"
    for requirements in (VariantAttributes(seasonal_adjustment="unadjusted"),
                         VariantAttributes(scale="millions"),
                         VariantAttributes(source_codes={"ADJUSTMENT": "NSA"})):
        with pytest.raises(ValueError, match="Variant"):
            selected("link", offered=offer(requirements=requirements))


@pytest.mark.parametrize("change", ["mode", "link", "status", "expiry", "group", "variant", "request"])
def test_extension_changes_invalidate_extended_confirmation_fingerprint(change):
    initial = selected()
    value, spec = initial.offer, initial.delivery
    if change == "mode":
        spec = DeliverySpec("link", link_ids=("l1",))
    elif change == "link":
        value = replace(value, links=(replace(value.links[0], url="https://example.org/new-data"),))
    elif change == "status":
        value = replace(value, links=(replace(value.links[0], status="blocked", reason="Restricted."),))
    elif change == "expiry":
        value = replace(value, links=(replace(value.links[0], expires_at=AT + timedelta(hours=2)),))
    elif change == "group":
        new_grouped = replace(value.proposal, groups=(replace(value.proposal.groups[0],
                                                            rationale="New grouping evidence."),))
        value = offer(suggested=new_grouped)
    elif change == "variant":
        new_grouped = replace(value.proposal, variants=(replace(value.proposal.variants[0],
            attributes=replace(value.proposal.variants[0].attributes, revision_status="revised")),))
        value = offer(suggested=new_grouped)
    elif change == "request":
        value = offer(request=replace(value.request, period_end="2023"))
    assert not initial.matches(value, spec)
    if change != "status":
        assert ConfirmedDelivery(value, spec, AT, "followup").fingerprint != initial.fingerprint


def test_changed_variant_metadata_invalidates_link_binding_even_with_same_candidate_id():
    value = offer()
    new_grouped = replace(value.proposal, variants=(replace(value.proposal.variants[0],
        attributes=replace(value.proposal.variants[0].attributes, price_basis="nominal")),))
    with pytest.raises(ValueError, match="different candidate"):
        replace(value, proposal=new_grouped)


@pytest.mark.parametrize("model", [DeliverySpec(), VariantAttributes(), grouped().variants[0],
                                   grouped().groups[0], grouped(), data_link(), offer(), selected()])
def test_extension_models_have_deterministic_strict_json_round_trips(model):
    restored = type(model).from_json(model.to_json())
    assert restored.to_json() == model.to_json()
    assert restored.to_dict() == model.to_dict()


def test_tampered_fingerprints_and_unknown_fields_are_rejected_without_leaking_values():
    serialized = selected().to_dict()
    serialized["fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="snapshot"):
        ConfirmedDelivery.from_dict(serialized)
    serialized = selected().to_dict()
    serialized["offer"]["proposal"]["variants"][0]["attributes"]["price_basis"] = "nominal"
    with pytest.raises(ValueError):
        ConfirmedDelivery.from_dict(serialized)
    with pytest.raises(ValueError) as error:
        DeliverySpec.from_dict({"schema_version": 1, "api_key": "pretend-private"})
    assert "pretend-private" not in str(error.value)


def test_utc_time_and_evidence_chronology_are_enforced():
    with pytest.raises(ValueError, match="UTC"):
        data_link(checked_at=AT.replace(tzinfo=None))
    with pytest.raises(ValueError, match="predates its evidence"):
        data_link(evidence=(evidence(retrieved_at=AT + timedelta(seconds=1)),))
    value = offer()
    group = replace(value.proposal.groups[0], evidence=(evidence(retrieved_at=AT + timedelta(seconds=1)),))
    value = offer(suggested=replace(value.proposal, groups=(group,)))
    with pytest.raises(ValueError, match="predates group evidence"):
        selected("file", offered=value)


@pytest.mark.parametrize("url", ["https://user:pretend-private@example.org/data",
                                 "https://example.org/data?api_key=pretend-private",
                                 "https://example.org/data?X-Amz-Signature=pretend-private",
                                 "https://example.org/data?signature=pretend-private",
                                 "https://example.org/data#access_token=pretend-private",
                                 "https://example.org:bad/data"])
def test_unsafe_share_urls_cannot_enter_even_blocked_link_snapshots(url):
    with pytest.raises(ValueError) as error:
        data_link(url=url, status="blocked", reason="Unavailable for sharing.")
    assert "pretend-private" not in str(error.value)


def test_variants_links_and_groups_are_frozen_detached_and_hidden_in_repr():
    codes = {"ADJUSTMENT": "SA"}
    attrs = VariantAttributes(source_codes=codes)
    codes["ADJUSTMENT"] = "NSA"
    assert attrs.source_codes["ADJUSTMENT"] == "SA"
    value = selected()
    dumped = value.to_dict()
    dumped["offer"]["links"][0]["url"] = "changed"
    assert value.offer.links[0].url != "changed"
    with pytest.raises(FrozenInstanceError):
        value.delivery.mode = "file"
    with pytest.raises(TypeError):
        attrs.source_codes["ADJUSTMENT"] = "changed"
    private = replace(value.offer.links[0], reason="pretend-private")
    assert "pretend-private" not in repr(private)
    with pytest.raises(ValueError):
        VariantAttributes(source_codes={"api_key": "pretend-private"})


def test_reconfirming_same_content_changes_record_time_not_content_hash():
    initial = selected()
    later = replace(initial, confirmed_at=AT + timedelta(minutes=1), confirmation_method="followup")
    assert later.fingerprint == initial.fingerprint
    assert later.to_dict() != initial.to_dict()


def test_link_only_never_promises_unit_conversion_or_unknown_period_coverage():
    for request in (data_request(unit_policy="convert", target_unit="EUR"),
                    data_request(period_end=None), data_request(countries=("DEU",))):
        with pytest.raises(ValueError):
            selected("link", offered=offer(request=request))


def test_value_contract_operations_have_no_network_database_download_or_file_generation(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Value contracts must not execute external operations")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    value = selected("link")
    assert value.delivery.file is None
    restored = ConfirmedDelivery.from_json(value.to_json())
    assert restored.matches(value.offer, value.delivery)
    assert list(tmp_path.iterdir()) == []
