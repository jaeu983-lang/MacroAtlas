"""The Gate 41 preflight reads only value-free workbook metadata."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

spec = importlib.util.spec_from_file_location(
    "gate_41_preflight", Path(__file__).parents[1] / "scripts/run_gate_41_preflight.py",
)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def _series_sheet(workbook, sheet_name, country, observations=(
        ("2024", 987654321.0),)):
    sheet = workbook.create_sheet(sheet_name)
    sheet.append([
        "period", "source_period", "raw_value", "observation_status", "source_agency",
        "dataset_id", "series_id", "dimensions_json", "calendar", "unit", "currency",
        "frequency",
    ])
    for period, raw_value in observations:
        sheet.append([
            period, period, raw_value, "", "World Bank", "2", "NY.GDP.MKTP.CD",
            json.dumps({"country_iso3": country}), "gregorian", "current U.S. dollars", "USD",
            "annual",
        ])
    return sheet


def _sidecar(path, *, series_count=1, observation_count=1):
    return {
        "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "series_count": series_count,
        "observation_count": observation_count,
        "freshness": [{"status": "FRESH"} for _ in range(series_count)],
    }


def test_preflight_summarizes_comparison_without_emitting_raw_values(tmp_path):
    path = tmp_path / "comparison.xlsx"
    workbook = Workbook()
    workbook.active.title = "Provenance"
    _series_sheet(workbook, "USA", "USA")
    _series_sheet(workbook, "Canada", "CAN")
    alignment = workbook.create_sheet("Alignment")
    alignment.append(["typed_period", None, None])
    alignment.append(["2024", 987654321.0, 987654321.0])
    workbook.save(path)

    report = preflight.inspect_workbook(
        path, "G", hashlib.sha256(path.read_bytes()).hexdigest(),
        _sidecar(path, series_count=2, observation_count=2),
    )

    assert report["aligned_periods"] == ["2024"]
    assert report["formula_cells"] == 0
    assert [item["country"] for item in report["series"]] == ["USA", "CAN"]
    assert report["series"][0]["zero_count"] == 0
    assert "987654321" not in json.dumps(report)


def test_preflight_counts_zero_and_missing_without_copying_values(tmp_path):
    path = tmp_path / "raw.xlsx"
    workbook = Workbook()
    workbook.active.title = "Provenance"
    _series_sheet(workbook, "WDI", "USA", (("2024", 0), ("2023", None)))
    workbook.save(path)

    report = preflight.inspect_workbook(
        path, "F", hashlib.sha256(path.read_bytes()).hexdigest(),
        _sidecar(path, observation_count=2),
    )

    summary = report["series"][0]
    assert summary["zero_count"] == 1
    assert summary["missing_count"] == 1
    assert "987654321" not in json.dumps(report)


def test_preflight_rejects_formula_cells(tmp_path):
    path = tmp_path / "source.xlsx"
    workbook = Workbook()
    workbook.active.title = "Provenance"
    sheet = _series_sheet(workbook, "WDI", "USA")
    sheet.cell(row=2, column=3, value="=1+1")
    workbook.save(path)

    with pytest.raises(preflight.PreflightError, match="formula_cells_present"):
        preflight.inspect_workbook(
            path, "F", hashlib.sha256(path.read_bytes()).hexdigest(), _sidecar(path),
        )
