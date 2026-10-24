"""Selected WDI GDP retrieval engine, independently testable with a fixture transport."""
from dataclasses import asdict
from typing import Protocol

from macro_data_platform.config import Settings
from macro_data_platform.connectors.worldbank import (
    ConnectorFailure,
    Download,
    GDPQuery,
    WorldBankTransport,
    parse_gdp,
)
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus
from macro_data_platform.orchestration.models import StageInput
from macro_data_platform.storage.raw_downloads import save_worldbank_download


class GDPTransport(Protocol):
    def fetch(self, query: GDPQuery) -> Download: ...


class WorldBankGDPEngine:
    def __init__(self, settings: Settings, transport: GDPTransport | None = None):
        self.settings = settings
        self.transport = transport if transport is not None else WorldBankTransport(settings)

    def run(self, request: StageInput) -> StageResult[dict]:
        # Whitelist fields: keys, arbitrary URLs and unrelated inputs must not enter history/files.
        data = request.input_data
        if not isinstance(data, dict) or set(data) != {"start_year", "end_year"}:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected only start_year and end_year query fields.",))
        try:
            query = GDPQuery(**data)
        except ValueError:
            return StageResult(StageStatus.FAILED_TERMINAL, error_code=ErrorCode.SCHEMA_CHANGED,
                               warnings=("Expected 1 to 10 annual periods in 1960..2100.",))
        paths = {}
        refs = ()
        try:
            download = self.transport.fetch(query)
            if download.source_url != query.url:
                raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                                       "Transport response URL differs from the approved endpoint.")
            saved = save_worldbank_download(self.settings, download)
            paths = asdict(saved)
            refs = (saved.raw_path, saved.manifest_path)
            parsed = parse_gdp(download, query)
        except ConnectorFailure as failure:
            return StageResult(failure.status, {**paths, "source_url": query.url}, refs,
                               (str(failure),), failure.code)
        except OSError:
            return StageResult(StageStatus.FAILED_TERMINAL,
                               {**paths, "source_url": query.url}, refs,
                               ("Local response preservation failed; existing files retained.",),
                               ErrorCode.INTERNAL_BUG)
        return StageResult(StageStatus.SUCCEEDED, {**parsed, **paths, "mode": download.kind.value},
                           refs, ("Minimal parsing only; full quality validation is not implemented.",))
