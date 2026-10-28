# Engine runtime smoke — 2026-10-28

This is a bounded live check of the fixed API engine paths and offline search
evaluation. It records one workspace on one date; it is not a claim that every
provider dataset, account permission, or full user workflow has been verified.

## Live API engine paths

Requests used fixed, read-only source queries and temporary project roots inside
the workspace. Raw files and manifests were written only to those temporary
roots and removed after each run. No source values, credentials, or credentialed
URLs are included here. OpenAI was not called.

| Engine | Query scope | Result |
|---|---|---|
| World Bank WDI | U.S. GDP, source 2, 2020–2024 | `SUCCEEDED`; five annual observations parsed; quality and freshness passed; raw response and manifest were captured in temporary storage. |
| BOJ metadata | FM08 / FXERD01 | `SUCCEEDED`; the fixed series identity, name, unit, and daily frequency matched the adapter contract. |
| BOJ observations | FXERD01, October 2026 | The source returned 31 calendar rows, including 14 nulls and future-dated null placeholders. The old check incorrectly used the last calendar row and withheld the series as `FRESHNESS_UNVERIFIED`. After the fix, freshness used the latest non-null value, 2026-10-26 (age 2 days); the stage `SUCCEEDED`, and all 31 rows and 14 nulls remained preserved. |
| BLS Public Data API v2 | CPI series `CUUR0000SA0`, 2026 | `SUCCEEDED`; nine monthly observations parsed and freshness passed. Unit and frequency metadata remain unverified by this query. |
| Census ACS 1-year | 2024, U.S. total population, `us:1` | `SUCCEEDED`; one geography row parsed and freshness passed. Variable definition, unit, and complete metadata mapping were not verified. |

The BOJ diagnosis made one extra metadata/data check and one direct response
inspection; a post-fix run checked the metadata and data stages again. No
automatic retries were issued. No task database or persistent raw directory
was written by these smoke runs.

## Registry and local evaluation

The shared registry assembled eight engine/version registrations into an
`Orchestrator`: World Bank, BOJ metadata/observations, BLS, Census, Gate C file
watch, and the two World Bank Gate A stages. The suite exercised the adapters
through deterministic fixtures.

The immutable v2 corpus validated at 36 cases: 12 each in development,
validation, and holdout, with no declared split leakage. Only development and
validation were executed; holdout was intentionally not run. Candidate policy
v2 (`37.5`) changed unrelated abstention from 8/8 returned to 0/8 in both
development and validation. Rankable and near-match top-1 counts stayed at
6/8 and 7/10 in development, and 6/8 and 12/12 in validation. The candidate
search stage required explicit confirmation in all 34 development and 36
validation queries, with zero bypasses and zero selection/collection payloads.
False-exact and forbidden-exact counts were zero in these fixed splits.

Four additional questions and assistant-authored feedback were generated in
this ChatGPT conversation, run against the same local catalog, and recorded as
AI-simulated development examples. The baseline matched 0/4 expectations and
candidate v2 matched 2/4. Candidate v2 abstained correctly for the BOJ policy
rate and Japan GDP questions, but ranked a wrong GDP measure first and tied a
CPI index with the requested inflation rate. Those two corrections are useful
development findings; they do not enter the fixed v2 corpus, validation, or
holdout. The examples are not actual user observations.

These measurements do not complete Gate C. Downstream prohibited actions after
selection, a frozen one-time holdout, a time/cost budget, and promotion review
remain unmeasured. The evaluated policy remains a candidate, not the product
default.

## Verification environment

The full local pytest suite passed (**861 tests**) after running with this
checkout's `src` directory first on `PYTHONPATH`; Ruff and CLI help checks passed. Without that
path override, the environment's editable install imported a sibling
`/workspace/MacroAtlas` checkout and failed during test collection. This is a
workspace import-path issue, not evidence of a product runtime failure.

The in-chat assistant authored the cases; no separate OpenAI API key or live
OpenAI call was needed. The local ignored synthetic database contains six
AI-simulated interactions after import (two earlier examples and the four
tracked examples above). AI examples are stored separately from real-user
feedback. The actual user-feedback `catalog.sqlite` did not exist in this
workspace during the check.
