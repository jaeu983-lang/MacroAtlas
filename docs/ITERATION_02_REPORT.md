# 02회차 결과 — Orchestrator와 작업 이력

기준일: 2026-10-24. PROJECT_PLAN.md §4/5/7/8 및 IMPLEMENTATION_PLAN.md 02 범위만 구현했다.
03회차는 진행하지 않았다. API 호출·실제 수집·CLI 제품 명령·사용자 설명서/PPT 제작 없음.

## 시작 상태와 검증

- AGENTS/GUIDELINES/PROJECT_PLAN/IMPLEMENTATION_PLAN/ARCHITECTURE/DECISION_LOG 및
  기관 조사대장·대표 시나리오와 기존 코드·테스트를 확인했다.
- 시작 브랜치 codex/iteration-01에서 별도 codex/iteration-02로 전환했다.
- 시작 시 전체 pytest **16 passed in 0.54s**, Ruff **All checks passed!**.
- 저장소의 모든 시작 파일이 untracked인 상태를 유지했다. 사용자 파일 삭제·커밋·병합 없음.

## 구현한 사용자 가치

작업을 생성·계획하고 독립 엔진으로 단계별 실행한 뒤, 프로세스가 바뀌어도 SQLite에서
요청·계획·결과·오류·시도·이벤트를 조회한다. 실패·검토·취소 시 후속 실행을 멈추고,
명시적인 resume으로 같은 요청 ID 아래 새 시도를 남긴다.

입력과 엔진 버전이 같고 원래 TTL 안에 있으며 주입된 검증기가 근거 유효성을 승인한
성공 앞 단계만 재사용한다. 검증되지 않은 결과는 재사용하지 않는다. 기관 관련 의미나
키 유무를 추정하지 않으며 실제 네트워크 어댑터는 없다.

## 변경 파일과 이유

| 파일 | 변경 이유 |
|---|---|
| src/macro_data_platform/orchestration/models.py | StageSpec/TaskPlan/StageInput, JSON 스냅샷 및 입력 검증 |
| src/macro_data_platform/orchestration/runner.py | 생성·계획·순차 실행·멱등성·재개·취소·복구·재사용 정책 |
| src/macro_data_platform/orchestration/__init__.py | Python API 공개 |
| src/macro_data_platform/storage/history.py | SQLite 저장, 트랜잭션·작업 이력·이벤트 조회 |
| src/macro_data_platform/storage/__init__.py | HistoryStore 공개 |
| tests/test_orchestration.py | 신규 45개 사례, 실제 로컬 SQLite와 모의 엔진 검증 |
| docs/ARCHITECTURE.md | 현재 Python API·상태·저장·복구 계약 및 제한 설명 |
| docs/DECISION_LOG.md | D-009 일부 해결, D-014~018 선택·제한 기록 |
| docs/ITERATION_02_REPORT.md | 이 보고서 |

기존 contracts.py의 상태/오류 계약, 기존 테스트 기준, 의존성 및 PowerShell 스크립트·
실행 정책은 변경하지 않았다. 새 외부 패키지를 설치하지 않았다.

## 실제 테스트 결과

저장소 .venv(Python 3.12.14, pytest 8.4.2) 사용. 신규 테스트는 네트워크 없이
모의 엔진/주입 시계/임시 SQLite로 수행했다. 임시 파일은 reports/pytest_iteration02_* 안에 있다.

| 검사 | 최종 실제 결과 |
|---|---|
| `.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_iteration02_verified` | **61 passed in 3.89s**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m ruff check src tests` | **All checks passed!**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m macro_data_platform.health` | 종료 코드 0, 레이아웃 정상 |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| `git diff --check` | 종료 코드 0. untracked 파일은 검사하지 않으므로 코드 검증 근거는 pytest/Ruff임 |

최신 로그는 reports/iteration_02_pytest.txt와 reports/iteration_02_ruff.txt에 저장했다
(Git 제외). 기존 16개 + 신규 45개이며 실패·건너뜀은 없다.

주요 검증: 정상 완료와 재시작 후 이력 조회, null/zero 구분, 입력/출력 근거 연결,
중복 요청·계획·완료 재실행의 멱등성, 키 충돌, 계획 불변성, 버전 불일치 차단,
실패 단계 재시도와 prefix 재사용, TTL 만료/역행/검증 부재·실패·예외,
원래 TTL 유지·의존 단계 무효화·검증기의 입력 변조 차단, 검토 확인, 종료 실패 우회 방지,
재시도 상한, 실행 전/실행 중 취소, KeyboardInterrupt와 복구, 이전 토큰 저장 차단,
동시 요청 및 중복 실행 방지, 엔진 예외·비 JSON/NaN 결과 격리, 스키마 버전 거부,
작업 생성·단계 결과·작업 완료 각각의 DB 장애 원자성 검증.

개발 중 장애 주입 테스트 1개가 작업 완료 실패 시 이미 커밋된 단계까지 롤백될 것으로
잘못 예상해 59 passed/1 failed였다. 단계 결과 커밋과 작업 완료 커밋이 별도라는
계약에 맞춰 두 장애 테스트로 분리·확장했다. 최종에는 단계 결과 실패의 원자적 롤백과
작업 완료 실패 시 성공 단계 보존·검증 후 재사용을 모두 확인했다.

## 보안·데이터 완전성과 실제 검증 범위

- 요청·계획·모든 실행 시도와 오류 코드를 보존한다. 저장은 매개변수화한 SQL과
  SQLite 트랜잭션을 사용한다. 읽은 스냅샷 수정이 DB 이력을 바꾸지 않는다.
- 엔진 예외 메시지/traceback을 저장하지 않아 예외에 포함될 수 있는 키를 기록하지 않는다.
  실제 키/.env는 읽지 않았다. 자격증명은 향후 엔진 실행 설정으로 별도 주입해야 한다.
- 본 API는 임의 문자열의 모든 비밀값을 자동 탐지하지 않는다. 호출자는 요청/입력/
  payload/근거 URL에 키를 넣지 않아야 하며 후속 커넥터의 비밀값 제거가 필요하다.
- 저장 경로는 Settings의 저장소 내부 정책을 사용한다. 원본·관측치 다운로드/수정은 없다.
- 공식 문서 조사 내용은 로컬 문서만 읽었다. 외부 문서 재확인·실제 API·ingestion은
  모두 NOT_RUN. X07 재개 개념을 모의 엔진으로 검증했으며 실제 X01 HTTP backoff나
  Gate A 실측 수집을 통과했다고 주장하지 않는다.

## 남은 한계와 다음 회차 선행 조건

- 현재는 순차 실행 Python API다. 자연어 계획 생성·제품 CLI·병렬 작업 큐는 없다.
- 취소는 실행 중인 엔진을 강제 종료하지 않는다. 중단 복구는 이전 작업자 종료와
  외부 부작용을 사람이 확인한 후 호출해야 한다. 자동 lease 만료·외부 exactly-once는 없다.
- 단계별 총 호출 상한은 기본 3(허용 1~10), TTL은 기본 3600초다. 재사용 검증기는
  호출자가 제공한다. 검증기 없이도 재개는 가능하지만 앞 단계를 재실행해 상한을 소비한다.
- 자동 HTTP backoff·rate limit·원본 비덮어쓰기·관측치 검증·피드백은 후속 회차다.
- SQLite는 작업 JSON 스냅샷과 이벤트만 지원한다. 전체 카탈로그/이관/큰 이력 최적화는 없다.
- 기존 PowerShell 서명 정책과 dependency lockfile 부재는 남아 있다. 정책 변경 없음.
- API 키 선택 등록 정책은 기획에만 있고 로딩·검증 기능은 아직 없다.
- 전체 파일이 untracked이므로 변경 검토와 Git 체크포인트가 필요하다.

02회차 완료 기준인 상태·정상/실패·검토/취소 및 모의 엔진 재개 테스트는 통과했다.
사람은 선형 계획·상한/TTL 기본값·복구 운영 정책과 diff를 검토해야 한다.
추가 결정 없이는 진행할 수 없는 02회차 코드 차단 사항은 없다.
03회차를 요청받으면 기관/허용 접근 경로 선정 및 네트워크 설정을 먼저 확인해야 한다.
이번에는 03회차를 시작하지 않았다.
