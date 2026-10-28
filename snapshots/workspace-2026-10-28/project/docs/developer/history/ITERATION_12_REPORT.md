# 12회차 Gate D 완료 보고 — 경험 재사용·지식 색인·개념 검색

일자: 2026-10-25\
상태: **Gate D 통과, 사람 diff 검토 대기**\
브랜치: `codex/iteration-07-08-discovery`\
커밋/스테이징/병합: 하지 않음

## 구현 범위

- append-only `knowledge_records`/`knowledge_events`에서 읽기 최적화 투영 `knowledge_current`를 분리했다. 등록·검토·취소는 해당 레코드 투영과 index generation만 갱신한다. 이전 DB는 `KnowledgeStore` 초기화 후 페이지 갱신을 명시적으로 실행해야 하며 진행 중에는 결과를 partial로 표시하고 재사용을 보류한다.
- `query`는 범위·source version·UTC 유효 기간·상태를 색인에서 선별하고 필요한 원문만 읽는다. 단일 조회의 색인, 원문, 세대 번호는 동일한 SQLite read transaction snapshot에서 확인한다. row/byte/time limit, 충돌 검토, uncertainty, generation-aware cache를 적용했다. 갱신·교정·취소와 다른 store 인스턴스의 변경은 세대 검사로 오래된 캐시 재사용을 막는다.
- 검토된 `ConceptSearchPolicy`가 명시된 경우에만 `subtype` 관계를 concept search candidate 확장에 사용한다. 상위 GDP 질의는 명목·실질 GDP를 함께 찾을 수 있지만 확장 결과에는 relation path/evidence/depth를 표시하고 `reusable=false`로 둔다. 이는 통계적 등가성·대체 가능성 사실이 아니며 자동으로 수집 경로를 선택하지 않는다. `related` 관계는 제외하고 하위 유형 질의는 형제까지 확장하지 않는다.
- 공식 근거는 요청된 기관/데이터셋/개념/분류 축과 저장 범위가 모두 일치할 때만 재사용 가능하다. 더 넓은 공식 주장이나 기관 미지정 기록은 관련 후보일 뿐이다. 사용자 설명/교정은 같은 기관 범위의 확인 필요 제안이며, 추론은 승인된 사실로 승격할 수 없다.
- 오프라인 benchmark `scripts/benchmark_knowledge.py`를 확장해 synthetic subtype 후보 정합성과 재사용 차단까지 측정하고 결과를 `reports/iteration_12_benchmark.json`에 저장했다.

## 주요 파일

- `src/macro_data_platform/storage/knowledge.py`: 범위 투영, bounded query/refresh, cache generation/snapshot, 안전한 검색 subtype 확장.
- `tests/test_knowledge_reuse.py`: 정확/넓은 범위 격리, 교정 우선, 공식 evidence와 inference 구분, conflict, resource caps, 시점/version, cross-store cache freshness, snapshot 중 동시 writer interleaving, concept subtype semantics, refresh와 query plan 회귀.
- `scripts/benchmark_knowledge.py`, `reports/iteration_12_benchmark.json`: synthetic scale 및 검색 정확성 benchmark.
- `AGENTS.md`, `PROJECT_PLAN.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`, `docs/developer/engines/KNOWLEDGE_ENGINE_PLAN.md`, `docs/developer/testing/REFERENCE_SCENARIOS.md`: Gate D 완료와 남은 경계를 기록.
- `.gitignore`: benchmark JSON을 무시하지 않도록 이 산출물만 예외 처리.

## Gate D 측정

환경: Windows 11 build 26200, Python 3.12.14, SQLite 3.53.1, AMD64. 크기별 30회 query 측정, baseline full-history decode는 10회 측정. 전체 행 수에는 GDP 개념 확장 전용 합성 레코드 2건이 포함된다. `application-cache-cleared`는 앱 결과 캐시를 비운 상태이지 OS/SQLite disk cache를 비운 cold-start 측정은 아니다.

| 전체 레코드 | 앱 캐시 미사용 p50 / p95 | warm-cache p50 / p95 | Python allocation peak | 정확 조회 행 / 근거 bytes | full-history p95 대비 |
|---:|---:|---:|---:|---:|---:|
| 102 | 5.063 / 8.516 ms | 3.363 / 4.309 ms | 49,536 bytes | 1 / 593 bytes | 1.02× |
| 1,002 | 7.576 / 16.625 ms | 5.245 / 8.175 ms | 71,022 bytes | 1 / 593 bytes | 3.53× |
| 10,002 | 12.458 / 13.793 ms | 4.996 / 5.944 ms | 127,673 bytes | 1 / 593 bytes | 39.00× |

- Gate D 측정 상한: application-cache-cleared p95 250ms, Python `tracemalloc` allocation 1MiB. 세 크기 모두 상한 안에 있었다. warm cache는 행/근거 0개를 읽었다.
- GDP 상위 검색은 policy v1에 근거가 있는 subtype 두 개(`gdp_nominal`, `gdp_real`)를 깊이 1에서 반환했고 index row 2개/근거 1,153 bytes를 읽었다. 둘 다 비재사용 후보임을 검사했다.
- 기관 범위의 broad query는 index row 21개(20개 반환 + 1개 초과 확인)에서 멈춰 `partial`을 반환했다. 미검토 충돌 가능성을 `potential_conflicts_unchecked_due_to_row_budget`로 알리고 전부 재사용하지 않았다.
- 소형 102행에서는 full-history 비교보다 indexed query가 사실상 동률(1.02×)이었다. 이 결과는 소형 자료의 성능 개선 주장을 뒷받침하지 않는다. 큰 synthetic dataset에서는 전체 JSON 역직렬화 baseline보다 개선됐다.
- 메모리는 Python `tracemalloc`만 측정했으며 native SQLite memory/process RSS, 동시 reader/writer의 처리량/경합, 운영 자료 분포는 포함하지 않는다.

## 테스트 및 검사

- 전체 pytest: **578 passed** (저장소 전체, 로컬 fixture/mock).
- `.venv\Scripts\ruff.exe check .`: 통과.
- `git diff --check`: 통과. 기존 파일 줄바꿈 안내 외 whitespace 오류 없음.
- benchmark: 100/1,000/10,000건 모두 assertion 통과, row/time/allocation cap 및 indexed query plan 사용 확인.
- 외부 HTTP 요청, 공식 문서 재조회, 기관 데이터 수집은 하지 않았다.

## 알려진 제한 및 데이터 무결성

- KnowledgeStore는 Python API이며 일반 제품 CLI, 대화형 UI, ChatGPT 자동 동기화는 없다. 공식 evidence URI는 저장하더라도 현재 페이지/약관/응답을 재검증하지 않는다.
- 공통 규칙 자동 생성·승인·다른 기관으로 배포하는 기능은 구현하지 않았다. 추론은 격리되며 13회차 범위로 남겼다.
- benchmark는 synthetic 단일 Windows 환경에 한정한다. native memory/RSS와 지속 동시 reader/writer 처리량·stress를 확인하지 않아 제품 SLA를 주장하지 않는다. 단일 snapshot/writer interleaving 회귀는 통과했다. production 대표 workload 성능 검증은 D-071 OPEN이다.
- append-only 원문/이벤트와 원자료를 삭제·수정하지 않는다. 조회 projection만 재구축 가능하며 결과가 제한·상충·갱신 중일 때 재사용을 보류한다. 검색 subtype 후보를 공식 통계 사실이나 자동 대체로 승격하지 않는다.

## 사람 검토

12회차 Gate D를 로컬 검증 범위에서 통과했다. D-062 한정 실행 예외는 소진했고 13회차는 시작하지 않았다. 전체 변경은 미커밋 상태이며, 사람의 diff 검토 후에만 체크포인트/커밋 여부를 결정한다.
