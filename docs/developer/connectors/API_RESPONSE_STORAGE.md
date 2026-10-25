# API response file archive — Iteration 25

**Status:** common write-once file storage and hash-checked read-back cover 12 API source clients plus 2 official-file source clients (TIC/BoE, Iteration 29). Tests use synthetic/mocked responses; no new institution was collected live. [Dataset contracts](DATASET_CONTRACTS.md) add seven explicit API/file selections, pinned profiles and validation receipts.

## Covered client sources

| Institution ID | Source | Response representation |
|---|---|---|
| `INT-04` | World Bank | Existing response entity bytes; the established `raw/worldbank/` path remains in use. |
| `US-04` | BEA | Canonical UTF-8 JSON made from the transport-sanitized payload. |
| `JP-03` | e-Stat | Canonical UTF-8 JSON made from the transport-sanitized payload. |
| `INT-02` | BIS | Response entity bytes. |
| `INT-03` | OECD | Response entity bytes. |
| `EU-01` | ECB | Response entity bytes. |
| `EU-02` | Eurostat | Response entity bytes. |
| `EU-03` | Deutsche Bundesbank | Response entity bytes. |
| `EU-05` | INSEE | Response entity bytes. |
| `US-02` | FRED | Canonical sanitized JSON; explicit page/vintage parameters. Original agency is not inferred from provider. |
| `US-06` | Census | Canonical sanitized header/row JSON or metadata; key omitted from manifest. |
| `US-05` | BLS v1 | Canonical sanitized JSON; HTTP POST and series/year body conditions retained. No v2 key. |
| `US-03` | Treasury TIC | CSV entity bytes for registered MFH history / January 2023 Table 3D files. |
| `EU-04` | Bank of England | IUDBEDR CSVF=TN entity bytes, native requested date range. |

The shared storage functions live in `macro_data_platform.storage.api_responses`:

- `save_api_response(settings, response, dataset_id=None, series_id=None)` writes a unique response and `request.json` manifest under the configured raw directory.
- `read_api_response(settings, saved_artifact)` reads both files back, checks the saved manifest hash, raw SHA-256, byte count, institution folder, and path boundaries.
- `SavedApiArtifact` carries the paths and hashes for a caller to retain in task history or another trusted record.

Files are created exclusively; an existing response is never overwritten. The manifest records the institution and provider separately from the request operation, safe source URL, HTTP method/status, retrieval time in UTC, content type, dataset/series IDs when supplied, representation, request parameters that passed redaction, byte count, and SHA-256. FRED original source agency remains explicitly unknown until separately established through release/source metadata.

## Data and credential boundary

- The World Bank and six SDMX clients return response entity bytes after Requests content decoding. This does not claim wire-level bytes.
- BEA, e-Stat, FRED, Census and BLS clients do not retain original JSON bytes. Their file is explicitly marked `sanitized_json_payload_canonical_utf8`; it is a reproducible serialization of the redacted parsed payload, not an exact raw HTTP archive.
- Credential parameter names are omitted. Known credential values are redacted from JSON payloads, parameter values, and URLs before writing. Tests use sentinels and assert they do not appear in archive files.
- World Bank non-200 response bodies remain archivable for its existing error-review path and the manifest sets `response_accepted=false`. The BEA/e-Stat/SDMX transports return response objects only for HTTP 200.
- Storage does not parse observations, normalize units, establish data equivalence, or silently populate an analysis table.
- Official CSV files use `response.csv`, `access_method=official_file`, `api_provider=null` and a distinct file provider. Exact source path/dataset/query are checked on write/read. Available ETag/Last-Modified headers pass credential redaction. Known keys found in the raw body cause rejection instead of rewriting source bytes. Shared writer's optional `expected_institution_id` rejects a source mismatch before creating files.

## Integration and evidence limits

The existing fixed World Bank workflow invokes `save_worldbank_download`, delegating to the common writer while preserving its path. The other 11 source clients return response objects; callers can explicitly use `save_api_response()` and retain its reference. A general discovery/ingestion workflow is not connected for those clients. Iteration 28's source validators check FRED page identity, Census table structure and BLS v1 success/selection; they do not normalize observations or establish statistical equivalence. See [FRED](FRED.md), [Census](CENSUS.md), [BLS v1](BLS.md).

`python scripts/verify_rest_adapters.py --fixture` writes three synthetic project-local artifacts, verifies read-back, and produces a report under `reports/iteration_28_offline_*.json`. The script blocks real HTTP and never loads `.env`. Fixture evidence is explicit in its report; archive `mode=api_response` alone is not a live-success claim.

This gate does not prove endpoint reachability, authentication, provider payload correctness, dataset completeness, or all-institution live success. See [the full institution validation program](../testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md) for the remaining source gates.
