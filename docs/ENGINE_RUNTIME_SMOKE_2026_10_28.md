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

## Post-merge WDI series follow-up

After PR #76 merged, `worldbank_series/1` was added for one explicitly selected
World Development Indicators series. A live Canada `SP.POP.TOTL` query for
2024–2025 completed as task `390eeac8-2ed6-40cc-84e5-b2ea5900c488`: two rows,
latest period 2025, age 301 days, `FRESH`. The raw response and request manifest
remain in ignored local `data/`; they were not committed. The 903-test full
suite, Ruff, and `git diff --check` passed for this follow-up. This single query
does not verify other WDI indicators, their meanings, or dataset terms.

## Post-merge WDI longer-range follow-up

After PR #77 merged, the `worldbank_series/1` annual request cap was raised from
10 to 100 periods while retaining the one-page, one-series, 1 MiB response
limits. A live Canada `SP.POP.TOTL` request for 1990–2025 completed as task
`2ad0c8e6-9b2f-4251-9b00-05f8e7e4d3e7` with 36 preserved rows, latest period
2025, age 301 days, and `FRESH`. Its raw response and manifest remain in ignored
local `data/`; they were not committed. This confirms that selected 36-year
request only, not other WDI series, units, metadata, or multi-page retrieval.
Product Gate D–G is unchanged.

## Post-merge BOJ longer-range follow-up

After PR #77 merged, the BOJ FXERD01 range cap was raised from 12 to 120
consecutive months. The 120-month API query still stays far below the official
60,000-point response cap; the existing 2 MiB transport limit remains active.
A live November 2016–October 2026 request completed as task
`00c40451-2a11-4966-aa9a-32e4d3bfb0ac`: 3,652 daily rows, 1,215 preserved nulls,
latest non-null date 2026-10-26, age two days, `FRESH`. CSV export revalidated
the stored response and completed with the same row and missing-value counts.
Raw, manifest, CSV, and provenance remain in ignored local `data/`; none were
committed. This confirms only that exact query and does not verify other BOJ
series, changed revisions, or natural failure/resume behavior. Product Gate D–G
is unchanged. After both range expansions, the full local pytest suite passed
911 tests; Ruff and `git diff --check` passed.

## Post-merge Gate D review

After PR #78 merged, `macro-promotion inspect` and `verify` both returned
`PASS`; the formal promotion ledger has zero events, no active acceptance, and
historical Gate C evidence verifies against Git. The AI reviewer recommends
`hold` with reason `evidence_follow_up_needed`: the passing scope is fixed local
search and confirmation-boundary behavior, while provider/raw-write/export and
real analyst use remain outside the evidence. This recommendation is kept in
the decision log as AI-authored; it is not a human decision, promotion-ledger
event, policy change, or Gate D completion.

## Post-merge BOJ monthly-range follow-up

After PR #76 merged, `boj_observations_range/1` and the `collect boj-fxer-range`
command were added for the same fixed FM08/FXERD01 daily series, with a limit of
one to twelve consecutive calendar months. The existing single-month route and
saved-task contract remain available. A live September–October 2026 query
completed as task `da20c2c3-aa05-48ab-99c1-d2232308dd46`: 61 calendar rows,
25 preserved nulls, latest non-null date 2026-10-26, age two days, and daily
freshness `FRESH`. CSV export revalidated the stored raw response and completed
with 61 rows and 25 missing values. The ignored local CSV and provenance files
were not committed. This confirms only the selected query, not other BOJ series,
changed-response review, or natural failure/resume behavior; product Gate D–G
status is unchanged.
