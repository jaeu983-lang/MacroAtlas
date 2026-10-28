"""Dataset-family contracts; original bytes/rows are never rewritten by validation."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from macro_data_platform.discovery.datasets import DatasetProfile
from macro_data_platform.ingestion.formats import parse_table

_MONTHS = {name: index + 1 for index, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_ROMAN_SERIES = frozenset({
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
    "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
})


def _fail():
    raise ValueError("Dataset-specific source structure, period or fixed selection changed")


def _numeric(value: str, missing: tuple[str, ...]) -> bool:
    if value in missing:
        return True
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def _api_rows(profile, response):
    parameters = dict(response.request_parameters)
    if profile.validator_id == "fred_page":
        if parameters.get("series_id") != profile.fixed["series_id"]:
            _fail()
        rows = response.payload["observations"]
        return {"data_row_count": len(rows), "scope": "explicit_page_only",
                "source_count": response.payload["count"], "offset": response.payload["offset"],
                "limit": response.payload["limit"], "complete_dataset_assessed": False}
    if profile.validator_id == "census_table":
        if parameters.get("get") != profile.fixed["variables"]:
            _fail()
        return {"data_row_count": len(response.payload) - 1, "columns": response.payload[0],
                "scope": "selected_table_query", "complete_dataset_assessed": False}
    if profile.validator_id == "bls_v1":
        results = response.payload["Results"]
        if isinstance(results, list):
            results = results[0]
        selected = profile.fixed["series_ids"].split(",")
        if [row["seriesID"] for row in results["series"]] != selected:
            _fail()
        return {"data_row_count": sum(len(row["data"]) for row in results["series"]),
                "scope": "selected_series_and_years", "complete_dataset_assessed": False}
    _fail()


def _mfh_series_codes(rows, country_row_index, period_count):
    label_row_index, code_row_index = country_row_index - 3, country_row_index - 2
    if label_row_index < 0 or code_row_index < 0:
        return None
    labels, codes = rows[label_row_index], rows[code_row_index]
    explicit = {}
    for period_index in range(period_count):
        column_index = period_index + 1
        label = labels[column_index].strip() if column_index < len(labels) else ""
        code = codes[column_index].strip().upper() if column_index < len(codes) else ""
        if re.fullmatch(r"Series(?:\s+[0-9]+/)?", label, flags=re.IGNORECASE):
            if code not in _ROMAN_SERIES:
                _fail()
            explicit[period_index] = code
    if not explicit:
        return None
    first_index = min(explicit)
    current = explicit[first_index]
    result = []
    for period_index in range(period_count):
        if period_index in explicit:
            current = explicit[period_index]
        result.append(current)
    return result


def _mfh(profile, response):
    rows = parse_table(response.body, "csv").rows
    text = " ".join(" ".join(row) for row in rows).casefold()
    if "major foreign holders of treasury securities" not in text or "billions of dollars" not in text:
        _fail()
    periods, count, blocks, series_breaks = set(), 0, 0, []
    for index, row in enumerate(rows):
        if not row or row[0].strip() != "Country":
            continue
        years = [value.strip() for value in row[1:]]
        while years and not years[-1]:
            years.pop()
        if index == 0 or not 1 <= len(years) <= 13 or any(not re.fullmatch(r"[0-9]{4}", value) for value in years):
            _fail()
        months = [value.strip() for value in rows[index - 1][1:1 + len(years)]]
        if len(months) != len(years) or any(value not in _MONTHS for value in months):
            _fail()
        block_periods = [f"{year}-{_MONTHS[month]:02}" for year, month in zip(years, months, strict=True)]
        period_positions = {}
        for period_index, period in enumerate(block_periods):
            period_positions.setdefault(period, []).append(period_index)
        duplicate_periods = {period: positions for period, positions in period_positions.items()
                             if len(positions) > 1}
        series_codes = _mfh_series_codes(rows, index, len(years)) if duplicate_periods else None
        for period, positions in duplicate_periods.items():
            if len(positions) != 2 or series_codes is None:
                _fail()
            distinct_codes = [series_codes[position] for position in positions]
            if any(code not in _ROMAN_SERIES for code in distinct_codes) or len(set(distinct_codes)) != 2:
                _fail()
            series_breaks.append({"period_key": period, "series_ids_in_source_order": distinct_codes})
        periods.update(block_periods)
        blocks += 1
        block_count = 0
        for source in rows[index + 1:]:
            if not source or not source[0].strip():
                if block_count:
                    break
                continue
            if source[0].strip() == "Country" or re.match(r"[0-9]+/", source[0].strip()):
                break
            values = list(source[1:])
            while len(values) > len(years) and not values[-1].strip():
                values.pop()
            if len(values) != len(years) or not all(_numeric(value, profile.missing_tokens) for value in values):
                _fail()
            block_count += 1
        if not block_count:
            _fail()
        count += block_count
    if not blocks:
        _fail()
    warnings = ["aggregates_and_notes_retained_in_raw"]
    if series_breaks:
        warnings.append("series_break_comparison_columns_retained_in_raw")
    return {"data_row_count": count, "source_row_count": len(rows), "header_blocks": blocks,
            "period_keys": sorted(periods), "scope": "full_file_native_blocks; not country-normalized",
            "series_breaks": sorted(series_breaks, key=lambda item: (item["period_key"], item["series_ids_in_source_order"])),
            "complete_dataset_assessed": False, "warnings": warnings}


def _table3d(profile, response):
    lines = response.body.splitlines(keepends=True)
    notes_markers = [
        index for index, line in enumerate(lines)
        if line.rstrip(b"\r\n").strip() in {b'"Notes:"', b"Notes:"}
    ]
    if len(notes_markers) > 1:
        _fail()
    notes_present = bool(notes_markers)
    table_body = b"".join(lines[:notes_markers[0]]) if notes_present else response.body
    rows = parse_table(table_body, "csv").rows
    joined = " ".join("".join(row) for row in rows)
    if "TABLE 3D:" not in joined or "Millions of dollars" not in joined or "January 2023" not in joined:
        _fail()
    header = next((index for index, row in enumerate(rows) if len(row) == 4
                   and tuple(value.strip() for value in row[1:]) == ("Total U.S.", "Long-term", "Short-term")), None)
    if header is None or header + 2 >= len(rows) or tuple(value.strip() for value in rows[header + 2][1:]) != (
        "Securities", "Securities", "Securities",
    ):
        _fail()
    count = 0
    for row in rows[header + 3:]:
        if not row or not row[0].strip() or len(row) == 1:
            continue
        if re.match(r"[0-9]+/", row[0].strip()):
            break
        if len(row) != 4 or not all(_numeric(value, profile.missing_tokens) for value in row[1:]):
            _fail()
        count += 1
    if count == 0 or profile.fixed.get("source_period") != "2023-01":
        _fail()
    warnings = ["regional_totals_and_memo_rows_retained_in_raw"]
    if notes_present:
        warnings.append("notes_section_retained_only_in_raw")
    return {"data_row_count": count, "validated_section_row_count": len(rows), "source_period": "2023-01",
            "scope": "fixed_2023_01_snapshot; not_latest", "complete_dataset_assessed": False,
            "notes_section_present": notes_present, "warnings": warnings}


def _boe(profile, response):
    rows = parse_table(response.body, "csv").rows
    if not rows or len(rows[0]) != 2 or rows[0][0].strip().casefold() != "date" or rows[0][1] != "IUDBEDR":
        _fail()
    parameters = dict(response.request_parameters)
    def native(value):
        parts = re.fullmatch(r"([0-9]{2})[ /]([A-Za-z]{3})[ /]([0-9]{2}|[0-9]{4})", value)
        if parts is None or parts[2] not in _MONTHS:
            _fail()
        year = int(parts[3])
        if len(parts[3]) == 2:
            # Pin century to the explicit request, never use the process's moving-year pivot.
            anchor = int(parameters["Datefrom"][-4:])
            candidates = [century + year for century in (anchor // 100 * 100 - 100, anchor // 100 * 100,
                                                         anchor // 100 * 100 + 100)]
            first = native(parameters["Datefrom"])
            last = native(parameters["Dateto"])
            selected = []
            for candidate in candidates:
                try:
                    at = date(candidate, _MONTHS[parts[2]], int(parts[1]))
                except ValueError:
                    continue
                if first <= at <= last:
                    selected.append(candidate)
            if len(selected) != 1:
                _fail()
            year = selected[0]
        return date(year, _MONTHS[parts[2]], int(parts[1]))
    first, last = native(parameters["Datefrom"]), native(parameters["Dateto"])
    seen = set()
    for row in rows[1:]:
        if len(row) != 2:
            _fail()
        at = native(row[0])
        if at in seen or not first <= at <= last or not _numeric(row[1], profile.missing_tokens):
            _fail()
        seen.add(at)
    if not seen:
        _fail()
    return {"data_row_count": len(seen), "columns": list(rows[0]),
            "scope": "native_reporting_dates_only", "complete_dataset_assessed": False,
            "warnings": ["no_calendar_fill_or_month_end_alignment"]}


_VALIDATORS = {"fred_page": _api_rows, "census_table": _api_rows, "bls_v1": _api_rows,
               "tic_mfh_blocks": _mfh, "tic_table3d": _table3d, "boe_tn": _boe}


def validate_dataset_response(profile: DatasetProfile, response) -> dict:
    validator = _VALIDATORS.get(profile.validator_id)
    if validator is None:
        raise ValueError("Dataset validator is not registered")
    try:
        summary = validator(profile, response)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return {"status": "needs_review", "reason_code": "dataset_contract_changed",
                "observations_accepted": False}
    return {"status": "contract_validated", "observations_accepted": False,
            "validation_scope": "source_contract_only; no normalized observations published", **summary}
