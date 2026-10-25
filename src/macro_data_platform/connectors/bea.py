"""BEA Data API v1 JSON client; no implicit discovery or network access."""
from collections.abc import Mapping
from typing import Any

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    JsonApiResponse,
    JsonApiTransport,
    validate_parameters,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_URL = "https://apps.bea.gov/api/data"
API_DOCS = "https://apps.bea.gov/API/docs/index.htm"
_METHODS = {
    "getdatasetlist": "GetDataSetList",
    "getparameterlist": "GetParameterList",
    "getparametervalues": "GetParameterValues",
    "getparametervaluesfiltered": "GetParameterValuesFiltered",
    "getdata": "GetData",
}
_RESERVED = frozenset({"userid", "method", "resultformat"})


class BEAClient:
    """Client for documented BEA methods. Its API key is always taken from Settings."""

    def __init__(self, settings: Settings, transport: JsonApiTransport | None = None):
        self.settings = settings
        self.transport = transport or JsonApiTransport(settings)

    def request(
        self,
        method: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> JsonApiResponse:
        credential = self.settings.bea_api_key
        if not credential:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                "BEA_API_KEY is not configured; set it in the local .env or process environment.",
            )
        if not isinstance(method, str) or method.casefold() not in _METHODS:
            raise ValueError("Unsupported BEA API method")
        canonical_method = _METHODS[method.casefold()]
        safe_parameters = validate_parameters(parameters, _RESERVED)
        query = {"UserID": credential, "method": canonical_method,
                 "ResultFormat": "JSON", **safe_parameters}
        return self.transport.get_json("BEA", API_URL, canonical_method, query, credential)

    def get_dataset_list(self) -> JsonApiResponse:
        return self.request("GetDataSetList")

    def get_parameter_list(self, dataset_name: str) -> JsonApiResponse:
        return self.request("GetParameterList", {"DatasetName": dataset_name})

    def get_parameter_values(
        self,
        dataset_name: str,
        parameter_name: str,
        filters: Mapping[str, str | int] | None = None,
    ) -> JsonApiResponse:
        parameters: dict[str, Any] = {
            "DatasetName": dataset_name,
            "ParameterName": parameter_name,
        }
        if filters:
            parameters.update(filters)
        return self.request("GetParameterValues", parameters)

    def get_data(
        self,
        dataset_name: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> JsonApiResponse:
        query = {"DatasetName": dataset_name, **(dict(parameters) if parameters else {})}
        return self.request("GetData", query)
