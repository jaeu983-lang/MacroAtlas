"""Integrity checks for write-once typed-series artifacts."""
from datetime import UTC, datetime
from pathlib import Path

import pytest

from macro_data_platform.config import Settings
from macro_data_platform.contracts import Observation, ObservationStatus, TimeSeries
from macro_data_platform.storage.typed_series import (
    load_typed_series_artifact,
    save_typed_series_artifact,
)


def _fixture_series(settings):
    raw = settings._inside("data/raw/fixture/source.json")
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'{"source":"fixture"}')
    manifest = settings._inside("data/raw/fixture/manifest.json")
    manifest.write_text('{"raw_sha256":"fixture"}', encoding="utf-8")
    return TimeSeries(
        source_agency="Fixture Agency",
        dataset_id="fixture-dataset",
        series_id="FIXTURE.VALUE",
        dimensions={"country": "US"},
        calendar="gregorian",
        observations=(
            Observation("2025", 0, ObservationStatus.OBSERVED),
            Observation("2024", None, ObservationStatus.MISSING),
        ),
        retrieved_at=datetime(2026, 10, 28, tzinfo=UTC),
        source_url="https://example.org/fixture",
        raw_ref="data/raw/fixture/source.json",
        manifest_ref="data/raw/fixture/manifest.json",
        unit="USD",
        frequency="annual",
        frequency_basis="request_contract",
    )


def test_saved_artifact_preserves_typed_observations_and_source_refs(tmp_path):
    settings = Settings(tmp_path)
    series = _fixture_series(settings)
    reference = save_typed_series_artifact(
        settings,
        series=(series,),
        engine_id="fixture/1",
        quality={"status": "passed", "issues": [], "freshness": {
            "status": "FRESH", "policy_id": "frequency_max_age_v2",
            "policy_fingerprint_sha256": "a" * 64,
        }},
    )

    document = load_typed_series_artifact(settings, reference)
    entry = document["series"][0]

    assert document["schema_version"] == "typed-series-artifact-v1"
    assert entry["contract"]["raw_ref"] == "data/raw/fixture/source.json"
    assert entry["contract"]["manifest_ref"] == "data/raw/fixture/manifest.json"
    assert entry["contract"]["observations"] == [
        {"period": "2025", "raw_value": 0, "status": "observed", "source_period": None},
        {"period": "2024", "raw_value": None, "status": "missing", "source_period": None},
    ]
    manifest = Path(tmp_path, reference["typed_series_manifest_path"])
    assert manifest.is_file()
    assert reference["observation_count"] == 2


def test_artifact_reader_detects_content_hash_mismatch(tmp_path):
    settings = Settings(tmp_path)
    reference = save_typed_series_artifact(
        settings,
        series=(_fixture_series(settings),),
        engine_id="fixture/1",
        quality={"status": "passed", "issues": [], "freshness": {"status": "FRESH"}},
    )
    artifact = Path(tmp_path, reference["typed_series_path"])
    artifact.write_bytes(artifact.read_bytes() + b" ")

    with pytest.raises(ValueError, match="artifact hash mismatch"):
        load_typed_series_artifact(settings, reference)


def test_artifact_reader_detects_changed_source_bytes(tmp_path):
    settings = Settings(tmp_path)
    reference = save_typed_series_artifact(
        settings,
        series=(_fixture_series(settings),),
        engine_id="fixture/1",
        quality={"status": "passed", "issues": [], "freshness": {"status": "FRESH"}},
    )
    Path(tmp_path, "data/raw/fixture/source.json").write_bytes(b'{"source":"changed"}')

    with pytest.raises(ValueError, match="source file is missing or changed|source hash mismatch"):
        load_typed_series_artifact(settings, reference)


@pytest.mark.parametrize("freshness_status", ["STALE", "FRESHNESS_UNVERIFIED"])
def test_nonfresh_series_cannot_be_persisted_as_success(tmp_path, freshness_status):
    settings = Settings(tmp_path)
    series = _fixture_series(settings)
    with pytest.raises(ValueError, match="FRESH"):
        save_typed_series_artifact(
            settings,
            series=(series,),
            engine_id="fixture/1",
            quality={"status": "passed", "issues": [], "freshness": {
                "status": freshness_status,
            }},
        )
