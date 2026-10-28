# Iteration 30 Report — bounded live canary (Gate U not passed)

**Date:** 2026-10-25
**Scope:** Seven registered dataset paths, one request attempt each, zero automatic retries.
**Setting:** `MACROATLAS_NETWORK_ENABLED=true` was set for this process only at the user's request. The repository `.env` remained unchanged.

## Latest targeted diagnosis and correction

Five further source requests (Census 1, BLS 4; zero automatic retries) confirmed that Census redirects to its official `invalid_key.html`. The two registered BLS POST requests, a documented single-series GET, and a documented Python-style POST all returned HTTP 503 HTML. The latter two error samples contained Akamai/JavaScript markers; an edge access/error response is a hypothesis, not a verified policy decision. Gate U remains NOT PASSED; no new successful source artifact was produced and no later iteration started.

The code now maps only recognized official Census data-key redirects to `AUTH_ACCESS` with fixed reasons, reports fixed JSON/HTML/other failure categories, and supports an explicitly selected subset of registered live profiles. Partial success cannot become a full Gate U pass. Details, local evidence, remaining credential/source actions and verification are in [the diagnosis report](../testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md). The earlier run records below are historical and remain unchanged.

## Follow-up live canary — run 2

A later user-authorized run repeated the same seven bounded profiles once each, with zero retries. It again set the network opt-in for that process only and left `.env` unchanged. The local-only result is [follow-up canary JSON](../../../reports/iteration_30_live_canary_02afcdd6b6254239adf01af824df4e64.json).

| Profile | Attempts | Outcome | HTTP | Raw/hash read-back |
|---|---:|---|---:|---|
| `fred.gdp` | 1 | `live_contract_validated` | 200 | 969 bytes; verified |
| `census.acs2023.population` | 1 | `live_request_failed` — `LICENSE_SECURITY` / `NEEDS_REVIEW`, `redirect_refused` | 302 | Not saved; redirect target/body not recorded |
| `bls.unemployment` | 1 | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE`, `http_transient_status` | 503 | Not saved |
| `bls.cpi` | 1 | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE`, `http_transient_status` | 503 | Not saved |
| `tic.mfh.history` | 1 | `live_contract_validated` | 200 | 98,124 bytes; verified; 955 data rows |
| `tic.treasury_holdings.2023_01` | 1 | `live_contract_validated` | 200 | 5,982 bytes; verified; 127 data rows |
| `boe.bank_rate` | 1 | `live_contract_validated` | 200 | 140 bytes; verified; 7 native dates |

The second run passed 4/7 source-contract checks. Gate U remains **NOT PASSED** because all seven profiles must pass. For Census, the evidence establishes only that the safe transport refused an HTTP 302 redirect; without a recorded, sanitized redirect destination we cannot attribute it to the endpoint, provider, or network intermediary. For BLS, the evidence establishes an HTTP 503 for each of two v1 requests; it does not identify the server-side cause. No response bodies, credentials, or redirect query values were stored. No retry or additional request was made. The earlier run and its immutable receipts remain historical evidence; this second run does not rewrite them.

The next safe diagnostic requires a separately bounded request budget: first inspect the Census redirect destination using an allowlisted, query-redacted diagnostic and verify its host against official source documentation; then retry Census only if the destination is expected. For BLS, make no request until a fresh two-request (or narrower profile-specific) budget is approved; retain v1 and classify any new 503 separately. Gate U and Iteration 31 remain blocked until each failed profile validates and stores/read-backs its response.

## First-run results — original receipts

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
| `tic.mfh.history` | 98,124 bytes; SHA-256 still matches the canary report | `contract_validated` | 26 header blocks, 955 data rows, 11 duplicate-period pairs with distinct source Series IDs; each is retained as a series break, with both columns preserved. |
| `tic.treasury_holdings.2023_01` | 5,982 bytes; SHA-256 still matches the canary report | `contract_validated` | Strict CSV validates the 160-row structured section before the single quoted `"Notes:"` row; 127 data rows satisfy the fixed 2023-01 contract. The malformed free-text notes remain only in the unchanged raw file. |

The TIC results below are **offline post-run validations of the same saved live responses**, not new live requests and not rewrites of the original canary receipts. Their original rows remain `live_needs_review` as recorded at execution time. MFH raw is 98,124 bytes and its original SHA-256 still matches. The current validator accepted 26 header blocks and 955 data rows, including 11 duplicate-period pairs with distinct source Series IDs: `2000-03` II/I and June pairs from `2002-06` through `2011-06`. Treasury's official notes identify these as series breaks and say the prior series estimate for the break month is shown for comparison only. Both columns remain preserved; no series was silently selected or merged. [Official MFH table and notes](https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfhhis01.html).

Table 3D raw is 5,982 bytes and its SHA-256 still matches; the current validator accepts the strict table section before its single Notes boundary. At the time of this first-run offline review, combining its original live evidence and these offline validations gave 4/7 source-response contract evidence (FRED and BoE validated live; both TIC files were downloaded/hash-read-back live, then contract-validated offline). That historical measure was not a 4/7 Gate U pass: the first-run execution-time result remained 2/7 and its TIC receipts remained `live_needs_review`. The later follow-up run and its independent Census/BLS statuses are recorded above; its result does not rewrite those first-run receipts.

The canary report writer now has a regression-tested path for recording fixed failure reason tokens and an HTTP status when available, without recording exception text, credentials, or response bodies. This improves a future separately authorized attempt; it does not repair or enrich the old report. No retry was made and Iteration 31 has not started.

Follow-up offline verification after the MFH Series-break update: targeted tests **85 passed, 1 skipped**; full suite **822 passed, 1 skipped, 0 failed in 82.45 seconds**; Ruff passed. The skip requires Windows symlink creation. `git diff --check` is recorded after final documentation updates. These checks made zero live requests.

Report-path review: the original canary JSON and TIC raw files were readable and their recorded hashes matched. A later network-off preflight confirmed the local `.env` network switch was false. Default sandbox output to `reports/` returned `PermissionError` without issuing requests; the same network-off run under the approved elevated context saved [a preflight JSON](../../../reports/iteration_30_live_canary_c1fa08b936df44869eebefc81e34ca42.json) with seven `not_run_network_disabled` results, zero requests, and zero retries. No existing report, raw file, or receipt was overwritten. This proves report output only in the approved execution context; it does not change Gate U or the original canary results.

## Evidence and limitations

- Local-only run JSON: [iteration 30 live canary](../../../reports/iteration_30_live_canary_ffc0fe15c3b440a28c65b64aa9b5bb81.json).
- Earlier network-off preflight: [preflight JSON](../../../reports/iteration_30_live_canary_d8a291e6301f4eb7a8be637f25a5d8b4.json), seven `not_run_network_disabled`, zero requests.
- This run verifies only these bounded source responses and registered structure checks. It does not establish complete dataset coverage, normalized ingestion, broader source availability, or a full 7/7 live pass.
- No automated tests were run as part of this live execution; the existing preparation report separately records the offline test results.
