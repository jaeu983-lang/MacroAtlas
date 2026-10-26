"""Bounded parsers for delimited files, spreadsheets, HTML tables and ZIP members."""
import csv
import io
import json
import math
import re
import stat
import zipfile
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any

import openpyxl
import xlrd

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000
MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ZIP_RATIO = 200
MAX_ROWS = 100_000
MAX_COLUMNS = 1000
MAX_CELLS = 500_000
MAX_FIELD_CHARS = 1_000_000
SUPPORTED_FORMATS = {"csv", "tsv", "txt", "html", "zip", "xls", "xlsx"}
_FORMULA_WARNING = "Spreadsheet formulas are preserved or returned as cached values; they are not evaluated."


@dataclass(frozen=True)
class ParsedTable:
    format: str
    headers: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    header_row: int
    sheet_name: str | None = None
    table_index: int | None = None
    zip_member: str | None = None
    duplicate_data_rows: tuple[int, ...] = ()
    blank_data_rows: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def _check_limits(raw: bytes) -> None:
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("source file must be nonempty bytes")
    if len(raw) >= MAX_INPUT_BYTES:
        raise ValueError("source file exceeds the sixteen MiB input limit")


def _validate_headers(values: list[Any]) -> tuple[str, ...]:
    if not 1 <= len(values) < MAX_COLUMNS:
        raise ValueError("table must contain 1..1000 columns")
    headers = []
    for value in values:
        if value is None:
            raise ValueError("table header contains an empty cell")
        text = str(value).strip()
        if not text:
            raise ValueError("table header contains an empty cell")
        headers.append(re.sub(r"\s+", " ", text))
    if len(headers) != len(set(headers)):
        raise ValueError("duplicate table headers are ambiguous")
    return tuple(headers)


def _table(format_name: str, header_values: list[Any], row_values: list[list[Any]], *,
           header_row: int, sheet_name: str | None = None,
           table_index: int | None = None, zip_member: str | None = None,
           warnings: tuple[str, ...] = ()) -> ParsedTable:
    if any(len(str(value)) >= MAX_FIELD_CHARS for row in [header_values, *row_values]
           for value in row if value is not None):
        raise ValueError("table field exceeds the field character limit")
    headers = _validate_headers(header_values)
    if len(row_values) >= MAX_ROWS:
        raise ValueError("table exceeds the 100000 data row limit")
    if len(headers) * (len(row_values) + 1) >= MAX_CELLS:
        raise ValueError("table exceeds the 500000 cell limit")
    rows = []
    duplicate_rows = []
    blank_rows = []
    first_seen = set()
    for index, values in enumerate(row_values, start=1):
        if len(values) != len(headers):
            raise ValueError("table contains a row with a different column count")
        row = tuple(_json_value(value) for value in values)
        if all(value is None or value == "" for value in row):
            blank_rows.append(index)
        else:
            signature = json.dumps(row, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False)
            if signature in first_seen:
                duplicate_rows.append(index)
            first_seen.add(signature)
        rows.append(row)
    return ParsedTable(format_name, headers, tuple(rows), header_row, sheet_name, table_index,
                       zip_member, tuple(duplicate_rows), tuple(blank_rows), warnings)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite spreadsheet numbers are not supported")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError("unsupported spreadsheet cell type")


def _parse_delimited(raw: bytes, format_name: str, *, delimiter: str,
                     header_row: int) -> ParsedTable:
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in {'"', "\r", "\n"}:
        raise ValueError("delimiter must be one non-quote character")
    try:
        text = _decode(raw)
    except UnicodeError:
        raise ValueError("delimited files must use UTF-8 or UTF-16 with a byte-order mark") from None
    if "\x00" in text:
        raise ValueError("delimited file contains a NUL character")
    if format_name == "txt" and delimiter not in text:
        raise ValueError("TXT input must declare a delimiter; fixed-width text is unsupported")
    if type(header_row) is not int or not 1 <= header_row <= MAX_ROWS:
        raise ValueError("header_row must be between 1 and 100000")
    prior_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_FIELD_CHARS)
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        records = []
        cells = 0
        for row in reader:
            if len(records) >= MAX_ROWS + header_row:
                raise ValueError("delimited file exceeds the row limit")
            if len(row) >= MAX_COLUMNS:
                raise ValueError("delimited file exceeds the column limit")
            cells += len(row)
            if cells >= MAX_CELLS:
                raise ValueError("delimited file exceeds the cell limit")
            records.append(row)
    except (csv.Error, UnicodeError):
        raise ValueError("malformed delimited input") from None
    finally:
        csv.field_size_limit(prior_limit)
    if len(records) < header_row:
        raise ValueError("selected header row is missing")
    headers = records[header_row - 1]
    data = records[header_row:]
    if not data:
        raise ValueError("delimited file has no data rows")
    return _table(format_name, headers, data, header_row=header_row)


class _HTMLTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.current_table: list[list[str]] | None = None
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.ignored_depth = 0
        self.cell_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "table":
            if self.current_table is not None:
                raise ValueError("nested HTML tables are ambiguous")
            if len(self.tables) >= 100:
                raise ValueError("HTML source exceeds the 100 table limit")
            self.current_table = []
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in {"th", "td"} and self.current_row is not None:
            if attrs.get("rowspan", "1") != "1" or attrs.get("colspan", "1") != "1":
                raise ValueError("HTML row/column spans require manual review")
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1
            return
        if self.ignored_depth:
            return
        if tag in {"th", "td"} and self.current_cell is not None:
            text = re.sub(r"\s+", " ", "".join(self.current_cell)).strip()
            if self.current_row is not None:
                if len(self.current_row) >= MAX_COLUMNS:
                    raise ValueError("HTML table exceeds the column limit")
                self.current_row.append(text)
                self.cell_count += 1
                if self.cell_count >= MAX_CELLS:
                    raise ValueError("HTML source exceeds the cell limit")
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_table is not None:
                if len(self.current_row) >= MAX_COLUMNS:
                    raise ValueError("HTML table exceeds the column limit")
                if len(self.current_table) >= MAX_ROWS:
                    raise ValueError("HTML table exceeds the row limit")
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None

    def handle_data(self, data):
        if self.current_cell is not None and not self.ignored_depth:
            self.current_cell.append(data)


def _parse_html(raw: bytes, *, table_index: int | None, header_row: int,
                zip_member: str | None = None) -> ParsedTable:
    if type(header_row) is not int or not 1 <= header_row <= MAX_ROWS:
        raise ValueError("header_row must be between 1 and 100000")
    try:
        text = _decode(raw)
    except UnicodeError:
        raise ValueError("HTML input must use UTF-8 or UTF-16 with a byte-order mark") from None
    parser = _HTMLTables()
    try:
        parser.feed(text)
        parser.close()
    except ValueError:
        raise
    except Exception:  # noqa: BLE001 - HTMLParser errors have no safe source context
        raise ValueError("HTML table parsing failed") from None
    if not parser.tables:
        raise ValueError("HTML input contains no tables")
    if table_index is None:
        if len(parser.tables) != 1:
            raise ValueError("select a table_index when HTML contains multiple tables")
        table_index = 0
    if type(table_index) is not int or not 0 <= table_index < len(parser.tables):
        raise ValueError("table_index is outside the document")
    rows = parser.tables[table_index]
    if len(rows) < header_row:
        raise ValueError("selected HTML header row is missing")
    return _table("html", rows[header_row - 1], rows[header_row:],
                  header_row=header_row, table_index=table_index, zip_member=zip_member)


def _validate_zip(raw: bytes, *, workbook: bool = False) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        entries = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        raise ValueError("input is not a valid ZIP container") from None
    if not 1 <= len(entries) < MAX_ZIP_ENTRIES:
        archive.close()
        raise ValueError("ZIP entry count is outside the allowed limit")
    names = [item.filename for item in entries]
    if len(names) != len(set(names)):
        archive.close()
        raise ValueError("ZIP contains duplicate member names")
    total = 0
    for entry in entries:
        name = entry.filename
        mode = (entry.external_attr >> 16) & 0xFFFF
        if ("\\" in name or name.startswith("/")
                or any(part in {"..", "."} for part in name.split("/"))
                or re.match(r"^[A-Za-z]:", name) or stat.S_ISLNK(mode)):
            archive.close()
            raise ValueError("ZIP contains a path traversal or symbolic link")
        if entry.flag_bits & 0x1:
            archive.close()
            raise ValueError("encrypted ZIP entries are unsupported")
        total += entry.file_size
        if total >= MAX_ZIP_UNCOMPRESSED_BYTES:
            archive.close()
            raise ValueError("ZIP exceeds the 64 MiB total uncompressed limit")
        if entry.file_size and entry.file_size / max(entry.compress_size, 1) >= MAX_ZIP_RATIO:
            archive.close()
            raise ValueError("ZIP member expansion ratio exceeds the safety limit")
    if workbook:
        names_lower = set(names)
        if "[Content_Types].xml" not in names_lower or "xl/workbook.xml" not in names_lower:
            archive.close()
            raise ValueError("XLSX container is missing workbook structure")
    return archive


def _zip_member(raw: bytes, *, selected: str | None) -> tuple[bytes, str, str]:
    archive = _validate_zip(raw)
    try:
        supported = [item for item in archive.infolist() if not item.is_dir()
                     and PurePosixPath(item.filename).suffix.lower() in {
                         ".csv", ".tsv", ".txt", ".html", ".htm", ".xls", ".xlsx",
                     }]
        if selected is None:
            if len(supported) != 1:
                raise ValueError("select a zip_member when archive has zero or multiple tabular files")
            entry = supported[0]
        else:
            if not isinstance(selected, str) or selected not in {item.filename for item in supported}:
                raise ValueError("requested zip_member is not a supported archive entry")
            entry = next(item for item in supported if item.filename == selected)
        if entry.file_size >= MAX_INPUT_BYTES:
            raise ValueError("selected ZIP member exceeds the sixteen MiB input limit")
        with archive.open(entry, "r") as stream:
            parts = []
            size = 0
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size >= MAX_INPUT_BYTES:
                    raise ValueError("selected ZIP member exceeds the input limit")
                parts.append(chunk)
        suffix = PurePosixPath(entry.filename).suffix.lower().lstrip(".")
        nested_format = "html" if suffix == "htm" else suffix
        return b"".join(parts), nested_format, entry.filename
    finally:
        archive.close()


def _select_sheet(names: list[str], requested: str | None) -> str:
    if requested is None:
        if len(names) != 1:
            raise ValueError("select a sheet_name when workbook contains multiple sheets")
        return names[0]
    if not isinstance(requested, str) or requested not in names:
        raise ValueError("requested sheet_name does not exist")
    return requested


def _parse_xlsx(raw: bytes, *, sheet_name: str | None, header_row: int) -> ParsedTable:
    archive = _validate_zip(raw, workbook=True)
    archive.close()
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False,
                                          keep_links=False)
    except Exception:  # noqa: BLE001 - do not expose library/parser diagnostics
        raise ValueError("XLSX workbook could not be opened safely") from None
    try:
        selected = _select_sheet(workbook.sheetnames, sheet_name)
        worksheet = workbook[selected]
        if (type(header_row) is not int or not 1 <= header_row <= MAX_ROWS
                or worksheet.max_row is None or worksheet.max_column is None
                or worksheet.max_row >= MAX_ROWS + header_row
                or worksheet.max_column >= MAX_COLUMNS
                or worksheet.max_row * worksheet.max_column >= MAX_CELLS):
            raise ValueError("XLSX dimensions exceed the parsing limit")
        raw_rows = []
        formula_found = False
        for row in worksheet.iter_rows(min_row=header_row, max_col=worksheet.max_column):
            values = []
            for cell in row:
                formula_found = formula_found or cell.data_type == "f"
                values.append(cell.value)
            raw_rows.append(values)
            if len(raw_rows) >= MAX_ROWS + 1:
                raise ValueError("XLSX exceeds the 100000 data row limit")
        while raw_rows and all(value is None for value in raw_rows[-1]):
            raw_rows.pop()
        if len(raw_rows) < 2:
            raise ValueError("XLSX sheet has no data rows")
        warnings = (_FORMULA_WARNING,) if formula_found else ()
        return _table("xlsx", raw_rows[0], raw_rows[1:], header_row=header_row,
                      sheet_name=selected, warnings=warnings)
    finally:
        workbook.close()


def _parse_xls(raw: bytes, *, sheet_name: str | None, header_row: int) -> ParsedTable:
    if not raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise ValueError("XLS input is not an OLE/BIFF workbook")
    try:
        workbook = xlrd.open_workbook(file_contents=raw, on_demand=True)
    except Exception:  # noqa: BLE001 - do not expose library/parser diagnostics
        raise ValueError("XLS workbook could not be opened safely") from None
    try:
        selected = _select_sheet(workbook.sheet_names(), sheet_name)
        sheet = workbook.sheet_by_name(selected)
        if (type(header_row) is not int or not 1 <= header_row <= MAX_ROWS
                or sheet.nrows >= MAX_ROWS + header_row or sheet.ncols >= MAX_COLUMNS
                or sheet.nrows * sheet.ncols >= MAX_CELLS):
            raise ValueError("XLS dimensions exceed the parsing limit")
        values = []
        for row_index in range(header_row - 1, sheet.nrows):
            row = []
            for column_index in range(sheet.ncols):
                cell_type = sheet.cell_type(row_index, column_index)
                value = sheet.cell_value(row_index, column_index)
                if cell_type == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate_as_datetime(value, workbook.datemode)
                elif cell_type == xlrd.XL_CELL_BOOLEAN:
                    value = bool(value)
                elif cell_type == xlrd.XL_CELL_ERROR:
                    value = f"ERROR:{xlrd.error_text_from_code.get(value, 'UNKNOWN')}"
                row.append(value)
            values.append(row)
        if len(values) < 2:
            raise ValueError("XLS sheet has no data rows")
        return _table("xls", values[0], values[1:], header_row=header_row,
                      sheet_name=selected, warnings=(_FORMULA_WARNING,))
    finally:
        workbook.release_resources()


def parse_tabular_document(raw: bytes, format_name: str, *, delimiter: str | None = None,
                           sheet_name: str | None = None, table_index: int | None = None,
                           zip_member: str | None = None, header_row: int = 1) -> ParsedTable:
    """Parse one declared table format; never extract ZIP members to disk."""
    _check_limits(raw)
    if format_name not in SUPPORTED_FORMATS:
        raise ValueError("unsupported tabular format")
    if format_name == "zip":
        member, nested_format, member_name = _zip_member(raw, selected=zip_member)
        parsed = parse_tabular_document(
            member, nested_format, delimiter=delimiter, sheet_name=sheet_name,
            table_index=table_index, header_row=header_row,
        )
        return replace(parsed, zip_member=member_name)
    if format_name in {"csv", "tsv", "txt"}:
        selected_delimiter = delimiter if delimiter is not None else (
            "," if format_name == "csv" else "\t"
        )
        return _parse_delimited(raw, format_name, delimiter=selected_delimiter,
                                header_row=header_row)
    if format_name == "html":
        return _parse_html(raw, table_index=table_index, header_row=header_row)
    if format_name == "xlsx":
        return _parse_xlsx(raw, sheet_name=sheet_name, header_row=header_row)
    return _parse_xls(raw, sheet_name=sheet_name, header_row=header_row)
