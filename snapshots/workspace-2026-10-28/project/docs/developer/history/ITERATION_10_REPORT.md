# 10회차 완료 보고 — 품질·오류 분류·복구 (Gate C)

일자: 2026-10-25\
상태: Gate C 통과, 사람 diff 검토 대기\
기준 브랜치: `codex/iteration-07-08-discovery`\
커밋: 만들지 않음

## 구현한 사용자 가치

- 429·408·5xx·timeout·connection failure를 한정된 재시도 경로로 분류한다. 재시도는 workflow 이력에 시도 수와 `retry_not_before`를 기록하고, due 시각 전에 `resume`이 호출돼도 네트워크 요청을 하지 않는다.
- 숫자형과 HTTP-date Retry-After를 읽고 최대 24시간을 지원한다. 그 상한을 넘는 429는 검토로 멈춘다. 401/403은 접근 거부, redirect는 보안 검토, 404/410은 terminal 경로 변경으로 분기한다.
- 선언한 media type/열/주기/요청 범위가 응답과 맞지 않으면 raw 원본과 manifest를 보존하고 관측치를 반환하지 않는다. 다운로드 중 source metadata 또는 사용자 확인 fingerprint가 바뀌어도 같은 방식으로 중단한다.
- 대량 요청용 durable unit ledger가 확인 fingerprint·기관·선택 series·국가·기간·frequency에 bound된다. 성공/재시도/검토/terminal/미실행 단위를 구분하고 성공 단위는 건너뛰며 pending 단위만 재개한다. 전체 요청/관측치/byte/time 자원과 raw artifact 경로를 기록한다.
- 실행 callback은 단위와 남은 byte/time budget을 전달받는다. callback이 초과된 결과를 반환하면 raw를 보존하고 해당 실행과 남은 단위를 검토 상태로 멈춘다.

## 주요 변경 파일

- `src/macro_data_platform/contracts.py`, `src/macro_data_platform/orchestration/models.py`, `src/macro_data_platform/orchestration/runner.py`: stage retry delay, runtime attempt number, durable due-time enforcement.
- `src/macro_data_platform/ingestion/retry.py`: exponential delay 및 최대 대기 상한.
- `src/macro_data_platform/connectors/worldbank.py`, `src/macro_data_platform/ingestion/worldbank.py`: 429/Retry-After·timeout 오류의 상태/지연 연결.
- `src/macro_data_platform/ingestion/discovered.py`, `src/macro_data_platform/discovery/series.py`: 파일/API status 분기, freshness/schema 재검사, source-route resume API.
- `src/macro_data_platform/ingestion/bulk.py`, `src/macro_data_platform/ingestion/batch.py`: budget-bound plan snapshot과 단위별 SQLite task-history progress, resume 및 stop policy.
- `tests/test_orchestration.py`, `tests/test_worldbank.py`, `tests/test_worldbank_request.py`, `tests/test_gate_a.py`, `tests/test_series_discovery.py`: backoff, 403, 429, format drift, metadata change, budget, partial execution/resume fixture.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`, `docs/developer/testing/REFERENCE_SCENARIOS.md`: Gate C 결과와 증거 범위.

## 테스트와 실제 결과

- Gate C 핵심 회귀: **237 passed in 44.66s**.
- 전체 pytest: **568 passed in 34.83s**.
- `ruff check .`: 통과.
- `git diff --check`: 통과. Git은 기존 LF 파일이 이후 갱신 때 CRLF로 바뀔 수 있다고 알렸으나 whitespace 오류는 없었다.
- 모든 신규 검증은 local fixture/mock이다. 외부 네트워크, 기관 페이지, live API 또는 live link 검증은 하지 않았다.

## 시나리오별 결과

| 시나리오 | 결과 | 근거/제한 |
|---|---|---|
| 429 + Retry-After | PASS | mock 429, due 전 차단, 대기 후 재개; 지원 상한 초과 시 review |
| 403 | PASS | `AUTH_ACCESS`, 인증 우회/fallback 없음 |
| 포맷/schema 변화 | PASS | MIME/열/행 mismatch, raw 보존, 관측치 없음 |
| 통계 의미 모호성 | PASS | 기존 GDP 미상 개념 clarification과 stock/flow 차단 fixture |
| 최신 확인 근거 변경 | PASS | fetch 중 metadata revision 변경 시 raw만 보존 |
| 단위별 재개와 예산 | PASS | success/retryable/not-run 분리, 성공 단위 재사용, byte 초과 중단 |
| link 재검증 | PASS (fixture only) | 만료·접근 상태·조건 fingerprint·credential URL; 실제 URL 요청 없음 |

## 미검증 가정과 한계

- 외부 source 서버의 현재 이용약관, Retry-After 실제 정책, file header/vintage는 검증하지 않았다. 이는 프로젝트의 offline 설정을 바꾸지 않고 확인한 로컬 상태 처리 테스트다.
- 429 이상 Retry-After는 자동 재시도 예약 없이 review 처리한다. 24시간 이하의 유효한 delay는 명시 재개에만 적용하고 background polling/sleep은 하지 않는다.
- source metadata가 바뀐 경우를 재현했으며 기관의 실제 수치 개정/vintage 비교는 하지 않았다.
- bulk callback은 외부 connector가 아니다. callback 작성자가 전달받은 남은 time/byte budget과 source 약관을 준수해야 한다. 저장소가 callback의 외부 부작용을 강제 종료할 수는 없다.
- file output은 선택 raw 포맷과 원본 유지 경로에 제한된다. 상이한 단위·frequency·vintage의 결과를 자동 병합하지 않는다.

## 보안·데이터 무결성 영향

- 403·redirect·format drift·metadata revision change는 접근/의미 경계를 통과하지 못한다. API credentials는 추가되지 않고 자격증명 fallback도 없다.
- 각 응답은 고유 raw 경로에 보존되며 재시도는 앞선 raw를 덮어쓰지 않는다. 승인된 확인 fingerprint가 stale해지면 normalized observations를 만들지 않는다.
- workflow와 unit result에는 예외 원문이나 응답 전체를 저장하지 않는다. raw artifact 경로와 safe error code만 이력화한다.
- bulk unit ledger는 `HistoryStore`의 SQLite task document/event에 저장한다. 새 DB schema version 또는 외부 서비스는 추가하지 않았다.

## 선행 조건과 사람 검토

- Gate C를 통과했으므로 11회차를 시작할 수 있다.
- Gate D 전에 13회차를 시작하지 않는다.
- 사람이 diff를 검토한 뒤 체크포인트/커밋 여부를 결정한다. 이 보고에서는 stage, commit, merge를 하지 않았다.
