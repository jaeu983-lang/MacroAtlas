# 27회차 updater pilot 상태 — 운영 가드 구현, Windows scheduler 실측 대기

> 최신 후속 구현: installer에 기준 branch·Python 경로·현재 대화형 사용자 principal을 명시했고, updater에 교차 프로세스 lock과 `ALREADY_RUNNING` 상태를 추가했다. 90일 지난 정상 no-op/일상 QA report만 제한적으로 정리하며 candidate·실패·cleanup 미완료 기록은 보존한다. Linux unit tests와 Windows CI dry-run으로 검증한다. 예약 task는 설치하거나 활성화하지 않았다.

기준일: 2026-10-27. PR #26 이후 Linux에서 updater를 두 차례, Windows에서 no-op 경로를 두 차례 수동 실행했다. Linux 첫 시도는 Codex token refresh `401 Unauthorized`로 막혔고, 기기 코드 재인증 뒤 두 번째 시도는 candidate QA와 PR handoff까지 성공했다. 첫 Windows 시도는 cleanup이 실패했지만 PR #31 수정 후 재실행에서 no-op cleanup까지 통과했다.

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

Linux 첫 시도는 자연 발생한 인증 실패 결과를, 두 번째는 candidate QA와 PR handoff 성공 경로를 보였다. Windows 두 번째 수동 실행은 no-op과 cleanup 성공을 보였다. Windows에서 변경 candidate의 QA·push·PR 성공 경로와 실제 scheduler principal은 아직 검증하지 않았다. 예약 작업은 설치하거나 활성화하지 않았다.

## 다음 단계

Windows no-op 실행과 cleanup은 검증됐다. Windows read-only `Get-ScheduledTask` 조회에서 `MacroData-HealthCheck`와 `MacroData-AgentImprovement`가 등록되지 않은 것을 확인했다. 따라서 조회할 task principal이나 실행 이력은 없다. Windows changed-candidate success와 failure 경로, 교차 실행 lock 및 보존 정책은 미해결이므로 scheduler는 비활성으로 둔다.


## 예약 설정 정적 검토 — 2026-10-27

정적 코드는 Linux에서 검토했다. 실제 Windows pilot은 사용자가 수행했고, read-only `Get-ScheduledTask` 조회 결과 MacroAtlas task가 하나도 등록되지 않았다. 그러므로 Windows task principal·로그온 조건·예약 실행 이력은 관찰할 수 없었다. Windows CI의 wrapper dry-run은 PowerShell 문법과 인자 전달 검사이며 실제 사용자 세션 pilot을 대체하지 않는다.

`scripts/install_tasks.ps1`은 매일 07:30 health check와 토요일 09:00 improvement task를 각각 등록한다. 둘 다 `StartWhenAvailable`과 task별 `MultipleInstances IgnoreNew`를 쓰며 실행 제한은 각각 30분과 2시간이다. Improvement task 인자에는 `-BaseRef`가 없어 `run_improvement.py`가 checkout의 `origin/HEAD`를 사용한다. 현재 Linux checkout의 `origin/HEAD`는 `origin/codex/iteration-04-gate-a`를 가리키지만, Windows clone의 remote HEAD도 같은지 확인되지 않았다. 미설정이면 updater는 `NOT_EXECUTED`로 종료한다.

`IgnoreNew`는 동일 task 이름의 중복 실행만 제한한다. installer와 updater에는 health task·manual run을 포함하는 공통 lock/idempotency guard가 없으며, 계획된 `ALREADY_RUNNING` 결과도 구현되어 있지 않다. Updater 보고서와 로그는 `reports/improvement_<run_id>/`에 보존되지만 자동 보존 기간·용량 한도·정리 정책이 없다. 실패 경로의 worktree도 의도적으로 남길 수 있으므로 장기 예약 전 디스크 사용량과 안전한 정리 기준이 필요하다. Task principal과 대화형 로그인 요건은 installer에서 명시하지 않아 실제 Windows에서 확인해야 한다.

결론: scheduler는 설치·활성화하지 않는다. 현재 Windows에는 MacroAtlas task가 등록돼 있지 않다. 수동 no-op과 cleanup은 통과했지만, scheduler를 고려하기 전에 explicit base ref, 수동·예약 실행 공통 중복 방지, report 보존 정책이 필요하다. 설치 전에는 task principal, 로그인 요건, 지연 시작, 실행 제한과 task 간 겹침을 설계 검토해야 한다. Windows candidate·failure 경로까지 검증하기 전 예약 활성화를 결정하지 않는다.

## Windows 첫 수동 실행 — 2026-10-27

- Windows와 Anaconda Python 3.12.8에서 dry-run이 `DRY_RUN`으로 통과했고 base ref와 SHA는 `origin/codex/iteration-04-gate-a` / `d925f91b890cd5ea5ee43d78750db9b3033515ff`였다.
- 실제 run `20261027T051148Z-d939d7d6`에서 Codex는 exit code 0으로 끝났지만 변경 파일은 없었다. 결과는 `CLEANUP_FAILED`, candidate/QA/push/PR은 없고 `network_requested=false`였다. 원본 report는 사용자 Windows 저장소 `reports/improvement_20261027T051148Z-d939d7d6/report.json`에 남아 있다.
- 사후 점검에서 Git 등록 worktree는 이미 해제됐고, `checkout` 폴더는 비어 있으며 `.git` marker가 없었다. 같은 이름의 임시 branch는 남아 있었다. 폴더 안에서 실행한 `git status`는 상위 저장소를 읽으므로 임시 worktree 상태 증거로 쓸 수 없다.
- 당시 updater는 `git worktree remove`의 stderr를 report에 기록하지 않아 최초 실패 원인은 확인할 수 없다. 보완 코드는 실패 출력을 구조화해 보존하고, 등록 해제된 빈 orphan 디렉터리만 지우며, 비어 있지 않은 경로와 base에서 이동한 branch는 보존한다.
- 이 시도는 Windows Codex 실행과 no-op 경로를 확인했지만, cleanup 실패 때문에 Windows pilot을 통과 처리하지 않는다. 보완 코드 병합 후 남은 빈 디렉터리와 base branch를 정리하고 재검증한다.

## Windows no-op 재검증 — 2026-10-27

- PR #31의 cleanup 보완을 포함한 base `8fc22c89ae343d696ef0071503b6a0bc0c90a69b`에서 실행했다. Anaconda Python 3.12.8과 Windows PowerShell wrapper를 사용했다.
- run `20261027T052555Z-e8c44ca0`: `NO_ACTIONABLE_CHANGE`, Codex exit code 0, `changed_paths=[]`, `candidate_commit=null`, `qa_report=null`, `push_status=NOT_RUN`, `network_requested=false`.
- cleanup은 `PASSED`: worktree remove return code 0, 임시 branch 삭제 성공. report는 Windows 저장소의 `reports/improvement_20261027T052555Z-e8c44ca0/report.json`에 남아 있다.
- 따라서 Windows 사용자 세션의 Codex no-op 및 cleanup 경로는 통과했다. 변경 candidate QA·push·PR과 retryable failure 경로는 실행되지 않았다. 사용자의 read-only task 조회에서 등록된 MacroAtlas scheduler가 없음을 확인했다.

## 운영 준비 보완 — 2026-10-27

- `install_tasks.ps1`은 `-BaseRef`를 필수로 받고, 설치 시 선택한 Python executable을 두 task action에 고정한다. 기준 ref는 현재 checkout에서 local/remote branch로 resolve돼야 한다. task principal은 현재 로그인한 사용자, `Interactive`, `Limited` 권한으로 명시한다.
- `-DryRun`은 trigger/action/settings/principal을 구성해 JSON으로 내보내고 `Register-ScheduledTask`를 호출하지 않는다. Windows CI에서 dry-run을 검증한다.
- updater는 `reports/.run_improvement.lock`의 OS 파일 잠금으로 manual/scheduled 호출을 직렬화한다. 점유 중인 호출은 네트워크나 worktree 작업 없이 `ALREADY_RUNNING` report를 남긴다. dry-run은 기존처럼 파일을 만들지 않는다.
- 90일 지난 `NO_ACTIONABLE_CHANGE` + `cleanup=PASSED` updater report는 checkout이 없고 Git worktree 등록 및 local branch가 모두 없으며 예상된 파일만 있을 때 정리한다. 90일 지난 `mode=check`, `status=PASSED` QA report만 같은 방식으로 정리한다. candidate QA, 실패, cleanup 문제, 예상 밖 파일, 손상된 report는 보존한다.
- 변경 candidate·Codex 실패와 실제 Task Scheduler 실행은 Windows에서 아직 확인하지 않았다. `Get-ScheduledTask`에서 등록된 MacroAtlas task가 없다는 기존 확인은 유지되며 scheduler는 비활성이다. 사용자의 Windows pilot에서 installer dry-run과 updater changed/failure 경로를 검증하기 전까지 예약 등록을 보류한다.

이 updater 작업은 MacroAtlas provider 접속이나 Gate C 원자료 증거와 별도다.
