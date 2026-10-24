"""Minimal iteration 03 response preservation; no normalized store or hash catalogue."""
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import API_DOCS, TERMS_URL, Download


@dataclass(frozen=True)
class SavedDownload:
    raw_path: str
    manifest_path: str


def save_worldbank_download(settings: Settings, download: Download) -> SavedDownload:
    # An exclusive new directory and exclusive files prevent silent raw overwrites.
    relative = Path(settings.data_dir) / "raw" / "worldbank" / uuid4().hex
    directory = settings._inside(str(relative))
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    raw = settings._inside(str(relative / "response.json"))
    with raw.open("xb") as stream:
        stream.write(download.body)
    manifest = settings._inside(str(relative / "request.json"))
    metadata = {
        "source_agency": "World Bank", "source_url": download.source_url,
        "retrieved_at": download.retrieved_at.isoformat(), "http_status": download.status_code,
        "content_type": download.content_type, "mode": download.kind.value,
        "byte_count": len(download.body), "raw_path": raw.relative_to(settings.project_root).as_posix(),
        "api_documentation_url": API_DOCS, "terms_url": TERMS_URL,
        "license_note": "Dataset-specific terms apply; no blanket license inferred.",
        "representation": "HTTP entity bytes after requests content decoding; not wire bytes.",
    }
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, allow_nan=False, indent=2)
    return SavedDownload(metadata["raw_path"], manifest.relative_to(settings.project_root).as_posix())
