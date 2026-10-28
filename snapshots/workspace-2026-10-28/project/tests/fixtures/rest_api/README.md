# REST contract fixtures — synthetic and recorded metadata

Synthetic files exercise documented JSON shapes and are not downloaded observations or evidence of live API access. Recorded metadata files are identified separately below. These fixtures are for contract tests, not financial analysis.

The original FRED/Census/BLS files and `bea_catalogue.json` / `estat_catalogue.json` are synthetic.
`recorded_bea_catalogue.json` and `recorded_estat_catalogue.json` are different: they contain the
sanitized canonical metadata responses captured in Iteration 31 on 2026-10-25. Their source URLs,
UTC retrieval times, hashes and redaction scope are in `recorded_api_catalogues.provenance.json`.
They are metadata only, contain no accepted observations, and are not byte-exact HTTP payloads.
Their hashes and source contracts are checked without network access. Credentials were removed
or replaced with `[REDACTED]` before these fixtures were copied.

- FRED: series/search/observations, series/release and release/sources from the [official v1 docs](https://fred.stlouisfed.org/docs/api/fred/). Pagination and real-time fields stay in the payload.
- Census: catalogue/variables/geography objects and header/row tables from [official query examples](https://www.census.gov/data/developers/guidance/api-user-guide.Example_API_Queries.html). Preserve strings, nulls, geographic identifiers and negative sentinels.
- BLS: v1 Results.series from the [official Python example](https://www.bls.gov/developers/api_python.htm) and the alternative one-item Results list in the [v1 signature](https://www.bls.gov/developers/api_signature.htm). Tests exercise both without rewriting archived structure. M13 and footnotes stay unmodified; no unit/frequency is inferred.
