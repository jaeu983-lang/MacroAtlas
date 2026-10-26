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
  두 OS에서 Python 3.11/3.12 matrix를 유지한다.

## 검증

격리 runner 실행은 implementation commit `8cdbbdfbd1ca67f2b12117d2addd87a73f4a809a`에서 수행했다.

- Report: `reports/maintenance_qa_baabddf87a9340b78dad4b4f05ee3bca/report.json`
- 환경: Linux, Python 3.12.14
- pytest: **678 passed**
- Ruff, commit whitespace, Python CLI help, installed CLI help, collect help, health: 모두 통과
- detached worktree cleanup: 통과
- 외부 네트워크 요청: 없음
- 단위 회귀: `python -m pytest -q tests/test_maintenance_qa.py` — **6 passed**
- 변경 파일 whitespace: `git diff --check` — 통과

이 runner는 clean committed HEAD만 검사하며 수정 중인 candidate SHA 입력은 아직 받지 않는다. PatternAnalyzer scope 연결,
자동 updater와 candidate QA handoff, scheduler 변경은 25–27회차다. Windows wrapper의 실제 실행은 이 PR의 Windows CI 결과에서
확인한다.
