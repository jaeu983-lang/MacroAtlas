# 12회차 — 기관별 지식 조회와 조건부 재사용

날짜: 2026-10-26
상태: 제한 구현·검증 완료, **Gate D 미통과**. Gate C 미통과 상태에서 사용자의 후속 실행 지시로
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

## 검증과 미완료 조건

- 외부 API/네트워크를 사용하지 않았다. Benchmark fixture는 feedback API의 기록/검토 호출을
  재생하는 end-to-end 부하가 아니라 projection query 경로만 측정한다.
- 이 구현은 `Orchestrator`가 새 task나 retry를 계획할 때 호출되지 않는다. 따라서 동일 기관의
  반복 작업에서 실제로 탐색 단계가 줄었는지, task latency 또는 재시도 횟수가 개선됐는지는
  측정하지 않았다.
- **Gate D 미통과:** 실제 반복 task/retry 흐름 연결과 같은 기관의 end-to-end 효율 검증이 남았다.
  이 보고서는 D 통과나 13회차 시작을 승인하지 않는다. Gate C 역시 원자료 변경·durable resume
  증거가 부족해 계속 미통과다.

검증: 전체 pytest **574 passed in 4.18s**, Ruff 전체 검사 통과, `git diff --check` 통과.
12회차 commit/push checkpoint는 task branch에 저장 후 갱신한다.
