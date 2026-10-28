"""e-Stat REST API v3.0 JSON client; no implicit discovery or network access."""
from collections.abc import Mapping

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    JsonApiResponse,
    JsonApiTransport,
    validate_parameters,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_ROOT = "https://api.e-stat.go.jp/rest/3.0/app/json"
API_DOCS = "https://www.e-stat.go.jp/api/en/api-info/api-spec"
_METHODS = {
    "getstatslist": "getStatsList",
    "getmetainfo": "getMetaInfo",
    "getstatsdata": "getStatsData",
}
_RESERVED = frozenset({"appid", "method"})


class EStatClient:
    """Client for e-Stat table, metadata and statistical data GET methods."""

    def __init__(self, settings: Settings, transport: JsonApiTransport | None = None):
        self.settings = settings
        self.transport = transport or JsonApiTransport(settings)

    def request(
        self,
        method: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> JsonApiResponse:
        credential = self.settings.estat_app_id
        if not credential:
            raise ConnectorFailure(
                StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                "ESTAT_APP_ID is not configured; set it in the local .env or process environment.",
            )
        if not isinstance(method, str) or method.casefold() not in _METHODS:
            raise ValueError("Unsupported e-Stat API method")
        canonical_method = _METHODS[method.casefold()]
        endpoint = f"{API_ROOT}/{canonical_method}"
        safe_parameters = validate_parameters(parameters, _RESERVED)
        query = {"appId": credential, **safe_parameters}
        return self.transport.get_json(
            "e-Stat", endpoint, canonical_method, query, credential,
        )

    def get_stats_list(self, parameters: Mapping[str, str | int] | None = None) -> JsonApiResponse:
        return self.request("getStatsList", parameters)

    def get_meta_info(self, stats_data_id: str) -> JsonApiResponse:
        return self.request("getMetaInfo", {"statsDataId": stats_data_id})

    def get_stats_data(
        self,
        stats_data_id: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> JsonApiResponse:
        query = {"statsDataId": stats_data_id, **(dict(parameters) if parameters else {})}
        return self.request("getStatsData", query)
