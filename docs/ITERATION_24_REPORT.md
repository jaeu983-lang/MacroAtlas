# 24회차 보고서 — 유지보수 검사 진입점 통합

기준일: 2026-10-26. 개발자 health script와 detached QA runner의 중복 검사를 한 Python entrypoint로 연결했다.
제품 data engine이나 코드 updater의 동작은 바꾸지 않았다.

## 변경

- `python scripts/run_maintenance_qa.py`가 clean working tree의 현재 commit을 detached worktree에 검사한다.
- 한 번의 실행에서 pytest, Ruff, commit whitespace, Python CLI help, 설치된 `macroatlas --help`와
  `macroatlas collect --help`, project health를 실행한다. 검사마다 timeout/log/status를 기록하며 한 도구가 없거나
  실패해도 나머지 검사를 계속한다.
- JSON report에 run ID, 검사 commit, Python/platform, network flag, 각 check와 cleanup 결과를 저장한다.
- `scripts/run_checks.ps1`은 동일 Python runner를 호출한다. 기본은 repository `.venv`를 사용하고 CI에서는 명시한
  Python 경로를 받는다.
- GitHub Actions는 Linux에서 Python runner를 직접 호출하고 Windows에서는 PowerShell wrapper로 같은 runner를 호출한다.
  두 OS에서 Python 3.11/3.12 matrix를 유지한다. 각 job은 검사별 결과를 stdout에 요약하고 report와 로그를 artifact로 보존한다.
- whitespace 검사가 commit diff만 비교하도록 Actions checkout에서 현재 commit과 부모 commit을 가져온다.

## 검증

최종 격리 runner 실행은 commit `bd660fa6f95b9ca9e08110f2c2a4a1b9fcf4f155`에서 수행했다.

- Report: `reports/maintenance_qa_7cdbace72b24409c86e11fe50bcbd6fc/report.json`
- 환경: Linux, Python 3.12.14
- pytest: **679 passed**
- Ruff, commit whitespace, Python CLI help, installed CLI help, collect help, health: 모두 통과
- detached worktree cleanup: 통과
- 외부 네트워크 요청: 없음
- 단위 회귀: `python -m pytest -q tests/test_maintenance_qa.py` — **7 passed**
- 변경 파일 whitespace: `git diff --check` — 통과
- GitHub Actions push·pull request 실행 모두 Linux/Windows Python 3.11/3.12 네 조합 통과
- 원격 검증 중 checkout depth 1로 인해 과거 14회차 문서의 공백이 현재 commit 오류로 잘못 잡힌 것을 확인했다.
  checkout depth를 2로 늘려 부모 commit을 포함하자 의도한 commit-diff 검사로 복구됐다.

이 runner는 clean committed HEAD만 검사하며 수정 중인 candidate SHA 입력은 아직 받지 않는다. PatternAnalyzer scope 연결,
자동 updater와 candidate QA handoff, scheduler 변경은 25–27회차다.
