# MacroAtlas 구현 현황

> 기준: 2026-10-28. 제품 범위와 완료 조건은 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 남은 코드 순서는 [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md)가 기준이다. 이 문서는 관측된 구현과 증거만 기록한다.

## 기준선

- 기본 브랜치: codex/iteration-04-gate-a, merge commit 825f2aa.
- PR #50은 merge commit 825f2aa로 병합됐고 당시 Ubuntu/Windows × Python 3.11/3.12 Actions 검사는 통과했다. 현재 변경은 PR #58에서 검토 중이다.
- 2026-10-28 base `825f2aa` 기준 로컬 전체 `pytest`와 `ruff check .`가 통과했다. legacy synthetic validator는 구조 기준 READY이고, 기존 v1 corpus validator는 9/36 BLOCKED였다.
- 요청에 따라 GPT-6가 27개 draft를 원본 hash, 공식 evidence, 기대 state/candidate/field, 금지 행동, Excel policy, split과 privacy 기준으로 하나씩 검토했다. 26건은 그대로 승인, 1건은 definition 기대값 2곳을 바로잡아 case version 2로 승인했다. 검토자 유형은 AI로 ledger에 표시했다.
- v2 corpus는 36/36, split/type quota 완성, 13 candidate, 27 review rows, evidence hash 통과, split leakage 0건이다. 원본 v1 9/36 BLOCKED는 이력으로 보존한다. v2 READY는 사례 무결성만 뜻하며 engine 평가 통과는 아니다.

## 현재 코드와 남은 조건

| 영역 | 현재 코드 | 남은 조건 |
|---|---|---|
| 공통 실행 | EngineRegistry와 composition root가 World Bank·BOJ·BLS·Census 및 Gate C adapter를 공통 Orchestrator에 조립한다. 대용량 worker는 별도 recovery 경계를 쓴다. | provider adapter를 다시 통합하지 않는다. |
| 검색 | CandidateSearchEngine과 rank_candidates가 고정 catalog를 검색한다. | 같은 결과를 평가하는 evaluator와 versioned SearchPolicy 비교가 없다. |
| 피드백 | SQLite append-only FeedbackStore와 명시 review 상태·CLI가 있다. | 사례 초안을 만들고 승인된 사례만 corpus 개발 세트로 전달하는 bridge가 없다. |
| 사례 | legacy split scaffold 6건, 역사적 v1 9건, GPT review ledger가 연결된 v2 36건이 분리돼 있다. v2는 schema, 원본·채택 case·근거 hash, split leakage를 검증한다. | FeedbackStore-to-case bridge와 engine evaluator는 없다. v2 case review는 AI provenance이며 실제 사용자 관찰을 대체하지 않는다. |
| 최신성 | FreshnessPolicy와 assess_freshness가 있고 World Bank·BOJ·BLS·Census 경로와 CSV 재검증에 연결된다. | source release calendar로 검증된 series policy와 공통 typed TimeSeries/Observation은 없다. 일반 tabular input도 freshness gate 범위 밖이다. |
| 출력 | 품질 통과 World Bank GDP·BOJ FXERD01 task의 CSV와 provenance sidecar를 내보낸다. XLSX parser는 입력 전용이다. | 원자료 XLSX와 다중 시계열 정렬 workbook이 없다. |
| 성능 | monotonic stage/선택 phase 계측과 privacy-safe report가 있다. 저장 fixture 표본은 161개다. | live latency 표본은 승인된 자연 요청에서만 모은다. 측정 전 cache·SQLite·raw-write 최적화는 하지 않는다. |

## 제품 Gate

| Gate | 상태 | 완료 조건 |
|---|---|---|
| 사례 corpus A | 통과 (v2) | 36건 quota, 27 review ledger rows, original/case/evidence hash, privacy, split/family 검사를 통과 |
| feedback bridge B | 미구현 | 명시 승인·비식별화된 FeedbackStore 기록만 case draft로 전달하고, 자동 promotion이 없음을 검증 |
| 평가 C | 미구현 | 동일 input/case/catalog으로 baseline과 candidate를 비교하고 유형별 ranking, field exactness, abstention, false-exact, 금지 행동을 보고 |
| 승격 D | 미구현 | validation 통과, frozen holdout 단회 확인, reviewer와 적용·rollback commit 기록 |
| Series·freshness E | 부분 구현 | 공통 typed model과 source-aware freshness를 provider별로 연결. latest 요청의 STALE/FRESHNESS_UNVERIFIED 값을 차단 |
| 원자료 XLSX F | 미구현 | source 값·결측·provenance 유지, no-overwrite와 freshness 확인 |
| 비교 XLSX G | 미구현 | 호환성 검증, 별도 정렬 sheet, 명시 변환 정책, 빈칸 결측, 자동 채움 금지 |
| 최종 관찰 | 대기 | A–G 통과 뒤 실제 분석가 1–2명 관찰 및 익명 evidence |

## 별도 workstream

반복 TIC/BIS 변경 감시는 범위에서 제외됐다. 대용량 처리 확인은 보존한 BIS GLI flat ZIP 한 건의 Linux 구조 보존 경로로 제한된다. Windows updater의 변경 후보·실패 복구와 실제 scheduler invocation은 미검증이고 scheduler는 꺼져 있다. 이 항목은 제품 A–G를 막지 않는다.

회차별 과거 수치와 실행 순서는 각 당시 보고서에 보존한다. 현재 상태와 다음 단계는 이 문서 및 위 두 기준 문서에서만 갱신한다.
