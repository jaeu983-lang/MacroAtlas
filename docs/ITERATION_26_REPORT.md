# 26회차 보고서 — isolated updater와 candidate QA handoff

기준일: 2026-10-27. 제품 data engine, 원자료와 예약 task 설정은 변경하지 않고 개발자 maintenance workflow의 updater→QA 연결을 구현했다.

## 변경

- `run_improvement.ps1`은 Python controller의 Windows wrapper가 됐다. Controller는 `origin/HEAD` 또는 명시 base에서 별도 Git worktree를 만들며 현재 checkout의 branch·파일을 바꾸지 않는다.
- Codex 변경은 `src/`, `tests/`, `docs/`, Python/PowerShell/shell scripts, `README.md`, `PROJECT_PLAN.md`만 허용한다. DB·credential·`.env`·symlink·`.github/`·reports 변경은 거부된다.
- no-op이면 worktree와 생성 branch를 정리한다. 다른 실패와 범위 밖 변경은 로컬 report/log와 worktree를 남기며 원격에 보내지 않는다.
- 허용된 변경은 task branch에 commit한 뒤 전체 base/candidate SHA를 `run_maintenance_qa.py`에 전달한다. candidate QA 성공 후에만 push하고 review PR을 만든다. 자동 merge와 publish는 없다.
- GitHub Actions는 Windows PowerShell wrapper와 Linux Python entrypoint의 updater dry-run을 확인한다. 예약 실행 설정은 활성화하거나 수정하지 않았다.

## 검증

- `tests/test_run_improvement.py`: 23 tests passed. allowlist, protected path와 symlink 차단, NUL status/rename 파싱, origin/HEAD 해석, dry-run 무변경, no-op cleanup, QA 실패 시 push 금지, QA 성공 후 `QA → push → PR` 순서를 확인했다.
- `pytest -q`: **709 tests passed**. `tests/test_run_improvement.py`: **24 tests passed**.
- `ruff check .`, `git diff --check`, `python -m py_compile scripts/run_improvement.py`: 통과.
- GitHub Actions에 Windows PowerShell/Linux updater dry-run을 추가했다. Workflow YAML parse와 local dry-run은 통과했다. 실제 Codex 수정을 시작하거나 push/PR을 수행하는 pilot은 실행하지 않았다.

실제 Windows Codex pilot, scheduler base-ref 설정, 중복 실행 방지와 로그 수명 확인은 27회차로 남긴다. 이 구현은 Gate C source revision/retry evidence를 추가하거나 변경하지 않는다.
