# Latest evidence review — 2026-10-26

Revision 9 follow-up adds two structured X04 fixture cases for holdings versus transactions/unknown
dimensions; the suite now passes **558 tests**. BIS recapture and Git push still fail at the runtime
proxy connection. No live revision/recovery evidence or Iteration 11 work is claimed.

See [Gate C evidence review](GATE_C_REVIEW_2026_10_26.md) for the current checkout,
556 passing tests, and a blocked live BIS recapture (ProxyError before any HTTP response).
Gate C remains not passed; Iteration 11 remains unstarted. Historical live captures below
are not new evidence from this run; their raw files are absent from this checkout.

# Iteration 10 report — quality diagnostics, error classes, and recovery

Completed as the next numbered iteration after 09. The implementation's automated checks used
local fixtures or mocked HTTP responses. A later explicit user request triggered the separate
post-publication live smoke check recorded below. Environment readiness telemetry still reports
network policy `unknown` and BLS/Census secret readiness `unknown`.

## Implemented

- BLS and Census ingestion now retain `SourceFailure.code`, safe HTTP status codes, and a manual
  retry hint for transient failures. This fixes a defect where a retryable BLS/Census failure lost
  its required error code and could be converted by the Orchestrator into `INTERNAL_BUG`.
- HTTP 401/403 map to `AUTH_ACCESS` and review; 429/5xx and timeouts map to retryable `TRANSIENT`;
  redirects map to `LICENSE_SECURITY`; unexpected HTTP statuses map to terminal `SITE_CHANGED`.
  JSON/media/schema drift maps to `SCHEMA_CHANGED`. Each engine invocation sends at most one request;
  recovery is an explicit Orchestrator resume bounded by the existing `max_attempts` setting. The
  later plan-alignment fix parses and persists server `Retry-After` seconds or HTTP-date and blocks
  resume until that minimum delay elapses. No automatic retry or exponential backoff is performed.
- BLS quality summaries count duplicate `(series_id, year, period)` observations and empty values.
  Census summaries check the requested geography code, duplicate geography rows, and null/empty
  cells. Quality failures keep the original response and return `NEEDS_REVIEW`; missing values are
  counted and preserved rather than removed or imputed.
- Unknown unit, frequency, metadata verification, and release/vintage stay unknown and appear as
  warnings. The checks do not infer frequency from periods, fill missing periods, convert units, or
  decide whether a value is an outlier.
- Statistical raw manifests record the original raw SHA256, a canonical fingerprint of the
  official URL plus exact request metadata, and a source-payload comparison SHA256. The bounded
  history scan compares canonical JSON for the same request; for BLS it excludes only the top-level
  `responseTime` field, while retaining the exact source body and raw hash. JSON key order and
  whitespace do not cause a source change. Non-JSON responses fall back to raw-byte comparison.
  Changed payloads get a new write-once package and `NEEDS_REVIEW/QUALITY_FAILURE`. If prior history
  integrity cannot be established or the scan exceeds 1,000 packages/64 MiB, comparison is marked
  unknown.

## Verification

- `python -m pytest`: **518 passed**.
- `python -m ruff check src tests`: passed.
- `git diff --check`: passed.
- Mocked cases cover 403, 429, 503, 404, timeout, one-request-per-attempt behavior, manual retry
  after reopening the Orchestrator, schema drift with raw preservation, missing/duplicate values,
  requested-geography mismatch, unknown metadata, changed and unchanged raw bytes, damaged history,
  and different request scopes.
- No environment changes, configuration publishing, or commits were made during implementation.

## Post-publication live smoke check

After the user asked to execute the next step, the current workspace engines made exactly one
request per source through the configured HTTPS proxy. No retry was sent.

| Source | Request | Result | Preserved artifact |
|---|---|---|---|
| BLS v2 | `CUUR0000SA0`, 2024 | HTTP 200, Orchestrator `COMPLETED`, 12 observations | `data/raw/bls/4e9589686bc44d19925d9629a98e46de/`, 1,181 bytes |
| Census ACS | 2022 ACS 1-year, California, `NAME` + `B01001_001E` | HTTP 200, Orchestrator `COMPLETED`, 1 observation | `data/raw/census/164b0d74c7e744c19b7208117f051cee/`, 64 bytes |

Both manifests identify `live_api`; byte counts and stored SHA256 values match their raw responses.
The manifests contain no key field names and their source URLs have no query string. Quality checks
passed structurally, while unit, frequency, and release/vintage remain unknown warnings.

Both new packages report `source_change_status=unknown_history_integrity`: earlier packages from
the same request predate the SHA256 manifest field, so the current run could not use them as trusted
comparison baselines. A post-hoc parsed comparison across three BLS captures found unchanged
observation rows; only the top-level `responseTime` field differed. All three raw hashes therefore
differ, but the source-data payload is identical under the new comparison rule. Four Census captures
have identical raw hashes. The old manifests still lack an anchored digest, so the engine correctly
leaves their integrity status unknown.

At the time of this smoke check, environment status reported the runtime running at observed spec
revision 5, while network policy and secret readiness were `unknown`. The configuration draft then
had saved BLS/Census bindings and repository reference `codex/iteration-04-gate-a`; the workspace
was on `codex/institution-discovery-05` with later source files uncommitted. These requests verified
the engines in that workspace, not a fresh checkout of the configured reference. No draft edit or
publish was performed in that check. The later revision-5 runtime state and network variable are
recorded in the dated follow-up below.

## Limits and gate status

The comparison currently covers BLS and Census packages, not World Bank packages. It does not
compare decoded JSON semantically, and an HTTP error response body is not archived. Automatic
exponential backoff, a shared rate limiter, economic outlier or gap detection, Census
margins-of-error checks, release-vintage identification, unit conversion, and cross-source
equivalence remain unimplemented. Existing Orchestrator invocation limits and manual resume provide
bounded recovery, but they do not implement a queued chunk scheduler.

Gate C remains **not passed** because the planned provider/file and change/recovery matrix is incomplete;
the BLS/Census smoke requests are only limited live checks. The repository-reference mismatch described
above is a separate release-traceability issue and is not itself a Gate C criterion. Iteration 11 should
wait until Gate C evidence is complete and reviewed.

## Follow-up — published checkout verification and World Bank X08 coverage

On 2026-10-26, the newly published environment was observed running at spec revision 4. Its checkout
was clean on `codex/institution-discovery-05` at
`781827593924e35dadbc1188f09c7ea40a7b7c76`, matching the published source checkpoint. This closes
the source-reference mismatch recorded above for that published baseline. Credential readiness for
`BLS_API_KEY` and `CENSUS_API_KEY`, and network policy enforcement, still report `unknown`. No live
API call was made during that specific revision-4 checkout verification; the later live-smoke evidence
is recorded in the final follow-up section below.

The local Gate C follow-up adds same-request World Bank source-payload comparison to the Gate A
audited path. It scopes history by exact official URL, request parameters, and evidence mode. It
compares canonical JSON (ignoring object-key order and formatting) or exact bytes for non-JSON
content, and verifies a prior raw file and manifest before trusting it. A changed payload preserves
both raw captures and returns `NEEDS_REVIEW` without publishing normalized observations. Failed
collection attempts do not become comparison baselines. Missing, damaged, scan-limited, or
method-incompatible history is
reported as unknown. The scan is capped at the latest 1,000 artifacts.

Fixture tests cover changed and unchanged payloads, different request scopes, tampered prior raw,
legacy artifacts without comparison fields, fixture/live baseline separation, and a retry that
changes the payload. TIC TSV/HTML and BIS ZIP/CSV-shaped fixtures also pass through the local
tabular ingestion engine, with raw/manifest/normalized hashes checked. The changed retry remains
`NEEDS_REVIEW` even after explicit retry approval because that approval predates the new payload
and does not acknowledge its contents. These local edits are not part of the published
checkout. Full verification: **534 pytest passed**, Ruff and `git diff --check` passed. Gate C remains
not passed: official TIC/BIS source and change workflows, Japan provider connectivity, and the
remaining provider-specific recovery evidence still need completion.

## Follow-up — live Treasury TIC file intake and source-change guard

The official Treasury portal linked to Table 5's plain-text file. One earlier GET to that exact
official URL returned HTTP 200, `text/plain`, and 3,804 bytes. The existing response was imported
without another network request through `TabularFileEngine` using tab separation and header row 6.
The raw file and normalized table hashes match their manifests. The parsed table has 36 country rows
and 13 monthly periods from 2025-08 through 2026-08. Treasury labels the measure "holdings at end of
time period" in billions of dollars; Japan's 2026-08 value is 1,068.3. This is a stock/holdings table,
not a securities-transaction flow. Capture provenance records the official URL, agency, title, HTTP
status, content type, and the inbox file's UTC modification time as the local capture timestamp.
The archived package is `data/raw/tabular/492bcc8a6a0e4892ac9c6a9377815aef/`.

The local tabular engine now compares verified raw bytes within the same source URL and parser scope.
Dynamic capture timestamp, HTTP status, and content type do not split a source scope. A changed source
or unverifiable comparison history preserves the new raw capture and returns `NEEDS_REVIEW` before
normalization. Deterministic tests cover changed bytes, unchanged bytes across capture timestamps,
and a tampered prior capture. The real TIC capture is the first observation; no second live TIC
download was made, so live TIC change detection remains unverified.

The current cloud runtime is running at observed spec revision 5 and is connected. BLS and Census
one-request live smoke artifacts in the workspace each returned HTTP 200 and have matching raw SHA256:
BLS `CUUR0000SA0` for 2024 (12 observations, 1,182 bytes) and Census ACS 2022 1-year California
`NAME` + `B01001_001E` (one row, 64 bytes). Their saved manifests report `source_change_status=unchanged`.
Credential and network readiness telemetry remains `unknown`. The `MACROATLAS_NETWORK_ENABLED=true`
runtime requirement is saved only in the current environment draft; it is not active in the posted
runtime. No environment publish, Git commit, or push was performed.

Final local verification at that follow-up: **551 pytest passed**, `ruff check .` passed, and
`git diff --check` passed. That state was superseded by the live BIS/BOJ follow-up below. Gate C
remained not passed because the TIC changed-file case had only fixture evidence, BIS file flow and
BOJ API access had not yet been checked, and provider-specific recovery evidence was incomplete.

## Follow-up — live BIS bulk intake and BOJ access classification (2026-10-26)

The current environment was observed running at posted spec revision 5 and connected. Its process
provides `MACROATLAS_NETWORK_ENABLED=true`; `Settings.from_env` reads it as enabled. Environment
telemetry still reports network policy and secret readiness as `unknown`. No settings were changed
or published during this follow-up.

The official BIS bulk-download page returned HTTP 200 and was archived with its extracted text and
manifest under `data/raw/guides/bis_bulk_download/6a5ca78f2e654ae68a11d624adae2655/`. It linked
`https://data.bis.org/static/bulk/WS_GLI_csv_col.zip`. The ZIP returned HTTP 200, `application/zip`,
104,833 bytes, and SHA256 `aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d`.
The archive contains one CSV (287,530 uncompressed bytes). After preserving case-distinct headers
such as `DECIMALS` and `Decimals`, `TabularFileEngine` imported it successfully: 225 rows and 220
columns, quarter columns spanning 1977-Q4 through 2026-Q1. Raw archive, manifest, and normalized
table hashes match. The package is `792fcb7fd5e246a9a426572642d78465`; the source `Last-Modified`
was recorded. This is a mixed multi-series table and no single unit/frequency is inferred. The
official flat alternative `WS_GLI_csv_flat.zip` returned HTTP 503; no retry was sent and no response
body was archived.

The official BOJ API notice returned HTTP 200 and states that time-series data can be accessed as
JSON or CSV. The linked API user manual returned HTTP 403; only response metadata was recorded in
`data/raw/guides/boj_api_manual/094c7ee9c7e54b6d9512d715af7aac97/manifest.json`. Since the manual
could not establish request parameters or series IDs and no BOJ observation collector exists, no
data API request was formed. BOJ collection is explicitly `BLOCKED`, not passed or silently skipped.

The guide fetcher now preserves `Retry-After` seconds on retryable failures and does not retry
automatically; a fixture verifies a 503 with `Retry-After: 17`. This is simulated error-path evidence.
Live changed-source comparison for TIC/BIS and a provider recovery/resume cycle remain unverified.
The suite now has **556 pytest passed**; `ruff check .` and `git diff --check` passed. Gate C remains
not passed, and Iteration 11 is not started. Code and documentation changes remain uncommitted and
unpushed on `codex/institution-discovery-05` at base HEAD `781827593924e35dadbc1188f09c7ea40a7b7c76`.
