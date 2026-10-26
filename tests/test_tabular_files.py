"""Iteration 09 bounded parsers, archive integrity, and duplicate handling tests."""
import hashlib
import io
import json
import warnings
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
import pytest

from macro_data_platform.config import Settings
from macro_data_platform.connectors.tabular_files import parse_tabular_document
from macro_data_platform.contracts import StageStatus
from macro_data_platform.ingestion.tabular_files import TabularFileEngine
from macro_data_platform.orchestration import Orchestrator, StageInput
from macro_data_platform.orchestration.models import StageSpec, TaskPlan
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def zipped(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return out.getvalue()


def xlsx_bytes():
    workbook = openpyxl.Workbook()
    workbook.active.title = "Readme"
    sheet = workbook.create_sheet("Data")
    sheet.append(["year", "value"])
    sheet.append([2020, 0])
    sheet.append([2021, "=SUM(B2:B2)"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_csv_preserves_zero_missing_duplicates_and_header_row():
    raw = b"Report title\nyear,value\n2020,0\n2021,\n2021,\n"
    table = parse_tabular_document(raw, "csv", header_row=2)
    assert table.headers == ("year", "value")
    assert table.rows == (("2020", "0"), ("2021", ""), ("2021", ""))
    assert table.duplicate_data_rows == (3,)
    assert table.blank_data_rows == ()


def test_tsv_and_delimited_txt_are_supported_but_fixed_width_is_reviewed():
    assert parse_tabular_document(b"code\tvalue\nA\t1\n", "tsv").rows == (("A", "1"),)
    assert parse_tabular_document(b"code|value\nA|1\n", "txt", delimiter="|").rows == (
        ("A", "1"),
    )
    with pytest.raises(ValueError, match="fixed-width"):
        parse_tabular_document(b"YEAR     VALUE\n2020     1\n", "txt")


def test_tic_shaped_tables_and_bis_style_zip_export_fixtures():
    fixtures = Path(__file__).parent / "fixtures" / "iteration09"
    tic_file = parse_tabular_document(
        (fixtures / "tic_monthly_holdings.tsv").read_bytes(), "tsv",
    )
    tic_table = parse_tabular_document(
        (fixtures / "tic_monthly_holdings.html").read_bytes(), "html",
    )
    bis = parse_tabular_document(
        (fixtures / "bis_global_liquidity_export.zip").read_bytes(), "zip",
        zip_member="SDMX/observations.csv",
    )
    assert tic_file.headers == ("Country", "2020-01", "2020-02", "2020-03")
    assert tic_table.rows[0] == ("Japan", "12.4", "111.0")
    assert bis.zip_member == "SDMX/observations.csv"
    assert bis.headers == ("REF_AREA", "CURRENCY", "COUNTERPART_SECTOR", "TIME_PERIOD", "OBS_VALUE")
    assert bis.rows[0] == ("USA", "USD", "S1", "2025-Q1", "123.4")


def test_csv_rejects_duplicate_headers_nonrectangular_rows_and_invalid_encoding():
    for raw in (b"A,a\n1,2\n", b"A,B\n1\n", b"A\n\xff"):
        with pytest.raises(ValueError):
            parse_tabular_document(raw, "csv")


def test_html_table_selects_by_index_and_rejects_ambiguous_spans():
    html = (b"<html><table><tr><th>year</th><th>value</th></tr><tr><td>2020</td>"
            b"<td>0</td></tr></table><table><tr><th>name</th></tr><tr><td>X</td></tr></table></html>")
    with pytest.raises(ValueError, match="table_index"):
        parse_tabular_document(html, "html")
    table = parse_tabular_document(html, "html", table_index=0)
    assert table.headers == ("year", "value") and table.rows == (("2020", "0"),)
    with pytest.raises(ValueError, match="spans"):
        parse_tabular_document(
            b"<table><tr><th rowspan='2'>year</th></tr></table>", "html",
        )


def test_zip_selects_one_member_without_extracting_and_keeps_member_provenance(tmp_path):
    raw = zipped({"tables/gdp.csv": b"year,value\n2020,0\n"})
    table = parse_tabular_document(raw, "zip")
    assert table.zip_member == "tables/gdp.csv"
    assert table.rows == (("2020", "0"),)
    assert list(tmp_path.iterdir()) == []
    ambiguous = zipped({"a.csv": b"x\n1\n", "b.tsv": b"code\tvalue\nB\t2\n"})
    with pytest.raises(ValueError, match="zip_member"):
        parse_tabular_document(ambiguous, "zip")
    assert parse_tabular_document(ambiguous, "zip", zip_member="b.tsv").rows == (("B", "2"),)


def test_zip_rejects_traversal_duplicates_expansion_bombs_and_nested_unsupported_files():
    with pytest.raises(ValueError, match="traversal"):
        parse_tabular_document(zipped({"../escape.csv": b"a\n1\n"}), "zip")
    duplicate = io.BytesIO()
    with warnings.catch_warnings(record=True) as caught, zipfile.ZipFile(duplicate, "w") as archive:
        warnings.simplefilter("always")
        archive.writestr("same.csv", b"a\n1\n")
        archive.writestr("same.csv", b"a\n2\n")
    assert any("Duplicate name" in str(item.message) for item in caught)
    with pytest.raises(ValueError, match="duplicate"):
        parse_tabular_document(duplicate.getvalue(), "zip")
    bomb = zipped({"large.csv": b"0" * 1_000_000})
    with pytest.raises(ValueError, match="expansion ratio"):
        parse_tabular_document(bomb, "zip")
    with pytest.raises(ValueError, match="zero or multiple"):
        parse_tabular_document(zipped({"readme.md": b"hello"}), "zip")


def test_xlsx_requires_sheet_selection_and_preserves_formula_text():
    raw = xlsx_bytes()
    with pytest.raises(ValueError, match="sheet_name"):
        parse_tabular_document(raw, "xlsx")
    table = parse_tabular_document(raw, "xlsx", sheet_name="Data")
    assert table.headers == ("year", "value")
    assert table.rows == ((2020, 0), (2021, "=SUM(B2:B2)"))
    assert table.warnings


def test_xlsx_rejects_invalid_zip_container_and_cell_limits():
    with pytest.raises(ValueError, match="container"):
        parse_tabular_document(b"not a workbook", "xlsx")


def test_xls_adapter_reads_real_biff_fixture_and_rejects_wrong_container():
    raw = (Path(__file__).parent / "fixtures" / "iteration09" / "simple.xls").read_bytes()
    table = parse_tabular_document(raw, "xls")
    assert table.headers == ("year", "value")
    assert table.rows == ((2020.0, 0.0), (2021.0, 12.5))
    assert table.warnings
    with pytest.raises(ValueError, match="OLE/BIFF"):
        parse_tabular_document(b"not xls", "xls")


def test_engine_archives_raw_before_parse_and_reuses_identical_input(tmp_path):
    settings = Settings(tmp_path)
    inbox = settings._inside("data/inbox")
    inbox.mkdir(parents=True)
    source = inbox / "simple.csv"
    source.write_bytes(b"year,value\n2020,0\n2020,0\n")
    request = StageInput("task", "parse file", "tabular_file", {
        "relative_path": "data/inbox/simple.csv", "format": "csv",
    }, None, ())
    engine = TabularFileEngine(settings)
    first = engine.run(request)
    second = engine.run(request)
    assert first.status is StageStatus.SUCCEEDED
    assert second.status is StageStatus.SUCCEEDED
    assert first.payload["package_id"] == second.payload["package_id"]
    assert first.payload["reused"] is False and second.payload["reused"] is True
    raw_path = tmp_path / first.payload["raw_path"]
    normalized_path = tmp_path / first.payload["normalized_path"]
    manifest = json.loads((tmp_path / first.payload["manifest_path"]).read_text())
    normalized = json.loads(normalized_path.read_text())
    assert raw_path.read_bytes() == source.read_bytes()
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == manifest["raw"]["sha256"]
    assert normalized["duplicate_data_rows"] == [2]
    assert manifest["table"]["duplicate_data_rows"] == [2]


def test_engine_keeps_unparseable_original_and_refuses_paths_outside_inbox(tmp_path):
    settings = Settings(tmp_path)
    inbox = settings._inside("data/inbox")
    inbox.mkdir(parents=True)
    source = inbox / "bad.csv"
    source.write_bytes(b"A,B\n1\n")
    engine = TabularFileEngine(settings)
    result = engine.run(StageInput("task", "parse", "tabular_file", {
        "relative_path": "data/inbox/bad.csv", "format": "csv",
    }, None, ()))
    assert result.status is StageStatus.NEEDS_REVIEW
    assert (tmp_path / result.payload["raw_path"]).read_bytes() == source.read_bytes()
    rejected = engine.run(StageInput("task", "escape", "tabular_file", {
        "relative_path": "data/inbox/../.env.example", "format": "csv",
    }, None, ()))
    assert rejected.status is StageStatus.FAILED_TERMINAL


def test_orchestrator_runs_tabular_file_engine_as_a_registered_stage(tmp_path):
    settings = Settings(tmp_path)
    inbox = settings._inside("data/inbox")
    inbox.mkdir(parents=True)
    (inbox / "source.tsv").write_bytes(b"code\tvalue\nA\t1\n")
    runner = Orchestrator(HistoryStore(settings), {("tabular_file", "1"): TabularFileEngine(settings)})
    task = runner.create("parse local file")
    runner.plan(task.task_id, TaskPlan((StageSpec("parse", "tabular_file", {
        "relative_path": "data/inbox/source.tsv", "format": "tsv",
    }),)))
    result = runner.run(task.task_id)
    assert result["status"] == "COMPLETED"
    assert result["stages"][0]["result"]["payload"]["table"]["row_count"] == 1
