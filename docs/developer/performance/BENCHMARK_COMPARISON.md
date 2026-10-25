# 성능 전후 비교

**현재 상태:** 수정 전 기준선만 확보. 제품 코드 성능 변경 전이라 after 값과 개선율은 없다.

## 전체 local test suite

| 지표 | 수정 전 기준선 | 수정 후 | 차이/개선율 |
|---|---:|---:|---:|
| Pytest 결과 | 625 passed, 1 skipped (626 collected), 3/3 반복 | 미실시 | — |
| wall p50 | 36.7677 s | 미실시 | 미측정 |
| wall p95 (3 run sample) | 37.3573 s | 미실시 | 미측정 |
| process CPU p50 | 25.2500 s | 미실시 | 미측정 |
| suite RSS | 미측정 | 미실시 | 미측정 |
| test call p50 / p95 중앙값 | 0.003158 / 0.171407 s | 미실시 | 미측정 |

## 통제 microbenchmark

수정 전 값은 [`BASELINE_REPORT.md`](BASELINE_REPORT.md)와 raw aggregate에 있다. 동일한 Python/OS, 입력 bytes, fixture, repetition 수로 post 값을 측정한 뒤에만 row별 차이를 추가한다. live API와 mock은 비교하지 않는다.

| workload | 수정 전 p50/p95 | 수정 후 | 비교 조건 |
|---|---:|---:|---|
| 자연어 규칙 parser | 0.3374 / 1.0971 ms | 미실시 | 같은 phrase/case 200회 |
| metadata normalization | 0.8543 / 1.4070 ms | 미실시 | 같은 World Bank-shaped metadata fixture 100회 |
| in-memory discovery search | 1.5814 / 2.2518 ms | 미실시 | 같은 검색어·단일 record fixture 50회 |
| CSV parse | 0.0770 / 0.1740 ms | 미실시 | blank와 0을 포함하는 동일 bytes 100회 |
| World Bank JSON parse | 0.1994 / 0.5409 ms | 미실시 | 동일 fixture 100회 |
| BEA mock API | 0.1668 / 0.3565 ms | 미실시 | 동일 request/response mock 40회 |
| e-Stat mock API | 0.1616 / 0.2864 ms | 미실시 | 동일 request/response mock 40회 |

## 고정 World Bank fixture E2E

| 지표 | 수정 전 기준선 | 수정 후 | 차이/개선율 |
|---|---:|---:|---:|
| 반복 결과 | 30/30 complete; 30/30 raw hash/read-back/invariant 통과 | 미실시 | — |
| dispatcher wall p50 / p95 | 160.1129 / 176.1139 ms | 미실시 | 미측정 |
| collect stage p50 / p95 | 55.3370 / 67.1090 ms | 미실시 | 미측정 |
| validate stage p50 / p95 | 28.6340 / 32.0980 ms | 미실시 | 미측정 |
| read-back p50 / p95 | 6.2956 / 7.6365 ms | 미실시 | 미측정 |
| mock calls/response bytes per run | 1 / 810 bytes | 미실시 | 통제 fixture 값 |
| live network | 0 request | 미실시 | — |

E2E raw sample 파일은 [`reports/performance_workflow_e2e_2026-10-25.json`](../../../reports/performance_workflow_e2e_2026-10-25.json)이다. 최초 tracemalloc-on 실험은 measurement overhead가 확인되어 제외했다.

## Iteration 21 — 새 fingerprint 기준선 (after 비교 아님)

Iteration 21은 제품 성능 변경 전의 traceable recheck다. 기존 수정 전 값과 같은 코드·환경이 확인된 before/after 짝이 아니므로 개선율 계산에는 사용하지 않는다.

| run | code fingerprint | 반복 | dispatcher p50 / p95 (ms) | CPU p50 (ms) | read-back p50 (ms) | invariants |
|---|---|---:|---:|---:|---:|---|
| 1 | `f5d78372974f6f19bfd5df2ee9461a2cb029703956dd976dc95743a192d68b46` | 30 | 143.2193 / 183.3994 | 93.7500 | 5.6087 | 30/30, raw hash/missing/zero PASS, live 0 |
| 2 | 동일 | 30 | 150.7658 / 189.8372 | 109.3750 | 5.7197 | 30/30, raw hash/missing/zero PASS, live 0 |

원시 표본은 [`run 1`](../../../reports/iteration_21_baseline_run_1.json), [`run 2`](../../../reports/iteration_21_baseline_run_2.json)에 있다. Iteration 18/20에 동등 code fingerprint가 없고, RSS/native memory는 계속 미측정이다. 이 수치로 회귀, 최적화 또는 타 기관 성능을 주장하지 않는다.

### Iteration 20 runtime recheck — no code change

The fixed fixture was rerun twice, 30 repetitions each, before any source performance edit. Dispatcher p50/p95 were 281.4949/340.0700 ms and 286.2774/350.5180 ms. All 60 runs completed, verified raw hashes, preserved the missing and zero observations, and used zero live HTTP requests. The same named scenario in Gate I reported 160.1129/176.1139 ms. Since no workflow source change explains the cross-run shift and runtime conditions were not fully controlled, these numbers are preserved as a recheck rather than an optimization or regression comparison. See [`reports/iteration_20_baseline_recheck.json`](../../../reports/iteration_20_baseline_recheck.json) and [`docs/developer/history/ITERATION_20_REPORT.md`](../history/ITERATION_20_REPORT.md).

### 다음 전후 측정 규약

- 변경 전 sample IDs, source revision, seed, payload checksum을 보존하고 동일 표본을 after에 다시 사용한다.
- randomized soak는 새로운 seed의 탐색용과 기존 seed replay의 전후 비교를 분리한다.
- 단계별 wall/CPU/memory/API counters와 정확성·복구 결과를 함께 비교한다.
- 정확성 필수항목이 하나라도 나빠지면 속도 이득을 통과로 처리하지 않는다.
- 실제 기관 비교는 같은 기관·endpoint·query·언어에 한한다. 기관별 p95가 다른 기관 평균에 묻히지 않게 보고한다.
