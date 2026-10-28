# MacroAtlas 병목 후보 및 개선 우선순위

**분석일:** 2026-10-25
**전제:** 측정된 병목, 구조적 연결 결손, 아직 증거가 없는 가설을 구분한다. 예상 효과를 숫자로 만들지 않는다.

## 확인된 문제와 후보

| 우선순위 | 관찰 | 상태 | 가능한 효과 | 정확성/안정성 위험 | 구현 난이도 | 다음 조치 |
|---|---|---|---|---|---|---|
| P0 | Python 기본 import 경로가 다른 OneDrive checkout을 우선해 테스트 수집이 12개 모듈에서 실패했다. local `src`/`tests` 우선으로 suite를 재실행하자 통과했다. | 재현됨, 환경/실행 안정성 문제 | 잘못된 코드 테스트·측정 방지. 코드 속도 향상은 측정하지 않음 | repo 경로를 고정해도 사용자의 다른 실행방식이 남을 수 있음 | 낮음 | 측정 스크립트는 자기 checkout을 우선. 프로젝트 실행 문서에 환경 검증 단계 추가 검토 |
| P0 | API 상태 레지스트리는 14개이며 초기 카탈로그는 21개다. BEA/e-Stat mock client는 workflow와 연결되지 않았다. | 코드/문서에서 확인 | 구현 완료·성능·정확성 주장을 정확히 분리 | 연결을 급히 하면 provider 별 조건·인증·의미가 core로 새어 들어갈 수 있음 | 중간~높음 | 공통 pipeline 계측과 기관별 계약 후 source 단위 연결 |
| P0 | 전체 통합 작업의 stage telemetry, live 요청 수/중복/bytes, 저장 read-back을 일관된 결과 객체로 모으는 기준선이 없다. | 현재 구현/측정에서 확인되지 않음 | 다음 병목을 단계별로 찾고 오류 재개 비용을 계산 가능 | 로그에 secret/query credential을 기록할 위험 | 중간 | secret-redacted run/stage ID와 숫자 counter만 남기는 telemetry contract 설계 |
| P1 | test call 누적시간이 Gate A와 series discovery 중심이다. | 이번 local test suite에서 측정됨. 제품 runtime 병목은 아님 | 검증 반복을 최적화하거나 느린 경로를 추가 profiling할 수 있음 | 테스트를 제거/약화하면 회귀 검출력 저하 | 낮음~중간 | slow test별 setup/call 분리; 병목인 setup만 개선하고 assertion 유지 |
| P1 | mock API benchmark는 같은 요청을 40회 넣어 39개 중복을 관찰했다. | 테스트 harness의 의도된 반복이며 실제 호출 중복 아님 | metadata lookup dedupe/cache 후보를 비교할 수 있음 | observations를 무차별 캐시하면 revision·조건·언어가 섞일 수 있음 | 중간 | 실제 discovery trace에서 반복률 먼저 측정; metadata만 version/ETag/TTL 기반 검토 |
| P1 | discovery/metadata를 한 요청마다 반복 읽는 비용, parsing 대용량 메모리, API pagination 비용은 현 microbenchmark로 판단 불가 | 미측정 가설 | 실제 hot path에 해당하면 비용 감소 가능 | premature caching/streaming 변경이 값 손실·stale metadata를 만들 수 있음 | 중간~높음 | 크기별 대표 fixture와 통제 response replay를 추가하고 측정 후 하나씩 적용 |
| P1 | 랜덤 데이터셋 다양성과 live 오류·복구 증거가 없다. | live 미실행 | 드물고 비인접한 dataset/언어/페이지 예외 검출 | 과도한 API 호출, 약관/쿼터 위반, 언어 fallback에 따른 매핑 오류 | 높음 | 어댑터/문서/예산 Gate 이후 기관별 seeded soak |
| P2 | Python heap 외 native SQLite/process RSS는 현재 baseline에 없다. Codex sandbox process 통계는 2초 sleep 대조군과 구분되지 않았다. | 계측 제한 확인 | 실제 메모리 leak/확장성 식별에 필요 | 신뢰할 수 없는 RSS를 숫자로 공표하는 위험 | 중간 | 허용된 별도 process profiler를 검증한 뒤 측정. 그 전에는 미측정 표기 |
| P2 | LLM token/cost, human review, agent tool-call 비용은 코드에 없다. | 구조적으로 미지원 | agent orchestration 개선 근거를 만들 수 있음 | 사용자 프롬프트/secret을 과도하게 logging할 위험 | 중간 | external agent adapter가 정해진 뒤 집계 수준·보존기간·redaction 결정 |

## 단순화 전에 지킬 경계

- 공통 pipeline은 입력 계약, 실행 추적, 원본 보존, 공통 validation, idempotent 저장, 오류/재개 정책을 소유한다.
- 기관 adapter는 공식 endpoint, 인증, dataset/series 식별, query encoding, pagination, 언어, revision, rate limits, provider-specific schema/error를 소유한다.
- SDMX 같은 protocol 공통 모듈은 transport/parser를 공유하되 IMF/BIS/ECB/Eurostat/OECD 등 기관별 dataflow, catalog, dimension order, version semantics를 한 규칙으로 단정하지 않는다.
- “코드 간소화”는 중복된 사실을 한 계약으로 이동하는 작업이다. 짧은 코드나 적은 클래스 자체를 목표로 하지 않으며, adapter 경계를 없애지 않는다.

## 권고 순서

1. Iteration 17 기준선과 기관·엔진 상태를 고정한다.
2. Iteration 18에서 사람이 재생할 대화 예시와 지원 중인 fixture E2E의 재현 baseline을 제공한다.
3. Iteration 19에서 전체 21개 API 상태와 실행 registry를 정합화했다.
4. Iteration 20에서 유지보수 Track M과 기관 확장 Track C를 병렬로 정의하고, E2E 고정 fixture를 재측정했다. 기존 Gate I timing과 현재 재측정 사이에 큰 차이가 있어 SQLite transaction/connect 변경을 보류했다.
5. Track M에서는 동일 seed/payload의 안정된 paired benchmark와 오류·복구 invariant를 확보한 뒤에만 공통 코드를 변경한다. Track C에서는 기관별 문서·adapter·fixture offline work를 독립적으로 진행한다.
6. 각 기관은 공통 platform gate와 해당 source gate가 모두 통과했을 때만 개별 live canary와 단계적 soak를 시작한다.

현재 데이터에서 CSV parse p95 0.174ms, World Bank JSON parse p95 0.541ms, mock API 호출 p95 0.357ms 이하였다는 점은 작은 입력 fixture만으로 제품 규모의 병목이 없다고 증명하지 않는다. 지금 확인된 가장 큰 개선 필요는 속도 코드보다 **통합 연결/계측/기관 coverage의 부족**이다.

## Iteration 21 후속 상태

고정 World Bank E2E를 같은 code fingerprint에서 30회씩 2 run 기록했으며, dispatcher p50/p95는 143.2193/183.3994 ms와 150.7658/189.8372 ms다. 각 표본과 environment/code identity가 보존되므로 이후 같은 조건을 맞출 수 있다. 단, 과거 Iteration 18/20은 fingerprint가 없어 이전 run들과 동등 비교는 여전히 불가능하다. 이 측정으로 새로운 제품 병목을 확정하거나 최적화 승인을 내리지 않는다. suite RSS·process RSS·native SQLite memory는 미측정이다.

## Iteration 18 E2E 보강 측정

- 저장소 내부 격리 디렉터리에서 다시 측정한 World Bank fixture 통합 경로의 dispatcher p50/p95는 160.1129/176.1139ms, collect stage는 55.337/67.109ms, validate stage는 28.634/32.098ms다. read-back p50/p95는 6.2956/7.6365ms다.
- 이 경로에서 mock API 1회가 관측치 3개를 반환한다. 30/30 run에서 raw hash와 missing/zero 상태가 유지됐다. 이 표본 크기/기관만으로 일반 기관 API의 성능을 일반화하지 않는다.
- cProfile은 transaction 780회, connect 1,380회, commit 390회를 기록했고, 누적시간은 각각 2.532초/1.685초/1.470초였다. profiler 시간은 실제 latency와 비교하지 않았다. 다음 공통 최적화는 transaction boundary와 state/recovery 불변식을 먼저 테스트하고, 같은 fixture benchmark의 before/after를 얻어야 한다.
- **현재 확인된 최적화 효과는 0개다.** E2E 측정은 후보를 더 잘 좁혔고 source behavior는 바꾸지 않았다. `SQLite connection/commit`을 즉시 합치면 atomic rollback·append-only audit·resume 동작이 달라질 수 있으므로 관련 failure tests 없이 단순화하지 않는다.
- Iteration 20에서 30회씩 2회 재측정했을 때 dispatcher p50/p95는 281.4949/340.0700ms 및 286.2774/350.5180ms였다. Gate I의 이전 값 160.1129/176.1139ms와 차이가 나므로 이 결과만으로 코드 개선/회귀를 단정하지 않는다. 현재 Track M의 첫 효율화 후보는 runtime 조건을 고정한 재측정이다.
