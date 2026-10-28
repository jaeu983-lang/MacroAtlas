# World Bank WDI exact-series collection

This is the raw-only annual series path added after the fixed USA GDP workflow.
It allows one explicitly selected WDI series per request; it does not extend or
replace GDP-specific Gate A validation.

```bash
macroatlas collect worldbank-series --country CAN --source-id 2 --indicator SP.POP.TOTL --start-year 2024 --end-year 2025 --live
```

The command requires an uppercase ISO3 country, the literal WDI source ID `2`,
an explicit indicator ID, and an inclusive year range. It accepts one series,
1–10 consecutive years within 1960–2100, one JSON page and at most 1 MiB. The
host is fixed at `api.worldbank.org`; arbitrary URLs, indicator discovery,
other World Bank source IDs and bulk requests are rejected. `--live` is required
to enable network access.

The response body and request manifest are written to a unique directory under
`data/raw/worldbank/` before parsing. The parser checks the response identity,
source/country/indicator, page metadata, annual range, duplicate years, and
number-or-null values. It preserves the original rows, order, nulls, zeroes,
empty unit strings and other provider fields. It does not infer a definition,
unit, currency, immutable vintage, or economic validity. The GDP-specific
negative-value check does not apply.

The common annual freshness policy checks the latest non-null observation.
`STALE` and `FRESHNESS_UNVERIFIED` observations are retained in raw files but
withheld from the task result. The route currently has no candidate search or
metadata refresh integration and no CSV/XLSX export.

## Runtime evidence and limits

Fixture tests cover query validation, response identity/schema, raw preservation,
freshness withholding, and the CLI/EngineRegistry path. One live request was
run on 2026-10-28 for Canada `SP.POP.TOTL`, source 2, 2024–2025. Task
`390eeac8-2ed6-40cc-84e5-b2ea5900c488` completed with two rows, latest period
2025, age 301 days and `FRESH`. Its raw response and manifest remain in local
ignored `data/`, not Git. This confirms only that exact request on that date;
it does not establish other indicators' availability, meaning, units, or
dataset terms. Check the selected dataset's terms before redistribution.

Official API references:

- [Indicators API authentication and limits](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)
- [API basic call structures](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures)
- [Indicator API queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries)
- [Dataset terms](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)
