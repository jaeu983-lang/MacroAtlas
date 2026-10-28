# MacroAtlas 구현 현황

> 기준: 2026-10-28. 이 문서는 관측된 구현과 Gate 증거만 기록한다. 제품 범위·순서·완료 조건은 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 엔진별 데이터 접근 한계는 [ENGINE_IMPLEMENTATION_STATUS.md](ENGINE_IMPLEMENTATION_STATUS.md)를 따른다.

## 기준선

- 대조 기준 기본 브랜치: `codex/iteration-04-gate-a`, HEAD `c5c7886` (PR #80 merge; 2026-10-28). 남은 구현 순서의 수용 기준은 [통합 제품 기획 §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)을 따른다.
- PR #50은 825f2aa, PR #58은 4b26bc9로 병합됐다. PR #58의 merge commit은 Ubuntu/Windows × Python 3.11/3.12 Actions 네 작업이 통과했다.
- PR #58 변경 기준 로컬 전체 `pytest`와 `ruff check .`가 통과했다. legacy synthetic validator는 구조 기준 READY이고, 기존 v1 corpus validator는 9/36 BLOCKED였다.
- 요청에 따라 GPT-6가 27개 draft를 원본 hash, 공식 evidence, 기대 state/candidate/field, 금지 행동, Excel policy, split과 privacy 기준으로 하나씩 검토했다. 26건은 그대로 승인, 1건은 definition 기대값 2곳을 바로잡아 case version 2로 승인했다. 검토자 유형은 AI로 ledger에 표시했다.
- v2 corpus는 36/36, split/type quota 완성, 13 candidate, 27 review rows, evidence hash 통과, split leakage 0건이다. 원본 v1 9/36 BLOCKED는 이력으로 보존한다. v2 READY는 사례 무결성만 뜻하며 engine 평가 통과는 아니다.

## 현재 코드와 남은 조건

| 영역 | 현재 코드 | 남은 조건 |
|---|---|---|
| 공통 실행 | EngineRegistry와 composition root가 World Bank·BOJ·BLS·Census 및 Gate C adapter를 공통 Orchestrator에 조립한다. 대용량 worker는 별도 recovery 경계를 쓴다. | provider adapter를 다시 통합하지 않는다. |
| 제한 API 사용 | `macroatlas collect bls`와 `macroatlas collect census`는 입력을 connector query contract로 검증하고 저장 plan에 기록한 뒤 EngineRegistry/Orchestrator로 실행·재개한다. API key는 query/task와 분리된 process environment에서 읽는다. | 전체 기관 catalog 검색, 전 series 단위·주기 보증, BLS/Census XLSX export는 구현하지 않았다. |
| World Bank exact series | `macroatlas collect worldbank-series`는 country/source/indicator/year 범위를 검증한 뒤 `worldbank_series/1`로 원자료와 manifest를 보존하고 parser/freshness 결과를 기록한다. | 연간 최대 100년·단일 series·단일 page만 허용. 자동 metadata 탐색/의미·단위 추론과 XLSX/CSV 전달은 없다. fixture 검증은 API live 증거가 아니다. |
| 로컬 후보 검색 | `macroatlas search`는 고정 WDI 후보와 저장된 hash-verified BLS/Census metadata를 `series_search/1`로 조회하고 결과 task를 보존한다. | network refresh가 없고 검색·선택·수집은 분리돼 있다. 전 provider catalog를 다루지 않으며 Gate D 결정도 대신하지 않는다. |
| 파일 용량 판정 | Iteration 29에서 transport·table parser·preflight가 공유 `CapacityFinding`과 고정 reason/observed/threshold/inspection point/disposition을 사용한다. Parser 용량 예외는 메시지 부분 문자열로 분류하지 않는다. | 새 용량 threshold와 scheduler는 추가하지 않았다. PR #64의 Linux/Windows × Python 3.11/3.12 CI 네 작업이 통과했다. |
| 검색 | CandidateSearchEngine은 versioned lexical baseline과 semantic evaluation candidate를 고정 catalog에서 비교한다. `macro-gate-c`는 split/hash, ranking/state/abstention/false-exact/forbidden/field 지표, confirmation-boundary trace, 반복 local p50/p95·처리량·표본 수를 기록한다. | 제품 Gate C는 fixed v2 search scope에서 2026-10-28 PASS다. holdout target 개선은 rankable/unrelated, near-match는 baseline과 동률이며 유형 퇴행은 없다. candidate p95 1.508ms, budget 100ms 및 baseline 대비 1.5배 안에 들었다. validation은 후보 조정에 사용돼 blind가 아니다. provider/API/raw-write/export 경로는 실행하지 않았고 정책은 승격되지 않았다. |
| GPT 합성 사례 | 이 대화의 GPT가 만든 질문과 엔진 결과·피드백을 실제 사용자 원장과 분리해 기록한다. 별도 OpenAI API는 필요하지 않다. 새 AI 개발 사례 4건은 fixture에 보존하고 synthetic DB에 import했다. | 합성 기록은 AI 사례이며 실제 사용자 관찰이 아니다. 개발용으로만 비교하며 v2 quota, validation 또는 holdout 사례 수에 더하지 않는다. |
| 피드백 | SQLite FeedbackStore의 revision 원장, 명시 review와 incomplete case seed에 더해 전체 revision의 고정 snapshot과 수동 분류 batch import/list/show를 구현했다. 입력/출력 count·key·hash 및 원본 revision hash가 다르면 저장을 거부한다. | AI 호출과 비식별화는 운영자가 수동으로 수행한다. 실제 사용자 feedback의 AI 분류 batch와 자연 사용자 사례는 아직 검증되지 않았다. 지시문과 코드는 자동 수정되지 않는다. |
| 사례 | legacy split scaffold 6건, 역사적 v1 9건, GPT review ledger가 연결된 v2 36건이 분리돼 있다. v2는 schema, 원본·채택 case·근거 hash, split leakage를 검증한다. | v2 case review는 AI provenance이며 실제 사용자 관찰을 대체하지 않는다. |
| 최신성·typed series | `TimeSeries`/`Observation` 공통 계약은 World Bank GDP/WDI, BOJ monthly/range, BLS, Census adapter에서 구조 검증된다. BLS 원 period code를 보존하고 혼합주기는 unknown으로 둔다. Census는 variable/geography별 series로 분리하되 unit/frequency를 추정하지 않는다. null/빈 값과 0을 구분하고 freshness 결과에 override/fallback 근거를 남긴다. | typed 계약은 파일 adapter와 저장/export 경로에 연결되지 않았다. 기관 release calendar로 검증된 exact-series policy가 없고 frequency tolerance는 초기 fallback이다. Gate E 미완료. |
| 출력 | 품질 통과 World Bank GDP·BOJ FXERD01 one-month/range task의 CSV와 provenance sidecar를 내보낸다. XLSX parser는 입력 전용이다. | 원자료 XLSX와 다중 시계열 정렬 workbook이 없다. |
| 성능 | monotonic stage/선택 phase 계측과 privacy-safe report가 있다. 저장 fixture 표본은 161개다. | live latency 표본은 승인된 자연 요청에서만 모은다. 측정 전 cache·SQLite·raw-write 최적화는 하지 않는다. |

2026-10-28의 bounded API live smoke, AI 개발 질문 비교, CLI·registry·테스트 환경 결과는 [엔진 실행 검증 기록](ENGINE_RUNTIME_SMOKE_2026_10_28.md)에 정리했다. 공통 typed series checkpoint는 [35회차 보고](ITERATION_35_REPORT.md)와 [36회차 보고](ITERATION_36_REPORT.md)를 따른다.

## 제품 Gate

| Gate | 상태 | 완료 조건 |
|---|---|---|
| 사례 corpus A | 통과 (v2) | 36건 quota, 27 review ledger rows, original/case/evidence hash, privacy, split/family 검사를 통과 |
| feedback bridge B | snapshot·수동 batch 구현, fixture 검증; 실제 사용자 검증 미완료. 합성 질문/피드백 6건은 별도 ignored DB에 있고 4건은 tracked fixture로 재생 가능 | feedback revision 원장을 계속 보존. 선택 seed는 privacy attestation을 거쳐 development draft만 출력한다. 실제 사용자 sample은 아직 없고 OpenAI API는 요구되지 않음 |
| 평가 C | PASS — fixed v2 search scope, 2026-10-28. holdout lock은 `COMPLETED` | dev/validation/holdout 전체 false-exact·forbidden-exact 0. 금지 동작 위반 0; holdout 36 query에서 확인 없는 계획은 전부 차단. Holdout rankable Top-1 +2, unrelated abstention +8, near-match 유지, 유형 퇴행 없음. candidate p95 1.508ms/100ms, baseline 대비 1.184배/1.5배, 외부 호출·비용 0. 후보 자동 승격은 없으며 provider/raw/export 내부 동작·통계적 동등성·사람 관찰은 미측정 |
| 승격 D | 원장·CLI 구현, AI 권고 hold, Gate D 미완료 | `macro-promotion`은 C artifact/hash/metrics를 검증하고 append-only hash-chain 원장에 accept/hold/reject 또는 rollback을 남긴다. AI가 별도 decision log에 `hold/evidence_follow_up_needed` 권고를 남겼다. 공식 승격 원장은 비어 있고 실제 사람 결정은 없다. accept에는 Gate C PASS, 서로 다른 사람의 self-attestation, 적용 commit이 필요하다. rollback은 적용 commit 뒤의 새 commit을 요구한다. 도구는 신원을 인증하지 않고 기본 정책을 바꾸지 않는다. |
| Series·freshness E | 부분 구현 — 공통 계약을 World Bank·BOJ·BLS·Census에 연결 | 파일 adapter 및 저장/export 연결, official release evidence를 가진 exact-series 정책, 미상/초과 최신성 값 차단을 검증해야 Gate E를 통과한다. 현재 frequency fallback은 결과에 명시된다. |
| 원자료 XLSX F | 미구현 | validated typed series만 입력. 원값·period·missing/zero·unit/frequency·source/raw hash/provenance를 보존하고 no-overwrite/path/formula safety를 검증 |
| 비교 XLSX G | 미구현 | compatibility contract를 통과한 series만 정렬. 원자료 sheet는 보존, 별도 alignment sheet에 명시 변환·calendar·결측 정책을 남기며 자동 보간/forward-fill 없음 |
| 최종 관찰 | 대기 | A–G 통과 뒤 AI 가상 분석가 시나리오를 임시 Gate 증거로 사용할 수 있다. 실제 분석가 관찰 여부는 따로 기록 |

## 별도 workstream

반복 TIC/BIS 변경 감시는 범위에서 제외됐다. 대용량 처리 확인은 보존한 BIS GLI flat ZIP 한 건의 Linux 구조 보존 경로로 제한된다. Windows updater의 변경 후보·실패 복구와 실제 scheduler invocation은 미검증이고 scheduler는 꺼져 있다. 이 항목은 제품 A–G를 막지 않는다.

회차별 과거 수치와 실행 순서는 각 당시 보고서에 보존한다. 현재 상태와 다음 단계는 이 문서 및 위 두 기준 문서에서만 갱신한다.

## 다음 Gate

Gate B의 snapshot과 수동 결과 저장은 구현했으나 실제 사용자 feedback 분류 결과는 아직 없다. AI 호출을 자동·예약 실행하지 않고, 운영자가 privacy를 확인한 snapshot에서 수동 분류한다. 제품 Gate C는 fixed v2 search scope에서 통과했고 후보 manifest·qualification·one-time holdout 결과는 [`evaluation/results/`](../evaluation/results/) 아래 보존했다. AI는 해당 제한을 근거로 `hold/evidence_follow_up_needed`를 권고했으며 [결정 로그 D-121](DECISION_LOG.md)에 AI 의견으로 분리 기록했다. 이는 공식 promotion ledger의 사람 결정이 아니므로 후보는 계속 미승격이고 Gate D는 미완료다. 도구는 사람 신원과 독립 검토의 실체를 인증하지 않는다. provider/raw/export 실행 경로는 향후 해당 기능 Gate에서 별도 검증한다. 세부 작업·산출물·판정 기준은 [PROJECT_PLAN §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)에만 둔다.

기본 브랜치의 대조 기준 commit은 [`c5c7886`](https://github.com/jaeu983-lang/MacroAtlas/commit/c5c7886d1488b6a1c9b41db3c41ea3673f805e64)이다. 이 문서는 코드가 실제로 구현·검증된 뒤 상태를 갱신한다.
