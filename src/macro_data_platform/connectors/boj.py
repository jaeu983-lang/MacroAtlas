"""Bounded Bank of Japan API support for one directly verified FX series."""
import math
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from macro_data_platform.connectors.statistical_http import (
    ApiDownload,
    SourceFailure,
    decode_json,
    request_json,
)
from macro_data_platform.contracts import ErrorCode, StageStatus
from macro_data_platform.performance.metrics import measured_phase

API_ROOT = "https://www.stat-search.boj.or.jp/api/v1"
METADATA_ENDPOINT = f"{API_ROOT}/getMetadata"
DATA_ENDPOINT = f"{API_ROOT}/getDataCode"
API_DOCS = "https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm"
DATABASE = "FM08"
SERIES_CODE = "FXERD01"
SERIES_NAME = "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market"
UNIT = "Yen per U.S. Dollar"
FREQUENCY = "DAILY"
_MONTH = re.compile(r"^[0-9]{6}$")
MAX_RANGE_MONTHS = 12


def _month_date(value: str) -> date:
    if not isinstance(value, str) or not _MONTH.fullmatch(value):
        raise ValueError("BOJ month must use YYYYMM")
    try:
        return date(int(value[:4]), int(value[4:]), 1)
    except ValueError:
        raise ValueError("BOJ month is outside the calendar") from None


@dataclass(frozen=True)
class BOJQuery:
    """One-month request for the only currently verified BOJ series."""

    month: str
    database: str = DATABASE
    series_code: str = SERIES_CODE

    def __post_init__(self):
        if self.database != DATABASE or self.series_code != SERIES_CODE:
            raise ValueError("only BOJ FM08 series FXERD01 is currently supported")
        _month_date(self.month)

    @property
    def metadata_url(self) -> str:
        return f"{METADATA_ENDPOINT}?{urlencode({'format': 'json', 'lang': 'en', 'db': self.database})}"

    @property
    def data_url(self) -> str:
        params = {
            "format": "json", "lang": "en", "db": self.database,
            "code": self.series_code, "startDate": self.month, "endDate": self.month,
        }
        return f"{DATA_ENDPOINT}?{urlencode(params)}"


@dataclass(frozen=True)
class BOJRangeQuery:
    """One to twelve consecutive months for the same verified daily FX series."""

    start_month: str
    end_month: str
    database: str = DATABASE
    series_code: str = SERIES_CODE

    def __post_init__(self):
        if self.database != DATABASE or self.series_code != SERIES_CODE:
            raise ValueError("only BOJ FM08 series FXERD01 is currently supported")
        start = _month_date(self.start_month)
        end = _month_date(self.end_month)
        month_count = (end.year - start.year) * 12 + end.month - start.month + 1
        if month_count < 1 or month_count > MAX_RANGE_MONTHS:
            raise ValueError("BOJ range must contain 1 to 12 consecutive months")

    @property
    def metadata_query(self) -> BOJQuery:
        return BOJQuery(self.start_month, self.database, self.series_code)

    @property
    def metadata_url(self) -> str:
        return self.metadata_query.metadata_url

    @property
    def data_url(self) -> str:
        params = {
            "format": "json", "lang": "en", "db": self.database,
            "code": self.series_code, "startDate": self.start_month,
            "endDate": self.end_month,
        }
        return f"{DATA_ENDPOINT}?{urlencode(params)}"


class BOJTransport:
    """Official JSON GETs only; the endpoint and requested series are fixed."""

    def fetch_metadata(self, query: BOJQuery) -> ApiDownload:
        return request_json(query.metadata_url, method="GET")

    def fetch_observations(self, query: BOJQuery | BOJRangeQuery) -> ApiDownload:
        return request_json(query.data_url, method="GET")


@measured_phase("parse")
def parse_boj_metadata(download: ApiDownload, query: BOJQuery) -> dict:
    if download.source_url != METADATA_ENDPOINT:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                            "BOJ metadata endpoint differed from the fixed official API.")
    document = decode_json(download)
    records = document.get("RESULTSET") if isinstance(document, dict) else None
    matches = ([row for row in records if isinstance(row, dict)
                and row.get("SERIES_CODE") == query.series_code]
               if isinstance(records, list) else [])
    if (not isinstance(document, dict) or document.get("STATUS") != 200
            or document.get("DB") != query.database or len(matches) != 1):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ metadata response did not identify exactly one requested series.")
    record = matches[0]
    expected = {
        "NAME_OF_TIME_SERIES": SERIES_NAME, "UNIT": UNIT, "FREQUENCY": FREQUENCY,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ series metadata differs from the verified FXERD01 definition.")
    return {
        "source_agency": "Bank of Japan", "database": query.database,
        "series_code": query.series_code, "series_name": record["NAME_OF_TIME_SERIES"],
        "unit": record["UNIT"], "frequency": record["FREQUENCY"],
        "category": record.get("CATEGORY"),
        "available_start": record.get("START_OF_THE_TIME_SERIES"),
        "available_end": record.get("END_OF_THE_TIME_SERIES"),
        "source_last_updated": record.get("LAST_UPDATE"),
        "source_url": METADATA_ENDPOINT, "api_documentation_url": API_DOCS,
        "metadata_status": "verified",
    }


@measured_phase("parse")
def parse_boj_observations(download: ApiDownload, query: BOJQuery,
                           metadata: dict) -> dict:
    if download.source_url != DATA_ENDPOINT:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                            "BOJ data endpoint differed from the fixed official API.")
    document = decode_json(download)
    results = document.get("RESULTSET") if isinstance(document, dict) else None
    if (not isinstance(document, dict) or document.get("STATUS") != 200
            or document.get("NEXTPOSITION") is not None or not isinstance(results, list)
            or len(results) != 1):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ response was not a complete single-series result.")
    record = results[0]
    if not isinstance(record, dict):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ series result had an unexpected structure.")
    values = record.get("VALUES") if isinstance(record, dict) else None
    dates = values.get("SURVEY_DATES") if isinstance(values, dict) else None
    observations = values.get("VALUES") if isinstance(values, dict) else None
    if (record.get("SERIES_CODE") != query.series_code
            or record.get("NAME_OF_TIME_SERIES") != metadata.get("series_name")
            or record.get("UNIT") != metadata.get("unit")
            or record.get("FREQUENCY") != metadata.get("frequency")
            or not isinstance(dates, list) or not isinstance(observations, list)
            or not dates or len(dates) != len(observations) or len(dates) > 31):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ observations did not match the verified series and month.")
    normalized = []
    previous_day = 0
    null_count = 0
    for source_day, value in zip(dates, observations, strict=True):
        if type(source_day) is not int:
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation date had an unexpected type.")
        text_day = str(source_day)
        try:
            parsed_day = date(int(text_day[:4]), int(text_day[4:6]), int(text_day[6:8]))
        except (ValueError, IndexError):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation date was invalid.") from None
        try:
            finite_value = value is None or (
                type(value) in {int, float} and math.isfinite(value))
        except OverflowError:
            finite_value = False
        if (len(text_day) != 8 or text_day[:6] != query.month or parsed_day.day <= previous_day
                or not finite_value):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation dates or values failed structural validation.")
        previous_day = parsed_day.day
        null_count += value is None
        normalized.append({"date": parsed_day.isoformat(), "value": value})
    return {
        "source_agency": "Bank of Japan", "dataset_id": query.database,
        "series_id": query.series_code, "series_name": metadata["series_name"],
        "unit": metadata["unit"], "frequency": metadata["frequency"],
        "period_start": f"{query.month[:4]}-{query.month[4:]}-01",
        "period_end": f"{query.month[:4]}-{query.month[4:]}-{previous_day:02d}",
        "source_url": download.source_url, "api_documentation_url": API_DOCS,
        "retrieved_at": download.retrieved_at.isoformat(),
        "source_last_updated": record.get("LAST_UPDATE"),
        "observations": normalized,
        "quality": {
            "status": "passed", "row_count": len(normalized),
            "missing_value_count": null_count,
            "scope": "series identity, date order and month bounds, finite values, null preservation",
            "not_checked": ["economic_outliers", "revision_history", "cross_source_equivalence"],
        },
    }


@measured_phase("parse")
def parse_boj_range_observations(download: ApiDownload, query: BOJRangeQuery,
                                 metadata: dict) -> dict:
    """Validate one full response for a bounded multi-month request."""
    if download.source_url != DATA_ENDPOINT:
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.LICENSE_SECURITY,
                            "BOJ data endpoint differed from the fixed official API.")
    document = decode_json(download)
    results = document.get("RESULTSET") if isinstance(document, dict) else None
    if (not isinstance(document, dict) or document.get("STATUS") != 200
            or document.get("NEXTPOSITION") is not None or not isinstance(results, list)
            or len(results) != 1):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ response was not a complete single-series result.")
    record = results[0]
    if not isinstance(record, dict):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ series result had an unexpected structure.")
    values = record.get("VALUES")
    dates = values.get("SURVEY_DATES") if isinstance(values, dict) else None
    observations = values.get("VALUES") if isinstance(values, dict) else None
    start = _month_date(query.start_month)
    last_month = _month_date(query.end_month)
    end = date(last_month.year, last_month.month,
               monthrange(last_month.year, last_month.month)[1])
    max_rows = (end - start).days + 1
    if (record.get("SERIES_CODE") != query.series_code
            or record.get("NAME_OF_TIME_SERIES") != metadata.get("series_name")
            or record.get("UNIT") != metadata.get("unit")
            or record.get("FREQUENCY") != metadata.get("frequency")
            or not isinstance(dates, list) or not isinstance(observations, list)
            or not dates or len(dates) != len(observations) or len(dates) > max_rows):
        raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                            "BOJ observations did not match the verified series and date range.")

    normalized = []
    previous_day = None
    null_count = 0
    for source_day, value in zip(dates, observations, strict=True):
        if type(source_day) is not int:
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation date had an unexpected type.")
        text_day = str(source_day)
        try:
            parsed_day = date(int(text_day[:4]), int(text_day[4:6]), int(text_day[6:8]))
        except (ValueError, IndexError):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation date was invalid.") from None
        try:
            finite_value = value is None or (
                type(value) in {int, float} and math.isfinite(value))
        except OverflowError:
            finite_value = False
        if (len(text_day) != 8 or not start <= parsed_day <= end
                or (previous_day is not None and parsed_day <= previous_day)
                or not finite_value):
            raise SourceFailure(StageStatus.NEEDS_REVIEW, ErrorCode.SCHEMA_CHANGED,
                                "BOJ observation dates or values failed structural validation.")
        previous_day = parsed_day
        null_count += value is None
        normalized.append({"date": parsed_day.isoformat(), "value": value})
    return {
        "source_agency": "Bank of Japan", "dataset_id": query.database,
        "series_id": query.series_code, "series_name": metadata["series_name"],
        "unit": metadata["unit"], "frequency": metadata["frequency"],
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "source_url": download.source_url, "api_documentation_url": API_DOCS,
        "retrieved_at": download.retrieved_at.isoformat(),
        "source_last_updated": record.get("LAST_UPDATE"),
        "observations": normalized,
        "quality": {
            "status": "passed", "row_count": len(normalized),
            "missing_value_count": null_count,
            "scope": "series identity, date order and requested range, finite values, null preservation",
            "not_checked": ["economic_outliers", "revision_history", "cross_source_equivalence"],
        },
    }
