# Iteration 25 — API response file archive and verified read-back

**Date:** 2026-10-25\
**Track:** C — API response storage module\
**Gate:** P — PASS\
**Starting Git HEAD:** `778ab41` (`codex/iteration-07-08-discovery`). The workspace already contained extensive user changes; they were preserved. No staging, commit, merge, or checkpoint was made.

## Goal and boundary

The user asked to save the current nine API clients' responses to files and run the full test suite again. The task also required SDMX work to distinguish shared transport safety, institution-specific routes, and institution-specific validation evidence.

This iteration adds a reusable write-once archive and integrity-checked read-back for the response types from World Bank, BEA, e-Stat, BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, and INSEE. It does not add additional API adapters, source-specific payload parsers, non-World-Bank workflow integration, or live requests.

## Implementation

- Added `src/macro_data_platform/storage/api_responses.py` with `save_api_response()` and `read_api_response()`. The archive writes an institution-scoped response file and `request.json` manifest, uses exclusive file creation, records source/operation/UTC retrieval/status/content type/representation/optional dataset and series IDs/byte count/SHA-256, and validates paths, institution identity, manifest hash, response hash, and byte count on read-back.
- Kept the existing World Bank `raw/worldbank/` folder and compatibility function. The World Bank workflow now reaches the common archive writer without changing its output path contract. Its non-200 response bodies remain preserved for review and are marked `response_accepted=false`.
- Added redacted safe request parameters to `JsonApiResponse`. BEA and e-Stat archive a canonical UTF-8 serialization of the already-redacted JSON payload; the manifest explicitly identifies this as a sanitized serialization, not exact HTTP response bytes. Credential parameter names and configured values are removed/redacted before writing.
- SDMX responses from the six client adapters remain provider response entity bytes after Requests content decoding. The common transport and institution-specific route clients remain separate. The SDMX documentation now gives independent statuses for transport, route, official payload fixture, authentication/access limits, parsing, archive/read-back, and live evidence.
- Updated the source registry and developer/operator documentation to reflect file archive availability without claiming workflow integration or live validation.

## Per-source evidence

| Source | Client-to-file/read-back | Payload fixture/parser | Auth/live evidence |
|---|---|---|---|
| World Bank | Fixture response stored and verified; existing workflow path retained | Existing fixed GDP parser remains its prior limited scope | Historical partial live evidence remains only USA/WDI/GDP; no new request |
| BEA | Mock response stored/read back; secret sentinel absent | No provider payload parser | Key is required by the client; no credential value was read and no live request was made |
| e-Stat | Mock response stored/read back; secret sentinel absent | No provider payload parser | Application ID is required by the client; no credential value was read and no live request was made |
| BIS, OECD, ECB, Eurostat, Bundesbank, INSEE | Each adapter response separately stored/read back using mock transport | No official provider response fixtures or provider parsers in this iteration | BIS/ECB/Eurostat documented as no-key; OECD/Bundesbank/INSEE auth/access details remain unknown in the registry. All six live statuses remain not run. |

For SDMX, common transport and source-route mock checks do not imply official response fixtures, successful authentication, parser correctness, or live reachability. The per-institution matrix is in [SDMX_FAMILY.md](../connectors/SDMX_FAMILY.md). Only the file archive/read-back column passed in this iteration.

## Files changed

- `src/macro_data_platform/storage/api_responses.py` — shared response serializer, write-once file archive, manifest and integrity-checked read-back.
- `src/macro_data_platform/storage/raw_downloads.py` — World Bank compatibility entry point delegates to the shared archive while preserving its established directory.
- `src/macro_data_platform/storage/__init__.py` — exports the archive/read-back API.
- `src/macro_data_platform/connectors/official_api.py` — includes redacted noncredential request parameters in the JSON response object so manifests can retain safe request context.
- `src/macro_data_platform/discovery/source_registry.py` — records which sources have the mock archive/read-back checks and which live/parser evidence remains absent.
- `tests/test_api_response_storage.py` — nine-source file round-trip, secret redaction, source/host validation, unique writes, tamper detection and World Bank failed-response preservation.
- `tests/test_worldbank.py` — updated the forced UUID collision test ID to the archive's required 32-character hex format.
- `PROJECT_PLAN.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/EXECUTION_PLAN.md`, `docs/developer/ARCHITECTURE.md` — current file-storage state and next gate.
- `docs/developer/connectors/API_RESPONSE_STORAGE.md`, `docs/developer/connectors/README.md`, `docs/developer/connectors/SDMX_FAMILY.md` — archive contract and the three SDMX responsibility layers.
- `docs/developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md` — independent SDMX evidence layers and current status.
- `docs/operator/reference/INSTITUTION_API_AUDIT.md`, `docs/operator/reference/INSTITUTION_IMPLEMENTATION_STATUS.md` — operator-visible implementation and evidence boundaries.
- `docs/developer/history/DECISION_LOG.md` — D-092.
- `docs/developer/history/ITERATION_25_REPORT.md` — this result.

## Verification

| Check | Result |
|---|---|
| Focused storage + World Bank + JSON API + SDMX connector tests | **122 passed, 1 skipped**, exit code 0 (3.05 seconds) |
| Full offline pytest suite | **666 passed, 1 skipped, 0 failed**, exit code 0 (37.93 seconds) |
| Skip reason | `tests/test_official_api_credentials.py:128`: symlink creation unavailable in this Windows environment |
| Ruff on changed Python files | **Passed** |
| Live network/API requests | **0** |

The test command used the repository `.venv` and explicitly set `PYTHONPATH` to the current `src` directory, avoiding the stale OneDrive editable installation seen in an initial collection attempt. No API key or `.env` file was read.

## Gate P assessment and limits

**PASS:** all nine currently implemented client response types were archived in tests and read back with source identity, representation, hash, length and path checks. Secret sentinels were absent. Existing World Bank file-path/error-preservation behavior remained covered. Full offline tests and Ruff passed.

This is **not** nine live API successes. Eight non-World-Bank clients still have no ingestion workflow that automatically invokes the archive; their explicit response objects can be saved through the helper and their mocked round-trip is verified. Official provider payload fixtures and parsers, live/auth results, and the five other documented-but-unimplemented API sources remain future source-specific gates. The next queued step is the IMF exact route/auth documentation gate; after that, add provider payload fixture/parser gates before source live canaries.

No external API request was made, and no secret was accessed. Human diff review remains required before integration.
