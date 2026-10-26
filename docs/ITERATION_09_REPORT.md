# Iteration 09 report — bounded file parsing and acquisition planning

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

Completed after Iteration 08, in the requested order. Work in this iteration uses local files and
deterministic fixtures; it made no external API requests. The runtime network policy and secret
readiness were `unknown`, so no live BLS, Census, or other source validation was attempted.

## Implemented

- Added explicit parsers for UTF-8/UTF-16 CSV and TSV, delimited TXT, HTML tables, selected tabular
  ZIP members, XLS, and XLSX. TXT must contain or declare a delimiter; fixed-width text is rejected.
  Ambiguous multi-table, multi-sheet, and multi-member inputs require an explicit selection.
- Added the `tabular_file/1` Orchestrator engine. It reads only an existing file under
  `data/inbox/`, requires an explicit format, and archives the original before parsing. The raw file
  and normalized JSON table are stored separately under `data/raw/tabular/` and
  `data/processed/tabular/`. Identical raw content, parser revision, and options reuse a verified
  prior package. Parse failures retain the source and return `NEEDS_REVIEW`.
- Kept duplicate data rows and their 1-based positions; blank rows and duplicate positions are
  reported. Duplicate headers, malformed row widths, non-finite spreadsheet values, HTML spans,
  nested tables, and unsupported table shapes are rejected for review. Spreadsheet formulas are
  not calculated: XLSX formulas remain text and XLS values are whatever cached values the file has.
- Applied bounded-input limits: 16 MiB source; 1,000 ZIP entries; 64 MiB ZIP expansion and 200x
  expansion ratio; 100,000 data rows; 1,000 columns; 500,000 cells; 1 MiB per delimited field.
  ZIP members are read in memory without extraction. Traversal paths, symlinks, encryption,
  duplicate member names, and expansion bombs are rejected. Added `openpyxl` and `xlrd` as declared
  runtime dependencies.
- Added the planning-only `plan_source_collection()` utility for the existing World Bank USA GDP
  path, selected BLS series, and Census ACS selections. It distinguishes `sample` and `full`, splits
  by supported year windows, BLS series groups, and Census variable/geography combinations, and
  caps plans at 1,000 chunks. Census chunks include `NAME`. Only `raw_json` is currently supported.
  Expected size is marked `unknown` unless the caller supplies an estimate. Planning performs zero
  network requests and does not enqueue or execute chunks.
- Added synthetic TIC-style TSV/HTML and BIS-style ZIP fixtures, plus a small XLS fixture. They
  exercise parser behavior, not current agency data or live source availability.

## Use

Place an explicitly selected file under `data/inbox/`, then register
`TabularFileEngine(settings)` as `("tabular_file", "1")`. A stage can pass, for example:

```python
{"relative_path": "data/inbox/source.tsv", "format": "tsv"}
```

Optional parser choices include `delimiter`, 1-based `header_row`, `sheet_name`, `table_index`,
and `zip_member`. There is no command-line importer or automatic file discovery yet.

The planning utility is called directly from Python, for example:

```python
plan_source_collection(
    "bls",
    {"series_ids": ["CUUR0000SA0"], "start_year": 2020, "end_year": 2024},
    mode="sample",
)
```

It returns a plan description only. It does not persist a task, start collectors, estimate bytes
from source metadata, or resume partial chunk results.

## Verification and remaining work

- `python -m pytest`: **499 passed**.
- `python -m ruff check src tests`: passed.
- `git diff --check`: passed.
- Focused parser/planner tests cover supported formats, duplicates and blanks, ambiguous inputs,
  unsafe ZIP contents, local-path restrictions, archive reuse and integrity, source preservation on
  parse failure, Orchestrator registration, bounded source plans, and malformed plan inputs.
- No external network requests, environment edits, environment publishing, or commits were made.

PDF numeric parsing, fixed-width text, arbitrary API discovery or fetching, API output conversion,
CSV/XLSX exporters, formula evaluation, broad statistical semantic validation, queued chunk
execution/recovery, and measured size estimation remain open. Iteration 09 does not claim Gate C;
the error/recovery and live-change cases remain for Iteration 10. Iteration 08 also remains a partial
Gate B result: the fixture World Bank path passes, while broad official search, natural-language
interpretation, and live BLS/Census selection-to-collection remain unverified.
