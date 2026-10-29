"""Source-preserving metadata normalization with explicit unknown/conflict states."""
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from macro_data_platform.performance.metrics import measured_phase

NORMALIZED_FIELDS = (
    "name", "definition", "unit", "frequency", "geo_coverage", "time_coverage",
    "seasonal_adjustment", "dimensions",
)


def _unknown(reason: str) -> dict:
    return {"value": None, "state": "unknown", "source_refs": [], "reason": reason}


def _field(value: Any, source_ref: str) -> dict:
    if value is None or value == "":
        return _unknown("source_value_empty")
    return {"value": value, "state": "known", "source_refs": [source_ref], "reason": None}


def _valid_source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("source_url must be credential-free HTTPS without a query")


def _valid_timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("retrieved_at must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("retrieved_at must be an ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds():
        raise ValueError("retrieved_at must be UTC")


@measured_phase("parse")
def normalize_bls_catalog(payload: Mapping, *, source_url: str, retrieved_at: str,
                          raw_path: str, start_year: int, end_year: int,
                          expected_series_id: str, series_index: int = 0) -> dict:
    _valid_source(source_url)
    _valid_timestamp(retrieved_at)
    results = payload.get("Results")
    series = results.get("series") if isinstance(results, Mapping) else None
    if not isinstance(series, list) or len(series) != 1 or not isinstance(series[0], Mapping):
        raise ValueError("expected exactly one BLS series catalogue row")
    row = series[0]
    if row.get("seriesID") != expected_series_id:
        raise ValueError("BLS catalogue series identifier differed from the request")
    catalog = row.get("catalog")
    if not isinstance(catalog, Mapping):
        raise TypeError("BLS catalogue fields were not returned")
    if type(series_index) is not int or series_index < 0:
        raise ValueError("BLS catalogue series index must be a nonnegative integer")
    pointer = f"/Results/series/{series_index}"
    get = lambda key: _field(catalog.get(key), f"{pointer}/catalog/{key}")
    fields = {name: _unknown("field_not_exposed_by_selected_bls_catalogue")
              for name in NORMALIZED_FIELDS}
    fields.update({
        "name": get("series_title"),
        "geo_coverage": get("area"),
        "seasonal_adjustment": get("seasonality"),
        "dimensions": _field({
            name: catalog[name] for name in (
                "item", "measure_data_type", "survey_abbreviation", "survey_name",
            ) if catalog.get(name) not in (None, "")
        } or None, f"{pointer}/catalog"),
    })
    return {
        "schema_version": "normalized-metadata-v1", "entity_type": "time_series",
        "source_agency": "U.S. Bureau of Labor Statistics", "source_url": source_url,
        "api_documentation_url": "https://www.bls.gov/developers/api_signature_v2.htm",
        "retrieved_at": retrieved_at, "source_version": None,
        "dataset_id": _unknown("BLS catalogue response did not expose a dataset identifier"),
        "identifier": _field(expected_series_id, f"{pointer}/seriesID"),
        "fields": fields,
        "source_attributes": {key: value for key, value in catalog.items()},
        "request_context": {"start_year": start_year, "end_year": end_year,
                            "catalogue": True},
        "raw_ref": {"path": raw_path, "json_pointer": pointer},
        "metadata_completeness": "partial",
    }


@measured_phase("parse")
def normalize_census_variable(payload: Mapping, *, source_url: str, retrieved_at: str,
                              raw_path: str, dataset_id: str, reference_year: int,
                              expected_variable_id: str) -> dict:
    _valid_source(source_url)
    _valid_timestamp(retrieved_at)
    if payload.get("name") != expected_variable_id:
        raise ValueError("Census variable identifier differed from the request")
    pointer = ""
    fields = {name: _unknown("field_not_exposed_by_selected_census_variable_metadata")
              for name in NORMALIZED_FIELDS}
    fields["name"] = _field(payload.get("label"), "/label")
    return {
        "schema_version": "normalized-metadata-v1", "entity_type": "variable",
        "source_agency": "U.S. Census Bureau", "source_url": source_url,
        "api_documentation_url": "https://www.census.gov/data/developers/guidance/api-user-guide.html",
        "retrieved_at": retrieved_at, "source_version": str(reference_year),
        "dataset_id": _field(dataset_id, "/request/dataset_id"),
        "identifier": _field(expected_variable_id, "/name"),
        "fields": fields,
        "source_attributes": {key: payload.get(key) for key in (
            "concept", "predicateType", "group", "limit", "predicateOnly",
        ) if key in payload},
        "request_context": {"reference_year": reference_year, "dataset_id": dataset_id},
        "raw_ref": {"path": raw_path, "json_pointer": pointer},
        "metadata_completeness": "partial",
    }


def _mapped_value(row: Mapping, mapping: Any, *, pointer: str) -> dict:
    if isinstance(mapping, str):
        return _field(row.get(mapping), f"{pointer}/{mapping}")
    if isinstance(mapping, Mapping):
        translations = {}
        refs = []
        for language, column in mapping.items():
            if not isinstance(language, str) or not isinstance(column, str):
                raise TypeError("language mappings must map language tags to column names")
            value = row.get(column)
            if value not in (None, ""):
                translations[language] = value
                refs.append(f"{pointer}/{column}")
        if not translations:
            return _unknown("source_columns_empty")
        return {"value": translations, "state": "known", "source_refs": refs,
                "reason": None}
    if isinstance(mapping, Sequence) and not isinstance(mapping, (str, bytes)):
        values, refs = [], []
        for column in mapping:
            if not isinstance(column, str):
                raise TypeError("column aliases must be strings")
            value = row.get(column)
            if value not in (None, ""):
                values.append(value)
                refs.append(f"{pointer}/{column}")
        if not values:
            return _unknown("source_columns_empty")
        serialized = {json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
                      for value in values}
        if len(serialized) > 1:
            return {"value": None, "state": "conflict", "source_refs": refs,
                    "candidates": values, "reason": "mapped_columns_disagree"}
        return {"value": values[0], "state": "known", "source_refs": refs,
                "reason": None}
    raise ValueError("column mapping must be a name, alias list, or language map")


@measured_phase("parse")
def normalize_codebook_rows(rows: Sequence[Mapping], *, columns: Mapping[str, Any],
                            source_agency: str, source_url: str,
                            retrieved_at: str, raw_path: str) -> list[dict]:
    """Normalize already-read sheet/table rows; never infer units or frequency."""
    _valid_source(source_url)
    _valid_timestamp(retrieved_at)
    if (not isinstance(rows, Sequence) or isinstance(rows, (str, bytes))
            or not all(isinstance(row, Mapping) for row in rows)):
        raise ValueError("rows must be a sequence of mappings")
    if (not isinstance(columns, Mapping) or "identifier" not in columns
            or set(columns) - {"identifier", *NORMALIZED_FIELDS}):
        raise ValueError("column map requires identifier and supported normalized fields")
    if not isinstance(source_agency, str) or not source_agency.strip():
        raise ValueError("source_agency is required")
    records = []
    for index, row in enumerate(rows):
        pointer = f"/rows/{index}"
        identifier = _mapped_value(row, columns["identifier"], pointer=pointer)
        fields = {name: (_mapped_value(row, columns[name], pointer=pointer)
                         if name in columns else _unknown("not_mapped_from_codebook"))
                  for name in NORMALIZED_FIELDS}
        records.append({
            "schema_version": "normalized-metadata-v1", "entity_type": "codebook_entry",
            "source_agency": source_agency, "source_url": source_url,
            "retrieved_at": retrieved_at, "source_version": None,
            "dataset_id": _unknown("codebook_dataset_id_not_mapped"),
            "identifier": identifier, "fields": fields, "source_attributes": {},
            "request_context": {"row_number": index + 1},
            "raw_ref": {"path": raw_path, "json_pointer": pointer},
            "metadata_completeness": "partial",
        })
    by_id = defaultdict(list)
    for record in records:
        ident = record["identifier"]
        if ident["state"] == "known" and isinstance(ident["value"], (str, int, float)):
            by_id[str(ident["value"])].append(record)
    for duplicates in by_id.values():
        for field_name in NORMALIZED_FIELDS:
            known = [record["fields"][field_name] for record in duplicates
                     if record["fields"][field_name]["state"] == "known"]
            unique = {json.dumps(item["value"], sort_keys=True, ensure_ascii=False, default=str)
                      for item in known}
            if len(unique) > 1:
                candidates = [{"value": item["value"], "source_refs": item["source_refs"]}
                              for item in known]
                for record in duplicates:
                    record["fields"][field_name] = {
                        "value": None, "state": "conflict",
                        "source_refs": [ref for candidate in candidates
                                        for ref in candidate["source_refs"]],
                        "candidates": candidates, "reason": "duplicate_identifier_disagrees",
                    }
    return records
