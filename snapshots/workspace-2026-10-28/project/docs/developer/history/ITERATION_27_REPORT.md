# Iteration 27 — API key research and local input preparation

**Date:** 2026-10-25\
**Gate:** R — PASS\
**Starting HEAD:** `778ab412d3076aad4a37d6f3140b6ced54b56d26`, branch `codex/iteration-07-08-discovery`. Extensive earlier worktree edits were preserved. No stage, commit, merge, publish, or checkpoint was made.

## Scope and result

The user requested official research into additional API keys and empty names in the local `.env` so they can issue and enter their own keys. The previously queued IMF detail-documentation task was replaced by this one iteration; IMF exact route/auth documentation remains the next candidate.

The confirmed additional credential names are `FRED_API_KEY`, `CENSUS_API_KEY`, and `BLS_API_KEY`. Together with existing BEA/e-Stat names, Settings supports five source credential variables. FRED covers FRED/ALFRED and Board series served through FRED. Census requires a key for data queries; the June 2026 official newsletter documents an exception for metadata queries. BLS registration is required for v2, while limited unregistered v1 is available; registered access requires renewal at least annually.

The local `.env` was updated by appending only missing names with empty values. The append operation verified exact preservation of the original byte prefix and existing values; `git check-ignore .env` confirmed exclusion. Existing BEA/e-Stat entries and network configuration were preserved. No actual value, filled/empty state of existing keys, or secret hash was printed. The operation structurally read the file to preserve it and detect names; no credential was sent to an external service.

## Research evidence

[Operator API key guide](../../operator/API_KEYS.md) records the official URLs, application steps, activation/renewal details, all 21 source profiles, and implementation limits. Primary evidence includes:

- [FRED v1 key rules](https://fred.stlouisfed.org/docs/api/api_key.html), [v2 key rules](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html), and [issuance/login page](https://fredaccount.stlouisfed.org/apikeys).
- [Census issuance procedure](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html), [registration](https://api.census.gov/data/key_signup.html), [2026 data-key announcement](https://www.census.gov/library/video/2026/adrm/requesting-a-census-data-api-key.html), and [June metadata exception](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23).
- [BLS official FAQ](https://www.bls.gov/developers/api_faqs.htm) for registration requirements, limits, email delivery, and annual renewal. The FAQ links the [registration page](https://data.bls.gov/registrationEngine/); direct retrieval of that form was unavailable through the web research tool, so its completion was not verified.
- [BEA registration](https://apps.bea.gov/api/signup/) and [e-Stat user guide](https://www.e-stat.go.jp/api/api/api/index.php/en/api-info/api-guide) for the existing credential paths.
- [IMF API page](https://data.imf.org/en/Resource-Pages/IMF-API) and Swagger link redirect to sign-in. This establishes documentation-login requirements, not a verified data API subscription-key requirement. No speculative `IMF_API_KEY` was introduced.
- [INSEE BDM documentation](https://www.insee.fr/en/information/2868055) and [API catalogue](https://www.insee.fr/fr/information/8184146). Direct BDM access and portal-specific API subscriptions are distinct; Sirene API-key rules were not copied to BDM. No speculative `INSEE_API_KEY` was introduced.

ECB help overview/data requests returned 503 during this research pass, so earlier official-document evidence was retained with that limitation stated. Six sources with previously unconfirmed API specifications retain that status; this task does not establish that they lack APIs or keys. Authentication unknown values in the registry were not promoted based only on unauthenticated examples or free access wording.

## Changes

| File | Change and reason |
|---|---|
| `.env` (ignored local file) | Append three empty credential names; preserve prior bytes and network setting |
| `src/macro_data_platform/config.py` | Allowlist three new names; add optional `repr=False` Settings fields using existing validation and precedence |
| `tests/test_official_api_credentials.py` | Three parameterized cases verify blank/default loading, stored values, process precedence, repr masking, and safe invalid-value errors |
| `docs/operator/API_KEYS.md` | Official issuance steps, empty-value template, source-by-source key decisions and known uncertainties |
| `docs/operator/README.md`, `docs/operator/OPERATOR_RUNBOOK.md` | Make the guide and five accepted variable names discoverable |
| `docs/operator/reference/INSTITUTION_API_AUDIT.md` | Add credential-research overlay without changing API/adapter/auth verdicts |
| `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/EXECUTION_PLAN.md` | Record the user-directed Iteration 27 scope and next IMF candidate |
| `docs/developer/history/DECISION_LOG.md` | D-094 |
| `docs/developer/history/ITERATION_27_REPORT.md` | This report |

The previously deleted `.env.example` was not restored. All example values in the operator guide are empty. Existing API clients, endpoint policies, raw responses, source observations and workflow behavior were not expanded.

## Validation

| Check | Result |
|---|---|
| Credential/config and source-registry tests | **36 passed, 1 skipped**, exit 0, 0.72 seconds |
| Full offline pytest | **688 passed, 1 skipped, 0 failed**, exit 0, 56.61 seconds |
| Ruff on modified Python files | **Passed**, using `--no-cache` |
| Skip | `tests/test_official_api_credentials.py:155`, Windows symlink creation unavailable |
| Actual local environment edit | Existing byte prefix preserved exactly; only `FRED_API_KEY`, `CENSUS_API_KEY`, `BLS_API_KEY` appended empty |
| Secret-bearing output or external credential transmission | None |
| Statistical data API, key issuance, authenticated live verification | None; only public documentation/registration pages were browsed |

Tests ran in the repository `.venv` with current `src` in `PYTHONPATH` and disabled pytest cache writes. They use dummy credential sentinels and temporary environment files. The real API keys were not validated.

## Remaining work and review

The user can now issue keys and enter them in `C:/Projects/MacroAtlas/.env`. Existing valid BEA/e-Stat credentials can be retained. Email activation and BLS renewal are user steps. New FRED/Census/BLS Settings fields prepare storage; their adapters remain unimplemented and need separate source contracts, mocked tests and bounded live validation. No additional API key names were inferred for IMF, INSEE BDM, or sources with unconfirmed API specifications. Human diff review remains required before integration; no further design decision blocks entering the confirmed keys.
