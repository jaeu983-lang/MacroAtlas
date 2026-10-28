# Iteration 20 — 병렬 작업 트랙과 기관별 live 준비 게이트

**Date:** 2026-10-25\
**Result:** Gate K PASS\
**Scope:** 기존 효율화 기능과 병목 근거를 다시 확인하고, 운영·유지보수와 기관 커넥터 확장을 병렬 track으로 정리했다. live API 호출이나 제품 source-code 성능 변경은 하지 않았다.

## 결정

- **Track M — 운영·유지보수:** 공통 orchestration, retry/resume, 저장, provenance, 보안, telemetry, 공통 효율화와 회귀를 소유한다.
- **Track C — 기관 커넥터 확장·업데이트:** 기관 공식 문서, 인증, source-specific adapter/fixture, 식별자·pagination·rate-limit·언어·revision 차이를 소유한다.
- 두 트랙의 독립된 offline 작업은 병렬로 진행할 수 있다. 공통 contract 변경은 영향받는 adapter fixtures로 회귀 검증한다.
- live는 각 기관별로 판단한다. 공통 platform gate와 해당 기관 source gate를 모두 통과한 기관부터 canary를 시작한다. 21개 기관 전체가 준비될 때까지 기다릴 필요는 없다.
- API가 `unconfirmed`인 기관은 공식 API 경로를 확인하기 전 endpoint를 추정해 호출하지 않는다. 공통 provider 또는 credential을 공유하는 프로필은 요청량·동시성 budget도 공유한다.

## 기존 효율화 기능 확인

`src/macro_data_platform/improvement/ImprovementAnalyzer`는 반복 incident, 사용자 피드백, 격리된 추론을 읽어 사람 검토용 개선 후보와 테스트 계획을 만드는 도구다. 이 코드는 읽기 전용이며 source code를 자동 변경하거나 성능을 자동 최적화하지 않는다.

이전 cProfile은 SQLite transaction/connect/commit 빈도를 최적화 후보로 지목했다. 그러나 connection 재사용이나 transaction 병합은 audit atomicity, rollback, idempotency 및 retry/resume 동작을 바꿀 수 있다. 현재 timing 변동만으로 해당 변경의 이득을 확정할 수 없어 공통 workflow와 storage 코드는 수정하지 않았다.

## Offline E2E 재측정

World Bank 고정 fixture 흐름을 동일한 script와 환경에서 30회씩 두 번 실행했다. 이 검사는 구조화 요청→확인→fixture 수집→검증→SQLite 저장/read-back이고 기관 live API를 호출하지 않는다.

| Run | Dispatcher p50 | Dispatcher p95 | CPU p50 | Read-back p50 | 완료·hash·missing/zero |
|---|---:|---:|---:|---:|---|
| 1 (30회) | 281.4949 ms | 340.0700 ms | 187.5000 ms | 11.9574 ms | 30/30 통과 |
| 2 (30회) | 286.2774 ms | 350.5180 ms | 203.1250 ms | 10.5237 ms | 30/30 통과 |

두 현재 run끼리는 근접하지만 Gate I에서 같은 이름의 시나리오로 기록한 dispatcher p50/p95 **160.1129/176.1139 ms**와는 큰 차이가 있다. 이번 작업은 해당 workflow source를 변경하지 않았고 런타임의 전체 변동 요인을 통제하지 못했다. 그러므로 이 차이를 코드 최적화나 코드 회귀로 표시하지 않는다. 안정적인 paired 기준선을 먼저 확보할 Track M 후속 작업으로 남긴다.

요약 수치는 [재측정 JSON](../../../reports/iteration_20_baseline_recheck.json), 이전 30개 raw sample은 [Gate I E2E 결과](../../../reports/performance_workflow_e2e_2026-10-25.json), 재현 명령은 `python scripts/benchmark_workflow_e2e.py`다. 재측정 동안 live HTTP 요청은 0회였다.

## 변경 파일

- `docs/developer/history/WORKSTREAMS_AND_LIVE_READINESS.md`: Track M/C 책임 경계, 병렬 실행 원칙, shared platform gate와 source-specific gate, per-provider budget을 정의했다.
- `reports/iteration_20_baseline_recheck.json`: 30회 E2E 2-run 요약과 정확성 invariant를 보존했다.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`, `PROJECT_PLAN.md`, `docs/developer/history/DECISION_LOG.md`: Gate K와 D-078, 병렬 track, 기존 순차 가정의 조정을 반영했다.
- `docs/developer/performance/BOTTLENECK_ANALYSIS.md`, `docs/developer/performance/OPTIMIZATION_LOG.md`, `docs/developer/performance/BENCHMARK_COMPARISON.md`: current recheck 수치와 최적화 변경 없음/효과 미입증을 기록했다.

## 검증 결과

- 고정 fixture E2E: **2 × 30/30 완료**; raw SHA256, missing과 zero 보존 invariant 통과; live HTTP 0회.
- `scripts/measure_test_suite.py`: **626 collected; 625 passed, 1 skipped, 0 failed**. Wall time **54.5015초**, process CPU **39.1094초**. 전체 suite RSS는 미측정.
- 전체 Ruff: `ruff check --no-cache .` 통과.
- benchmark recheck JSON parse 및 invariant 검증 통과.
- `git diff --check` 통과. 기존 파일의 LF→CRLF 경고만 확인했다.

## 미검증·보안·데이터 한계

- benchmark는 World Bank 단일 고정 fixture이며 21개 기관의 속도, 데이터 정확성, API quota를 대표하지 않는다.
- source-level code optimization 효과는 이번 회차에 0개다. performance 개선율은 계산하지 않았다.
- 실제 기관 live 요청, 인증 성공, 사용자의 `.env` 접근은 0회다. live test는 source별 준비 gate를 통과한 이후 별도 실행해야 한다.
- API 키 값은 읽거나 보고하지 않았다. fixture에서 원본 hash, 결측, 0, provenance 경계에 변경은 없었다.

## 다음 진행 방식

Track C는 공식 API 문서와 source fixture가 준비된 기관부터 offline 개발을 진행할 수 있다. Track M은 통제된 paired measurement와 복구 테스트를 갖춘 공통 병목만 변경한다. 두 트랙 결과가 모두 live gate를 만족하면 준비된 기관 단위로 canary를 시작하고, 기관별 쿼터를 확인한 뒤 2시간·6시간 soak로 넓힌다. 이번 결과는 stage/commit하지 않았고 사람의 diff 검토가 남아 있다.
