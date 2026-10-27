# World Bank GDP quality-policy recheck — 2026-10-27

This is a read-only recheck of the already preserved USA/WDI `NY.GDP.MKTP.CD` task
`0f968a54-9855-439c-aaf2-bb7022fb5c8c` for 2020–2022. It did not make an HTTP request,
write to `data/catalog.sqlite`, replace the archived validation, or alter either source artifact.

The task and artifact records were read from SQLite in read-only mode. The captured response and
request manifest were verified against their recorded SHA-256 hashes, then the saved response was
parsed with `worldbank_gdp_parser_v2` and evaluated with `worldbank_gate_a_v2`.

| Check | Result |
|---|---|
| Raw SHA-256 | `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1` |
| Request manifest SHA-256 | `c8df61cb996e3a5fa3049bc3a4d7fbe3dc042fd2a6d6d22fc1d4d861359ebaff` |
| Parser / quality policy | `worldbank_gdp_parser_v2` / `worldbank_gate_a_v2` |
| Quality result | `passed`; no issues |
| Rows / missing values / negative GDP values | 3 / 0 / 0 |
| Unit and frequency | Unknown; warning retained |

This confirms only that the new negative-value guard does not reject this preserved sample. The
original database validation remains version 1; this report does not rewrite historical task
evidence. The World Bank indicator metadata endpoint was checked separately on 2026-10-27. Its official
title and definition identify GDP in current US dollars, but its structured `unit` field is empty and
the response contains no frequency field. The response and request manifest are preserved at
[`docs/evidence/worldbank_gdp_indicator_metadata_20261027.json`](evidence/worldbank_gdp_indicator_metadata_20261027.json)
and [its manifest](evidence/worldbank_gdp_indicator_metadata_20261027.manifest.json). Therefore the
indicator's current-US-dollar meaning is verified from official descriptive metadata, while normalized
`unit` and `frequency` remain unknown; no unit value was inferred or written into observations.

Broader outlier review, revision history, and cross-source equivalence remain outside the verified scope.

## Official indicator metadata check — 2026-10-27

- Request: one `GET` to `https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD?format=json`, with redirects disabled and a 20-second timeout.
- Response: HTTP 200, `application/json;charset=utf-8`, `Last-Modified: Sun, 25 Oct 2026 14:54:27 GMT`, 938 bytes, SHA-256 `51cec1e144a5bad8d92238630c0a305e20116e86d34ad95c7c315ed166255b28`.
- Captured at: `2026-10-27T06:51:46.588787+00:00`.
- The exact indicator ID is `NY.GDP.MKTP.CD`; source is WDI (`2`); official name is `GDP (current US$)`. `sourceNote` says values are expressed in United States dollars at current prices. The response's `unit` value is the empty string and it has no periodicity/frequency field.
- Decision: preserve the empty raw observation unit and keep normalized unit/frequency unknown. The official display label is descriptive evidence, not a structured unit conversion rule. Do not change the archived observation or quality result.
