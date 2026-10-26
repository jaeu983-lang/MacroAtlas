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

The current environment status after the smoke check reports the runtime running at observed spec
revision 5, but network policy and secret readiness remain `unknown`. The current configuration
draft is based on the active version and has saved BLS/Census bindings. Its repository reference is
still `codex/iteration-04-gate-a`; the current workspace is on `codex/institution-discovery-05`
with the later source files uncommitted. These two requests verify the engines in the current
workspace, not that a fresh checkout from the configured repository reference contains those files.
No draft edit or publish was performed.

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
