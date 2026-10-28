# MacroAtlas 성능 기준선 보고서

**측정일:** 2026-10-25 UTC
**Git 기준점:** `778ab412d3076aad4a37d6f3140b6ced54b56d26`
**원시 집계:** [`reports/performance_baseline_2026-10-25.json`](../../../reports/performance_baseline_2026-10-25.json)
**재현 스크립트:** [`scripts/measure_performance_baseline.py`](../../../scripts/measure_performance_baseline.py), [`scripts/measure_test_suite.py`](../../../scripts/measure_test_suite.py)

## 기준선 조건

- Windows 11 build 26200, Python 3.12.14, AMD64, Ruff 0.17.2.
- Offline fixture/mock만 사용. live HTTP 요청 0건, 기관 데이터 전송 0 bytes.
- 기준점 커밋은 확인했지만 worktree는 이미 dirty였고 시작 시 Git status 86건이었다. `src`, `tests`, `tests/fixtures`, `pyproject.toml`의 SHA256 fingerprint는 `14a0a465bf91d80b4f80ab72f4ef10bb9baf11cdabfb09bf749e33e2cf1da0de`다. 기존 변경을 baseline 전 코드로 오인하지 않는다.
- Python에서 이 환경의 기본 import 경로가 다른 OneDrive의 MacroAtlas checkout을 가리켜 첫 pytest 수집이 12개 모듈에서 실패했다. 이 실패는 제품 회귀가 아니라 잘못된 checkout import였다. 실행 스크립트에서 현재 repo의 `src`/`tests`를 우선하도록 수정해 올바른 worktree에서 재실행했다.

## 전체 로컬 테스트 — 같은 측정 스크립트 3회

`python scripts/measure_test_suite.py`는 pytest call duration을 모듈별로 수집한다. 한 번은 suite를 통과했으나 별도의 일반 CLI 실행이 82.96초를 보여, 그 값은 실행 경로가 달라 반복 표본에는 합치지 않았다.

| 반복 | 수집 | 통과/실패/skip | 전체 wall (초) | process CPU (초) | 개별 test call p50 / p95 (초) |
|---|---:|---:|---:|---:|---:|
| 1 | 626 | 625 / 0 / 1 | 36.7231 | 25.0156 | 0.003158 / 0.177055 |
| 2 | 626 | 625 / 0 / 1 | 37.3573 | 25.2500 | 0.002741 / 0.166413 |
| 3 | 626 | 625 / 0 / 1 | 36.7677 | 26.4844 | 0.003292 / 0.171407 |
| 요약 | — | 모든 반복 동일 | wall p50 **36.7677**, p95 **37.3573** | CPU p50 **25.2500**, p95 **26.4844** | call p50 중앙값 **0.003158**, call p95 중앙값 **0.171407** |

반복이 3회뿐이라 run-level p95는 표본 최댓값을 뜻한다. 이는 로컬 fixture/mock suite의 기준선이며 실제 사용자 요청 처리시간이 아니다. suite RSS는 샌드박스 프로세스 API가 대조 작업과 구분되는 신뢰 가능한 결과를 주지 않아 미측정이다.

가장 많은 누적 test call 시간을 가진 모듈은 Gate A, series discovery, orchestration, workflow, World Bank request tests였다. 이는 테스트 코드 실행시간의 분포이며, 제품 경로 병목으로 단정할 수 없다. 별도 profiling과 실제 workload가 필요하다.

## 엔진 microbenchmark — 단일 통제 실행

모든 행은 fixture/mock 입력이며 각 측정 함수는 표기한 횟수만큼 반복했다. 표의 wall은 각 호출 샘플 분포이고 CPU는 Windows Python `process_time` 누적값이다. Python allocation은 `tracemalloc` peak이며 OS RSS/SQLite native memory가 아니다.

| 사례 | n | wall p50 / p95 / max (ms) | CPU 합계 (초) | Python allocation peak (bytes) |
|---|---:|---:|---:|---:|
| 자연어 규칙 파서 | 200 | 0.3374 / 1.0971 / 10.3261 | 0.109375 | 52,995 |
| World Bank 형태 metadata 정규화 | 100 | 0.8543 / 1.4070 / 2.9938 | 0.078125 | 88,257 |
| 메모리 내 series discovery fixture 검색 | 50 | 1.5814 / 2.2518 / 2.8173 | 0.093750 | 128,853 |
| CSV parse, blank/0 보존 | 100 | 0.0770 / 0.1740 / 1.4774 | 0.000000* | 44,721 |
| World Bank JSON fixture parse | 100 | 0.1994 / 0.5409 / 2.3229 | 0.031250 | 15,242 |
| BEA dataset-list mock API client | 40 | 0.1668 / 0.3565 / 0.5653 | 0.015625 | 6,330 |
| e-Stat table-list mock API client | 40 | 0.1616 / 0.2864 / 0.7259 | 0.000000* | 5,239 |

`*` Windows process CPU clock의 분해능 때문에 작은 누적값이 0.000000으로 반올림될 수 있다. CPU 0을 실제 CPU 사용 0으로 해석하지 않는다. microbenchmark는 워밍업 구간이 별도 정의되지 않았고 한 프로세스의 단일 batch이므로 재현 시 반복 실행으로 분산을 확인해야 한다.

### Mock API 호출·바이트

| 기관 | 총 mock call | 고유 request fingerprint | 같은 요청 반복 | query 문자열 bytes 합계 | response body bytes 합계 | live 요청 |
|---|---:|---:|---:|---:|---:|---:|
| BEA | 40 | 1 | 39 | 3,360 | 2,360 | 0 |
| e-Stat | 40 | 1 | 39 | 1,960 | 2,080 | 0 |

반복은 측정 스크립트가 같은 요청을 의도적으로 40회 주입한 결과다. 실제 MacroAtlas workload의 중복 비율로 해석하면 안 된다. bytes는 mock 파라미터 인코딩과 fixture body 길이만 합산했으며 HTTP framing, TLS, live 전송량은 측정하지 않았다.

## 기존 기록과 경계

- Iteration 12의 합성 SQLite knowledge 검색 기록은 10,002건에서 cold p95 13.793ms / warm p95 5.944ms라고 보고한다. 이 benchmark는 다른 workload와 이전 시점 결과이므로 이번 microbenchmark와 합치지 않는다.
- 이전 Iteration 16 보고서의 전체 pytest는 625 passed/1 skipped, 38.82초다. 현재 같은 harness 3회 결과는 36.72~37.36초다. 이 차이는 비교 가능한 수정 전후 결과가 아니며, 코드 개선율을 계산하지 않는다.
- natural-language parsing은 현재 규칙 파서 fixture다. LLM 응답 시간/토큰, 에이전트 tool-call 수, 사람 승인 시간은 저장소에 계측 코드가 없어 미측정이다.
- 기관 API는 전부 mock 또는 fixture다. live API latency, rate-limit, live response bytes, 실제 dataset completeness/quality는 미검증이다.

## 고정 World Bank workflow E2E fixture — 30회

`python scripts/benchmark_workflow_e2e.py`는 이미 있는 구조화 요청→확인→mock 수집→검증→SQLite 저장/read-back 경로를 새 격리 디렉터리에서 30회 실행한다. 자연어 agent나 live API는 포함하지 않는다. 시간 재실행에서는 `tracemalloc`을 꺼 계측 간섭을 줄였다.

| 측정 구간 | p50 (ms) | p95 (ms) | max (ms) |
|---|---:|---:|---:|
| workflow 준비 | 24.4676 | 29.7148 | 33.4152 |
| dispatcher 전체 | 160.1129 | 176.1139 | 236.6913 |
| SQLite/raw read-back | 6.2956 | 7.6365 | 18.4157 |
| collect stage UTC timestamp 차이 | 55.3370 | 67.1090 | 95.2120 |
| validate stage UTC timestamp 차이 | 28.6340 | 32.0980 | 36.6320 |
| dispatcher process CPU | 109.3750 | 125.0000 | 140.6250 |

30회 모두 완료됐고 각 표본은 mock API 1회, query string 57 bytes, mock response 810 bytes, 관측치 3개를 처리했다. raw response hash가 read-back에서 일치했고 값은 `[123.5, null, 0]`, 상태는 `[reported, missing, reported]`로 보존됐다. live HTTP 0회다. CPU 표본은 Windows timer resolution 때문에 15.625ms 단위로 양자화된다. SQLite native memory/RSS는 측정하지 않았다. 전체 30개 raw sample은 [`reports/performance_workflow_e2e_2026-10-25.json`](../../../reports/performance_workflow_e2e_2026-10-25.json)에 있다.

별도 cProfile 진단은 `HistoryStore.transaction` 780회, `_connect` 1,380회, SQLite `commit` 390회를 보였다. profile 누적시간은 transaction 2.532초, connect 1.685초, commit 1.470초였지만 profiler 시간은 wall latency와 직접 비교하지 않았다. 이는 connection/transaction 경로를 더 분석할 **후보**이지, 아직 수정 후 성능 향상을 입증한 결과는 아니다. 최초 tracemalloc-on 실행은 timing overhead 때문에 제외했으며, 표에는 저장소 내부 격리 디렉터리에서 tracing을 끄고 다시 측정한 30개 표본만 포함했다.

### Iteration 21 재현성 보강 — 새 기준선, 최적화 아님

Iteration 21에서 같은 checkout/code fingerprint로 독립 benchmark를 두 번 실행하고 sample-level JSON을 보존했다. Windows 11, Python 3.12.14, AMD64, 12 logical CPUs에서 dispatcher p50/p95는 run 1이 143.2193/183.3994 ms, run 2가 150.7658/189.8372 ms였다. Dispatcher CPU p50은 93.7500/109.3750 ms, read-back p50은 5.6087/5.7197 ms다.

두 run은 같은 Git HEAD와 fingerprint를 기록했고, 각각 30/30 완료, mock request 1회/sample, raw hash 일치, missing·zero 보존, live HTTP 0이었다. 세부 원시값은 [`run 1`](../../../reports/iteration_21_baseline_run_1.json), [`run 2`](../../../reports/iteration_21_baseline_run_2.json), 요약과 한계는 [Iteration 21 report](../history/ITERATION_21_REPORT.md)에서 확인한다.

Iteration 18/20의 결과에는 동일한 code fingerprint가 없으므로 과거와 같은 코드/환경이었다고 추정하거나 개선율을 내지 않는다. 현재 결과도 한 쌍의 run뿐이라 runtime 분산의 충분한 기준으로 확정하지 않는다. Process RSS, Python allocation, native SQLite memory는 여전히 미측정이다.
