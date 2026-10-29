# BLS Public Data API v2 and Census ACS

This note describes the limited observation paths exposed by `macroatlas collect bls` and
`macroatlas collect census`. It does not claim general catalogue search or coverage of all agency
datasets.

## Official references

| Source | Endpoint and documentation |
|---|---|
| BLS Public Data API v2 | `https://api.bls.gov/publicAPI/v2/timeseries/data/`; [API v2 signature](https://www.bls.gov/developers/api_signature_v2.htm) |
| Census ACS | `https://api.census.gov/data/{year}/{dataset}`; [Census API guide](https://www.census.gov/data/developers/guidance/api-user-guide.html) |

## Requests and authentication

BLS accepts one to twenty unique series IDs and an inclusive range of one to twenty calendar years
within 1900–2100. The connector sends one JSON POST with `seriesid`, `startyear`, and `endyear`.
`BLS_API_KEY` is optional for ordinary series data. When a registered key is configured, the
connector also requests `catalog=true` and keeps source-returned series title and catalogue
attributes with JSON-pointer provenance. The catalogue may still omit dataset ID, frequency, unit,
or currency; those fields remain unknown. Without a registered key, the connector omits the
catalogue option and preserves ordinary series-data access. A series ID alone does not prove its
unit, frequency, seasonal adjustment, or economic meaning.

Census accepts one year (connector validation range 2009–2100), dataset `acs/acs1` or `acs/acs5`,
one to fifty unique variable IDs including `NAME`, and geography `us:1` or one `state:NN`. It sends
one GET with `get` and `for` parameters. `CENSUS_API_KEY` is required and read from the process
environment. The API decides whether a requested year/dataset is currently available. The adapter
does not page, batch multiple geographies, or look up variable definitions.

Both commands require `--live`, validate query fields before creating the task, and use the shared
EngineRegistry and Orchestrator. Their task plan contains only the validated query, never API keys.
The Census transport sends its required key as a URL parameter to the official endpoint; the
transport strips the query string from returned source identity, errors, and persisted manifest.
BLS sends its optional key in the POST body, and the body is not included in task history or logs.
When available, the catalogue response is retained as partial metadata evidence and displayed in
the raw XLSX series sheets and the `Series metadata` tab; missing title is explicitly marked
`unknown` and unavailable unit/currency/dataset fields remain unknown.

## Response handling and limits

The shared JSON transport uses a 25-second request timeout, a 2 MiB response cap, verified TLS, and
redirect rejection. It sends one request per stage and does not retry automatically. HTTP 401/403
becomes `NEEDS_REVIEW`; 429/5xx and transient transport failures become `FAILED_RETRYABLE` with a
manual resume hint; unexpected response schemas, redirects, and other statuses stop for review or
terminal failure according to the shared error mapping. Error text does not include credential
values, request URLs, or response bodies.

BLS validates that the response confirms success, returns exactly the requested series IDs, and
contains structurally valid period fields within the requested years. It preserves monthly,
quarterly, annual, or semiannual period labels as provided. Census validates response header order,
row shape, and geography field, then preserves string and null cells. Neither parser invents units
or variable definitions. Quality and freshness checks can withhold observations as
`FRESHNESS_UNVERIFIED` or `STALE`; download time does not make an old observation current.

Each completed or review-stopped response has a preserved raw JSON response and a credential-free
request manifest under `data/raw/{bls,census}/`. Raw hashes and source-change state are retained.
The current CSV exporter accepts only verified World Bank GDP and BOJ FXER tasks. BLS/Census CLI
commands do not create CSV or XLSX analysis workbooks.

API usage limits, terms, attribution, or downstream reuse rights should be checked against the
linked official agency guidance for the intended request. The connector's local caps do not imply an
agency quota or redistribution permission. Fixture tests validate adapter behavior and are not live
API availability evidence.
