"""Conservative quality summaries for source-preserving statistical API results."""
from collections import Counter


def validate_bls_result(parsed: dict, source_change_status: str) -> dict:
    """Check visible period keys without guessing a series' frequency or unit."""
    issues = []
    warnings = []
    duplicate_period_count = 0
    empty_value_count = 0
    for series in parsed["observations"]:
        rows = series["data"]
        counts = Counter((row["year"], row["period"]) for row in rows)
        duplicate_period_count += sum(count - 1 for count in counts.values() if count > 1)
        empty_value_count += sum(row["value"] == "" for row in rows)
    if duplicate_period_count:
        issues.append("duplicate_series_periods")
    if empty_value_count:
        warnings.append("empty_values_preserved")
    if parsed.get("unit") is None:
        warnings.append("unit_unknown")
    if parsed.get("frequency") is None:
        warnings.append("frequency_unknown")
    if parsed.get("source_version") is None:
        warnings.append("revision_vintage_unknown")
    if parsed.get("metadata_status") != "verified":
        warnings.append("series_metadata_unverified")
    _append_source_change(issues, warnings, source_change_status)
    return {
        "status": "failed" if issues else "passed", "issues": issues,
        "warnings": list(dict.fromkeys(warnings)),
        "row_count": sum(len(series["data"]) for series in parsed["observations"]),
        "duplicate_period_count": duplicate_period_count,
        "empty_value_count": empty_value_count,
        "unit": "unknown" if parsed.get("unit") is None else "known_from_source",
        "frequency": "unknown" if parsed.get("frequency") is None else "known_from_source",
        "source_change_status": source_change_status,
        "not_checked": ["economic_outliers", "full_period_coverage", "revision_vintage",
                         "cross_source_equivalence"],
    }


def validate_census_result(parsed: dict, source_change_status: str) -> dict:
    """Check selected geography keys and duplicates without assigning ACS semantics."""
    issues = []
    warnings = []
    observations = parsed["observations"]
    geography_dimension, expected_code = next(iter(parsed["geography_dimensions"].items()))
    actual_codes = [row.get(geography_dimension) for row in observations]
    if any(code != expected_code for code in actual_codes):
        issues.append("requested_geography_mismatch")
    duplicate_geographies = sum(
        count - 1 for count in Counter(actual_codes).values() if count > 1
    )
    if duplicate_geographies:
        issues.append("duplicate_geography_rows")
    source_variables = [name for name in parsed["variable_ids"] if name != "NAME"]
    missing_value_count = sum(
        row.get(variable) is None or row.get(variable) == ""
        for row in observations for variable in source_variables
    )
    if missing_value_count:
        warnings.append("missing_values_preserved")
    if parsed.get("unit") is None:
        warnings.append("unit_unknown")
    if parsed.get("frequency") is None:
        warnings.append("frequency_unknown")
    if parsed.get("source_version") is None:
        warnings.append("revision_vintage_unknown")
    if parsed.get("metadata_status") != "verified":
        warnings.append("variable_metadata_unverified")
    _append_source_change(issues, warnings, source_change_status)
    return {
        "status": "failed" if issues else "passed", "issues": issues,
        "warnings": list(dict.fromkeys(warnings)), "row_count": len(observations),
        "duplicate_geography_count": duplicate_geographies,
        "missing_value_count": missing_value_count,
        "unit": "unknown" if parsed.get("unit") is None else "known_from_source",
        "frequency": "unknown" if parsed.get("frequency") is None else "known_from_source",
        "source_change_status": source_change_status,
        "not_checked": ["variable_definitions", "margins_of_error", "geographic_coverage",
                         "revision_vintage", "cross_source_equivalence"],
    }


def _append_source_change(issues: list[str], warnings: list[str], status: str) -> None:
    if status == "changed":
        issues.append("source_payload_changed_since_prior_request")
    elif status not in {"first_observation", "unchanged"}:
        warnings.append("prior_response_comparison_unavailable")
