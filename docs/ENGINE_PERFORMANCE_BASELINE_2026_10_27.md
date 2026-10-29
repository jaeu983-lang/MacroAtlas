# 엔진 성능 계측 오프라인 기준선 — 2026-10-27

## 측정 범위

단일 Linux x86_64 / Python 3.12.14 환경에서 구현 commit `bef7315b1ec95e63b1c23940e255e3857eb1c959`로 임시 프로젝트를 만들고 표본을 모았다. 실제 네트워크 요청은 0건이다. World Bank·BOJ의 transport double은 기존 테스트 fixture를 돌려 사용했고, tabular parser는 작은 TSV를 보관 입력으로 반복 실행했다. CSV exporter는 이 fixture 실행으로 생성한 완료 task를 다시 읽었다. KnowledgeStore는 고정 시각의 빈 feedback index에서 첫 miss와 warm cache hit를 측정했다.

전체 표본은 161개다: World Bank stage 40개, BOJ stage 40개, tabular stage 20개, stored CSV export 40개, knowledge miss 1개와 hit 20개. evidence class와 execution scope를 보존했으며, `macro-perf report`가 출력한 그룹의 p50/p95만 아래에 옮겼다. 20개 미만 그룹의 p95는 표시하지 않는다.

## 반복 표본

모든 시간은 milliseconds이며 소수 셋째 자리로 반올림했다. phase p50은 stage p50 안에서 측정한 경계 시간이다. phase들이 inclusive 경계로 겹칠 수 있으므로 서로 더해 stage 시간으로 해석하지 않는다.

| scope / engine / stage | evidence / cache | n | stage p50 | stage p95 | 측정된 phase p50 |
|---|---|---:|---:|---:|---|
| `orchestrator_stage` / `worldbank_collect_audit` / `collect` | fixture | 20 | 2.054 | 2.366 | parse 0.049, raw_write 0.333, SQLite 1.002 |
| `orchestrator_stage` / `worldbank_validate` / `validate` | fixture | 20 | 1.386 | 1.593 | parse 0.051, quality 0.063, SQLite 0.785 |
| `orchestrator_stage` / `boj_metadata` / `metadata` | fixture | 20 | 1.435 | 2.113 | parse 0.015, raw_write 1.328 |
| `orchestrator_stage` / `boj_observations` / `collect` | fixture | 20 | 1.579 | 2.182 | parse 0.026, quality 0.040, raw_write 1.292 |
| `orchestrator_stage` / `tabular_file` / `parse` | stored | 20 | 0.827 | 1.034 | parse 0.035, raw_write 0.517 |
| `csv_export` / `csv_export` / `export` | stored | 40 | 1.863 | 2.114 | parse 0.041, quality 0.057, SQLite 0.105, export 0.178 |
| `knowledge_lookup` / `knowledge` / `query` | stored / hit | 20 | 0.260 | 0.318 | SQLite 0.239 |
| `knowledge_lookup` / `knowledge` / `query` | stored / miss | 1 | 0.428 | 미확정 | SQLite 0.357 |

fixture transport가 수행한 로컬 응답 처리에는 `network` phase를 만들지 않았다. 따라서 위 결과는 network latency, 실사용 데이터 크기, 다른 OS나 실제 catalog 규모를 설명하지 않는다. `CSV export`는 40개 sample로 p95 조건을 충족했지만 task 종류·fixture 규모가 작아 production exporter의 처리량 기준선은 아니다.

## 판단

이 작은 fixture에서 World Bank stage는 SQLite 경계, BOJ stage는 raw 보존 경계가 상대적으로 크게 보였다. 각 stage 전체의 p50도 0.827–2.054 ms이고 공식 production 목표 시간이나 지연 허용치가 아직 정해지지 않아 이 수치만으로 저장 계층 최적화를 정당화할 수 없다. exporter는 측정된 네 phase 합보다 전체 시간이 커서 hash/manifest 검증 및 일반 Python 경로가 남지만, 이 역시 작은 fixture 40건으로 병목 확정에 부족하다.

따라서 이 기준선 작업에서는 catalog cache, task JSON, provider adapter 또는 SQLite 쓰기를 최적화하지 않았다. 향후 승인된 자연 API 요청은 network와 local phase를 분리해 별도 evidence class로 쌓고, 보존 task 및 더 큰 fixture의 p50/p95/처리량을 비교한 뒤 큰 비용이 재현될 때에만 최적화 후보를 둔다. 대용량 worker의 qualification/production 시간·RSS는 기존 기록으로 유지하며 이 표와 합산하지 않는다.

## Typed XLSX 후속 기준선 — 2026-10-29

PR #91에서 추가된 원자료·비교 XLSX 경로에는 성능 telemetry가 없었다. PR #92 후보에서는 hash 검증, freshness 평가, workbook 생성·게시를 계측하고 검증된 label·시간·byte/row/column count만 별도 `performance.sqlite`에 쓴다. `docs/evidence/xlsx_fixture_performance_20261029.json`은 commit `c167139246aa31aa5db1088eeab440d098e9279d`의 코드로 임시 프로젝트에서 생성한 fixture-only 결과다. 저장 사용자 데이터와 분리했고 API 호출은 하지 않았다.

각 경로를 20회 실행해 그룹별 p95 표본 조건을 채웠다. 결과 시간은 milliseconds이며 fixture 규모가 작다.

| engine / workload | n | 입력 median rows/bytes | 출력 median rows/bytes | total p50/p95 | 큰 하위시간 p50/p95 |
|---|---:|---:|---:|---:|---|
| `typed_xlsx` raw series | 20 | 2 / 1,984 | 2 / 7,855 | 4.294 / 6.147 | export 3.543 / 5.305 |
| `series_compare_xlsx` | 20 | 4 / 4,789 | 4 / 12,853 | 15.421 / 16.619 | export 13.096 / 14.455 |

Comparison fixture에서는 workbook 생성·게시가 가장 큰 계측 구간이었다. 이 자료는 2개 연도·2개 series fixture에서 비교 workbook 생성 비용이 raw export보다 큰 것을 보여줄 뿐, 실제 자료 크기나 production 병목을 증명하지 않는다. p95 latency/throughput 예산을 실행 전에 정하지 않았으므로 성능 gate 통과나 최적화 필요성을 주장하지 않는다. 재현 가능한 비용 한도를 정하려면 더 큰 fixture와 허용 예산이 필요하다.

같은 시점에 기존 프로젝트의 `macro-perf report`를 읽기 전용으로 확인한 결과는 별도 `live_api` 표본이다. 4개 그룹에 각 2개씩 총 8개 sample이 있어 p95는 모두 `INSUFFICIENT_SAMPLE`이다. `worldbank_series` collect의 stage p50은 11.727 s였고 network phase p50 11.726 s가 대부분을 차지했다; parse 0.113 ms, quality 0.162 ms, raw write 0.912 ms였다. `boj_observations_range` collect p50은 1.423 s, network phase 1.413 s였다. 해당 sample들의 `code_sha`는 `unknown`이므로 이를 현재 commit의 성능이나 최적화 증거로 묶지 않는다. 이번 점검에서 provider에 새 요청을 보내지 않았으며, n=2만으로 병목 일반화·기관 전체 latency·원격 서비스 책임을 판단하지 않는다. 이는 fixture XLSX 표와 합산하지 않은 기존 live sample 관찰이다.

### 후속 BLS 진단 표본 — Iteration 42, 2026-10-29

명시 요청된 BLS metadata 확인 요청은 별도 `live_api` class로 저장했다. 단일 API stage 총시간은 473.079 ms, network 469.993 ms, parse 0.233 ms, quality 0.258 ms, raw write 0.952 ms였다. 같은 typed artifact의 로컬 raw XLSX export는 별도 `stored` class로 14.880 ms였다. 두 표본 모두 n=1이고 앞의 fixture·기존 provider 표본과 합치지 않으며 p50/p95·production 기준선·최적화 판정을 만들지 않는다. value-free hash와 phase 기록은 [Iteration 42 evidence](evidence/iteration_42_bls_live_metadata_freshness_performance_20261029.json)에 있다.
