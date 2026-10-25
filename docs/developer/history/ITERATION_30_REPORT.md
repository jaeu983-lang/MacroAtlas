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

**Gate U at the original run: NOT PASSED.** Only two of seven paths reached `live_contract_validated`; the other five remained failed or required review. The one-attempt budget was consumed. During that canary, no retry, fallback, or parser change was performed.

## Post-run offline review of saved TIC responses

After the original run, the saved raw files were inspected and the current source validators were run against those bytes locally. No network request was made, and neither the write-once raw files nor the original receipts were changed.

| Profile | Saved raw | Offline result with current validator | Finding |
|---|---|---|---|
| `tic.mfh.history` | 98,124 bytes; SHA-256 still matches the canary report | `needs_review` | Header blocks contain 13 year-month columns and duplicate `(year, Jun)` pairs. The meaning is unknown; no columns were removed, merged, or reinterpreted. |
| `tic.treasury_holdings.2023_01` | 5,982 bytes; SHA-256 still matches the canary report | `contract_validated` | Strict CSV validates the 160-row structured section before the single quoted `"Notes:"` row; 127 data rows satisfy the fixed 2023-01 contract. The malformed free-text notes remain only in the unchanged raw file. |

The Table 3D result is an **offline post-run validation of the same saved live response**, not a new live request and not a rewrite of the original canary receipt. Its original row remains `live_needs_review` as recorded at execution time. Combining the original evidence with this later validator result, the latest source-response contract evidence is 3/7 (FRED, BoE, and Table 3D); MFH is unresolved, Census remains `LICENSE_SECURITY/NEEDS_REVIEW`, and the two BLS failures remain `TRANSIENT/FAILED_RETRYABLE`. Gate U remains **NOT PASSED**. The original sanitized report omitted transport reason details, so the Census/BLS causes cannot be recovered from that run.

The canary report writer now has a regression-tested path for recording fixed failure reason tokens and an HTTP status when available, without recording exception text, credentials, or response bodies. This improves a future separately authorized attempt; it does not repair or enrich the old report. No retry was made and Iteration 31 has not started.

Follow-up offline verification: targeted tests **84 passed, 1 skipped**; full suite **821 passed, 1 skipped, 0 failed**; changed Python Ruff checks passed; `git diff --check` passed. The skipped test requires Windows symlink creation. These checks made zero live requests.

Report-path review: the original canary JSON and TIC raw files were readable and their recorded hashes matched. Creating a separate post-run JSON under `reports/` from this Codex shell returned `PermissionError`; no existing report, raw file, or receipt was overwritten. The post-run findings are recorded here and in the live-canary report. The user previously ran the canary from regular PowerShell and its files were saved, so this write denial is specific to the current execution context; it is not evidence that the original canary report was lost.

## Evidence and limitations

- Local-only run JSON: [iteration 30 live canary](../../../reports/iteration_30_live_canary_ffc0fe15c3b440a28c65b64aa9b5bb81.json).
- Earlier network-off preflight: [preflight JSON](../../../reports/iteration_30_live_canary_d8a291e6301f4eb7a8be637f25a5d8b4.json), seven `not_run_network_disabled`, zero requests.
- This run verifies only these bounded source responses and registered structure checks. It does not establish complete dataset coverage, normalized ingestion, broader source availability, or a full 7/7 live pass.
- No automated tests were run as part of this live execution; the existing preparation report separately records the offline test results.
