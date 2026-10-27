# 26회차 후속 보고 — Codex CLI invocation compatibility

2026-10-27, PR #17 merge HEAD `e036fb3082129047a550e642d1e1ac3916b457c4`에서 updater를 한 번 시작했다. 설치된 Codex CLI는
`--ask-for-approval`을 `exec` subcommand 뒤에서 거부해 exit code 2를 반환했다. CLI help를 대조하니 approval 정책은 top-level 옵션이며,
`exec --help`에는 해당 옵션이 없었다.

Codex prompt는 시작되지 않았다. candidate commit, QA, push 또는 PR도 발생하지 않았다. 생성된 branch의 worktree는 HEAD가 base SHA와
같고 clean임을 확인한 뒤 제거했으며, 보고서와 CLI 오류 로그는 Git-ignored `reports/`에 보존했다.

후속 수정은 approval 옵션을 `codex --ask-for-approval never exec --sandbox workspace-write` 순서로 보내고, 실제 worktree를 만들기
전에 이 안전 실행 형태의 `--help` preflight를 수행한다. 회귀 테스트는 인자 순서와 지원하지 않는 옵션 거부를 확인한다. 실제 Codex
task pilot은 이 변경이 병합된 뒤 다시 평가한다.

수정 branch의 전체 suite는 **711 tests passed**, updater 전용 suite는 **26 tests passed**다. Ruff, `git diff --check`, Python compile,
workflow YAML parse와 설치된 Codex CLI help preflight도 통과했다. Windows CI 결과는 PR 검증 뒤 이 기록에 추가한다.
