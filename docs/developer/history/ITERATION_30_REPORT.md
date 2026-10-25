# Iteration 30 Report — bounded live canary (Gate U not passed)

**Date:** 2026-10-25
**Scope:** Seven registered dataset paths, one request attempt each, zero automatic retries.
**Setting:** `MACROATLAS_NETWORK_ENABLED=true` was set for this process only at the user's request. The repository `.env` remained unchanged.

## Results

| Profile | Attempts | Outcome | HTTP | Raw/hash read-back |
|---|---:|---|---:|---|
| `fred.gdp` | 1 | `live_contract_validated` | 200 | Verified |
| `census.acs2023.population` | 1 | `live_request_failed` — `LICENSE_SECURITY` / `NEEDS_REVIEW` | Not recorded | Not recorded |
| `bls.unemployment` | 1 | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE` | Not recorded | Not recorded |
| `bls.cpi` | 1 | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE` | Not recorded | Not recorded |
| `tic.mfh.history` | 1 | `live_needs_review` — `dataset_contract_changed` | 200 | Verified |
| `tic.treasury_holdings.2023_01` | 1 | `live_needs_review` — `dataset_contract_changed` | 200 | Verified |
| `boe.bank_rate` | 1 | `live_contract_validated` | 200 | Verified |

The report records seven source request attempts and zero retries. FRED and BoE passed their registered source contract checks. Both TIC files were stored and hash-checked, but their current payloads did not satisfy the registered validators. Census and both BLS paths failed before a validated artifact was reported. The sanitized report does not include response bodies or exception messages, so the exact Census and BLS causes are unresolved.

## Gate decision

**Gate U: NOT PASSED.** Only two of seven paths reached `live_contract_validated`; the other five remain failed or require review. The one-attempt budget is consumed. No retry, fallback, or parser change was performed. Iteration 31 remains blocked until the Census safety classification, the two TIC schema findings, and BLS transient failures are reviewed and a new bounded attempt is authorized.

## Evidence and limitations

- Local-only run JSON: [iteration 30 live canary](../../../reports/iteration_30_live_canary_ffc0fe15c3b440a28c65b64aa9b5bb81.json).
- Earlier network-off preflight: [preflight JSON](../../../reports/iteration_30_live_canary_d8a291e6301f4eb7a8be637f25a5d8b4.json), seven `not_run_network_disabled`, zero requests.
- This run verifies only these bounded source responses and registered structure checks. It does not establish complete dataset coverage, normalized ingestion, broader source availability, or a full 7/7 live pass.
- No automated tests were run as part of this live execution; the existing preparation report separately records the offline test results.
