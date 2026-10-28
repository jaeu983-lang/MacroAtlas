"""FRED v1 JSON pages and metadata; ALFRED real-time windows stay explicit."""
import re
from datetime import date

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    JsonApiResponse,
    JsonApiTransport,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_ROOT = "https://api.stlouisfed.org/fred"
API_DOCS = "https://fred.stlouisfed.org/docs/api/fred/"


def _schema() -> ConnectorFailure:
    return ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "FRED response did not match the requested page or metadata contract.")


def _series_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
        raise ValueError("FRED series ID must be a bounded identifier")
    return value


def _date(value: str) -> str:
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("FRED dates must use valid YYYY-MM-DD values") from None
    return value


class FREDClient:
    """One bounded request per method; page methods never imply full-dataset coverage."""

    def __init__(self, settings: Settings, transport: JsonApiTransport | None = None):
        self.settings = settings
        self.transport = transport or JsonApiTransport(settings)

    def _get(self, path: str, operation: str, parameters: dict[str, str]) -> JsonApiResponse:
        credential = self.settings.fred_api_key
        if not credential:
            raise ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                                   "FRED_API_KEY is not configured in local settings.")
        response = self.transport.get_json(
            "FRED", f"{API_ROOT}/{path}", operation,
            {**parameters, "api_key": credential, "file_type": "json"}, credential,
        )
        if not isinstance(response.payload, dict) or "error_code" in response.payload:
            raise _schema()
        return response

    @staticmethod
    def _rows(response: JsonApiResponse, field: str) -> list[dict]:
        rows = response.payload.get(field)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise _schema()
        return rows

    @staticmethod
    def _page(response: JsonApiResponse, field: str, limit: int, offset: int) -> list[dict]:
        rows = FREDClient._rows(response, field)
        count = response.payload.get("count")
        if (type(count) is not int or count < 0
                or type(response.payload.get("offset")) is not int
                or type(response.payload.get("limit")) is not int
                or response.payload.get("offset") != offset or response.payload.get("limit") != limit
                or len(rows) != min(limit, max(0, count - offset))):
            raise _schema()
        return rows

    @staticmethod
    def _page_parameters(limit: int, offset: int, maximum: int) -> dict[str, str]:
        if (type(limit) is not int or not 1 <= limit <= maximum
                or type(offset) is not int or not 0 <= offset <= 10_000_000):
            raise ValueError("FRED page limit or offset exceeds the supported range")
        return {"limit": str(limit), "offset": str(offset)}

    def get_series(self, series_id: str) -> JsonApiResponse:
        identity = _series_id(series_id)
        response = self._get("series", "series_metadata", {"series_id": identity})
        rows = self._rows(response, "seriess")
        if len(rows) != 1 or rows[0].get("id") != identity:
            raise _schema()
        return response

    def search_series_page(self, text: str, *, limit: int = 100, offset: int = 0) -> JsonApiResponse:
        if (not isinstance(text, str) or not text.strip() or len(text) > 1024
                or any(ord(char) < 32 for char in text)):
            raise ValueError("FRED search requires bounded nonempty text")
        parameters = self._page_parameters(limit, offset, 1000)
        response = self._get("series/search", "series_search_page", {**parameters, "search_text": text})
        if any(not isinstance(row.get("id"), str) for row in self._page(response, "seriess", limit, offset)):
            raise _schema()
        return response

    def get_observations_page(
        self, series_id: str, start: str, end: str, *, limit: int = 1000, offset: int = 0,
        realtime_start: str | None = None, realtime_end: str | None = None,
    ) -> JsonApiResponse:
        parameters = {"series_id": _series_id(series_id), "observation_start": _date(start),
                      "observation_end": _date(end), **self._page_parameters(limit, offset, 10_000)}
        if start > end:
            raise ValueError("FRED observation window must be ordered")
        if (realtime_start is None) != (realtime_end is None):
            raise ValueError("FRED real-time windows require both endpoints")
        if realtime_start is not None:
            parameters.update(realtime_start=_date(realtime_start), realtime_end=_date(realtime_end))
            if realtime_start > realtime_end:
                raise ValueError("FRED real-time window must be ordered")
        response = self._get("series/observations", "observations_page", parameters)
        if realtime_start is not None and (
            response.payload.get("realtime_start") != realtime_start
            or response.payload.get("realtime_end") != realtime_end
        ):
            raise _schema()
        for row in self._page(response, "observations", limit, offset):
            try:
                observed = _date(row.get("date"))
            except ValueError:
                raise _schema() from None
            if not start <= observed <= end or not isinstance(row.get("value"), str):
                raise _schema()
        return response

    def get_series_release(self, series_id: str) -> JsonApiResponse:
        response = self._get("series/release", "series_release", {"series_id": _series_id(series_id)})
        if not self._rows(response, "releases"):
            raise _schema()
        return response

    def get_release_sources(self, release_id: int) -> JsonApiResponse:
        if type(release_id) is not int or not 1 <= release_id <= 2_147_483_647:
            raise ValueError("FRED release ID must be a positive bounded integer")
        response = self._get("release/sources", "release_sources", {"release_id": str(release_id)})
        if not self._rows(response, "sources"):
            raise _schema()
        return response
