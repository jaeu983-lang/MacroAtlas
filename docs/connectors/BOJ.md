# Bank of Japan API — limited FXERD01 collector

## Supported scope

The adapter supports only BOJ database FM08, series FXERD01. collect boj-fxer queries one
calendar month; collect boj-fxer-range queries one to twelve consecutive months. Both paths use
the same verified series identity and metadata contract. They do not support other databases,
series, ranges longer than twelve months, getDataLayer, or automatic series discovery.

The series metadata is retrieved from `/api/v1/getMetadata`; observations come from
`/api/v1/getDataCode`. The adapter performs one HTTPS GET per Orchestrator stage. Metadata and data
have separate persisted stages, so a transient data failure can resume the same task after the
verified metadata stage is reused. A server `Retry-After` is persisted and enforced. No hidden retry
is sent.

## Evidence and parsing

The official API manual and live examples are recorded in
[`../BOJ_LIVE_RECHECK_2026_10_26.md`](../BOJ_LIVE_RECHECK_2026_10_26.md). The manual documents both
endpoints and limits the observation response to 60,000 data points. The directly verified series is
“US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market”, unit `Yen per U.S. Dollar`, frequency
`DAILY`.

The parser validates that metadata and observation identifiers match, dates are unique, ordered and
inside the requested month, values are finite numbers or `null`, and the response has no continuation
position. Null values remain null. It does not infer missing observations, fill dates, or judge
economic outliers. The top-level response `DATE` field is excluded only from the canonical
same-request comparison because two verified responses differed there while their requested date and
value arrays were identical. Exact raw hashes remain in the manifest.

Raw responses and credential-free manifests are saved under `data/raw/boj/`. A changed observation
response is preserved with `NEEDS_REVIEW`; no normalized observations are returned until review.
Metadata changes also stop before the data stage.

## Run

From the repository root after installing the package:

```powershell
.\.venv\Scripts\macroatlas.exe collect boj-fxer --month 202609 --live
.\.venv\Scripts\macroatlas.exe collect boj-fxer-range --start-month 202609 --end-month 202610 --live
.\.venv\Scripts\macroatlas.exe status <TASK_ID>
.\.venv\Scripts\macroatlas.exe resume <TASK_ID> --live
```

`--live` is required. The command creates and plans the task before sending requests. Resume the same
task ID after the transient condition clears; do not create a new task to repeat a failed attempt.
Observed evidence is recorded in the local SQLite history and JSON output. Data files and the local DB
are ignored by Git.

## Current limits

The 2026-10-26 single-month collector run completed with 30 daily rows and 11 preserved nulls. The
multi-month route is capped at twelve calendar months, well below the API manual's 60,000-point
response limit; the live follow-up and fixture results are recorded in the decision log and runtime
smoke report. Other BOJ series, ranges longer than twelve months, license interpretation, a live
changed revision, and natural provider failure/resume remain unverified. Freshness-passed range tasks
are revalidated by the existing CSV exporter; they do not expand Gate C's accepted scope.
