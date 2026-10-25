"""Small source-specific catalogue contracts, independent of HTTP and ingestion."""
import re
from typing import Any


def _code(value: Any) -> int | None:
    if type(value) is int and 0 <= value <= 999999:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,6}", value):
        return int(value)
    return None


def validate_api_catalogue(source: str, payload: Any) -> dict:
    """Never treat HTTP 200, an error envelope, or an empty page as catalogue success."""
    if source not in {"bea", "estat"}:
        raise ValueError("Only the registered BEA/e-Stat catalogue checks are supported")
    result = {"status": "needs_review", "reason": "catalogue_schema_changed",
              "scope": "metadata_only", "observations_accepted": False,
              "complete_dataset_assessed": False}
    if not isinstance(payload, dict):
        return result
    if source == "bea":
        envelope = payload.get("BEAAPI")
        if not isinstance(envelope, dict):
            return result
        content = envelope.get("Results")
        error = envelope.get("Error")
        if isinstance(content, dict) and "Error" in content:
            error = content["Error"]
        if error is not None:
            return {**result, "reason": "source_api_error",
                    "provider_status": _code(error.get("APIErrorCode"))
                    if isinstance(error, dict) else None}
        rows = content.get("Dataset") if isinstance(content, dict) else None
        if not isinstance(rows, list) or not rows:
            return {**result, "reason": "empty_or_invalid_catalogue"}
        identifiers = []
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("DatasetName"), str)
                    or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", row["DatasetName"])
                    or not isinstance(row.get("DatasetDescription"), str)
                    or not row["DatasetDescription"].strip()):
                return result
            identifiers.append(row["DatasetName"])
    else:
        envelope = payload.get("GET_STATS_LIST")
        if not isinstance(envelope, dict) or not isinstance(envelope.get("RESULT"), dict):
            return result
        status = _code(envelope["RESULT"].get("STATUS"))
        if status != 0:
            return {**result, "reason": "empty_catalogue" if status == 1 else "source_api_error",
                    "provider_status": status}
        parameters = envelope.get("PARAMETER")
        if (not isinstance(parameters, dict) or parameters.get("LANG") != "E"
                or _code(parameters.get("LIMIT")) != 1):
            return {**result, "reason": "request_selection_not_confirmed"}
        content = envelope.get("DATALIST_INF")
        rows = content.get("TABLE_INF") if isinstance(content, dict) else None
        rows = [rows] if isinstance(rows, dict) else rows
        if not isinstance(rows, list) or len(rows) != 1:
            return {**result, "reason": "empty_or_oversized_catalogue_page"}
        identifiers = []
        for row in rows:
            if not isinstance(row, dict):
                return result
            title = row.get("TITLE")
            title = title.get("$") if isinstance(title, dict) else title
            if (not isinstance(row.get("@id"), str)
                    or not re.fullmatch(r"[0-9]{1,32}", row["@id"])
                    or not isinstance(title, str) or not title.strip()):
                return result
            identifiers.append(row["@id"])
    if len(set(identifiers)) != len(identifiers):
        return {**result, "reason": "duplicate_metadata_identifiers"}
    return {**result, "status": "metadata_contract_validated", "reason": "selected_metadata_present",
            "entry_count": len(identifiers), "identifiers": identifiers}
