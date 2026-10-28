"""Pinned dataset contract receipts alongside independently hashed raw archives."""
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import _redact_payload
from macro_data_platform.discovery.datasets import DatasetProfile
from macro_data_platform.storage.api_responses import SavedApiArtifact, read_api_response

_MAX_RECEIPT = 128 * 1024


def _digest(document) -> str:
    return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedDatasetArtifact:
    receipt_path: str
    receipt_sha256: str
    raw: SavedApiArtifact
    profile_id: str
    profile_sha256: str
    validation_status: str


def save_dataset_receipt(settings: Settings, profile: DatasetProfile, raw: SavedApiArtifact,
                         validation: dict, *, fixture_mode: bool = False) -> SavedDatasetArtifact:
    loaded = read_api_response(settings, raw)
    if (raw.institution_id != profile.institution_id or loaded.manifest["dataset_id"] != profile.dataset_id
            or validation.get("status") not in {"contract_validated", "needs_review"}):
        raise ValueError("Dataset receipt must agree with the archived source and validation")
    document = {"schema_version": 1, "profile": profile.to_dict(), "profile_sha256": profile.fingerprint,
                "raw": asdict(raw), "validation": validation,
                "run_evidence": "synthetic_fixture" if fixture_mode else "source_request_not_live_verified",
                "request_parameters": loaded.manifest["request_parameters"]}
    secrets = tuple(value for value in (settings.bea_api_key, settings.estat_app_id, settings.fred_api_key,
                                        settings.census_api_key, settings.bls_api_key) if value)
    if _redact_payload(document, secrets) != document:
        raise ValueError("Dataset receipt contains a configured credential")
    body = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8") + b"\n"
    if len(body) > _MAX_RECEIPT:
        raise ValueError("Dataset receipt exceeds the supported size")
    relative = (Path(raw.manifest_path).parent / "dataset_validation.json").as_posix()
    path = settings._inside(relative)
    with path.open("xb") as stream:
        stream.write(body)
    return SavedDatasetArtifact(relative, hashlib.sha256(body).hexdigest(), raw, profile.profile_id,
                                profile.fingerprint, validation["status"])


def read_dataset_artifact(settings: Settings, saved: SavedDatasetArtifact) -> tuple[dict, bytes]:
    expected = (Path(saved.raw.manifest_path).parent / "dataset_validation.json").as_posix()
    if saved.receipt_path != expected:
        raise ValueError("Dataset receipt must be beside its pinned source archive")
    path = settings._inside(saved.receipt_path)
    with path.open("rb") as stream:
        body = stream.read(_MAX_RECEIPT + 1)
    if len(body) > _MAX_RECEIPT or hashlib.sha256(body).hexdigest() != saved.receipt_sha256:
        raise ValueError("Dataset receipt hash or size mismatch")
    document = json.loads(body)
    if (document.get("schema_version") != 1 or document.get("raw") != asdict(saved.raw)
            or document.get("profile_sha256") != saved.profile_sha256
            or _digest(document["profile"]) != saved.profile_sha256
            or document["profile"]["profile_id"] != saved.profile_id
            or document["validation"]["status"] != saved.validation_status):
        raise ValueError("Dataset receipt differs from its pinned contract")
    loaded = read_api_response(settings, saved.raw)
    if (document["profile"]["institution_id"] != loaded.manifest["institution_id"]
            or document["profile"]["dataset_id"] != loaded.manifest["dataset_id"]
            or document["request_parameters"] != loaded.manifest["request_parameters"]):
        raise ValueError("Dataset receipt source selection differs from the archive")
    return document, loaded.body
