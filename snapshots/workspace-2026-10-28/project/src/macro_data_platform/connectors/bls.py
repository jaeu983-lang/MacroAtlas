"""BLS Public Data API 1.0 only; never reads or transmits BLS_API_KEY."""
import re
from collections.abc import Sequence

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_api import (
    ConnectorFailure,
    JsonApiResponse,
    JsonApiTransport,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
API_DOCS = "https://www.bls.gov/developers/api_signature.htm"
MAX_SERIES = 25
MAX_YEARS = 10


def _schema() -> ConnectorFailure:
    return ConnectorFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BLS v1 reported a warning, incomplete selection, or changed response schema.")


class BLSClient:
    """One v1 POST, at most 25 series and 10 inclusive years; no v2 fallback."""

    def __init__(self, settings: Settings, transport: JsonApiTransport | None = None):
        self.transport = transport or JsonApiTransport(settings)

    def get_data(self, series_ids: Sequence[str], start_year: int, end_year: int) -> JsonApiResponse:
        if (not isinstance(series_ids, (list, tuple)) or not 1 <= len(series_ids) <= MAX_SERIES
                or any(not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]{1,64}", value)
                       for value in series_ids) or len(set(series_ids)) != len(series_ids)):
            raise ValueError("BLS v1 requires 1 to 25 distinct uppercase series identifiers")
        if (type(start_year) is not int or type(end_year) is not int
                or not 1900 <= start_year <= end_year <= 2100
                or end_year - start_year >= MAX_YEARS):
            raise ValueError("BLS v1 supports up to 10 inclusive years in 1900..2100")
        response = self.transport.post_json("BLS", API_URL, "timeseries_v1", {
            "seriesid": list(series_ids), "startyear": str(start_year), "endyear": str(end_year),
        })
        payload = response.payload
        if (not isinstance(payload, dict) or payload.get("status") != "REQUEST_SUCCEEDED"
                or payload.get("message") != []):
            raise _schema()
        results = payload.get("Results")
        # The official v1 signature uses a one-item list; the official Python example uses a dict.
        if isinstance(results, list) and len(results) == 1:
            results = results[0]
        rows = results.get("series") if isinstance(results, dict) else None
        if not isinstance(rows, list) or len(rows) != len(series_ids):
            raise _schema()
        found: set[str] = set()
        for series in rows:
            if not isinstance(series, dict) or not isinstance(series.get("seriesID"), str):
                raise _schema()
            identity = series["seriesID"]
            if identity not in series_ids or identity in found:
                raise _schema()
            found.add(identity)
            data = series.get("data")
            if not isinstance(data, list) or not data:
                raise _schema()
            seen: set[tuple[str, str]] = set()
            for row in data:
                if not isinstance(row, dict):
                    raise _schema()
                year, period = row.get("year"), row.get("period")
                if (not isinstance(year, str) or not re.fullmatch(r"[0-9]{4}", year)
                        or not start_year <= int(year) <= end_year
                        or not isinstance(period, str) or not re.fullmatch(r"[A-Z][0-9]{2}", period)
                        or not isinstance(row.get("value"), str)
                        or not isinstance(row.get("footnotes"), list) or (year, period) in seen):
                    raise _schema()
                seen.add((year, period))
        return response
