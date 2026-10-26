"""BLS Public Data API v2 series-data connector."""
import json
import re
from dataclasses import dataclass

from macro_data_platform.connectors.statistical_http import (
    ApiDownload,
    SourceFailure,
    decode_json,
    read_optional_api_key,
    request_json,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
API_DOCS = "https://www.bls.gov/developers/api_signature_v2.htm"
_SERIES = re.compile(r"^[A-Z0-9]{2,30}$")


@dataclass(frozen=True)
class BLSQuery:
    series_ids: tuple[str, ...]
    start_year: int
    end_year: int

    def __post_init__(self):
        if (not 1 <= len(self.series_ids) <= 20
                or len(set(self.series_ids)) != len(self.series_ids)
                or not all(_SERIES.fullmatch(x) for x in self.series_ids)):
            raise ValueError("BLS accepts 1..20 unique alphanumeric series IDs")
        if (type(self.start_year) is not int or type(self.end_year) is not int
                or not 1900 <= self.start_year <= self.end_year <= 2100
                or self.end_year - self.start_year >= 20):
            raise ValueError("BLS requires a window of 1..20 years in 1900..2100")


class BLSTransport:
    def fetch(self, query: BLSQuery) -> ApiDownload:
        payload = {
            "seriesid": list(query.series_ids), "startyear": str(query.start_year),
            "endyear": str(query.end_year),
        }
        key = read_optional_api_key("BLS_API_KEY")
        if key is not None:
            payload["registrationkey"] = key
        body = json.dumps(payload, separators=(",", ":")).encode()
        return request_json(API_URL, method="POST", body=body,
                            headers={"Content-Type": "application/json"})


def parse_bls(download: ApiDownload, query: BLSQuery) -> dict:
    data = decode_json(download)
    if not isinstance(data, dict) or data.get("status") != "REQUEST_SUCCEEDED":
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                            "BLS did not confirm a successful request.")
    results = data.get("Results")
    series = results.get("series") if isinstance(results, dict) else None
    if not isinstance(series, list) or len(series) != len(query.series_ids):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BLS response series count differed from the request.")
    actual = [entry.get("seriesID") if isinstance(entry, dict) else None for entry in series]
    if set(actual) != set(query.series_ids):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BLS response contained unexpected series identifiers.")
    for entry in series:
        rows = entry.get("data")
        if not isinstance(rows, list):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BLS observation list was missing.")
        for row in rows:
            year = row.get("year") if isinstance(row, dict) else None
            period = row.get("period") if isinstance(row, dict) else None
            value = row.get("value") if isinstance(row, dict) else None
            if (not isinstance(year, str) or not year.isascii() or not year.isdecimal()
                    or not query.start_year <= int(year) <= query.end_year
                    or not isinstance(period, str)
                    or not re.fullmatch(r"(?:M(?:0[1-9]|1[0-3])|Q0[1-4]|A01|S0[1-2])", period)
                    or not isinstance(value, str)):
                raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                    "BLS observation fields failed structural validation.")
    return {
        "source_agency": "U.S. Bureau of Labor Statistics", "source_url": API_URL,
        "api_documentation_url": API_DOCS, "dataset_id": None,
        "series_ids": list(query.series_ids), "start_year": query.start_year,
        "end_year": query.end_year, "frequency": None, "unit": None,
        "metadata_status": "unknown_without_series_catalogue_verification",
        "status": data["status"], "message_codes": data.get("messageCodes", []),
        "observations": series, "retrieved_at": download.retrieved_at.isoformat(),
    }
