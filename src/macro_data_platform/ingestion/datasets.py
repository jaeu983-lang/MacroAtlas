"""Explicit dataset execution; source routing and validation remain independently replaceable."""
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from macro_data_platform.config import Settings
from macro_data_platform.connectors.dataset_bindings import default_dataset_bindings
from macro_data_platform.connectors.official_api import JsonApiResponse
from macro_data_platform.connectors.official_files import OfficialFileResponse
from macro_data_platform.contracts import EvidenceKind
from macro_data_platform.discovery.datasets import get_dataset_profile
from macro_data_platform.ingestion.dataset_validators import validate_dataset_response
from macro_data_platform.storage.api_responses import save_api_response
from macro_data_platform.storage.datasets import SavedDatasetArtifact, save_dataset_receipt


class DatasetCollector:
    def __init__(self, settings: Settings, bindings: Mapping | None = None, *, fixture_mode: bool = False):
        if fixture_mode and bindings is None:
            raise ValueError("Fixture collection requires explicitly injected bindings")
        self.settings = settings
        self.bindings = default_dataset_bindings(settings) if bindings is None else dict(bindings)
        self.fixture_mode = fixture_mode

    def collect(self, profile_id: str, parameters: Mapping) -> SavedDatasetArtifact:
        profile = get_dataset_profile(profile_id)
        binding = self.bindings.get(profile.adapter_id)
        if binding is None:
            raise ValueError("Dataset adapter is unavailable; no fallback route is authorized")
        response = binding.fetch(profile, parameters)
        expected = JsonApiResponse if profile.access_method == "api" else OfficialFileResponse
        if not isinstance(response, expected):
            raise TypeError("Dataset response access method differs from its selected contract")
        if isinstance(response, OfficialFileResponse) and self.fixture_mode != (response.kind == EvidenceKind.FIXTURE):
            raise ValueError("Official file evidence differs from the collector mode")
        parts = urlsplit(response.source_url)
        if urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")) != profile.source_url:
            raise ValueError("Dataset response URL differs from its selected source")
        raw = save_api_response(self.settings, response, dataset_id=profile.dataset_id,
                                series_id=profile.fixed.get("series_id"),
                                expected_institution_id=profile.institution_id)
        # Keep completed raw files even when the source's tabular layout has changed.
        validation = validate_dataset_response(profile, response)
        return save_dataset_receipt(self.settings, profile, raw, validation, fixture_mode=self.fixture_mode)
