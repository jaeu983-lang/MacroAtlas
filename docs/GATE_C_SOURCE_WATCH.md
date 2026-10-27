# TIC/BIS live source watch

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

현재 상태(2026-10-27): 사용자가 TIC/BIS 자료 변경상태 확인은 필요하지 않다고 지정해 두 반복 감시 자동화를
중지했습니다. 아래 명령은 사용자가 다시 단발 확인을 요청할 때만 검토하며, 자동 실행하지 않습니다.

The CLI provides one manual live GET for each previously checked official file. Each task and stage
are persisted before the request, so a natural retryable provider failure has a task ID and attempt
history ready for later resume.

```powershell
.\.venv\Scripts\macroatlas.exe watch tic --live
.\.venv\Scripts\macroatlas.exe watch bis --live
```

The TIC source URL ends in `.txt`, but its exact comparison profile uses the TSV parser and header row 6.
The BIS profile fixes `WS_GLI_csv_col.zip` and explicitly selects its verified member
`WS_GLI_csv_col.csv`. Capture time, HTTP status, content type and `Last-Modified` are recorded as
provenance but do not change the comparison scope. The request is bounded to one GET, 30 seconds and
16 MiB, with TLS verification, configured proxy/CA use, redirects disabled and no automatic retry.

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

## Exact-scope profile audit — 2026-10-27

Before the next live comparison, the preserved raw manifests were checked read-only against the
requested baselines: TIC SHA256 `e5de973b1a6f13c8ec95707d665ce107f53f467db10d7a2d991677ee67d1de11`
with TSV/header row 6, and BIS SHA256
`aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d` with ZIP member
`WS_GLI_csv_col.csv`. The existing watcher profile had drifted to TXT plus extra TIC scope metadata
and BIS automatic member selection. The profile was corrected to match these exact baseline scopes
before issuing another request. This local audit made no source request and is not natural change or
provider failure evidence.

## Post-merge monitoring — 2026-10-26

PR #2 merged at `82a018e`; local and remote base HEAD matched. A daily condition-watch automation
was created and enabled. Each future run must first verify access to this workspace, SQLite history
and preserved baselines; scheduling success does not prove future workspace availability. Missing
storage is a blocker, not permission to create a replacement baseline. Unchanged results stay quiet.

Immediate recheck: TIC task `bb269b6e-adac-451b-b6a5-ad85b3bc5aa7` and BIS task
`2b795b28-a742-4821-bbfe-8887e37b5099` both completed with `unchanged`. No natural failure occurred.
Gate C D-067 limited pass remains; actual revision and natural durable recovery remain NOT_RUN.
The automation reassesses evidence when observed and reports actionable changes only.

## Monitoring stopped by user request — 2026-10-27

The user no longer requires recurring checks of TIC/BIS source-change status. The
`Gate C 자연 증거 감시` and `Gate C Source Watch` automations were disabled. No
further scheduled source requests are planned. The captures, baseline hashes,
`unchanged` results, and historical `NOT_RUN` statuses above are preserved as
records; stopping the watch does not change the Gate C limited-pass judgment or
claim a source revision/recovery event occurred. A future one-off check requires
a new user request and an explicitly scoped run.
