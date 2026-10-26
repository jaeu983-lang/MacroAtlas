# 18회차 — 유지보수 실행기와 QA/PR 연결

PR #3과 #4는 사용자 명시 지시로 순서대로 통합했다. 통합 HEAD는 `25f3c87`이다. 기존 CI 네 조합은 성공했고 통합 checkout에서 기존 645개 회귀 검사를 통과했다.

- Python 공통 QA runner: clean commit을 detached worktree에서 검사하고 commit/환경/검사별 결과와 로그를 보존한다. 오류·timeout·cleanup 실패는 실패로 반환한다.
- 분석 범위: 저장된 고정 TIC/BIS source와 BOJ FM08/FXERD01 계획에서 기관·dataset만 연결한다. 경제 concept은 추정하지 않으며 미상 범위의 반복 제안은 차단한다. 과거 task는 변경하지 않는다.
- 개선 prompt와 개발자 가이드에 수정 branch → commit → 격리 QA → push → 검토 PR 흐름을 연결했다.
- 신규 runner 실패·timeout·dirty-tree 계약과 file scope adapter 테스트를 추가했다.

정식 BIS 대용량 handoff, CSV 전달 및 Gate C 자연 증거는 완료로 처리하지 않는다. runner의 Windows 실동작은 Linux 실행과 구분해 후속 CI에서 확인해야 한다.

## 실행 검증

신규 4개 계약 테스트와 전체 회귀 suite(649개), Ruff, diff 검사 통과. commit `51bd724`를 detached worktree에서 실제 실행한 QA 결과는 PASSED이며 pytest/Ruff/diff/CLI 및 worktree cleanup이 모두 통과했다. 로컬 보고서: `reports/maintenance_qa_b8636be76f214589bcba53c24545c883/report.json`. 원격 PR CI 결과는 GitHub에서 별도로 확인한다.
