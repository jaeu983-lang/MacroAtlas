"""Alignment 01: deterministic value contracts; no workflow execution or HTTP."""
import json
import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from macro_data_platform.contracts import EvidenceKind, SourceEvidence
from macro_data_platform.workflow_contracts import (
    Candidate,
    CandidateProposal,
    ConfirmedSelection,
    DataRequest,
    OutputSpec,
)

AT = datetime(2026, 10, 24, tzinfo=UTC)


def evidence(**changes):
    values = {"evidence_id": "fixture:e1", "source_agency": "fixture agency",
              "source_url": "https://example.org/metadata?source=2", "retrieved_at": AT,
              "kind": EvidenceKind.FIXTURE, "original_ref": "fixture:metadata-v1"}
    return SourceEvidence(**{**values, **changes})


def candidate(**changes):
    values = {"candidate_id": "c1", "institution_id": "fixture-agency", "label": "GDP fixture",
              "definition": "Synthetic annual GDP for contract tests; not actual data.",
              "dataset_id": "fixture-source", "series_key": {"indicator": "fixture-gdp"},
              "countries": ("USA", "JPN"), "dimensions": {}, "frequency": "annual",
              "available_start": "2010", "available_end": "2024", "evidence": (evidence(),),
              "verification_status": "documented", "availability_status": "available",
              "auth_requirement": "none", "support_status": "supported",
              "supported_outputs": ("raw_json", "csv"), "rationale": "Fixture evidence only."}
    return Candidate(**{**values, **changes})


def data_request(**changes):
    values = {"request_id": "r1", "text": "GDP data", "concept": "GDP", "countries": ("USA",),
              "dimensions": {}, "period_start": "2020", "period_end": "2022",
              "frequency": "source", "unit_policy": "preserve",
              "vintage_requirement": "latest_available"}
    return DataRequest(**{**values, **changes})


def proposal(**changes):
    values = {"proposal_id": "p1", "request_id": "r1", "revision": 1,
              "created_at": AT, "candidates": (candidate(),)}
    return CandidateProposal(**{**values, **changes})


def confirmation(**changes):
    values = {"request": data_request(), "proposal": proposal(), "candidate_id": "c1",
              "proposal_revision": 1, "output": OutputSpec("raw_json", "data/raw"),
              "confirmed_at": AT, "confirmation_method": "explicit_request"}
    return ConfirmedSelection(**{**values, **changes})


@pytest.mark.parametrize("hint", [None, "fixture-agency"])
def test_unspecified_and_named_institution_requests_remain_explicit_drafts(hint):
    request = DataRequest("r", "원하는 데이터", institution_hint=hint)
    assert request.institution_hint == hint
    assert request.concept is None
    assert request.period_start is None
    assert request.frequency is None
    assert request.unit_policy is None
    assert request.dimensions is None
    assert DataRequest.from_json(request.to_json()).to_dict() == request.to_dict()


@pytest.mark.parametrize("count", [0, 1, 3])
def test_proposals_support_zero_one_and_multiple_candidates(count):
    value = proposal(candidates=[candidate(candidate_id=f"c{i}") for i in range(count)])
    assert len(value.candidates) == count
    assert CandidateProposal.from_json(value.to_json()).to_dict() == value.to_dict()


def test_unknown_candidate_metadata_and_access_do_not_become_verified():
    value = Candidate("c", "agency", "unverified candidate")
    restored = Candidate.from_json(value.to_json())
    for field in ("definition", "unit", "frequency", "metadata_revision", "source_version"):
        assert getattr(restored, field) is None
    assert restored.verification_status == "unknown"
    assert restored.availability_status == "unknown"
    assert restored.auth_requirement == "unknown"
    assert restored.support_status == "unknown"
    assert restored.series_id is None
    assert restored.series_key == {}


@pytest.mark.parametrize("kind", list(EvidenceKind))
def test_evidence_modes_round_trip_without_promoting_verification_or_availability(kind):
    value = Candidate("c", "agency", "candidate", evidence=(evidence(kind=kind),))
    restored = Candidate.from_json(value.to_json())
    assert restored.evidence[0].kind == kind
    assert restored.verification_status == "unknown"
    assert restored.availability_status == "unknown"


@pytest.mark.parametrize("model", [data_request(), candidate(), proposal(),
                                   OutputSpec("xlsx", "data/export"), confirmation()])
def test_all_models_round_trip_json_deterministically(model):
    serialized = model.to_json()
    restored = type(model).from_json(serialized)
    assert restored.to_dict() == model.to_dict()
    assert restored.to_json() == serialized
    assert json.loads(serialized)["schema_version"] == 1


def test_confirmation_is_not_a_boolean_and_records_exact_snapshots():
    value = confirmation()
    assert value.request.request_id == value.proposal.request_id
    assert value.proposal_revision == 1
    assert len(value.fingerprint) == 64
    assert value.matches(value.request, value.proposal, value.output)
    assert not value.matches(True, value.proposal, value.output)
    with pytest.raises(ValueError, match="confirmation"):
        confirmation(confirmation_method=True)
    with pytest.raises(ValueError, match="typed"):
        confirmation(request=True)


@pytest.mark.parametrize("field,missing", [("concept", None), ("countries", ()),
                                          ("dimensions", None), ("period_start", None),
                                          ("period_end", None), ("frequency", None),
                                          ("unit_policy", None), ("vintage_requirement", None)])
def test_missing_required_conditions_cannot_be_confirmed(field, missing):
    request = data_request(**{field: missing})
    with pytest.raises(ValueError, match="remain unknown"):
        confirmation(request=request)


@pytest.mark.parametrize("changes", [
    {"candidate_id": "missing"}, {"proposal_revision": 2}, {"proposal_revision": True},
    {"proposal": proposal(request_id="different")}, {"proposal": proposal(candidates=())},
])
def test_wrong_candidate_request_or_proposal_revision_cannot_be_confirmed(changes):
    with pytest.raises(ValueError):
        confirmation(**changes)


@pytest.mark.parametrize("changes", [
    {"definition": None}, {"series_id": None, "series_key": {}}, {"evidence": ()},
    {"verification_status": "unknown"}, {"availability_status": "unknown"},
    {"availability_status": "unavailable"}, {"auth_requirement": "unknown"},
    {"support_status": "unknown"}, {"support_status": "unsupported"},
    {"available_start": None}, {"available_end": None}, {"dimensions": None},
])
def test_unresolved_candidate_cannot_be_confirmed(changes):
    with pytest.raises(ValueError):
        confirmation(proposal=proposal(candidates=(candidate(**changes),)))


def test_requested_output_is_preserved_but_not_confirmed_if_unsupported():
    output = OutputSpec("xlsx", "data/export")
    assert output.format == "xlsx"
    with pytest.raises(ValueError, match="unsupported"):
        confirmation(output=output)
    assert output.format == "xlsx"


@pytest.mark.parametrize("change", ["start", "end", "country", "institution", "frequency",
                                    "output_format", "output_dir", "definition", "metadata",
                                    "evidence", "proposal_revision", "candidate"])
def test_changes_in_conditions_or_evidence_invalidate_old_confirmation(change):
    initial = confirmation()
    request, suggested, output = initial.request, initial.proposal, initial.output
    if change == "start":
        request = replace(request, period_start="2019")
    elif change == "end":
        request = replace(request, period_end="2023")
    elif change == "country":
        request = replace(request, countries=("JPN",))
    elif change == "institution":
        request = replace(request, institution_hint="another-hint")
    elif change == "frequency":
        request = replace(request, frequency="annual")
    elif change == "output_format":
        output = replace(output, format="csv")
    elif change == "output_dir":
        output = replace(output, relative_dir="data/export")
    elif change == "definition":
        suggested = replace(suggested, candidates=(candidate(definition="Revised definition"),))
    elif change == "metadata":
        suggested = replace(suggested, candidates=(candidate(metadata_revision="v2"),))
    elif change == "evidence":
        suggested = replace(suggested, candidates=(candidate(
            evidence=(evidence(original_ref="fixture:metadata-v2"),),
        ),))
    elif change == "proposal_revision":
        suggested = replace(suggested, revision=2)
    elif change == "candidate":
        suggested = replace(suggested, candidates=(candidate(candidate_id="c2"),))
    assert not initial.matches(request, suggested, output)
    selected_id = "c2" if change == "candidate" else "c1"
    changed = confirmation(request=request, proposal=suggested, output=output,
                           proposal_revision=suggested.revision, candidate_id=selected_id)
    assert changed.fingerprint != initial.fingerprint


def test_confirmation_timestamp_and_method_do_not_change_condition_identity():
    initial = confirmation()
    later = replace(initial, confirmed_at=AT + timedelta(minutes=1), confirmation_method="followup")
    assert later.fingerprint == initial.fingerprint
    assert later.to_dict() != initial.to_dict()


def test_fingerprint_is_stable_when_mapping_insertion_order_changes():
    first = candidate(series_key={"indicator": "fixture", "country": "USA"})
    second = candidate(series_key={"country": "USA", "indicator": "fixture"})
    a = confirmation(proposal=proposal(candidates=(first,)))
    b = confirmation(proposal=proposal(candidates=(second,)))
    assert a.fingerprint == b.fingerprint


def test_tampered_json_or_missing_fingerprint_is_rejected():
    for change in ("fingerprint", "missing", "condition"):
        data = confirmation().to_dict()
        if change == "fingerprint":
            data["fingerprint"] = "0" * 64
        elif change == "missing":
            del data["fingerprint"]
        else:
            data["request"]["period_end"] = "2023"
        with pytest.raises(ValueError, match="snapshot"):
            ConfirmedSelection.from_dict(data)


def test_mutable_constructor_inputs_and_exported_json_cannot_mutate_models():
    countries = ["USA"]
    dimensions = {"sector": ["ALL"]}
    series_key = {"indicator": "fixture"}
    evidences = [evidence()]
    item = candidate(countries=countries, dimensions=dimensions,
                     series_key=series_key, evidence=evidences)
    candidates = [item]
    value = proposal(candidates=candidates)
    original = value.to_json()
    countries.append("JPN")
    dimensions["sector"].append("OTHER")
    series_key["indicator"] = "changed"
    evidences.clear()
    candidates.clear()
    exported = value.to_dict()
    exported["candidates"][0]["series_key"]["indicator"] = "changed"
    assert value.to_json() == original
    with pytest.raises(TypeError):
        item.series_key["indicator"] = "changed"
    with pytest.raises(FrozenInstanceError):
        item.label = "changed"
    request = data_request(countries=["USA"], dimensions={"sector": ["ALL"]})
    assert request.countries == ("USA",)
    assert request.dimensions["sector"] == ("ALL",)


@pytest.mark.parametrize("start,end", [("2022", "2020"), ("2020", "2020-01"),
                                       ("latest", "2022"), ("0000", "2022"),
                                       ("2020-13", "2021-01"), ("2021-02-29", "2021-03-01"),
                                       ("2020-Q5", "2021-Q1"), (True, "2022")])
def test_invalid_periods_are_rejected_without_guessing(start, end):
    with pytest.raises(ValueError):
        data_request(period_start=start, period_end=end)


@pytest.mark.parametrize("start,end", [("2020", "2022"), ("2020-01", "2022-12"),
                                       ("2020-Q1", "2022-Q4"), ("2020-02-29", "2022-01-01")])
def test_resolved_calendar_periods_round_trip_without_frequency_inference(start, end):
    value = data_request(period_start=start, period_end=end, frequency=None)
    restored = DataRequest.from_json(value.to_json())
    assert restored.period_start == start
    assert restored.period_end == end
    assert restored.frequency is None


@pytest.mark.parametrize("changes", [
    {"countries": ("DEU",)}, {"period_start": "2009"}, {"period_end": "2025"},
    {"frequency": "monthly"}, {"unit_policy": "convert", "target_unit": "USD"},
    {"vintage_requirement": "vintage-1"}, {"dimensions": {"unknown": ("ALL",)}},
])
def test_unsupported_or_unknown_coverage_is_not_confirmed(changes):
    with pytest.raises(ValueError):
        confirmation(request=data_request(**changes))


def test_known_dimensions_units_and_vintage_are_preserved_but_no_conversion_occurs():
    item = candidate(dimensions={"sector": ["ALL", "BANK"]}, unit="USD", source_version="v1")
    request = data_request(dimensions={"sector": ["BANK"]}, unit_policy="convert",
                           target_unit="EUR", vintage_requirement="v1", frequency="annual")
    result = confirmation(request=request, proposal=proposal(candidates=(item,)))
    assert result.request.target_unit == "EUR"
    assert result.proposal.candidates[0].unit == "USD"
    with pytest.raises(ValueError, match="Dimension selection"):
        confirmation(request=replace(request, dimensions={"sector": ("OTHER",)}),
                     proposal=result.proposal)


@pytest.mark.parametrize("stamp", [datetime(2026, 10, 24),
                                   datetime(2026, 10, 24, tzinfo=timezone(timedelta(hours=9)))])
def test_timestamps_must_be_explicit_utc(stamp):
    with pytest.raises(ValueError, match="UTC"):
        proposal(created_at=stamp)
    with pytest.raises(ValueError, match="UTC"):
        confirmation(confirmed_at=stamp)


def test_confirmation_cannot_predate_proposal_or_evidence():
    with pytest.raises(ValueError, match="predates proposal"):
        confirmation(confirmed_at=AT - timedelta(seconds=1))
    future = candidate(evidence=(evidence(retrieved_at=AT + timedelta(seconds=1)),))
    with pytest.raises(ValueError, match="predates its evidence"):
        confirmation(proposal=proposal(candidates=(future,)))


@pytest.mark.parametrize("path", ["", ".", "..", "../outside", "data/../outside", "/absolute",
                                  "C:/absolute", "C:relative", "\\\\server\\share", "\\root",
                                  "data/file:stream", "data/NUL.txt", "data/CON", "data/trailing.",
                                  "data/trailing ", "data/evil\x00", "data//export"])
def test_output_paths_are_safe_on_windows_and_posix(path):
    with pytest.raises(ValueError):
        OutputSpec("raw_json", path)


def test_output_path_normalization_containment_and_no_directory_creation(tmp_path):
    value = OutputSpec("raw_json", "data\\출력")
    assert value.relative_dir == "data/출력"
    assert value.resolve_under(tmp_path) == tmp_path / "data" / "출력"
    assert list(tmp_path.iterdir()) == []


def test_resolved_output_escape_is_rejected_even_when_lexically_relative(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    # Simulate a resolver following an existing link outside the root. No OS links are created.
    def resolve(path):
        return root if path == root else root.parent / "outside"
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="leaves the repository"):
        OutputSpec("raw_json", "linked/export").resolve_under(root)


@pytest.mark.parametrize("auth,variable", [("none", None), ("optional", None),
                                          ("optional", "EXAMPLE_API_KEY"),
                                          ("required", "EXAMPLE_API_KEY"), ("unknown", None)])
def test_authentication_policy_is_separate_from_credential_values(auth, variable):
    value = candidate(auth_requirement=auth, credential_env_var=variable)
    assert value.auth_requirement == auth
    assert value.credential_env_var == variable
    assert "credential_value" not in value.to_dict()


@pytest.mark.parametrize("changes", [{"auth_requirement": "required"},
                                     {"credential_env_var": "EXAMPLE_API_KEY"},
                                     {"auth_requirement": "optional", "credential_env_var": "key=value"}])
def test_inconsistent_or_credential_value_shaped_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        candidate(**changes)


@pytest.mark.parametrize("suffix", ["?api_key=pretend-private", "?access-token=pretend-private",
                                    "?app_id=pretend-private", "?UserID=pretend-private"])
def test_credential_query_parameters_are_rejected_without_echoing_values(suffix):
    with pytest.raises(ValueError) as caught:
        evidence(source_url="https://example.org/data" + suffix)
    assert "pretend-private" not in str(caught.value)


def test_model_representations_and_decode_errors_do_not_echo_user_text_or_secrets():
    private = "pretend-private-value"
    models = [data_request(text=private), candidate(label=private, rationale=private)]
    models.append(proposal(candidates=(models[-1],)))
    models.append(confirmation(request=models[0], proposal=models[-1]))
    for model in models:
        assert private not in repr(model)
        assert private not in str(model)
    data = data_request().to_dict()
    data["api_key"] = private
    with pytest.raises(ValueError) as caught:
        DataRequest.from_dict(data)
    assert private not in str(caught.value)
    with pytest.raises(ValueError) as caught:
        DataRequest.from_json(private)
    assert private not in str(caught.value)


@pytest.mark.parametrize("field", ["series_key", "dimensions"])
def test_nested_credential_fields_are_not_accepted_as_source_codes(field):
    value = "pretend-private-value" if field == "series_key" else ["pretend-private-value"]
    with pytest.raises(ValueError) as caught:
        candidate(**{field: {"api_key": value}})
    assert "pretend-private-value" not in str(caught.value)


@pytest.mark.parametrize("serialized", [
    '{"schema_version":1,"request_id":"r","text":"a","text":"b"}',
    '{"schema_version":1,"request_id":"r","text":"a","concept":NaN}',
])
def test_nonstandard_or_ambiguous_json_is_not_accepted(serialized):
    with pytest.raises(ValueError, match="JSON"):
        DataRequest.from_json(serialized)


@pytest.mark.parametrize("data", [{}, {"schema_version": 2}, {"schema_version": True},
                                  {"schema_version": 1, "request_id": "r"}])
def test_invalid_snapshots_fail_with_value_error(data):
    with pytest.raises(ValueError):
        DataRequest.from_dict(data)


def test_duplicate_identifiers_dimensions_and_revisions_are_rejected():
    with pytest.raises(ValueError):
        proposal(candidates=(candidate(), candidate()))
    with pytest.raises(ValueError):
        proposal(revision=True)
    with pytest.raises(ValueError):
        candidate(evidence=(evidence(), evidence()))
    with pytest.raises(ValueError):
        data_request(countries=("USA", "USA"))
    with pytest.raises(ValueError):
        data_request(dimensions={"sector": []})


def test_contract_operations_never_execute_http_database_or_filesystem_writes(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Contract operations must be side-effect free")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    model = confirmation()
    restored = ConfirmedSelection.from_json(model.to_json())
    assert restored.matches(model.request, model.proposal, model.output)
    assert model.output.resolve_under(tmp_path) == tmp_path / "data/raw"
    assert list(tmp_path.iterdir()) == []
