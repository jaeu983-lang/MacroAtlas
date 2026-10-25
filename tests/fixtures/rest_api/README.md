# Synthetic REST contract fixtures — Iteration 28

These invented values exercise documented JSON shapes; they are not downloaded official observations or evidence of live API access. Never use them for financial analysis.

- FRED: series/search/observations, series/release and release/sources from the [official v1 docs](https://fred.stlouisfed.org/docs/api/fred/). Pagination and real-time fields stay in the payload.
- Census: catalogue/variables/geography objects and header/row tables from [official query examples](https://www.census.gov/data/developers/guidance/api-user-guide.Example_API_Queries.html). Preserve strings, nulls, geographic identifiers and negative sentinels.
- BLS: v1 Results.series from the [official Python example](https://www.bls.gov/developers/api_python.htm) and the alternative one-item Results list in the [v1 signature](https://www.bls.gov/developers/api_signature.htm). Tests exercise both without rewriting archived structure. M13 and footnotes stay unmodified; no unit/frequency is inferred.
