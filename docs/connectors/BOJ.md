# Bank of Japan API — limited FXERD01 collector

## Supported scope

The current adapter supports only BOJ database `FM08`, series `FXERD01`, and one calendar month per
request. The verified example is September 2026. It does not support other databases, series, date
ranges, `getDataLayer`, or automatic series discovery.

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
.\.venv\Scripts\macroatlas.exe status <TASK_ID>
.\.venv\Scripts\macroatlas.exe resume <TASK_ID> --live
```

`--live` is required. The command creates and plans the task before sending requests. Resume the same
task ID after the transient condition clears; do not create a new task to repeat a failed attempt.
Observed evidence is recorded in the local SQLite history and JSON output. Data files and the local DB
are ignored by Git.

## Current limits

The 2026-10-26 collector run completed with 30 daily rows and 11 preserved nulls. This confirms the
fixed path only. Other BOJ series, long-range limits, license interpretation, a live changed revision,
and natural provider failure/resume remain unverified. This adapter does not expand Gate C's accepted
scope.
