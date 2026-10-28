"""Bounded, non-executing parsers for source-declared tabular files."""
from __future__ import annotations

import csv
import io
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class ParseLimits:
    max_input_bytes: int = 16 * 1024 * 1024
    max_archive_members: int = 128
    max_archive_bytes: int = 32 * 1024 * 1024
    max_compression_ratio: int = 100
    max_html_tables: int = 128
    max_rows: int = 100_000
    max_columns: int = 512
    max_cells: int = 500_000

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (
            self.max_input_bytes, self.max_archive_members, self.max_archive_bytes,
            self.max_compression_ratio, self.max_html_tables, self.max_rows,
            self.max_columns, self.max_cells,
        )):
            raise ValueError("parser limits must be positive integers")


DEFAULT_LIMITS = ParseLimits()
MAX_SOURCE_BYTES = DEFAULT_LIMITS.max_input_bytes


class FormatParseError(ValueError):
    """Untrusted source bytes cannot be parsed under the declared bounded format."""


@dataclass(frozen=True)
class ParsedTable:
    format: str
    rows: tuple[tuple[str, ...], ...]
    source_member: str | None = None
    sheet_name: str | None = None
    table_index: int | None = None
    warnings: tuple[str, ...] = ()


def _input(body: bytes, limits: ParseLimits) -> None:
    if not isinstance(body, bytes) or not body or len(body) > limits.max_input_bytes:
        raise FormatParseError("source file is empty or exceeds the input byte limit")


def _bounded(rows, fmt: str, limits: ParseLimits, **metadata) -> ParsedTable:
    result = []
    cells = 0
    for row in rows:
        row = tuple(str(value) for value in row)
        if len(result) >= limits.max_rows or len(row) > limits.max_columns:
            raise FormatParseError("tabular row or column limit exceeded")
        cells += len(row)
        if cells > limits.max_cells:
            raise FormatParseError("tabular cell limit exceeded")
        result.append(row)
    warnings = []
    if result and len(result[0]) != len(set(result[0])):
        warnings.append("duplicate_header_values_preserved")
    seen, duplicates = set(), False
    for row in result[1:] if len(result) > 1 else ():
        if row in seen:
            duplicates = True
        seen.add(row)
    if duplicates:
        warnings.append("duplicate_rows_preserved")
    return ParsedTable(fmt, tuple(result), warnings=tuple(warnings), **metadata)


def _decode(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise FormatParseError("only UTF-8 source text is supported") from None


class _HTMLTables(HTMLParser):
    def __init__(self, limits: ParseLimits):
        super().__init__(convert_charrefs=True)
        self.limits = limits
        self.tables: list[list[list[str]]] = []
        self.table_depth = 0
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.cell_count = 0
        self.invalid_reason: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table_depth:
                self.invalid_reason = "nested HTML tables are ambiguous"
                return
            if len(self.tables) >= self.limits.max_html_tables:
                self.invalid_reason = "HTML table count exceeds the limit"
                return
            self.tables.append([])
            self.table_depth = 1
        elif self.table_depth == 1 and tag == "tr":
            if self.row is not None:
                self.invalid_reason = "nested HTML rows are ambiguous"
                return
            self.row = []
        elif self.table_depth == 1 and tag in {"th", "td"} and self.row is not None:
            attributes = dict(attrs)
            if (self.cell is not None or
                    attributes.get("rowspan", "1") != "1" or
                    attributes.get("colspan", "1") != "1"):
                self.invalid_reason = "HTML merged cells are unsupported"
                return
            self.cell = []
        elif self.table_depth == 1 and tag == "br" and self.cell is not None:
            self.cell.append(" ")
        elif self.table_depth == 1 and tag in {"script", "style"} and self.cell is not None:
            self.invalid_reason = "HTML script or style content inside a cell is ambiguous"

    def handle_endtag(self, tag):
        if self.table_depth == 1 and tag in {"th", "td"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
            self.cell_count += 1
            if self.cell_count > self.limits.max_cells:
                self.invalid_reason = "HTML cell limit exceeded"
            elif len(self.row) > self.limits.max_columns:
                self.invalid_reason = "HTML column limit exceeded"
        elif self.table_depth == 1 and tag == "tr" and self.row is not None:
            if self.row:
                self.tables[-1].append(self.row)
                if len(self.tables[-1]) > self.limits.max_rows:
                    self.invalid_reason = "HTML row limit exceeded"
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth = 0

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _archive_infos(body: bytes, limits: ParseLimits):
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError):
        raise FormatParseError("invalid ZIP container") from None
    if not infos or len(infos) > limits.max_archive_members:
        archive.close()
        raise FormatParseError("ZIP member count is empty or exceeds the limit")
    names, total = set(), 0
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (not name or "\\" in name or path.is_absolute() or
                any(part in {".", ".."} for part in path.parts) or name in names or
                stat.S_ISLNK(mode) or info.flag_bits & 1):
            archive.close()
            raise FormatParseError("ZIP contains an unsafe, duplicate, or encrypted member")
        names.add(name)
        total += info.file_size
        if total > limits.max_archive_bytes:
            archive.close()
            raise FormatParseError("ZIP expanded byte limit exceeded")
        if info.file_size and (not info.compress_size or
                               info.file_size / info.compress_size > limits.max_compression_ratio):
            archive.close()
            raise FormatParseError("ZIP compression ratio exceeds the limit")
    return archive, infos


def _safe_xml(body: bytes, limits: ParseLimits):
    if len(body) > limits.max_archive_bytes:
        raise FormatParseError("XML part exceeds the byte limit")
    upper = body.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FormatParseError("XML DTD and entity declarations are forbidden")
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        raise FormatParseError("invalid XML source part") from None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _column_number(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]{1,3})[1-9][0-9]*", reference or "")
    if match is None:
        raise FormatParseError("XLSX cell has an invalid coordinate")
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - ord("A") + 1
    return column


def _xlsx(body: bytes, *, sheet: str | None, limits: ParseLimits):
    archive, infos = _archive_infos(body, limits)
    names = {item.filename for item in infos if not item.is_dir()}
    if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
        archive.close()
        raise FormatParseError("XLSX workbook structure is incomplete")
    if any("externallinks" in name.lower() or name.lower().endswith("vbaproject.bin")
           for name in names):
        archive.close()
        raise FormatParseError("XLSX external links or macros are unsupported")
    try:
        workbook = _safe_xml(archive.read("xl/workbook.xml"), limits)
        relationships = _safe_xml(archive.read("xl/_rels/workbook.xml.rels"), limits)
        relation_map = {}
        for relation in relationships:
            if _local(relation.tag) != "Relationship":
                continue
            if relation.get("TargetMode", "Internal") != "Internal":
                raise FormatParseError("XLSX external relationships are unsupported")
            relation_id, target = relation.get("Id"), relation.get("Target")
            if not relation_id or not target:
                raise FormatParseError("XLSX relationship is incomplete")
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                      else posixpath.join("xl", target))
            if path.startswith("../") or path == ".." or path not in names:
                raise FormatParseError("XLSX relationship escapes or misses the archive")
            relation_map[relation_id] = path
        sheets = []
        for node in workbook.iter():
            if _local(node.tag) == "sheet":
                rid = next((value for key, value in node.attrib.items()
                            if key.rsplit("}", 1)[-1] == "id"), None)
                if not node.get("name") or rid not in relation_map:
                    raise FormatParseError("XLSX sheet relationship is invalid")
                sheets.append((node.get("name"), relation_map[rid]))
        if not sheets:
            raise FormatParseError("XLSX workbook contains no worksheets")
        if sheet is None:
            if len(sheets) != 1:
                raise FormatParseError("multiple XLSX sheets require an explicit sheet name")
            sheet_name, path = sheets[0]
        else:
            selected = [item for item in sheets if item[0] == sheet]
            if len(selected) != 1:
                raise FormatParseError("requested XLSX sheet was not found uniquely")
            sheet_name, path = selected[0]
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = _safe_xml(archive.read("xl/sharedStrings.xml"), limits)
            for item in root:
                if _local(item.tag) == "si":
                    shared.append("".join(node.text or "" for node in item.iter()
                                          if _local(node.tag) == "t"))
                    if len(shared) > limits.max_cells:
                        raise FormatParseError("XLSX shared-string limit exceeded")
        root = _safe_xml(archive.read(path), limits)
        row_values = []
        seen_rows = set()
        for row in root.iter():
            if _local(row.tag) != "row":
                continue
            row_number = row.get("r")
            if row_number is None or not row_number.isdigit() or int(row_number) < 1:
                raise FormatParseError("XLSX row has an invalid coordinate")
            row_index = int(row_number)
            if row_index > limits.max_rows or row_index in seen_rows:
                raise FormatParseError("XLSX row limit exceeded or row index is duplicated")
            seen_rows.add(row_index)
            cells = {}
            for cell in row:
                if _local(cell.tag) != "c":
                    continue
                if cell.find("{*}f") is not None:
                    raise FormatParseError("XLSX formulas are not evaluated")
                reference = cell.get("r")
                column = _column_number(reference)
                if column > limits.max_columns or column in cells:
                    raise FormatParseError("XLSX column limit or duplicate cell exceeded")
                kind = cell.get("t", "n")
                value = cell.find("{*}v")
                if kind == "inlineStr":
                    parsed = "".join(node.text or "" for node in cell.iter()
                                     if _local(node.tag) == "t")
                elif value is None or value.text is None:
                    parsed = ""
                elif kind == "s":
                    try:
                        shared_index = int(value.text)
                        if shared_index < 0:
                            raise IndexError
                        parsed = shared[shared_index]
                    except (ValueError, IndexError):
                        raise FormatParseError("XLSX shared-string reference is invalid") from None
                elif kind == "e":
                    raise FormatParseError("XLSX contains a spreadsheet error cell")
                else:
                    parsed = value.text
                cells[column] = parsed
            row_values.append((row_index, cells))
            if len(row_values) > limits.max_rows:
                raise FormatParseError("XLSX row limit exceeded")
        if not row_values:
            raise FormatParseError("XLSX worksheet contains no rows")
        max_row = max(index for index, _ in row_values)
        max_column = max((max(cells, default=0) for _, cells in row_values), default=0)
        if max_row * max_column > limits.max_cells:
            raise FormatParseError("XLSX sparse cell expansion exceeds the cell limit")
        matrix = [[""] * max_column for _ in range(max_row)]
        for row_index, cells in row_values:
            for column, value in cells.items():
                matrix[row_index - 1][column - 1] = value
        return _bounded(matrix, "xlsx", limits, sheet_name=sheet_name)
    finally:
        archive.close()


def _xls(body: bytes, *, sheet: str | None, limits: ParseLimits):
    try:
        import xlrd
    except ImportError:
        raise FormatParseError("legacy XLS requires the declared xlrd parser dependency") from None
    try:
        workbook = xlrd.open_workbook(file_contents=body, on_demand=True)
        if sheet is None:
            if workbook.nsheets != 1:
                raise FormatParseError("multiple XLS sheets require an explicit sheet name")
            source = workbook.sheet_by_index(0)
        else:
            source = workbook.sheet_by_name(sheet)
        if source.nrows > limits.max_rows or source.ncols > limits.max_columns or (
                source.nrows * source.ncols > limits.max_cells):
            raise FormatParseError("XLS row, column, or cell limit exceeded")
        rows = []
        for row_index in range(source.nrows):
            values = []
            for column in range(source.ncols):
                cell = source.cell(row_index, column)
                if cell.ctype == xlrd.XL_CELL_ERROR:
                    raise FormatParseError("XLS contains a spreadsheet error cell")
                values.append("" if cell.ctype == xlrd.XL_CELL_EMPTY else str(cell.value))
            rows.append(values)
        return _bounded(rows, "xls", limits, sheet_name=source.name)
    except FormatParseError:
        raise
    except Exception as exc:
        raise FormatParseError("XLS workbook is invalid or unsupported") from exc
    finally:
        try:
            workbook.release_resources()
        except UnboundLocalError:
            pass


_ZIP_FORMATS = {".csv": "csv", ".tsv": "tsv", ".txt": "txt",
                ".html": "html", ".htm": "html", ".xlsx": "xlsx", ".xls": "xls"}


def parse_table(body: bytes, format: str, *, delimiter: str | None = None,
                member: str | None = None, sheet: str | None = None,
                table_index: int | None = None, limits: ParseLimits = DEFAULT_LIMITS) -> ParsedTable:
    """Parse one explicitly declared table; preserve every source row including duplicates."""
    _input(body, limits)
    if format == "zip":
        archive, infos = _archive_infos(body, limits)
        try:
            files = [info for info in infos if not info.is_dir()]
            selected = None
            if member is None:
                eligible = [item for item in files
                            if PurePosixPath(item.filename).suffix.lower() in _ZIP_FORMATS]
                if len(eligible) != 1:
                    raise FormatParseError("ZIP needs an explicit member unless exactly one table exists")
                selected = eligible[0]
            else:
                if member.startswith(("/", "\\")) or "\\" in member or ".." in PurePosixPath(member).parts:
                    raise FormatParseError("ZIP member path is unsafe")
                matches = [item for item in files if item.filename == member]
                if len(matches) != 1:
                    raise FormatParseError("ZIP member was not found uniquely")
                selected = matches[0]
            inner = _ZIP_FORMATS.get(PurePosixPath(selected.filename).suffix.lower())
            if inner is None:
                raise FormatParseError("ZIP member format is unsupported")
            inner_body = archive.read(selected)
        except (KeyError, OSError, zipfile.BadZipFile):
            raise FormatParseError("ZIP member could not be read") from None
        finally:
            archive.close()
        parsed = parse_table(inner_body, inner, delimiter=delimiter, sheet=sheet,
                             table_index=table_index, limits=limits)
        return ParsedTable(parsed.format, parsed.rows, source_member=selected.filename,
                           sheet_name=parsed.sheet_name, table_index=parsed.table_index,
                           warnings=parsed.warnings)
    if format == "xlsx":
        return _xlsx(body, sheet=sheet, limits=limits)
    if format == "xls":
        return _xls(body, sheet=sheet, limits=limits)
    if format == "html":
        parser = _HTMLTables(limits)
        try:
            parser.feed(_decode(body))
            parser.close()
        except (ValueError, AssertionError):
            raise FormatParseError("invalid HTML table") from None
        if parser.invalid_reason:
            raise FormatParseError(parser.invalid_reason)
        tables = [table for table in parser.tables if table]
        if table_index is None:
            if len(tables) != 1:
                raise FormatParseError("HTML needs an explicit table index unless exactly one table exists")
            index = 0
        elif type(table_index) is not int or table_index < 0 or table_index >= len(tables):
            raise FormatParseError("requested HTML table index is out of range")
        else:
            index = table_index
        return _bounded(tables[index], format, limits, table_index=index)
    if format not in {"csv", "tsv", "txt"}:
        raise FormatParseError("unsupported declared table format")
    if format == "txt" and (not isinstance(delimiter, str) or len(delimiter) != 1):
        raise FormatParseError("TXT parsing requires an explicit single-character delimiter")
    separator = delimiter if format == "txt" else ("\t" if format == "tsv" else ",")
    try:
        rows = csv.reader(io.StringIO(_decode(body), newline=""), delimiter=separator, strict=True)
        return _bounded(rows, format, limits)
    except csv.Error:
        raise FormatParseError("invalid delimited table") from None
