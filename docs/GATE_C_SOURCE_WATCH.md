# TIC/BIS live source watch

The CLI provides one manual live GET for each previously checked official file. Each task and stage
are persisted before the request, so a natural retryable provider failure has a task ID and attempt
history ready for later resume.

```powershell
.\.venv\Scripts\macroatlas.exe watch tic --live
.\.venv\Scripts\macroatlas.exe watch bis --live
```

The TIC profile fixes Table 5's official TXT URL, tab delimiter and header row 6. The BIS profile fixes
`WS_GLI_csv_col.zip` and preserves the verified parser scope: a single supported table member is
selected automatically. Capture time, HTTP status and content type are recorded as provenance but do
not change the comparison scope. The request is bounded to one GET, 30 seconds and 16 MiB, with TLS
verification, configured proxy/CA use, redirects disabled and no automatic retry.

Both profiles store raw bytes and a manifest before parsing. If the exact-scope bytes change or the
previous manifest cannot be verified, the new raw is retained and the parser returns `NEEDS_REVIEW`
without writing a normalized table. An unchanged file is parsed and compared with the preserved
baseline.

## 2026-10-26 live recheck

| Source | Task | HTTP | Raw SHA256 | Source change | Parsed shape |
|---|---|---:|---|---|---|
| TIC Table 5 | `dd5fc688-cdf7-4171-9e81-5f8992d3ae49` | 200 | `e5de973b1a6f13c8ec95707d665ce107f53f467db10d7a2d991677ee67d1de11` | `unchanged` | 36 rows × 14 columns |
| BIS column ZIP | `395102cd-94e0-4001-86f8-bba0310ea5b9` | 200 | `aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d` | `unchanged` | 225 rows × 220 columns |

The raw and normalized hashes match the previously preserved exact-scope baseline for both sources.
No actual source revision or provider error occurred during these requests. The durable-resume fixture
test is labeled simulated; it is not live failure evidence. To record a future natural error, run
`macroatlas status <TASK_ID>` and later `macroatlas resume <TASK_ID> --live` after the source condition
clears and any `Retry-After` delay elapses. Keep the task ID unchanged.

This watch is manual and does not create a recurring job. Natural source changes and natural
failure-to-resume remain outside the current limited Gate C pass until observed.

## Post-merge monitoring — 2026-10-26

PR #2 merged at `82a018e`; local and remote base HEAD matched. A daily condition-watch automation
was created and enabled. Each future run must first verify access to this workspace, SQLite history
and preserved baselines; scheduling success does not prove future workspace availability. Missing
storage is a blocker, not permission to create a replacement baseline. Unchanged results stay quiet.

Immediate recheck: TIC task `bb269b6e-adac-451b-b6a5-ad85b3bc5aa7` and BIS task
`2b795b28-a742-4821-bbfe-8887e37b5099` both completed with `unchanged`. No natural failure occurred.
Gate C D-067 limited pass remains; actual revision and natural durable recovery remain NOT_RUN.
The automation reassesses evidence when observed and reports actionable changes only.
