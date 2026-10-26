# 12회차 — 기관별 지식 조회와 조건부 재사용

## 최신 상태 — Gate D 통과 (2026-10-26)

후속 Orchestrator 연결과 반복 task 검증으로 Gate D를 통과 처리했다. 같은 기관·dataset의 accepted
`source_method` feedback을 사용자가 직접 선택하면 표시된 search stage를 건너뛰고 downstream stage에
범위·feedback ID·근거를 전달한다. 30회 local E2E 비교에서 stage 실행 수가 task당 2→1로 감소했다.
전체 근거와 수치는 문서 마지막 `Gate D Orchestrator integration` 절에 있다. 13회차는 시작하지 않았다.

아래 원래 보고는 Gate D 통합 전 상태를 기록한다. 당시 미통과 판정은 뒤의 후속 evidence로 대체한다.

날짜: 2026-10-26
초기 보고 상태: 제한 구현·검증 완료, **Gate D 미통과**. Gate C 통과 전 사용자의 후속 실행 지시로
순서를 예외 진행했으며 두 게이트의 판정은 변경하지 않았다.

## 구현한 범위

- [knowledge.py](../src/macro_data_platform/storage/knowledge.py)는 피드백 이력과 task JSON을 매
  조회마다 읽지 않는 institution-scoped SQLite projection을 제공한다. `feedback_current`의
  insert/update trigger가 갱신 queue를 채우고, `refresh()`만 호출당 최대 500건을 투영한다.
  조회 도중 변경이 대기 중이면 `NEEDS_REFRESH`를 반환한다. pending 상태·projection revision·후보는
  하나의 SQLite read snapshot에서 확인한다.
- 기관은 필수 범위다. 요청한 dataset/concept/classification axis/version과 정확히 일치하거나
  더 넓은 null scope만 반환한다. 요청 차원을 생략한 경우, 그 차원 값이 특정된 기록은 제외한다.
  유효 시점과 버전도 조회에 반영한다.
- 기본 결과는 accepted user instruction 및 공식 근거다. 공식 근거는 참조로만, inference는
  명시적으로 포함해도 `review_required`·`not_promoted`로 표시한다. 동일한 kind/category/정확
  범위의 상충 항목은 review-required다. 취소·편집·검토 상태 변경은 queue와 revision key로 캐시를
  무효화한다.
- `decide_reuse()`는 적용하지 않고 사람의 다음 선택만 제안한다. 과거 output preference가 있으면
  사용자의 확인을 받고, 없으면 새 출력 선택을 묻는다. 충돌 또는 부분 조회에서는 재사용을 막는다.
  현재 요청에 명시된 지시는 lookup 결과보다 우선한다.
- 조회는 후보 최대 500행과 truncation 판정용 1행, 반환 최대 50개, LRU 최대 64항목·직렬화 데이터
  최대 1 MB로 제한한다. index refresh는 별도 명시 호출이며 요청 query가 전체 rebuild를 하지 않는다.
- [test_knowledge.py](../tests/test_knowledge.py)는 기관·자료 범위 격리, explicit refresh와 청크
  상한, official/inference 경계, 유효 시점·버전, edit/withdrawal 및 캐시 무효화, 사용자 확인,
  충돌, 후보 상한/부분 결과를 검증한다.

## 성능 측정

환경: Linux x86_64, Python 3.12.14, SQLite 3.53.1. 각 크기에서 synthetic `feedback_current`
fixture를 일괄 입력해 SQLite projection 조회만 분리했고 30회씩 측정했다. Cold는 새
`KnowledgeStore`의 process-local cache miss를 뜻하며 OS page cache는 비우지 않았다. 메모리는
`tracemalloc`의 호출당 최대 Python 할당 증가분이며 SQLite native memory와 process RSS는 포함하지
않는다. 시간과 메모리는 별도 run에서 측정했다. 바이트는 조회된 SQLite field의 UTF-8 논리
크기로, 실제 디스크/page I/O가 아니다. 반환 상한은 20개, candidate scan 상한은 500개(상한
판정용 sentinel 1개 추가)였다. 시간은 크기별 30회, 메모리는 10회 측정했다.

| 투영 행 수 | Cache miss p50 / p95 | Cache hit p50 / p95 | 최대 Python 할당 증가 miss / hit | 실제 반환 후보 행 / 논리 byte | 결과 |
|---:|---:|---:|---:|---:|---|
| 100 | 1.332 / 1.594 ms | 0.368 / 0.497 ms | 167,636 / 52,820 bytes | 100 / 19,590 | 20개 반환, 결과 상한으로 `partial` |
| 1,000 | 3.694 / 3.943 ms | 0.375 / 0.475 ms | 797,490 / 53,083 bytes | 501 / 98,587 | 20개 반환, scan·결과 상한으로 `partial` |
| 5,000 | 3.621 / 3.895 ms | 0.383 / 0.470 ms | 797,490 / 53,083 bytes | 501 / 98,587 | 20개 반환, scan·결과 상한으로 `partial` |

세 경우 모두 반환된 행은 요청 기관·dataset·concept와 일치했고 relation expansion depth는 0이다.
100행 case는 요청 limit 20으로 인해 `partial`; 1,000/5,000행 case는 500 후보 scan cap과 결과
limit 모두에 걸렸다. `decide_reuse()`는 부분 목록에서 재사용 후보를 만들지 않는다. 이 수치는
특정 실행 환경과 synthetic 조회 workload에 대한 관찰값으로,
성능 목표 달성이나 실제 반복 task의 속도 향상을 보장하지 않는다.

## 초기 구현 당시 검증과 미완료 조건 (후속 Orchestrator 연결 전)

- 외부 API/네트워크를 사용하지 않았다. Benchmark fixture는 feedback API의 기록/검토 호출을
  재생하는 end-to-end 부하가 아니라 projection query 경로만 측정한다.
- 이 구현은 `Orchestrator`가 새 task나 retry를 계획할 때 호출되지 않는다. 따라서 동일 기관의
  반복 작업에서 실제로 탐색 단계가 줄었는지, task latency 또는 재시도 횟수가 개선됐는지는
  측정하지 않았다.
- 당시 **Gate D 미통과:** 실제 반복 task/retry 흐름 연결과 같은 기관의 end-to-end 효율 검증이 남았다.
  이 보고서는 D 통과나 13회차 시작을 승인하지 않는다. Gate C 역시 원자료 변경·durable resume
  증거가 부족해 계속 미통과다.

검증: 전체 pytest **574 passed in 4.18s**, Ruff 전체 검사 통과, `git diff --check` 통과.
구현·테스트·보고서는 commit `aab3c67`로 `origin/codex/gate-c-evidence-review`에 push했다.
실행 환경 publish는 하지 않았다.

## Gate D Orchestrator integration — 2026-10-26

### 연결 동작

- `KnowledgeStore.confirm_reuse()`는 task가 지정한 institution/category/scope 안에서만 조회하고,
  사용자가 전달한 하나의 `feedback_id`가 accepted `user_instruction`인지 확인한다. 미완료 조회,
  broad-scope 후보, 상충 기록, 추론, 미검토 기록은 선택 근거가 될 수 없다. knowledge index revision과
  pending queue를 저장 직전에 다시 확인해 조회 뒤 변경된 지식은 계획에 반영하지 않는다.
- `Orchestrator.plan_with_knowledge()`는 사용자가 명시한 현재 지시를 최우선으로 저장한다. 이전
  feedback을 사용할 때는 해당 category로 표시된 stage만 계획에서 제외하고, 선택한 feedback의
  institution, scope, revision, text, evidence refs를 task에 저장해 downstream `StageInput`으로
  전달한다. `KNOWLEDGE_REUSED` event에는 feedback ID와 생략 stage가 남는다. 이 context는 stage
  fingerprint에도 들어가므로 다른 지식 버전의 결과를 같은 것으로 재사용하지 않는다.
- 일반 `plan()`과 표식 없는 stage는 기존 동작을 유지한다. 잘못된 기관·범위·feedback 선택은 계획
  저장 전 거부한다. 데이터 자체를 자동 수정하거나 기관 간 공통 사실로 승격하지 않는다.

### Same-institution end-to-end efficiency

Local fixture workflow: 첫 BLS/CPI task가 `search`와 `collect`를 실행하고, `search` stage에 연결된
사용자 승인 `source_method`를 동일 institution/dataset 범위로 저장했다. 반복 task에서 사용자가 그
feedback ID를 명시 선택하자 `search`는 실행하지 않았고 `collect`가 전달된 `Official BLS API` 근거를
사용했다. 시나리오의 검색 관련성은 선택 feedback ID, 정확한 `bls`/`cpi` scope, 최종 source method가
일치하는지 확인했다. 다른 institution `census`에서 같은 feedback ID를 선택하면 planning이 거부됐다.

기준 환경: Linux x86_64, Python 3.12.14, SQLite 3.53.1. 각 처리군에서 `create → plan → run`을
30회 수행했으며 HTTP/외부 API는 호출하지 않았다.

| 측정 | 이전 경험 없이 계획 | 확인된 범위 지식 재사용 | 관찰 |
|---|---:|---:|---|
| stage 실행/반복 task | 2 | 1 | 30회 합계 60→30, 50% 감소 |
| E2E latency p50 | 4.207 ms | 3.444 ms | 한 번의 local fixture 실행 관측값 |
| E2E latency p95 | 4.582 ms | 4.537 ms | 한 번의 local fixture 실행 관측값; 차이는 작음 |
| 호출당 최대 Python 할당 증가분 | 32,304 bytes | 39,301 bytes | knowledge context 경로가 약 6.8 KB 더 큼; native SQLite/RSS 제외 |
| cold lookup SQLite 후보 읽기 | — | 1 row / 178 logical bytes | scan cap 500, 결과 cap 50, expansion depth 0 |
| cached lookup SQLite 후보 읽기 | — | 0 rows / 0 bytes | cache hit; 기존 조회 후보를 재표시 |

Latency는 실제 기관/API 수집 성능이 아니라 SQLite와 fixture stage를 포함한 local orchestration 경로의
30회 관측값이다. 한 번의 benchmark라 p95 수치로 지속적인 시간 개선을 주장하지 않는다. 호출 수 감소가
결정적 효율 증거이고 시간은 해당 실행 환경에 한정된다. 지식 전달로 Python 메모리는 소폭 늘었다.
이전 storage-only 규모별 p50/p95 및 메모리 표는 위 성능 측정 절에 유지한다.

### 안전성 회귀와 판정

`tests/test_knowledge_orchestration.py`는 동일 기관의 반복 task stage 생략, 다른 기관 선택 차단,
현재 지시 우선, index 조회 뒤 feedback 취소 경합 차단을 검증한다. `tests/test_knowledge.py`는
broad-scope, 상충, inference, unreviewed, 부분 조회·cache invalidation 경계를 검증한다.
조회 cache hit는 실제 SQLite read rows/bytes를 0으로 보고하도록 수정했다.

**Gate D 통과.** 이 결과는 명시 확인을 거친 institution/dataset-scoped instruction의 task planning
통합을 증명한다. UI에서 동의 수집, 자동 feedback 선택, 기관 간 공통 규칙 승격은 제공하지 않는다.
Gate C의 제한 범위 및 live 미검증 증거는 [Gate C 증거표](GATE_C_REVIEW_2026_10_26.md)를 따른다.
이번 task에서는 13회차를 시작하지 않았다.

최종 검증: 전체 pytest **580 passed**, `ruff check .` 통과, `git diff --check` 통과.
검증에는 외부 네트워크 요청이 없었다.
