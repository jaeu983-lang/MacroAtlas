"""Iteration 09 bounded format parser fixtures; no external source requests."""
from __future__ import annotations

import io
import zipfile

import pytest

from macro_data_platform.ingestion.formats import FormatParseError, ParseLimits, parse_table


def _zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return output.getvalue()


def _xlsx(*, second_sheet=False, formula=False, duplicate_row=False,
          shared_index="1", error_cell=False):
    sheets = ('<sheet name="Holdings" sheetId="1" r:id="rId1"/>'
              + ('<sheet name="Notes" sheetId="2" r:id="rId2"/>' if second_sheet else ''))
    rels = ('<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            + ('<Relationship Id="rId2" Target="worksheets/sheet2.xml" '
               'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
               if second_sheet else ''))
    formula_cell = (
        '<c r="B2"><f>1+1</f><v>2</v></c>' if formula else
        '<c r="B2" t="e"><v>#REF!</v></c>' if error_cell else
        '<c r="B2"><v>123.50</v></c>'
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
        '<c r="B1" t="inlineStr"><is><t>Amount</t></is></c></row>'
        f'<row r="2"><c r="A2" t="s"><v>{shared_index}</v></c>'
        f'{formula_cell}</row>'
        + ('<row r="2"><c r="A2"><v>duplicate</v></c></row>' if duplicate_row else '')
        + '</sheetData></worksheet>'
    )
    entries = {
        "xl/workbook.xml": (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheets}</sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rels}</Relationships>'),
        "xl/sharedStrings.xml": (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<si><t>Period</t></si><si><t>2020</t></si></sst>'),
        "xl/worksheets/sheet1.xml": sheet,
    }
    if second_sheet:
        entries["xl/worksheets/sheet2.xml"] = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Notes</t></is></c>'
            '</row></sheetData></worksheet>')
    return _zip(entries)


def test_delimited_formats_preserve_missing_and_duplicate_rows():
    parsed = parse_table(b"period,value\n2020,\n2020,\n", "csv")
    assert parsed.rows == (("period", "value"), ("2020", ""), ("2020", ""))
    assert "duplicate_rows_preserved" in parsed.warnings
    assert parse_table(b"period\tvalue\n2020\t0\n", "tsv").rows[-1] == ("2020", "0")
    assert parse_table(b"period|value\n2020|NA\n", "txt", delimiter="|").rows[-1] == (
        "2020", "NA")
    with pytest.raises(FormatParseError, match="explicit"):
        parse_table(b"2020|1\n", "txt")


def test_duplicate_header_values_are_reported_and_not_rewritten():
    parsed = parse_table(b"period,value,value\n2020,1,2\n", "csv")
    assert parsed.rows[0] == ("period", "value", "value")
    assert parsed.rows[1] == ("2020", "1", "2")
    assert "duplicate_header_values_preserved" in parsed.warnings


def test_html_table_selection_and_cell_text_are_explicit():
    body = (b"<table><tr><th>Period</th><th>Value</th></tr>"
            b"<tr><td>2020</td><td>1&nbsp;234</td></tr></table>")
    parsed = parse_table(body, "html")
    assert parsed.rows == (("Period", "Value"), ("2020", "1\u00a0234"))
    multi = body + b"<table><tr><td>Other</td></tr></table>"
    with pytest.raises(FormatParseError, match="table index"):
        parse_table(multi, "html")
    assert parse_table(multi, "html", table_index=1).rows == (("Other",),)


@pytest.mark.parametrize(
    "body",
    [
        b"<table><tr><td rowspan='2'>A</td><td>B</td></tr></table>",
        b"<table><tr><td><table><tr><td>A</td></tr></table></td></tr></table>",
    ],
)
def test_html_ambiguous_cell_layouts_fail_closed(body):
    with pytest.raises(FormatParseError):
        parse_table(body, "html")


def test_html_table_count_is_bounded():
    with pytest.raises(FormatParseError, match="count"):
        parse_table(b"<table><tr><td>A</td></tr></table>" * 2, "html",
                    limits=ParseLimits(max_html_tables=1))


def test_zip_requires_unambiguous_member_and_never_extracts_paths(tmp_path):
    zipped = _zip({"tables/holdings.csv": "period,value\n2020,1\n"})
    parsed = parse_table(zipped, "zip")
    assert parsed.source_member == "tables/holdings.csv"
    assert parsed.rows[-1] == ("2020", "1")
    with pytest.raises(FormatParseError, match="member"):
        parse_table(_zip({"a.csv": "a\n", "b.csv": "b\n"}), "zip")
    with pytest.raises(FormatParseError, match="unsafe"):
        parse_table(_zip({"../outside.csv": "a\n"}), "zip")
    assert list(tmp_path.iterdir()) == []


def test_zip_expansion_ratio_and_member_budgets_are_enforced():
    zipped = _zip({"table.csv": "a\n" + "x" * 20_000})
    with pytest.raises(FormatParseError, match="ratio"):
        parse_table(zipped, "zip", limits=ParseLimits(max_compression_ratio=2))
    with pytest.raises(FormatParseError, match="member count"):
        parse_table(_zip({"a.csv": "a", "b.csv": "b"}), "zip",
                    limits=ParseLimits(max_archive_members=1))


def test_xlsx_reads_one_declared_sheet_without_evaluating_cells():
    parsed = parse_table(_xlsx(), "xlsx")
    assert parsed.sheet_name == "Holdings"
    assert parsed.rows == (("Period", "Amount"), ("2020", "123.50"))
    with pytest.raises(FormatParseError, match="explicit sheet"):
        parse_table(_xlsx(second_sheet=True), "xlsx")
    assert parse_table(_xlsx(second_sheet=True), "xlsx", sheet="Notes").rows == (("Notes",),)
    with pytest.raises(FormatParseError, match="formulas"):
        parse_table(_xlsx(formula=True), "xlsx")


def test_xlsx_rejects_external_relationships_and_xml_entity_declarations():
    external = _zip({
        "xl/workbook.xml": (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="https://example.invalid/sheet.xml" '
            'TargetMode="External"/></Relationships>'),
    })
    with pytest.raises(FormatParseError, match="external"):
        parse_table(external, "xlsx")
    injected = _zip({
        "xl/workbook.xml": '<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>',
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'),
    })
    with pytest.raises(FormatParseError, match="DTD"):
        parse_table(injected, "xlsx")


@pytest.mark.parametrize(
    ("workbook", "message"),
    [
        (_xlsx(shared_index="-1"), "shared-string"),
        (_xlsx(duplicate_row=True), "duplicated"),
        (_xlsx(error_cell=True), "error cell"),
    ],
)
def test_xlsx_rejects_invalid_cell_references_and_ambiguous_rows(workbook, message):
    with pytest.raises(FormatParseError, match=message):
        parse_table(workbook, "xlsx")


def test_source_and_table_budgets_fail_closed():
    with pytest.raises(FormatParseError, match="input byte"):
        parse_table(b"a,b\n1,2\n", "csv", limits=ParseLimits(max_input_bytes=3))
    with pytest.raises(FormatParseError, match="row or column"):
        parse_table(b"a\n1\n2\n", "csv", limits=ParseLimits(max_rows=2))


def test_legacy_xls_requires_an_explicit_available_parser(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "xlrd", None)
    with pytest.raises(FormatParseError, match="xlrd"):
        parse_table(b"not a workbook", "xls")
