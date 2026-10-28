# MacroAtlas 구현 현황

> 기준: 2026-10-28. 이 문서는 관측된 구현과 Gate 증거만 기록한다. 제품 범위·순서·완료 조건은 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 엔진별 데이터 접근 한계는 [ENGINE_IMPLEMENTATION_STATUS.md](ENGINE_IMPLEMENTATION_STATUS.md)를 따른다.

## 기준선

- 대조 기준 기본 브랜치: `codex/iteration-04-gate-a`, HEAD `5638363` (PR #66 merge; 2026-10-28). 남은 구현 순서의 수용 기준은 [통합 제품 기획 §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)을 따른다.
- PR #50은 825f2aa, PR #58은 4b26bc9로 병합됐다. PR #58의 merge commit은 Ubuntu/Windows × Python 3.11/3.12 Actions 네 작업이 통과했다.
- PR #58 변경 기준 로컬 전체 `pytest`와 `ruff check .`가 통과했다. legacy synthetic validator는 구조 기준 READY이고, 기존 v1 corpus validator는 9/36 BLOCKED였다.
- 요청에 따라 GPT-6가 27개 draft를 원본 hash, 공식 evidence, 기대 state/candidate/field, 금지 행동, Excel policy, split과 privacy 기준으로 하나씩 검토했다. 26건은 그대로 승인, 1건은 definition 기대값 2곳을 바로잡아 case version 2로 승인했다. 검토자 유형은 AI로 ledger에 표시했다.
- v2 corpus는 36/36, split/type quota 완성, 13 candidate, 27 review rows, evidence hash 통과, split leakage 0건이다. 원본 v1 9/36 BLOCKED는 이력으로 보존한다. v2 READY는 사례 무결성만 뜻하며 engine 평가 통과는 아니다.

## 현재 코드와 남은 조건

| 영역 | 현재 코드 | 남은 조건 |
|---|---|---|
| 공통 실행 | EngineRegistry와 composition root가 World Bank·BOJ·BLS·Census 및 Gate C adapter를 공통 Orchestrator에 조립한다. 대용량 worker는 별도 recovery 경계를 쓴다. | provider adapter를 다시 통합하지 않는다. |
| 파일 용량 판정 | Iteration 29에서 transport·table parser·preflight가 공유 `CapacityFinding`과 고정 reason/observed/threshold/inspection point/disposition을 사용한다. Parser 용량 예외는 메시지 부분 문자열로 분류하지 않는다. | 새 용량 threshold와 scheduler는 추가하지 않았다. PR #64의 Linux/Windows × Python 3.11/3.12 CI 네 작업이 통과했다. |
| 검색 | CandidateSearchEngine과 rank_candidates가 고정 catalog를 검색한다. `search-baseline`/`search-compare`는 development, `search-validation`은 validation split의 input/case/catalog/policy hash, Top-1/MRR, 기대 상태, unrelated abstention, forbidden 반환, false-exact, status/field 구조 일치와 정책 delta를 측정한다. candidate v2(37.5)는 두 split에서 unrelated 8/8 반환을 0/8로 낮추고 rankable·near-match 지표를 유지했으며 false-exact/forbidden-exact는 0건이다. 실제 검색 단계 70회에서 확인 요구 70, bypass 0, 선택/수집 payload 0이었다. 고정 fixture 순위 및 검색 경계 기준은 통과했다. | candidate v2는 평가용 wrapper이며 제품 기본 정책이 아니다. 후속 수집·raw-write·export trace가 없어 전체 Gate C는 미통과다. 자연 사용자 사례와 제품 확정 의미, holdout 단회 평가, 정책별 독립 검토 및 명시 승격/rollback도 미완료다. |
| 피드백 | SQLite FeedbackStore의 revision 원장, 명시 review와 incomplete case seed에 더해 전체 revision의 고정 snapshot과 수동 분류 batch import/list/show를 구현했다. 입력/출력 count·key·hash 및 원본 revision hash가 다르면 저장을 거부한다. | AI 호출과 비식별화는 운영자가 수동으로 수행한다. 실제 사용자 feedback의 AI 분류 batch와 자연 사용자 사례는 아직 검증되지 않았다. 지시문과 코드는 자동 수정되지 않는다. |
| 사례 | legacy split scaffold 6건, 역사적 v1 9건, GPT review ledger가 연결된 v2 36건이 분리돼 있다. v2는 schema, 원본·채택 case·근거 hash, split leakage를 검증한다. | v2 case review는 AI provenance이며 실제 사용자 관찰을 대체하지 않는다. |
| 최신성 | FreshnessPolicy와 assess_freshness가 있고 World Bank·BOJ·BLS·Census 경로와 CSV 재검증에 연결된다. | source release calendar로 검증된 series policy와 공통 typed TimeSeries/Observation은 없다. 일반 tabular input도 freshness gate 범위 밖이다. |
| 출력 | 품질 통과 World Bank GDP·BOJ FXERD01 task의 CSV와 provenance sidecar를 내보낸다. XLSX parser는 입력 전용이다. | 원자료 XLSX와 다중 시계열 정렬 workbook이 없다. |
| 성능 | monotonic stage/선택 phase 계측과 privacy-safe report가 있다. 저장 fixture 표본은 161개다. | live latency 표본은 승인된 자연 요청에서만 모은다. 측정 전 cache·SQLite·raw-write 최적화는 하지 않는다. |

## 제품 Gate

| Gate | 상태 | 완료 조건 |
|---|---|---|
| 사례 corpus A | 통과 (v2) | 36건 quota, 27 review ledger rows, original/case/evidence hash, privacy, split/family 검사를 통과 |
| feedback bridge B | snapshot·수동 batch 구현, fixture 검증; 실제 사용자 검증 미완료 | feedback revision 원장을 계속 보존. 선택 seed는 privacy attestation을 거쳐 development draft만 출력한다. 분류는 별도 versioned batch이며 실제 사용자 sample/AI 분류 결과는 아직 없음 |
| 평가 C | development/validation ranker 비교 구현·Gate 미통과 | 실행/출력 trace와 실제 사용자 사례 보완 후 후보를 고정하고 holdout 단회 평가한다. 비대상 퇴행·false-exact·금지 동작은 0건이어야 하며 목표 유형 개선 및 사전 정의 시간/비용 기준도 통과해야 함 |
| 승격 D | 미구현 | Gate C 판정 뒤 사람이 독립 reviewer와 함께 case/policy hash·지표·결정·적용 commit·rollback commit을 append-only ledger에 남긴다. 자동 promotion 없음 |
| Series·freshness E | 부분 구현 | typed Series/Observation을 정의하고 공식 release evidence와 series별 정책을 연결한다. 미상 policy는 `FRESHNESS_UNVERIFIED`, 초과는 `STALE`; 두 상태는 latest result/export에서 차단 |
| 원자료 XLSX F | 미구현 | validated typed series만 입력. 원값·period·missing/zero·unit/frequency·source/raw hash/provenance를 보존하고 no-overwrite/path/formula safety를 검증 |
| 비교 XLSX G | 미구현 | compatibility contract를 통과한 series만 정렬. 원자료 sheet는 보존, 별도 alignment sheet에 명시 변환·calendar·결측 정책을 남기며 자동 보간/forward-fill 없음 |
| 최종 관찰 | 대기 | A–G 통과 뒤 실제 분석가 1–2명 관찰 및 익명 evidence |

## 별도 workstream

반복 TIC/BIS 변경 감시는 범위에서 제외됐다. 대용량 처리 확인은 보존한 BIS GLI flat ZIP 한 건의 Linux 구조 보존 경로로 제한된다. Windows updater의 변경 후보·실패 복구와 실제 scheduler invocation은 미검증이고 scheduler는 꺼져 있다. 이 항목은 제품 A–G를 막지 않는다.

회차별 과거 수치와 실행 순서는 각 당시 보고서에 보존한다. 현재 상태와 다음 단계는 이 문서 및 위 두 기준 문서에서만 갱신한다.

## 다음 Gate

Gate B의 snapshot과 수동 결과 저장은 구현했으나 실제 사용자 feedback 분류 결과는 아직 없다. AI 호출을 자동·예약 실행하지 않고, 운영자가 privacy를 확인한 snapshot에서 수동 분류한다. Gate C는 금지 동작 trace, 실제 사용자 사례, frozen holdout 단회 확인이 빠져 미통과이며, D 승격 ledger는 C 판정 뒤에 구현한다. 세부 작업·산출물·판정 기준은 [PROJECT_PLAN §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)에만 둔다.

기본 브랜치의 기준 commit은 [`5638363`](https://github.com/jaeu983-lang/MacroAtlas/commit/5638363f5a64c3c5d76e4304ef8402fa8fd479d7)이다. 이 문서는 코드가 실제로 구현·검증된 뒤 상태를 갱신한다.
