# Iteration 28 — FRED, Census and keyless BLS v1 adapters with file tests

**Date:** 2026-10-25\
**Gate:** S — PASS\
**Starting HEAD:** `778ab412d3076aad4a37d6f3140b6ced54b56d26`. Existing dirty worktree changes were preserved; no stage, commit, merge, publish or checkpoint was performed.

## Delivered scope

The user requested FRED and Census adapters while they enter keys, plus **BLS API 1.0 only**, through file storage and testing. This one iteration replaces the previously queued IMF documentation candidate; IMF remains a later independent gate.

| Provider | Implemented and tested | Explicit limits |
|---|---|---|
| FRED / ALFRED v1 | Series metadata, search page, observation page with optional real-time window, series release and release sources; sanitized JSON archive/read-back | Explicit one-page methods and preserved count/offset/limit; no automatic pagination, frequency/unit transformation or Board crosswalk; original agency is not inferred from the FRED API provider |
| Census | Keyless catalogue/variables/geography metadata and keyed data queries returning original header/row arrays; archive/read-back | 1–50 distinct variables, explicit predicates, safe dataset path; no expanded group query, automatic split, numeric coercion or statistical sentinel interpretation |
| BLS v1 | Keyless POST of 1–25 series and up to 10 inclusive years; success/warning/selection/schema checks; archive/read-back | V1 URL only, no registrationkey or v2 fallback; one request per method, no automatic retry/daily-budget scheduler |

These are limited Python clients and source-specific response-contract checks, not a general natural-language ingestion workflow or normalized observation database.

## Official request evidence

- FRED v1: [series](https://fred.stlouisfed.org/docs/api/fred/series.html), [search](https://fred.stlouisfed.org/docs/api/fred/series_search.html), [observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [series release](https://fred.stlouisfed.org/docs/api/fred/series_release.html), [release sources](https://fred.stlouisfed.org/docs/api/fred/release_sources.html). The configured FRED key is sent only through the reviewed v1 request and is removed from response metadata and files. FRED real-time request/response bounds are checked.
- Census: [developer guide](https://www.census.gov/data/developers.html), [query examples](https://www.census.gov/data/developers/guidance/api-user-guide.Example_API_Queries.html), and [metadata key exception](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23). The data key is taken only from Settings; metadata calls omit it.
- BLS: [v1 signatures](https://www.bls.gov/developers/api_signature.htm), [official Python example](https://www.bls.gov/developers/api_python.htm), [FAQ](https://www.bls.gov/developers/api_faqs.htm). The period-filtered multi-series request is a v1 JSON POST. The signature documents a one-item Results list, while the Python example accesses a Results object; both are validated while preserving the original payload. The documented unregistered daily allowance is 25 requests; enforcement across jobs remains an operator responsibility.

Only official documentation was browsed. No actual statistical endpoint or credential-validation request was made.

## Shared transport and storage

`BoundedHttpTransport.post_json()` adds a 16 KiB request-body limit and reuses GET's network opt-in, host/path policy, `trust_env=False`, default TLS verification, no redirects, `(5,20)` second connect/read timeout, elapsed budget and streaming response-size guard. The JSON-family wrapper permits POST only at the fixed BLS v1 URL with the three documented fields. The existing World Bank/SDMX/BEA/e-Stat GET contracts remain covered by regression tests.

The archive registers FRED `US-02`, BLS `US-05` and Census `US-06`, bringing explicit client-to-file support to 12 source clients. It records HTTP method and safe request conditions, excludes Census `key` and credential parameter names, and redacts all five configured known credential values before file serialization. FRED has a separate API-provider label and unknown `original_source_agency` until independently established. Stored JSON is **sanitized canonical UTF-8 payload, not exact HTTP response bytes**.

FRED `"."`, `"0"`, Census null/negative sentinels/leading-zero geographic identifiers, BLS `"-"`, M13 and footnotes are preserved without numerical conversion. API errors, BLS warnings/partial selections, wrong pages/vintages, malformed tables, redirects and incomplete oversized responses are not silently accepted as collected observations.

## Inspectable project files

The fixture-only script blocks real Requests HTTP, uses explicit dummy settings and never loads `.env`. It generated and verified three write-once artifacts:

| Source | Saved JSON | Manifest |
|---|---|---|
| FRED | [response](../../../data/raw/api/US-02/fb1975fce52e4543a2f2df96b2a0a205/response.json) | [request](../../../data/raw/api/US-02/fb1975fce52e4543a2f2df96b2a0a205/request.json) |
| Census | [response](../../../data/raw/api/US-06/82e6c31e4241483aa7a2c3e5f2387381/response.json) | [request](../../../data/raw/api/US-06/82e6c31e4241483aa7a2c3e5f2387381/request.json) |
| BLS v1 | [response](../../../data/raw/api/US-05/3d74bb90f9d74b6bb99c157270eb9cbd/response.json) | [request](../../../data/raw/api/US-05/3d74bb90f9d74b6bb99c157270eb9cbd/request.json) |

[Machine-readable fixture report](../../../reports/iteration_28_offline_1ed43019cf344e5d86c64d5d79105a79.json) labels every result `synthetic_fixture` / `fixture_file_roundtrip_pass`, records safe request conditions, file paths/hashes, and live request count 0. These values are invented test data, not financial data. Archive mode `api_response` alone is not live evidence.

Reproduce from the repository root with the repository Python runtime and current `src` on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe scripts/verify_rest_adapters.py --fixture
```

Each run uses new UUIDs and preserves existing files. There is no live mode. Fixture-directory creation and raw-parent creation were initially denied in the managed environment; narrowly scoped approved retries created only the requested project-local directories/artifacts. No global ACL, sandbox setting or secret was changed.

## Verification

| Check | Final result |
|---|---|
| New source contract/file tests | **71 passed**, 0 failed (1.30 seconds) |
| Full offline suite | **763 passed, 1 skipped, 0 failed**, exit 0 (70.76 seconds) |
| Skip | `tests/test_official_api_credentials.py:155`, symlink creation unavailable in this Windows environment |
| Ruff, all modified Python files | **Passed**, `--no-cache` |
| Project-local demonstration | All 3 sources saved and read back with payload equality, safe manifest and hash checks |
| Real keys read/modified or credential transmissions | None; `.env` was not read or changed |
| Live statistical requests | **0**; official documentation research and synthetic fixtures only |

The suite ran in the repository `.venv` with current `src` on `PYTHONPATH`. Tests cover allowed routes, source identity, page/vintage/period checks, missing and zero preservation, Census timeseries predicates, BLS alternative Results shapes, v1 caps, v2/key rejection, credentials, network opt-in, HTTP/TLS/timeout failures without retries or artifacts, redaction, write-once/hash read-back and tamper rejection. New POST request-size/response-size checks share the existing GET regression coverage.

## Material files changed

- New clients: `src/macro_data_platform/connectors/fred.py`, `census.py`, `bls.py`.
- Shared execution and files: `connectors/http_transport.py`, `connectors/official_api.py`, `storage/api_responses.py`.
- Readiness: `discovery/source_registry.py`, `tests/test_source_registry.py`; all three remain partial/source-specific synthetic/not-live. Board-specific adapter status remains unimplemented.
- Tests and fixtures: `tests/test_us_rest_connectors.py`, `tests/test_http_transport.py`, `tests/fixtures/rest_api/README.md`, `fred.json`, `census.json`, `bls_v1.json`.
- Reproduction: `scripts/verify_rest_adapters.py`; ignored project raw examples and the fixture report above.
- Developer docs: three connector references and index, shared HTTP/archive/architecture references, implementation/execution plan, all-source testing program, D-095 and this report.
- Operator/product docs: key guide, runbook/index, source catalogue/audit/implementation status, `PROJECT_PLAN.md`, `README.md`.

## Remaining limits and review

FRED/Census credentials and all three live payloads are unverified. Census root catalogue or large variable/data queries may exceed the 1 MiB response cap; clients deliberately refuse oversize responses rather than implementing asynchronous/split downloads. FRED returns explicit pages; whole-dataset assembly is absent. BLS daily allowance coordination, automatic retries and v2 are absent. Units, missing-code semantics, revisions and original statistical agencies require source metadata and later quality gates; metadata is preserved without inferred equivalence.

Human diff review remains required before integration. No further key is needed for the current BLS v1 path. FRED/Census keys can be entered by the user for a later bounded live gate. IMF exact route/auth documentation is the next separate candidate; this task does not proceed to it.
