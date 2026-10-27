# 27회차 updater pilot 상태 — Linux 성공, Windows no-op 정리 보완 대기

기준일: 2026-10-27. PR #26 이후 Linux에서 updater를 두 차례 수동 실행했다. 첫 시도는 Codex token refresh `401 Unauthorized`로 막혔고, ChatGPT 보안 설정에서 기기 코드 로그인을 활성화한 뒤 재인증해 두 번째 시도는 candidate QA와 PR handoff까지 성공했다. 두 실행 모두 Linux이므로 실제 Windows pilot 완료로 간주하지 않는다.

## 첫 시도: 인증 차단

- 기준 commit: `341a2f843cd0e0e3282279608a6e15d45d1fb2d5` (PR #26 merge)
- updater report: `reports/improvement_20261027T032741Z-f5086104/report.json`
- `codex login status`는 로그인 상태를 표시했지만 Codex 요청은 access token refresh `401`로 prompt 전에 종료됐다.
- 결과는 `CODEX_AUTH_REQUIRED`; candidate, QA, push, PR은 없었다. 실패 분석용 isolated worktree와 branch, log를 Git-ignored `reports/` 아래 보존했다.

## 재인증 후 updater 결과

사용자가 ChatGPT 보안 설정에서 device-code login을 활성화한 뒤 `codex login --device-auth` 인증을 완료했다. 이후 updater를 최신 merge commit 기준으로 실행했다.

- 기준 commit: `e3ff376feaec0ddbb388df6fbd1117ed6e3dbe99` (PR #27 merge)
- candidate: `45bea5eb5cd630686d42335c034f0f9cf55c1803`
- 변경: malformed task plan에 dictionary가 아닌 항목이 있으면 CSV export를 `unsupported_task_plan`으로 거부하고, DB·출력 경로를 변경하지 않는 회귀 테스트를 추가했다.
- candidate QA의 pytest, Ruff, diff, CLI 3종, health 7개 검사가 모두 통과했다. 중복 실행된 GitHub Actions의 Ubuntu/Windows × Python 3.11/3.12 8개 job도 모두 통과했다.
- [PR #28](https://github.com/jaeu983-lang/MacroAtlas/pull/28)은 merge commit `bb94bba38711002adb7fb4948ef5643c3d54b628`로 통합됐다.

첫 시도는 자연 발생한 인증 실패 결과를 보여주고 두 번째는 successful candidate 경로를 검증했다. 첫 Windows 수동 실행에서는 no-op 경로를 관측했지만 cleanup이 실패했다. 예약 작업은 설치하거나 활성화하지 않았다.

## 다음 단계

Windows에서 no-op 실행과 Codex CLI 호출은 관측했다. 임시 worktree 정리가 실패했으므로 정리 코드를 보완하고 같은 no-op 경로를 다시 검증한다. Windows failure/success 경로, 사용자 세션과 task principal의 실증은 남아 있다. scheduler는 비활성으로 둔다.


## 예약 설정 정적 검토 — 2026-10-27

현재 연결된 실행기는 Linux이며 `powershell`, `pwsh`, Windows Task Scheduler에 접근할 수 없다. 따라서 실제 Windows pilot, 등록된 task의 사용자·로그온 조건 조회, 예약 실행 결과는 확인하지 않았다. Windows CI의 wrapper dry-run은 PowerShell 문법과 인자 전달 검사이며 실제 사용자 세션 pilot을 대체하지 않는다.

`scripts/install_tasks.ps1`은 매일 07:30 health check와 토요일 09:00 improvement task를 각각 등록한다. 둘 다 `StartWhenAvailable`과 task별 `MultipleInstances IgnoreNew`를 쓰며 실행 제한은 각각 30분과 2시간이다. Improvement task 인자에는 `-BaseRef`가 없어 `run_improvement.py`가 checkout의 `origin/HEAD`를 사용한다. 현재 Linux checkout의 `origin/HEAD`는 `origin/codex/iteration-04-gate-a`를 가리키지만, Windows clone의 remote HEAD도 같은지 확인되지 않았다. 미설정이면 updater는 `NOT_EXECUTED`로 종료한다.

`IgnoreNew`는 동일 task 이름의 중복 실행만 제한한다. installer와 updater에는 health task·manual run을 포함하는 공통 lock/idempotency guard가 없으며, 계획된 `ALREADY_RUNNING` 결과도 구현되어 있지 않다. Updater 보고서와 로그는 `reports/improvement_<run_id>/`에 보존되지만 자동 보존 기간·용량 한도·정리 정책이 없다. 실패 경로의 worktree도 의도적으로 남길 수 있으므로 장기 예약 전 디스크 사용량과 안전한 정리 기준이 필요하다. Task principal과 대화형 로그인 요건은 installer에서 명시하지 않아 실제 Windows에서 확인해야 한다.

결론: scheduler는 설치·활성화하지 않는다. Windows pilot 전에는 대상 저장소의 명시적 base branch를 확정하고, 수동 실행과 예약 작업이 공유하는 중복 방지 및 report 보존 정책을 마련한다. 그다음 Windows에서 먼저 dry-run으로 경로·인증·기준 ref를 확인하고, 사람이 시작한 단일 updater 실행의 상태 보고서를 검토한다. Scheduler 검토에서는 실제 task principal, 로그인 요구, 지연 시작, 실행 제한과 두 task의 겹침도 확인한다. no-op/failure/success 및 cleanup 동작까지 검증한 뒤에만 예약 활성화를 별도 결정한다.

## Windows 첫 수동 실행 — 2026-10-27

- Windows와 Anaconda Python 3.12.8에서 dry-run이 `DRY_RUN`으로 통과했고 base ref와 SHA는 `origin/codex/iteration-04-gate-a` / `d925f91b890cd5ea5ee43d78750db9b3033515ff`였다.
- 실제 run `20261027T051148Z-d939d7d6`에서 Codex는 exit code 0으로 끝났지만 변경 파일은 없었다. 결과는 `CLEANUP_FAILED`, candidate/QA/push/PR은 없고 `network_requested=false`였다. 원본 report는 사용자 Windows 저장소 `reports/improvement_20261027T051148Z-d939d7d6/report.json`에 남아 있다.
- 사후 점검에서 Git 등록 worktree는 이미 해제됐고, `checkout` 폴더는 비어 있으며 `.git` marker가 없었다. 같은 이름의 임시 branch는 남아 있었다. 폴더 안에서 실행한 `git status`는 상위 저장소를 읽으므로 임시 worktree 상태 증거로 쓸 수 없다.
- 당시 updater는 `git worktree remove`의 stderr를 report에 기록하지 않아 최초 실패 원인은 확인할 수 없다. 보완 코드는 실패 출력을 구조화해 보존하고, 등록 해제된 빈 orphan 디렉터리만 지우며, 비어 있지 않은 경로와 base에서 이동한 branch는 보존한다.
- 이 시도는 Windows Codex 실행과 no-op 경로를 확인했지만, cleanup 실패 때문에 Windows pilot을 통과 처리하지 않는다. 보완 코드 병합 후 남은 빈 디렉터리와 base branch를 정리하고 재검증한다.

이 updater 작업은 MacroAtlas provider 접속이나 Gate C 원자료 증거와 별도다.
