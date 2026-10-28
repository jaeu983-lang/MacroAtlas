# Iteration 18 — 사람용 대화 시나리오와 E2E fixture 계측

**Date:** 2026-10-25
**Result:** Gate I PASS
**Scope:** 사람이 재생할 Q&A 예시 파일과 현재 World Bank fixture workflow의 측정. 기관/API source code 변경과 live 호출은 없음.

## 사용자 가치

- `docs/user/examples/HUMAN_CONVERSATION_TESTS.md`에 8개 다중 turn 대화 예시를 작성했다. 사람이 실제 연결된 에이전트에 질문을 입력하고 대화를 기록할 수 있도록 기대 응답·통과 기준·실제 응답 기록란을 포함한다.
- 현재 repository에 대화 UI/LLM이 없다는 사실을 파일 첫머리에 명시했다. 예시는 현재 MacroAtlas가 생성한 출력이 아니며, 에이전트 연결 후 사람이 재생할 목표 대화다.
- 사례는 누락 정보, 명목/실질 혼동, API 미확인 TIC, BEA 인증정보, e-Stat 영어 우선/일본어 보완, 결측과 0, 429 재개, randomized soak를 다룬다.

## E2E benchmark

`scripts/benchmark_workflow_e2e.py`가 World Bank 고정 fixture 경로를 매회 독립 temp root에서 30회 실행했다. 입력은 이미 구조화된 `DataRequest`이므로 자연어 parsing/LLM은 측정하지 않는다.

| 구간 | p50 | p95 | max |
|---|---:|---:|---:|
| workflow 준비 | 24.4676 ms | 29.7148 ms | 33.4152 ms |
| dispatcher | 160.1129 ms | 176.1139 ms | 236.6913 ms |
| SQLite/raw read-back | 6.2956 ms | 7.6365 ms | 18.4157 ms |
| collect stage timestamp 차이 | 55.3370 ms | 67.1090 ms | 95.2120 ms |
| validate stage timestamp 차이 | 28.6340 ms | 32.0980 ms | 36.6320 ms |
| dispatcher CPU | 109.3750 ms | 125.0000 ms | 140.6250 ms |

30/30 작업 완료, raw hash 검증, 저장된 값 `[123.5, null, 0]` 및 상태 `[reported, missing, reported]` read-back 통과. 표본당 mock API 1회, mock query 57 bytes, mock body 810 bytes, live HTTP 0회. timing run은 저장소 안의 격리 temp root에서 수행했고 raw sample은 `reports/performance_workflow_e2e_2026-10-25.json`이다.

CPU 값은 Windows process timer의 15.625ms quantization 영향을 받는다. suite/E2E native SQLite memory와 process RSS는 신뢰할 수 있게 측정하지 못했다. 첫 E2E timing 시도는 `tracemalloc`을 켜 latency를 부풀려 제외했다. 정식 timing run은 tracing을 껐다.

## Profile 해석

별도 30-run cProfile은 `HistoryStore.transaction` 780회, `_connect` 1,380회, SQLite `commit` 390회를 기록했다. profile 누적시간은 각각 2.532초, 1.685초, 1.470초다. profiler는 실행시간에 영향을 주므로 profile wall 값은 기준선 latency로 쓰지 않았다. transaction boundary를 합치면 atomic rollback, audit append-only, retry/resume에 영향을 줄 수 있어 이번 회차에는 코드를 수정하지 않았다. 개선율은 미측정이다.

## 검사 결과

- E2E fixture benchmark: **30/30 completed**, raw source/value/hash invariants pass, live HTTP 0.
- `scripts/measure_test_suite.py`: **625 passed, 1 skipped, 0 failed** (626 collected), 38.5757초, process CPU 27.7812초. 전체 suite는 이 저장소 `src`/`tests` import를 우선하는 계측 경로로 실행했다.
- 일반 `python -m pytest -q`는 ambient Python path가 OneDrive의 다른 MacroAtlas checkout을 먼저 가져와 12개 모듈 collection에서 실패했다. 이 실패를 제품 테스트 회귀로 보지 않고, 경로 고정 harness의 통과와 구분했다.
- Ruff 전체 저장소 통과. raw JSON parse와 30개 invariants, 대화/보고서 whitespace 검사, `git diff --check` 통과. diff check는 기존 LF→CRLF 경고만 냈다.
- 외부 기관 API와 `.env` credential은 접근/출력하지 않았다.

## 제한 및 다음 단계

- 대화 파일은 사용자의 수동 입력용이다. 현재 앱 안에 실제 자유형 대화를 생성하는 agent UI가 없으므로 실제 에이전트 응답 검증은 미실행이다.
- E2E는 World Bank 단일 fixture route다. 실제 World Bank latency, BEA/e-Stat workflow, 다른 기관/API, random live collection은 미검증이다.
- Iteration 19에서는 SQLite transaction/connect profile 후보를 관련 오류·복구 테스트와 함께 분석하고, 전후 paired E2E에서 효과가 확인되는 경우에만 공통 경로 하나를 단순화한다.
- worktree는 기존 변경이 많은 dirty 상태여서 변경을 stage/commit하지 않았다.
