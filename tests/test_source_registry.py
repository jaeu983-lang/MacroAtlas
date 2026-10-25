"""API-first institution status is separate from implementation and live evidence."""
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from macro_data_platform.discovery.source_registry import (
    AccessPriority,
    AdapterStatus,
    ApiAvailability,
    AuthRequirement,
    FixtureScope,
    LiveValidation,
    all_source_profiles,
    get_source_profile,
    profiles_by_api_availability,
    profiles_by_scenario,
)


def test_registry_covers_catalog_sources_and_preserves_scenario_groups():
    rows = all_source_profiles()

    assert len(rows) == 21
    assert {row.institution_id for row in rows} == {
        "INT-01", "INT-02", "INT-03", "INT-04", "US-01", "US-02", "US-03",
        "US-04", "US-05", "US-06", "EU-01", "EU-02", "EU-03", "EU-04",
        "EU-05", "JP-01", "JP-02", "JP-03", "CN-01", "CN-02", "CN-03",
    }
    assert {row.institution_id for row in profiles_by_scenario("E")} == {"EU-01", "EU-02"}
    assert {row.institution_id for row in profiles_by_scenario("F")} == {"JP-01", "JP-02", "JP-03"}
    assert {row.institution_id for row in profiles_by_scenario("G")} == {"CN-01", "CN-02", "CN-03"}
    assert {row.institution_id for row in profiles_by_scenario("H")} == {"INT-03", "INT-04"}
    assert {row.institution_id for row in rows if not row.scenario_ids} == {
        "US-01", "US-02", "US-05", "US-06", "EU-03", "EU-04", "EU-05",
    }


def test_documented_and_unconfirmed_api_sources_are_separate_groups():
    documented = profiles_by_api_availability(ApiAvailability.DOCUMENTED)
    unconfirmed = profiles_by_api_availability(ApiAvailability.UNCONFIRMED)

    assert {row.institution_id for row in documented} == {
        "INT-01", "INT-02", "INT-03", "INT-04", "US-01", "US-02", "US-04",
        "US-05", "US-06", "EU-01", "EU-02", "EU-03", "EU-05", "JP-01", "JP-03",
    }
    assert {row.institution_id for row in unconfirmed} == {
        "US-03", "JP-02", "EU-04", "CN-01", "CN-02", "CN-03",
    }
    assert all(row.access_priority == AccessPriority.API_FIRST for row in documented)
    assert all(row.access_priority == AccessPriority.API_AUDIT_FIRST for row in unconfirmed)
    assert all(not row.api_families and not row.api_documentation_urls for row in unconfirmed)
    assert profiles_by_api_availability(ApiAvailability.NOT_OFFERED) == ()
    assert len(documented) == 15
    assert len(unconfirmed) == 6


def test_api_availability_does_not_imply_connector_or_live_validation():
    imf = get_source_profile("INT-01")
    bea = get_source_profile("US-04")
    world_bank = get_source_profile("INT-04")

    assert imf.api_availability == ApiAvailability.DOCUMENTED
    assert imf.adapter_status == AdapterStatus.FIXTURES_ONLY
    assert imf.live_validation == LiveValidation.NOT_RUN
    assert bea.api_availability == ApiAvailability.DOCUMENTED
    assert bea.adapter_status == AdapterStatus.PARTIAL
    assert bea.fixture_scope == FixtureScope.SOURCE_SPECIFIC
    assert bea.live_validation == LiveValidation.PARTIAL
    assert "GetDataSetList metadata only" in bea.live_scope
    assert world_bank.api_availability == ApiAvailability.DOCUMENTED
    assert world_bank.adapter_status == AdapterStatus.PARTIAL
    assert world_bank.live_validation == LiveValidation.PARTIAL
    assert "fixed route only" in world_bank.live_scope


def test_sdmx_route_clients_are_partial_and_do_not_claim_live_validation():
    for institution_id in ("INT-02", "INT-03", "EU-01", "EU-02", "EU-03", "EU-05"):
        profile = get_source_profile(institution_id)
        assert profile.adapter_status == AdapterStatus.PARTIAL
        assert profile.fixture_scope == FixtureScope.SOURCE_SPECIFIC
        assert profile.live_validation == LiveValidation.NOT_RUN
        assert "mocked route tests" in profile.status_note
        assert "live" in profile.status_note


def test_authentication_profiles_only_contain_environment_variable_names():
    bea = get_source_profile("US-04")
    estat = get_source_profile("JP-03")
    unauthenticated = get_source_profile("INT-04")

    assert (bea.authentication, bea.credential_env_var) == (AuthRequirement.REQUIRED, "BEA_API_KEY")
    assert (estat.authentication, estat.credential_env_var) == (AuthRequirement.REQUIRED, "ESTAT_APP_ID")
    assert bea.adapter_status == estat.adapter_status == AdapterStatus.PARTIAL
    assert bea.fixture_scope == estat.fixture_scope == FixtureScope.SOURCE_SPECIFIC
    assert bea.live_validation == estat.live_validation == LiveValidation.PARTIAL
    assert "metadata only" in bea.live_scope and "metadata only" in estat.live_scope
    assert "no observation ingestion" in bea.live_scope
    assert "no observation ingestion" in estat.live_scope
    assert get_source_profile("US-01").api_provider == "Federal Reserve Bank of St. Louis (FRED)"
    assert get_source_profile("US-01").credential_env_var == "FRED_API_KEY"
    assert (get_source_profile("US-05").authentication,
            get_source_profile("US-05").credential_env_var) == (
                AuthRequirement.OPTIONAL, "BLS_API_KEY",
            )
    assert (get_source_profile("US-06").authentication,
            get_source_profile("US-06").credential_env_var) == (
                AuthRequirement.REQUIRED, "CENSUS_API_KEY",
            )
    assert (unauthenticated.authentication, unauthenticated.credential_env_var) == (AuthRequirement.NONE, None)
    assert "secret" not in str([row.to_dict() for row in all_source_profiles()]).lower()


def test_us_rest_clients_have_source_fixture_scope_but_no_live_claim():
    for identity in ("US-02", "US-05", "US-06"):
        profile = get_source_profile(identity)
        assert profile.adapter_status == AdapterStatus.PARTIAL
        assert profile.fixture_scope == FixtureScope.SOURCE_SPECIFIC
        assert profile.live_validation == LiveValidation.NOT_RUN
        assert "synthetic fixture" in profile.status_note
    assert "keyless v1" in get_source_profile("US-05").status_note
    assert "no v2 fallback" in get_source_profile("US-05").status_note
    assert get_source_profile("US-01").adapter_status == AdapterStatus.NOT_IMPLEMENTED


def test_unconfirmed_api_is_not_recorded_as_absent_or_given_a_guessed_endpoint():
    for row in profiles_by_api_availability(ApiAvailability.UNCONFIRMED):
        document = row.to_dict()
        assert document["api_availability"] == "unconfirmed"
        assert document["api_documentation_urls"] == []
        assert document["api_families"] == []
        assert document["authentication"] == "unknown"
        assert "api_endpoint" not in document
    assert "not proof" in get_source_profile("US-03").status_note


def test_profiles_reject_insecure_docs_urls_and_unsubstantiated_api_claims():
    row = get_source_profile("US-03")
    with pytest.raises(ValueError, match="HTTPS"):
        replace(row, official_source_urls=("http://home.treasury.gov/data",))
    with pytest.raises(ValueError, match="unconfirmed APIs"):
        replace(row, api_families=("REST",))
    with pytest.raises(ValueError, match="environment variable"):
        replace(get_source_profile("US-04"), credential_env_var="short")


def test_profile_validation_requires_exact_live_scope_and_valid_scenario():
    with pytest.raises(ValueError, match="A-H"):
        replace(get_source_profile("INT-04"), scenario_ids=("Z",))
    with pytest.raises(ValueError, match="exact scope"):
        replace(get_source_profile("INT-04"), live_scope=None)
    with pytest.raises(ValueError, match="one of A-H"):
        profiles_by_scenario("AA")
    with pytest.raises(TypeError, match="ApiAvailability"):
        profiles_by_api_availability("documented")
    with pytest.raises(ValueError, match="uppercase environment variable"):
        replace(get_source_profile("US-05"), credential_env_var="bls-key")
    with pytest.raises(ValueError, match="API provider"):
        replace(get_source_profile("EU-04"), api_provider="not verified")


def test_profile_json_view_is_detached_and_has_research_date():
    profile = get_source_profile("EU-02")
    document = profile.to_dict()
    document["api_families"].append("invented")

    assert profile.api_families == (
        "Catalogue API", "SDMX 2.1", "SDMX 3.0", "Statistics API JSON-stat",
    )
    assert profile.docs_checked_on == date(2026, 10, 25)
    assert profile.fixture_scope == FixtureScope.SOURCE_SPECIFIC


def test_catalog_api_snapshot_lists_every_registry_source():
    reference_dir = Path(__file__).parents[1] / "docs" / "operator" / "reference"
    catalog = (reference_dir / "INSTITUTION_CATALOG.md").read_text(encoding="utf-8")
    registry_ids = {row.institution_id for row in all_source_profiles()}
    inventory = catalog.split("## 초기 기관·서비스 21개", 1)[1].split(
        "## 21개 기관 API 우선 상태 스냅샷", 1
    )[0]
    inventory_ids = re.findall(r"^\| ([A-Z]+-\d{2}) \|", inventory, re.MULTILINE)
    assert len(inventory_ids) == 21
    assert set(inventory_ids) == registry_ids

    snapshot = catalog.split("## 21개 기관 API 우선 상태 스냅샷", 1)[1].split(
        "## 대표 유형 및 테스트 연결", 1
    )[0]
    audit = (reference_dir / "INSTITUTION_API_AUDIT.md").read_text(encoding="utf-8")

    for row in all_source_profiles():
        assert f"| {row.institution_id} |" in snapshot
        assert f"| {row.institution_id} |" in audit
