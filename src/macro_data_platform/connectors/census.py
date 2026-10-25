"""Bounded Census Data API metadata and header/row JSON requests."""
import re
from collections.abc import Mapping, Sequence

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    JsonApiResponse,
    JsonApiTransport,
    validate_parameters,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_ROOT = "https://api.census.gov/data"
API_DOCS = "https://www.census.gov/data/developers.html"


def _schema() -> ConnectorFailure:
    return ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Census response did not match the selected metadata or table contract.")


def _dataset(value: str) -> str:
    if (not isinstance(value, str) or len(value) > 512
            or not 1 <= len(value.split("/")) <= 8
            or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", part) for part in value.split("/"))):
        raise ValueError("Census dataset must be a bounded official catalogue path")
    return value


class CensusClient:
    """Metadata is keyless; data keys come only from Settings, with no numeric conversion."""

    def __init__(self, settings: Settings, transport: JsonApiTransport | None = None):
        self.settings = settings
        self.transport = transport or JsonApiTransport(settings)

    def _metadata(self, endpoint: str, operation: str, field: str, expected: type) -> JsonApiResponse:
        response = self.transport.get_json("Census", endpoint, operation, {}, "")
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get(field), expected):
            raise _schema()
        return response

    def list_datasets(self) -> JsonApiResponse:
        return self._metadata(API_ROOT + ".json", "dataset_catalogue", "dataset", list)

    def get_variables(self, dataset: str) -> JsonApiResponse:
        return self._metadata(f"{API_ROOT}/{_dataset(dataset)}/variables.json", "variables", "variables", dict)

    def get_geographies(self, dataset: str) -> JsonApiResponse:
        return self._metadata(f"{API_ROOT}/{_dataset(dataset)}/geography.json", "geographies", "fips", list)

    def get_data(
        self, dataset: str, variables: Sequence[str], predicates: Mapping[str, str | int],
    ) -> JsonApiResponse:
        dataset = _dataset(dataset)
        if (not isinstance(variables, (list, tuple)) or not 1 <= len(variables) <= 50
                or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", name)
                       for name in variables) or len(set(variables)) != len(variables)):
            raise ValueError("Census get requires 1 to 50 distinct variable identifiers")
        selected = validate_parameters(predicates, frozenset({"key", "get", "api_key"}))
        if not selected:
            raise ValueError("Census data requires explicit geography or other predicates")
        credential = self.settings.census_api_key
        if not credential:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                   "CENSUS_API_KEY is not configured in local settings.")
        response = self.transport.get_json(
            "Census", f"{API_ROOT}/{dataset}", "data",
            {"get": ",".join(variables), **selected, "key": credential}, credential,
        )
        table = response.payload
        if (not isinstance(table, list) or not table or not isinstance(table[0], list)
                or not table[0] or any(not isinstance(name, str) for name in table[0])
                or len(set(table[0])) != len(table[0]) or not set(variables) <= set(table[0])):
            raise _schema()
        if any(not isinstance(row, list) or len(row) != len(table[0])
               or any(value is not None and not isinstance(value, str) for value in row)
               for row in table[1:]):
            raise _schema()
        return response
