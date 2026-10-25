# MacroAtlas 최적화 기록

## Iteration 17 — 기준선·진단·장기 보정 계획

**상태:** 진단 문서/재현 계측 도구 완료. 제품 코드 성능 변경은 아직 없음.
**작업 범위:** 1~3단계(구조 확인, 수정 전 측정, 병목 후보·우선순위)와 randomized institution fine-tuning 계획.

### 변경 내용

- `scripts/measure_performance_baseline.py`: 오프라인 parser/discovery/metadata/BEA/e-Stat mock microbenchmark, wall p50/p95/max, Python allocation, mock 요청/응답 bytes·fingerprint 집계를 출력한다.
- `scripts/measure_test_suite.py`: 전체 pytest call duration, 모듈별 분포, wall/process CPU, 결과 수를 JSON으로 출력한다. 현재 checkout의 `src`와 `tests`를 import path 앞에 둔다.
- `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`: engine matrix, API-first/all institution design, per-institution docs versus common conformance policy, English-first/Japanese-Chinese fallback, random dataset and long soak sequence.
- `docs/developer/performance/BASELINE_REPORT.md`, `docs/developer/performance/BOTTLENECK_ANALYSIS.md`, `docs/developer/performance/BENCHMARK_COMPARISON.md`, `docs/developer/testing/REGRESSION_REPORT.md`, `reports/performance_baseline_2026-10-25.json`: 실측값과 한계, 후속 비교 기준.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `PROJECT_PLAN.md`, `docs/developer/history/DECISION_LOG.md`: Iteration 17 Gate H와 결정 추적.

### 효과

- 같은 test measurement harness 세 번: 625 passed/1 skipped 매번. wall median 36.7677초, p95 37.3573초.
- Parser/metadata/search/API mock 각 workload의 지연과 Python allocation 기준선 확보.
- 단일 source status 표가 A–H 14개이며 catalog의 21개 중 7개가 실행 레지스트리에 없음을 문서에서 확인.

### 성능 개선량

**계산하지 않음.** 수정 전후 코드 변경이 없고 같은 workload의 post-change 값이 없으므로 최적화율은 미측정이다. mock의 반복 호출은 harness가 의도한 것으로 실제 workload 중복률이 아니다.

### 다음 변경 전제

- Gate H를 사람 검토.
- Iteration 18은 사용자 대화 예시와 기존 workflow E2E 기준선을 제공했다. 공통 제품 코드 최적화는 후속 Iteration 19에서 오류/복구 검증 뒤에 판단한다.
- 실제 API 접속은 network authorization, 공식 제한, adapter fixture, credential 보호가 확인된 뒤 기관별 승인 범위에서 별도 측정.

## Iteration 20 — live 전 최적화 재평가와 병렬 workstream

**상태:** offline 기준선 재확인과 운영계획 수정 완료. 제품 source code 성능 변경 없음.

- `ImprovementAnalyzer`는 반복 오류·사용자 피드백·격리된 추론의 read-only 개선 후보를 만든다. 승인 없이 코드나 source contract를 수정하지 않으며 성능 optimizer가 아니다.
- 고정 World Bank fixture E2E를 각 30회씩 두 번 측정했다. dispatcher p50/p95는 281.4949/340.0700ms 및 286.2774/350.5180ms였다. 두 run 모두 30/30 완료, raw hash 확인, missing/zero 유지, live HTTP 0회였다.
- Gate I의 동일 명명 workload p50/p95 160.1129/176.1139ms와 큰 차이가 났다. 이번 작업에서 해당 workflow source를 바꾸지 않았으므로, uncontrolled cross-run 비교를 코드 최적화/회귀로 표시하지 않고 환경 민감성으로 보류했다.
- SQLite transaction/connect 후보를 더 줄이는 변경은 audit atomicity, rollback, retry/resume에 영향을 줄 수 있어 적용하지 않았다. 성능 수치가 안정되지 않아 현 회차에는 입증된 최적화 효과가 없다.
- 운영·유지보수 Track M과 기관 확장 Track C를 별도 병렬 workstream으로 정리했다. source-specific offline 작업은 병행 가능하며 live canary는 공통 platform gate와 기관별 source gate를 모두 통과한 기관부터 시작한다.
- 근거: `reports/iteration_20_baseline_recheck.json`, `docs/developer/history/WORKSTREAMS_AND_LIVE_READINESS.md`, `docs/developer/history/ITERATION_20_REPORT.md`.

## Iteration 21 — benchmark 재현성 기록 개선, 제품 최적화 없음

**상태:** Gate L PASS. 고정 World Bank fixture를 각 30회씩 독립 실행 2회; 제품 engine 코드 변경 및 성능 최적화는 없음.

- `scripts/benchmark_workflow_e2e.py`에 Git HEAD, source/test/fixture/script fingerprint, 환경/CPU 식별, raw SHA256, missing/zero 상태와 sample 번호 기록을 추가했다.
- 원시 표본·환경·invariant는 `reports/iteration_21_baseline_run_1.json`, `reports/iteration_21_baseline_run_2.json`에 보존했다.
- Dispatcher p50/p95는 143.2193/183.3994 ms와 150.7658/189.8372 ms였다. 둘 다 30/30 완료 및 live HTTP 0. 두 run 결과는 미래 재현을 위한 새 기준선이지 paired before/after 최적화 측정이 아니다.
- Iteration 18/20의 code fingerprint 부재로 과거와 코드 동등성은 미확인이다. RSS, Python allocation, native SQLite memory는 여전히 미측정이다.
- 첫 실행에서 계측 코드의 초기화 순서 오류를 발견해 같은 iteration 내 수정했다. 최종 두 실행의 모든 결과 invariant는 true였다.
- 상세: `docs/developer/history/ITERATION_21_REPORT.md`.

## Iteration 18 — 사람용 Q&A 시나리오와 대표 workflow E2E 계측

**상태:** 사람 테스트 파일과 offline benchmark 추가. 제품 코드 성능 최적화는 아직 없음.

- `docs/user/examples/HUMAN_CONVERSATION_TESTS.md`: 실제 사람이 재생할 8개 질문→응답→답변→후속 응답 사례, 기대 동작, 기록란을 제공. 현재 repo에는 자연어 agent/UI가 없다는 점을 첫머리에 표시한다.
- `scripts/benchmark_workflow_e2e.py`: 기존 World Bank fixture 경로를 매회 격리 저장소에서 실행하고 단계/dispatcher/read-back wall time, CPU quantization, mock request/body bytes 및 raw/normalized 불변식을 수집한다.
- `reports/performance_workflow_e2e_2026-10-25.json`: 30개 raw time samples와 요약 통계.
- E2E 결과: dispatcher p50/p95 160.1129/176.1139ms, read-back p50/p95 6.2956/7.6365ms; 30/30 hash 및 `[123.5, null, 0]` read-back 통과; live HTTP 0회.
- 별도 cProfile은 SQLite transaction/connect/commit 경로를 조사 후보로 좁혔지만 profiler 시간은 latency 비교에 사용하지 않았다. 아직 변경 전/후 성능 개선율은 없다.
- 최초 tracemalloc-on 실행은 tracing 영향을 고려해 제외했고, 정식 30회 timing run에서는 tracing을 껐다. E2E RSS/native SQLite memory는 계속 미측정이다.
