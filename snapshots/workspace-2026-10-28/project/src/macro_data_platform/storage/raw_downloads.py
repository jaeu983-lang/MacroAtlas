"""Compatibility entry point for the World Bank raw-response archive."""
from dataclasses import dataclass
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import Download
from macro_data_platform.storage.api_responses import save_api_response


@dataclass(frozen=True)
class SavedDownload:
    raw_path: str
    manifest_path: str


def save_worldbank_download(settings: Settings, download: Download) -> SavedDownload:
    saved = save_api_response(settings, download, _artifact_id=uuid4().hex)
    return SavedDownload(saved.raw_path, saved.manifest_path)
