# Iteration 16 — local credentials, BEA and e-Stat API clients

**Date:** 2026-10-25\
**Result:** Gate G PASS\
**Scope:** Local `.env` settings plus source-specific BEA and e-Stat JSON GET clients. No live API calls.

## User value delivered

- Created an ignored repository-root `.env` with blank `BEA_API_KEY` and `ESTAT_APP_ID` fields for the user to fill in.
- Added `Settings.from_project_env()` to read the local file and let process environment values override it. The loader accepts only the project settings and these two credentials; it does not execute shell syntax or interpolate values.
- Added a bounded shared HTTPS/JSON transport and callable clients for BEA dataset/parameter/data methods and e-Stat table-list/metadata/statistical-data methods.
- Updated the source registry and catalog to distinguish these mock-tested clients from workflow integration and live validation.

## Files changed

- `src/macro_data_platform/config.py`: bounded `.env` parsing, process environment precedence, default-off network setting, and credential fields omitted from `Settings` repr.
- `src/macro_data_platform/connectors/official_api.py`: fixed endpoint allowlist, GET-only bounded transport, safe error classification, and credential redaction in returned JSON.
- `src/macro_data_platform/connectors/bea.py` and `src/macro_data_platform/connectors/estat.py`: institution-specific methods and required credential handling.
- `src/macro_data_platform/discovery/source_registry.py`, `tests/test_source_registry.py`, and `docs/operator/reference/INSTITUTION_CATALOG.md`: BEA/e-Stat implementation state is now partial, source-specific mock fixture coverage, live not run.
- `tests/test_official_api_credentials.py`: dotenv precedence and validation, request shapes, no-key/network-off behavior, HTTP/JSON errors, and secret redaction.
- `.env.example` and local ignored `.env`: blank names for the user-entered credentials; the local file remains blank.
- `PROJECT_PLAN.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`, `docs/user/USER_GUIDE.md`, `docs/developer/connectors/BEA.md`, and `docs/developer/connectors/ESTAT.md`: scope, usage, evidence, and limits.

## Tests and checks

- Focused settings, adapter and registry tests: **43 passed, 1 skipped**.
- Full local pytest suite: **625 passed, 1 skipped in 38.82s**.
- Full Ruff check: **passed**.
- `git diff --check`: **passed**; Git printed only existing LF-to-CRLF conversion notices.
- The skipped test attempts to create a symlink for the `.env` rejection case. This Windows environment denied symlink creation, so that specific runtime check was not completed.

## External evidence and live status

- Official documentation confirms BEA's fixed data URI, `UserID`, method and JSON format: <https://apps.bea.gov/API/docs/index.htm> and <https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf>.
- Official e-Stat documentation confirms v3.0 JSON API routes and Application ID registration: <https://www.e-stat.go.jp/api/en/api-info/api-spec> and <https://www.e-stat.go.jp/api/api/api/index.php/en/api-info/api-guide>.
- API calls in the test suite use mocked HTTP only. Neither institution was contacted; no key was validated. The local `.env` contents were not read back or printed.

## Limits and security/data-integrity implications

- BEA/e-Stat clients are callable Python APIs only. They are not connected to MacroAtlas discovery/ingestion workflows, a UI or a CLI.
- The returned JSON is sanitized and is not a byte-exact raw archive. The clients do not implement pagination, normalized metadata/observations, statistical validation, dataset-specific license review, or automated retries.
- `.env` is ignored by Git but is ordinary plaintext on this machine. Users must protect it locally. Network access remains off by default; API requests require an explicit network setting. Credentials are sent in query parameters as required by the official APIs, but request URLs, exceptions, Settings repr and returned credential fields are not exposed by the clients.
- TLS verification remains enabled, redirects are refused, environment-derived proxy/credential configuration is disabled for the transport, and response bytes are bounded to one MiB.

## Human action required

The user can now enter each value in the corresponding blank field in the repository-root `.env`. Keep `MACROATLAS_NETWORK_ENABLED=false` until an intentional live request is approved. No commit, stage, merge, publish, or deployment was performed.
