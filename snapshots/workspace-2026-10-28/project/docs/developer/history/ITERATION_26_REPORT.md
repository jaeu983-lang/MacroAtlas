# Iteration 26 — Shared HTTP transport and API-family boundaries

**Date:** 2026-10-25\
**Track:** C — connector transport architecture\
**Gate:** Q — PASS\
**Starting Git HEAD:** `778ab412d3076aad4a37d6f3140b6ced54b56d26`. The worktree already contained extensive user changes. They were preserved; no staging, commit, merge, or checkpoint was made.

## Goal and boundary

The user asked why the World Bank and SDMX paths were separate and requested a structural redesign. They share HTTP GET mechanics, but their API contracts differ: the current World Bank path is a fixed WDI Indicators JSON request; SDMX clients build provider-specific data and structure routes and preserve provider payload bytes. This iteration shares the HTTP execution primitive without merging those API-family rules.

No endpoint, provider identifier, credentials policy, response parser, workflow, storage contract, or live API behavior was intentionally expanded. The task used mocked requests only.

## New structure

```text
WorldBank WDI wrapper ─┐
BEA/e-Stat JSON wrapper ├─> BoundedHttpTransport ─> HTTPS GET session
SDMX family wrapper ───┘
       └─ provider clients keep source-specific routes and identifiers
```

- Added `src/macro_data_platform/connectors/http_transport.py`. It owns the common opt-in guard, HTTPS host/path policy, `trust_env=False`, default TLS behavior, GET-only request setup, `(5, 20)` second connect/read timeouts, redirect refusal, elapsed and response-byte limits, streamed raw entity bytes, and fixed-kind transport errors.
- `WorldBankTransport` now delegates the HTTP request while retaining its WDI path/query, one MiB cap, all-status response-body preservation, `Retry-After` parsing, and World Bank error contract.
- `JsonApiTransport` delegates HTTP while retaining the exact BEA/e-Stat endpoint allowlist, credential parameters/redaction, JSON content-type and payload validation, one MiB cap, and JSON-family HTTP status mapping.
- `SdmxApiTransport` delegates HTTP while retaining its six provider root/path rules, dimension and query validation, credential-like query rejection, eight MiB cap, raw response object, and SDMX-family status mapping.
- Added `tests/test_http_transport.py` for shared safety and bound behavior. Updated the World Bank time-budget test to patch the new shared monotonic clock.
- Updated the architecture and API-family references. [HTTP_TRANSPORT.md](../connectors/HTTP_TRANSPORT.md) now explains the API-family separation and the shared transport boundary; [ARCHITECTURE.md](../ARCHITECTURE.md) links it.

## Why the APIs remain separate

The World Bank path has a source-specific query and JSON page envelope, validates WDI country/indicator/year rows, preserves error bodies, and parses `Retry-After`. SDMX has data/structure resources, provider-specific agency/flow/version/dimension paths, and may return SDMX-ML, CSV, JSON, or other raw representations. Those details do not have a safe common parser or route contract. Only their HTTP execution mechanics are common. A shared transport pass therefore says nothing about source payload correctness or an institution's API readiness.

## Files changed in this iteration

- `src/macro_data_platform/connectors/http_transport.py` — shared bounded GET primitive.
- `src/macro_data_platform/connectors/worldbank.py` — delegates HTTP execution; keeps WDI response and error rules.
- `src/macro_data_platform/connectors/official_api.py` — delegates HTTP execution; keeps JSON API and credential rules.
- `src/macro_data_platform/connectors/sdmx.py` — delegates HTTP execution; keeps provider routes, query constraints, and SDMX status rules.
- `tests/test_http_transport.py` — shared transport policy, network opt-in, redirect, timeout, size, TLS, and request failure coverage.
- `tests/test_worldbank.py` — time-budget test follows the shared transport clock.
- `docs/developer/ARCHITECTURE.md`, `docs/developer/connectors/README.md`, `docs/developer/connectors/HTTP_TRANSPORT.md`, `docs/developer/connectors/SDMX_FAMILY.md`, `docs/developer/connectors/WORLDBANK.md` — describe shared HTTP layer and source-specific API boundaries.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/EXECUTION_PLAN.md`, `docs/developer/history/DECISION_LOG.md` — record Iteration 26, Gate Q, and D-093.
- `docs/developer/history/ITERATION_26_REPORT.md` — this result.

## Verification

| Check | Result |
|---|---|
| Focused HTTP + World Bank + SDMX + JSON credentials + response archive regressions | **141 passed, 1 skipped**, exit 0 (3.28 seconds) |
| Full offline pytest suite | **685 passed, 1 skipped, 0 failed**, exit 0 (52.20 seconds) |
| Skip | `tests/test_official_api_credentials.py:128`: symlink creation unavailable in this Windows environment |
| Ruff on changed Python files | **Passed** using `ruff check --no-cache`; local cache writes were denied by the environment |
| `git diff --check` | **Passed** with no whitespace errors; Git printed LF→CRLF working-tree notices |
| Live HTTP/API requests | **0** |

Tests used the repository `.venv` and the current checkout's `src` directory in `PYTHONPATH`. No `.env` file or credential value was inspected. No performance improvement percentage is claimed; this iteration consolidates duplicated implementation and validates behavior, but does not include a benchmark comparison.

## Gate Q assessment and remaining limits

**PASS:** common host/path safety, network opt-in, safe session configuration, timeout/elapsed/byte bounds, and raw response acquisition now live in one primitive. The existing wrapper tests passed for World Bank failure-body/`Retry-After` handling, JSON credential redaction and status behavior, and SDMX route/raw-body/status behavior. Invalid streamed chunk types now produce a fixed schema failure rather than a low-level type error. The full offline suite and Ruff passed.

This does not verify official payload fixtures, provider parsing, credentials against institutions, workflow-to-storage integration, live reachability, or end-to-end ingestion for any source. Existing live evidence remains the earlier narrow World Bank USA/WDI/GDP request only. IMF detailed route/auth documentation is the next separate candidate and must not be inferred from this transport change.

No external API request was made, no secret was read, and no commit or stage operation was performed. Human diff review remains required.
