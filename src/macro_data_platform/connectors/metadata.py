"""Bounded official API transports for metadata catalogues."""
import json
import re
from urllib.parse import urlencode

from macro_data_platform.connectors.statistical_http import (
    ApiDownload,
    read_api_key,
    request_json,
)

BLS_METADATA_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_DATASET = re.compile(r"^acs/(?:acs1|acs5)$")
_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")


def fetch_bls_catalog(series_id: str, start_year: int, end_year: int) -> ApiDownload:
    """Request one BLS v2 series catalogue row; API key stays in the POST body."""
    from macro_data_platform.connectors.bls import BLSQuery

    query = BLSQuery((series_id,), start_year, end_year)
    payload = {
        "seriesid": list(query.series_ids), "startyear": str(query.start_year),
        "endyear": str(query.end_year), "catalog": True,
        "registrationkey": read_api_key("BLS_API_KEY"),
    }
    return request_json(BLS_METADATA_URL, method="POST",
                        body=json.dumps(payload, separators=(",", ":")).encode(),
                        headers={"Content-Type": "application/json"})


def fetch_census_variable(year: int, dataset: str, variable_id: str) -> ApiDownload:
    """Fetch one Census ACS variable metadata document using a fixed API path."""
    if type(year) is not int or not 2009 <= year <= 2100:
        raise ValueError("Census ACS year must be an integer from 2009..2100")
    if not isinstance(dataset, str) or not _DATASET.fullmatch(dataset):
        raise ValueError("unsupported Census ACS dataset")
    if not isinstance(variable_id, str) or not _VARIABLE.fullmatch(variable_id):
        raise ValueError("invalid Census variable identifier")
    key = read_api_key("CENSUS_API_KEY")
    endpoint = f"https://api.census.gov/data/{year}/{dataset}/variables/{variable_id}.json"
    response = request_json(f"{endpoint}?{urlencode({'key': key})}", method="GET")
    return ApiDownload(endpoint, response.body, response.status_code,
                        response.retrieved_at, response.content_type, response.kind)
