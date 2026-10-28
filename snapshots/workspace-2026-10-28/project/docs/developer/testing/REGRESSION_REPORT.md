# 기능·정확성 회귀 검증 보고서

**현재 상태:** 기준선 회귀 확인 완료. 이번 회차 제품 코드 최적화는 없음.

## 로컬 검증

| 검사 | 결과 |
|---|---|
| 전체 pytest, 같은 계측 스크립트 3회 | 매회 625 passed, 1 skipped, 0 failed (626 collected) |
| Ruff 전체 저장소 | `ruff check --no-cache .` 통과 |
| 변경 공백 검사 | `git diff --check` 통과. 기존 수정 파일들의 LF→CRLF 경고만 출력 |
| 오프라인 microbenchmark assertions | 7개 사례 모두 assertion 통과 |
| 외부 HTTP | 0회 |

skip 1개는 Windows 환경에서 `.env` symlink 생성 권한이 없어 해당 보호 시나리오를 실행할 수 없는 기존 테스트다. 성공으로 계산하지 않았다.

## 초기 환경 오류와 조치

처음 실행한 pytest는 Python site path에서 `C:\Users\...\OneDrive\문서\ChatGPT\MacroAtlas\src`를 우선 import해 현재 repository에 있는 모듈 대신 다른 checkout의 코드를 찾았다. 그 결과 12개 collection error가 났다. 실제 repository에 의존 모듈은 존재했고, `scripts/measure_test_suite.py`가 자기 저장소의 `src`/`tests`를 우선하도록 한 후 전체 suite 3회가 통과했다. 이를 제품 회귀로 기록하지 않으며, 환경 경로 혼합은 재현 가능한 테스트 실행의 위험으로 병목 문서에 남겼다.

## 정확성 범위 및 제한

- microbenchmark의 일부 assertion은 missing vs zero 보존, 단일 parsed row, mock API response parsing을 확인한다.
- 전체 pytest는 현재 fixture/mock 계약의 회귀 기준이다. 실제 IMF/BIS/BEA/e-Stat/기타 기관 데이터·약관·API revision을 검증하지 않는다.
- 기관 API request count/bytes는 mock transport 수치이며 wire network와 live rate-limit 데이터는 아니다.
- 저장 read-back이 포함된 전체 각 기관별 randomized live ingest는 아직 구현/검증되지 않았다.
- 이번 회차는 raw observation, source ID, unit, frequency, dimension, revision의 제품 코드 변환을 건드리지 않았다. 따라서 before/after 데이터 정확성 차이는 없다.

## 다음 변경의 통과 조건

Iteration 18 이후에는 각 코드 변경 직후 관련 테스트와 동일 seed/payload benchmark를 재실행한다. 필수 출처 추적성, 결측/0, 단위/주기/차원, raw hash, 저장 read-back, 실패 resume 및 기존 전체 테스트에 회귀가 없어야 한다. live canary 결과는 fixture 결과와 별도로 보고한다.

## 사람용 Q&A 및 E2E 재검증

- `docs/user/examples/HUMAN_CONVERSATION_TESTS.md`는 사람이 에이전트에 실제 입력해 결과를 기록하는 시나리오 파일이다. 문서의 “기대 응답”은 현재 MacroAtlas UI/LLM이 생성한 실측 결과가 아니다.
- `scripts/benchmark_workflow_e2e.py`의 30/30 fixture 실행은 SQLite read-back에서 원본 hash와 `123.5`, missing, `0`을 다시 확인했다. live API는 0회다.
- `tracemalloc` 계측은 benchmark latency를 오염시키는 것을 확인해 정식 E2E wall-time run에서 비활성화했다. E2E memory는 미측정으로 둔다.
- 이번 회차에도 source observation 변환, API connector, database schema는 변경하지 않았다. 따라서 제품 코드 before/after 회귀 비교는 없고 최적화율은 미측정이다.
