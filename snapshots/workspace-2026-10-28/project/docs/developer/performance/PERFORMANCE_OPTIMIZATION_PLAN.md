# 성능·메모리 최적화 운영 계획

**기준일:** 2026-10-25
**운영 주기와 책임:** [docs/operator/OPERATING_PLAN.md](../../operator/OPERATING_PLAN.md)
**수정 전 측정과 실제 결과:** [BASELINE_REPORT.md](BASELINE_REPORT.md), [BENCHMARK_COMPARISON.md](BENCHMARK_COMPARISON.md), [OPTIMIZATION_LOG.md](OPTIMIZATION_LOG.md)

## 목표

공통 Python 엔진의 메모리·시간·요청량을 줄이되 데이터 정확성, 출처 추적, raw 보존, 중단 후 복구를 지킵니다. 측정에서 반복되는 병목이 확인됐을 때만 코드를 바꿉니다. 측정 오차와 구분되지 않는 개선은 적용하지 않습니다.

현재 저장소에 외부 LLM 호출 엔진이 연결되어 있지 않으므로 토큰·LLM 지연·LLM 비용은 측정하지 않습니다. 사람의 피드백 처리 시간은 실제 운영을 시작한 뒤에만 기록합니다.

## 현재 기준

- 21개 기관 중 API 문서 확인 15개, 공식 명세 미확인 6개, 공식 API 미제공 확인 0개.
- “문서 확인”은 adapter·dataset·인증·live 수집 성공이 아닙니다.
- 확인된 live 수집 범위는 World Bank USA/WDI/GDP 한 경로입니다.
- BEA·e-Stat JSON client는 mock 검증이며 workflow/live 검증이 아닙니다.
- Iteration 20 fixture E2E는 30회씩 두 번 실행되어 각 run 30/30 완료했고 raw hash·missing/zero invariant를 지켰습니다. run 간 수치 차이가 과거 Gate I 결과와 커서 코드 최적화 효과는 입증되지 않았습니다. 공통 workflow/storage 코드는 이 근거로 바꾸지 않았습니다.
- Iteration 21은 동일한 source/test/fixture/script fingerprint와 환경 식별을 기록하며 고정 E2E를 두 번, 각 30회 재현했습니다. dispatcher p50/p95는 143.2193/183.3994ms 및 150.7658/189.8372ms입니다. 이 수치는 미래 측정용 baseline이며 Iteration 18/20과 동등 조건 before/after가 아닙니다.
- 수정 전 전체 검사 기준은 당시 625 passed, 1 skipped였으며, suite peak RSS는 측정되지 않았습니다. 전 기관 속도나 live 품질을 대표하지 않습니다.

세부 결과는 [Iteration 20 보고서](../history/ITERATION_20_REPORT.md)와 reports/iteration_20_baseline_recheck.json을 확인합니다.

## 측정 단위

엔진별 단독 측정과 실제 workflow 조합을 나눕니다. connector가 미구현인 기관은 live 지표를 만들지 않고 공식 문서/fixture 범위만 보고합니다.

| 측정 대상 | 기록 항목 |
|---|---|
| 응답시간 | 단계별 wall time, 전체 wall time, p50/p95, cold/warm 구분 |
| CPU·메모리 | process CPU, peak RSS, Python allocation/peak, GC 영향 가능성 |
| API 효율 | 요청 수, 중복 비율, 응답 바이트, pagination, retry, cache hit/miss |
| 정확성 | source/dataset/series, 행·기간, 단위·주기·차원, raw hash, missing/zero, revision |
| 안정성 | 성공/부분 성공, 실패 분류, 재시도·재개 횟수와 시간, 저장 read-back |
| 운영 | 사람의 분류·검토시간, 실제 자동화가 연결된 후의 도구/LLM 호출 비용 |

자료 수집과 파싱, 정규화, 검증, SQLite 저장·조회, workflow overhead를 가능한 만큼 나눕니다. 계측기 추가에 따른 오버헤드는 별도로 기록합니다.

## 통제된 before/after

1. OS/Python/의존성/코드 기준, dataset fixture, seed, 반복 순서, 캐시 상태, 동시 작업을 기록합니다.
2. 먼저 최소 3회 예비 측정으로 런타임 변동을 확인합니다.
3. 안정된 통제 시나리오는 baseline과 변경 후보를 각각 같은 조건으로 30회 반복합니다. 차이가 들쭉날쭉하면 반복을 늘리거나 결과를 “판정 불가”로 남깁니다.
4. 전체 workflow와 각 단계 수치를 함께 보며, profiler/tracer가 켜진 결과와 일반 실행을 분리합니다.
5. 성능 수치뿐 아니라 동일한 데이터 정확성·저장·복구 invariant를 검증합니다.
6. 실 API가 필요한 측정은 fixture 결과에 합산하지 않고 기관·시각·요청량·응답 변경을 따로 기록합니다.

초기에는 첫 두 격주 주기의 run 간 분산을 측정해 최소 수용효과 기준을 정합니다. 변동 폭보다 작은 성능 차이는 개선으로 선언하지 않습니다. 명확한 변화가 없으면 기준선으로 유지합니다.

## 무작위 데이터 검증

- 무작위 선택은 seed, 기관, API 계열, format, dataset/series, 주기, 기간 크기, 언어, revision, run ID를 기록해 재현 가능해야 합니다.
- 기관별 층화 표본과 미검증 목록을 함께 유지합니다. 같은 데이터셋의 인접 series만 반복 추출하지 않도록 holdout을 둡니다.
- Fixture replay는 결정적 offline 시험에 사용하고, live 재호출은 기관별 안전 budget에 맞춰 선택합니다.
- 데이터셋 간 비교는 단위·주기·정의가 확인된 경우만 수행합니다. 라벨 유사성만으로 동등하다고 보지 않습니다.
- 새 응답은 raw/manifest/hash와 함께 새 run으로 저장합니다. revision 변화는 parser regression과 분리합니다.

## 채택할 병목 우선순위

| 우선 | 후보 | 수정 전 확인 | 주된 위험 |
|---:|---|---|---|
| 1 | API/metadata 중복 요청 | 같은 run의 endpoint·요청 fingerprint·cache hit/miss | 오래된 메타데이터 재사용, revision 누락 |
| 2 | 큰 응답의 메모리 점유 | peak RSS, Python allocation, 파일 크기, chunk 크기 | 부분 데이터 누락, pagination 경계 오류 |
| 3 | 파싱/정규화 반복 비용 | 단계별 profile과 값/hash 비교 | 숫자·단위·결측 표기 변화 |
| 4 | SQLite transaction/connect 빈도 | 호출 수와 반복시간; rollback/atomicity fixture | 이력 원자성·idempotency·재개 깨짐 |
| 5 | retry/cache 정책 | 호출·지연·429·timeout fixture | 서버 부담, stale 결과, 재시도 폭증 |

Iteration 20은 SQLite 연결/transaction을 아직 변경할 근거를 확보하지 못했습니다. 실제 측정 전에는 이를 “확정 병목”이라고 부르지 않습니다. 후보의 예상 효과·정확성 위험·난이도와 적용 순서는 BOTTLENECK_ANALYSIS.md에서 업데이트합니다.

## 성능 변경 수용 조건

아래를 모두 충족해야 합니다.

- 통제 조건에서 효과가 반복 재현되고 측정 변동보다 큽니다.
- 요구된 성능 지표가 개선됩니다. 다른 지표의 퇴행도 함께 제시합니다.
- raw hash·원출처·시점·단위·주기·차원·revision 보존에 차이가 없습니다.
- 결측, 비공개, 해당 없음, 0을 구별하고 통계 행/기간 완전성을 유지합니다.
- 실패·부분 응답·취소·재시도·재개와 저장 read-back 검사가 통과합니다.
- 영향받는 모든 source fixture 및 관련 회귀 검사에 통과합니다.
- 코드 변경, 명령, 측정 원시값, 결과, 제한과 검토 상태를 최적화 로그에 남깁니다.

정확성 invariant가 하나라도 실패하면 수치가 빨라져도 채택하지 않습니다. 측정된 후보가 없거나 개선이 재현되지 않으면 코드는 그대로 둡니다.

## 기관별·공통 범위 구분

모든 connector는 공통 입력/출처/오류 계약과 공통 conformance suite를 사용합니다. 각 기관 문서에는 API 계열·버전, endpoint, auth, 식별자, pagination, limit, 응답 필드, 언어, revision/vintage, 라이선스, source fixture와 검증 범위를 둡니다. 기관 고유 예외를 공통 core에 조건문으로 확장하지 않습니다.

API 문서가 확인된 기관과 문서가 확인되지 않은 기관은 카탈로그 기준으로 관리합니다. 미확인 기관은 endpoint를 추정하지 않습니다. API 우선 경로가 대상 표에 없다는 사실이 확인되면 공식 파일/표를 별도의 보조 접근 경로로 평가합니다. 기관의 실제 값 다운로드 시험은 해당 source gate 뒤에 진행합니다.

## 운영 연결

- 매주 오류·사람 피드백을 먼저 재현하고, 원인이 공통 엔진인지 기관 adapter인지 구분합니다.
- 2주마다 대표 workload의 memory/performance 기준을 재측정하고, 근거가 있는 최소 변경만 적용합니다.
- 기관 추가는 수요 기반으로 언제든 offline 작업을 시작할 수 있으며, live는 공통 platform gate + source gate 이후에만 실행합니다.
- Canary → 2시간 → 6시간 이상의 단계는 서비스 한도와 사용자 승인에 따라 확장합니다. 여기 적힌 시간은 운영 계획이지 기관의 공식 API 제한이 아닙니다.

주기와 실제 책임은 [운영 계획](../../operator/OPERATING_PLAN.md), 회차 보고서와 원시 benchmark를 기준으로 합니다.
