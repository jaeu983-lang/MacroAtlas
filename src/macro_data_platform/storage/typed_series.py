"""Write-once, hash-linked persistence for freshness-passed typed series."""
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.contracts import Observation, ObservationStatus, TimeSeries

TYPED_SERIES_SCHEMA = "typed-series-artifact-v1"
TYPED_SERIES_MANIFEST_SCHEMA = "typed-series-manifest-v1"
MAX_TYPED_SERIES_BYTES = 64 * 1024 * 1024
MAX_TYPED_SERIES_MANIFEST_BYTES = 64 * 1024
MAX_TYPED_SERIES_SOURCE_REF_BYTES = 64 * 1024 * 1024


def _series_document(series: TimeSeries) -> dict:
    return {
        "source_agency": series.source_agency,
        "dataset_id": series.dataset_id,
        "series_id": series.series_id,
        "dimensions": dict(series.dimensions),
        "calendar": series.calendar,
        "observations": [
            {
                "period": item.period,
                "raw_value": item.raw_value,
                "status": item.status.value,
                "source_period": item.source_period,
            }
            for item in series.observations
        ],
        "retrieved_at": series.retrieved_at.isoformat(),
        "source_url": series.source_url,
        "raw_ref": series.raw_ref,
        "manifest_ref": series.manifest_ref,
        "unit": series.unit,
        "currency": series.currency,
        "frequency": series.frequency,
        "frequency_basis": series.frequency_basis,
        "source_revision": series.source_revision,
    }


def _validate_series_refs(settings: Settings, series: Sequence[TimeSeries]) -> list[dict]:
    refs = {}
    for item in series:
        for role, reference in (("raw", item.raw_ref), ("manifest", item.manifest_ref)):
            relative = Path(reference)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("typed series source reference must be repository-relative")
            if not relative.is_relative_to(Path(settings.data_dir) / "raw"):
                raise ValueError("typed series source reference must point into raw storage")
            path = settings.project_root / relative
            if any(parent.is_symlink() for parent in (path, *path.parents)
                   if parent != settings.project_root):
                raise ValueError("typed series source reference must not traverse a symlink")
            settings._inside(reference)
            if not path.is_file():
                raise ValueError("typed series source reference must exist as a file")
            if path.stat().st_size > MAX_TYPED_SERIES_SOURCE_REF_BYTES:
                raise ValueError("typed series source reference exceeds its read limit")
            digest = hashlib.sha256()
            byte_count = 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    byte_count += len(chunk)
                    digest.update(chunk)
            refs[(role, relative.as_posix())] = {
                "role": role, "path": relative.as_posix(),
                "sha256": digest.hexdigest(), "bytes": byte_count,
            }
    return [refs[key] for key in sorted(refs)]


def _check_no_symlinks(project_root: Path, path: Path) -> None:
    current = path
    while current != project_root:
        if current.is_symlink():
            raise ValueError("typed series artifact path must not traverse a symlink")
        current = current.parent
    if current.is_symlink():
        raise ValueError("project root must not be a symlink")


def _validate_series_document(contract: Mapping) -> TimeSeries:
    fields = {
        "source_agency", "dataset_id", "series_id", "dimensions", "calendar",
        "observations", "retrieved_at", "source_url", "raw_ref", "manifest_ref",
        "unit", "currency", "frequency", "frequency_basis", "source_revision",
    }
    if not isinstance(contract, Mapping) or set(contract) != fields:
        raise ValueError("typed series contract fields do not match the schema")
    rows = contract["observations"]
    if not isinstance(rows, list):
        raise TypeError("typed series observations are invalid")
    observations = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
                "period", "raw_value", "status", "source_period"}:
            raise ValueError("typed series observation fields do not match the schema")
        observations.append(Observation(
            row["period"], row["raw_value"], ObservationStatus(row["status"]),
            row["source_period"],
        ))
    return TimeSeries(
        source_agency=contract["source_agency"],
        dataset_id=contract["dataset_id"],
        series_id=contract["series_id"],
        dimensions=contract["dimensions"],
        calendar=contract["calendar"],
        observations=tuple(observations),
        retrieved_at=datetime.fromisoformat(contract["retrieved_at"]),
        source_url=contract["source_url"],
        raw_ref=contract["raw_ref"],
        manifest_ref=contract["manifest_ref"],
        unit=contract["unit"],
        currency=contract["currency"],
        frequency=contract["frequency"],
        frequency_basis=contract["frequency_basis"],
        source_revision=contract["source_revision"],
    )


def save_typed_series_artifact(
    settings: Settings,
    *,
    series: Sequence[TimeSeries],
    engine_id: str,
    quality: Mapping,
) -> dict:
    """Persist passing typed series and return the hash-linked artifact references."""
    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    if (not isinstance(series, Sequence) or isinstance(series, (str, bytes)) or not series
            or any(not isinstance(item, TimeSeries) for item in series)):
        raise ValueError("series must contain one or more TimeSeries values")
    if not isinstance(engine_id, str) or re.fullmatch(r"[a-z0-9_/-]{1,80}", engine_id) is None:
        raise ValueError("engine_id is invalid")
    if not isinstance(quality, Mapping) or quality.get("status") != "passed":
        raise ValueError("only quality-passed typed series can be persisted")
    freshness = quality.get("freshness")
    if isinstance(freshness, list) and len(freshness) != len(series):
        raise ValueError("per-series freshness count must match typed series count")
    if isinstance(freshness, dict) and len(series) != 1:
        raise ValueError("a single freshness record can describe only one typed series")
    if not isinstance(freshness, (dict, list)):
        raise TypeError("quality must include freshness evidence")
    if isinstance(freshness, dict) and freshness.get("status") != "FRESH":
        raise ValueError("only FRESH typed series can be persisted")
    if isinstance(freshness, list) and any(
            not isinstance(item, Mapping) or item.get("status") != "FRESH"
            for item in freshness):
        raise ValueError("every typed series must have FRESH quality evidence")

    source_refs = _validate_series_refs(settings, series)
    if isinstance(freshness, dict):
        freshness_rows = [freshness]
    else:
        freshness_rows = list(freshness)
    created_at = datetime.now(UTC).isoformat()
    document = {
        "schema_version": TYPED_SERIES_SCHEMA,
        "engine_id": engine_id,
        "created_at": created_at,
        "source_refs": source_refs,
        "quality": dict(quality),
        "series": [
            {"contract": _series_document(item), "freshness": freshness_rows[index]}
            for index, item in enumerate(series)
        ],
    }
    artifact_bytes = json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if not artifact_bytes or len(artifact_bytes) > MAX_TYPED_SERIES_BYTES:
        raise ValueError("typed series artifact exceeds its output limit")
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    root_relative = Path(settings.data_dir) / "processed" / "typed_series"
    root_candidate = settings.project_root / root_relative
    _check_no_symlinks(settings.project_root, root_candidate)
    root = settings._inside(root_relative.as_posix())
    root.mkdir(parents=True, exist_ok=True)
    artifact_id = uuid4().hex
    directory = root / artifact_id
    directory.mkdir(exist_ok=False)
    artifact_path = directory / "series.json"
    manifest_path = directory / "manifest.json"
    artifact_relative = artifact_path.relative_to(settings.project_root).as_posix()
    manifest_relative = manifest_path.relative_to(settings.project_root).as_posix()
    with artifact_path.open("xb") as stream:
        stream.write(artifact_bytes)
    manifest = {
        "schema_version": TYPED_SERIES_MANIFEST_SCHEMA,
        "engine_id": engine_id,
        "created_at": created_at,
        "artifact_path": artifact_relative,
        "artifact_sha256": artifact_sha256,
        "artifact_bytes": len(artifact_bytes),
        "source_refs": source_refs,
        "series_count": len(series),
        "observation_count": sum(len(item.observations) for item in series),
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2,
    ).encode("utf-8")
    with manifest_path.open("xb") as stream:
        stream.write(manifest_bytes)
    return {
        "typed_series_path": artifact_relative,
        "typed_series_sha256": artifact_sha256,
        "typed_series_manifest_path": manifest_relative,
        "typed_series_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "series_count": len(series),
        "observation_count": sum(len(item.observations) for item in series),
    }


def load_typed_series_artifact(settings: Settings, reference: Mapping) -> dict:
    """Load an artifact only after checking its path, content, and linked manifest hashes."""
    required = {
        "typed_series_path", "typed_series_sha256", "typed_series_manifest_path",
        "typed_series_manifest_sha256",
    }
    if not isinstance(reference, Mapping) or not required.issubset(reference):
        raise ValueError("typed series artifact reference is incomplete")
    paths = {}
    for key in ("typed_series_path", "typed_series_manifest_path"):
        relative = reference[key]
        if not isinstance(relative, str):
            raise TypeError("typed series artifact paths must be strings")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("typed series artifact path must be repository-relative")
        expected_root = Path(settings.data_dir) / "processed" / "typed_series"
        if not candidate.is_relative_to(expected_root):
            raise ValueError("typed series artifact path is outside its storage directory")
        path = settings.project_root / candidate
        _check_no_symlinks(settings.project_root, path)
        settings._inside(relative)
        if not path.is_file():
            raise ValueError("typed series artifact file is missing")
        size_limit = (MAX_TYPED_SERIES_BYTES if key == "typed_series_path"
                      else MAX_TYPED_SERIES_MANIFEST_BYTES)
        if path.stat().st_size > size_limit:
            raise ValueError("typed series artifact exceeds its read limit")
        paths[key] = path

    artifact_bytes = paths["typed_series_path"].read_bytes()
    manifest_bytes = paths["typed_series_manifest_path"].read_bytes()
    if len(artifact_bytes) > MAX_TYPED_SERIES_BYTES:
        raise ValueError("typed series artifact exceeds its read limit")
    if len(manifest_bytes) > MAX_TYPED_SERIES_MANIFEST_BYTES:
        raise ValueError("typed series manifest exceeds its read limit")
    if hashlib.sha256(artifact_bytes).hexdigest() != reference["typed_series_sha256"]:
        raise ValueError("typed series artifact hash mismatch")
    if hashlib.sha256(manifest_bytes).hexdigest() != reference["typed_series_manifest_sha256"]:
        raise ValueError("typed series manifest hash mismatch")
    try:
        document = json.loads(artifact_bytes)
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, ValueError):
        raise ValueError("typed series artifact JSON is invalid") from None
    if (not isinstance(document, dict) or document.get("schema_version") != TYPED_SERIES_SCHEMA
            or not isinstance(document.get("quality"), dict)
            or document["quality"].get("status") != "passed"
            or not isinstance(document.get("series"), list) or not document["series"]
            or not isinstance(manifest, dict)
            or manifest.get("schema_version") != TYPED_SERIES_MANIFEST_SCHEMA
            or manifest.get("artifact_path") != reference["typed_series_path"]
            or manifest.get("artifact_sha256") != reference["typed_series_sha256"]
            or manifest.get("artifact_bytes") != len(artifact_bytes)
            or manifest.get("source_refs") != document.get("source_refs")):
        raise ValueError("typed series artifact and manifest do not match")
    series_count = len(document["series"])
    observation_count = 0
    contract_refs = set()
    for entry in document["series"]:
        if (not isinstance(entry, dict) or not isinstance(entry.get("contract"), dict)
                or not isinstance(entry.get("freshness"), dict)
                or entry["freshness"].get("status") != "FRESH"):
            raise ValueError("typed series artifact contains an unverified series")
        contract = entry["contract"]
        _validate_series_document(contract)
        observations = contract["observations"]
        observation_count += len(observations)
        for key in ("raw_ref", "manifest_ref"):
            if not isinstance(contract.get(key), str):
                raise TypeError("typed series source reference is invalid")
            role = "raw" if key == "raw_ref" else "manifest"
            contract_refs.add((role, contract[key]))
    source_refs = document.get("source_refs")
    if not isinstance(source_refs, list):
        raise TypeError("typed series source references are invalid")
    verified_source_refs = set()
    for source_ref in source_refs:
        if (not isinstance(source_ref, dict)
                or source_ref.get("role") not in {"raw", "manifest"}
                or not isinstance(source_ref.get("path"), str)
                or not isinstance(source_ref.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", source_ref.get("sha256", "")) is None
                or type(source_ref.get("bytes")) is not int):
            raise ValueError("typed series source reference record is invalid")
        candidate = Path(source_ref["path"])
        if (candidate.is_absolute() or ".." in candidate.parts
                or not candidate.is_relative_to(Path(settings.data_dir) / "raw")):
            raise ValueError("typed series source path is invalid")
        path = settings.project_root / candidate
        _check_no_symlinks(settings.project_root, path)
        settings._inside(source_ref["path"])
        if (not path.is_file() or path.stat().st_size > MAX_TYPED_SERIES_SOURCE_REF_BYTES
                or path.stat().st_size != source_ref["bytes"]):
            raise ValueError("typed series source file is missing or changed")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != source_ref["sha256"]:
            raise ValueError("typed series source hash mismatch")
        verified_source_refs.add((source_ref["role"], source_ref["path"]))
    if (manifest.get("series_count") != series_count
            or manifest.get("observation_count") != observation_count
            or verified_source_refs != contract_refs):
        raise ValueError("typed series provenance counts or references do not match")
    return document
