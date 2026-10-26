"""U.S. Census Bureau API connector for explicitly selected ACS tables."""
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from macro_data_platform.connectors.statistical_http import (
    ApiDownload,
    SourceFailure,
    decode_json,
    read_api_key,
    request_json,
)
from macro_data_platform.contracts import ErrorCode, StageStatus

_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")
_GEOGRAPHY = re.compile(r"^(?:us:1|state:[0-9]{2})$")


@dataclass(frozen=True)
class CensusQuery:
    year: int
    dataset: str
    variables: tuple[str, ...]
    geography: str

    def __post_init__(self):
        if type(self.year) is not int or not 2009 <= self.year <= 2100:
            raise ValueError("Census ACS year must be an integer from 2009..2100")
        if self.dataset not in {"acs/acs1", "acs/acs5"}:
            raise ValueError("supported Census datasets are acs/acs1 and acs/acs5")
        if (not 1 <= len(self.variables) <= 50 or len(set(self.variables)) != len(self.variables)
                or not all(_VARIABLE.fullmatch(v) for v in self.variables)):
            raise ValueError("Census requires 1..50 unique variable identifiers")
        if "NAME" not in self.variables:
            raise ValueError("include NAME to retain a geography label")
        if not _GEOGRAPHY.fullmatch(self.geography):
            raise ValueError("geography must be us:1 or state:NN")


class CensusTransport:
    def fetch(self, query: CensusQuery) -> ApiDownload:
        key = read_api_key("CENSUS_API_KEY")
        params = {"get": ",".join(query.variables), "for": query.geography}
        params["key"] = key
        url = f"https://api.census.gov/data/{query.year}/{query.dataset}?{urlencode(params)}"
        # ApiDownload and persisted manifests use only the credential-free endpoint URL.
        result = request_json(url, method="GET")
        return ApiDownload(f"https://api.census.gov/data/{query.year}/{query.dataset}",
                           result.body, result.status_code, result.retrieved_at,
                           result.content_type, result.kind)


def parse_census(download: ApiDownload, query: CensusQuery) -> dict:
    data = decode_json(download)
    if isinstance(data, str):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.AUTH_ACCESS,
                            "Census rejected the API request or credential.")
    geography_dimension = query.geography.split(":", 1)[0]
    expected_headers = [*query.variables, geography_dimension]
    if (not isinstance(data, list) or len(data) < 2 or not isinstance(data[0], list)
            or data[0] != expected_headers):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Census response headers differed from the requested variables.")
    observations = []
    for row in data[1:]:
        if (not isinstance(row, list) or len(row) != len(expected_headers)
                or not all(value is None or isinstance(value, str) for value in row)):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "Census observation row had an unexpected shape.")
        observation = dict(zip(query.variables, row, strict=False))
        observation[geography_dimension] = row[-1]
        observations.append(observation)
    if not observations:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "Census returned no observations for the selected geography.")
    return {
        "source_agency": "U.S. Census Bureau", "source_url": download.source_url,
        "api_documentation_url": "https://www.census.gov/data/developers/guidance/api-user-guide.html",
        "dataset_id": query.dataset, "year": query.year,
        "variable_ids": list(query.variables), "geography": query.geography,
        "geography_dimensions": {geography_dimension: query.geography.split(":", 1)[1]},
        "frequency": None, "unit": None,
        "metadata_status": "unknown_without_variable_catalogue_verification",
        "observations": observations, "retrieved_at": download.retrieved_at.isoformat(),
    }
