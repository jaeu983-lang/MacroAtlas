# MacroAtlas 구현 현황

> 기준: 2026-10-29. 이 문서는 관측된 구현과 Gate 증거만 기록한다. 제품 범위·순서·완료 조건은 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 엔진별 데이터 접근 한계는 [ENGINE_IMPLEMENTATION_STATUS.md](ENGINE_IMPLEMENTATION_STATUS.md)를 따른다.

## 기준선

- 대조 기준 기본 브랜치: `codex/iteration-04-gate-a`, HEAD `9d61865` (PR #94 merge; 2026-10-29). 남은 구현 순서의 수용 기준은 [통합 제품 기획 §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)을 따른다.
- PR #50은 825f2aa, PR #58은 4b26bc9로 병합됐다. PR #58의 merge commit은 Ubuntu/Windows × Python 3.11/3.12 Actions 네 작업이 통과했다.
- PR #58 변경 기준 로컬 전체 `pytest`와 `ruff check .`가 통과했다. legacy synthetic validator는 구조 기준 READY이고, 기존 v1 corpus validator는 9/36 BLOCKED였다.
- 요청에 따라 GPT-6가 27개 draft를 원본 hash, 공식 evidence, 기대 state/candidate/field, 금지 행동, Excel policy, split과 privacy 기준으로 하나씩 검토했다. 26건은 그대로 승인, 1건은 definition 기대값 2곳을 바로잡아 case version 2로 승인했다. 검토자 유형은 AI로 ledger에 표시했다.
- v2 corpus는 36/36, split/type quota 완성, 13 candidate, 27 review rows, evidence hash 통과, split leakage 0건이다. 원본 v1 9/36 BLOCKED는 이력으로 보존한다. v2 READY는 사례 무결성만 뜻하며 engine 평가 통과는 아니다.

## 현재 코드와 남은 조건

| 영역 | 현재 코드 | 남은 조건 |
|---|---|---|
| 공통 실행 | EngineRegistry와 composition root가 World Bank·BOJ·BLS·Census 및 Gate C adapter를 공통 Orchestrator에 조립한다. 대용량 worker는 별도 recovery 경계를 쓴다. | provider adapter를 다시 통합하지 않는다. |
| 제한 API 사용 | `macroatlas collect bls`와 `macroatlas collect census`는 입력을 connector query contract로 검증하고 저장 plan에 기록한 뒤 EngineRegistry/Orchestrator로 실행·재개한다. API key는 query/task와 분리된 process environment에서 읽는다. | 전체 기관 catalog 검색, 전 series 단위·주기 보증, BLS/Census XLSX export는 구현하지 않았다. |
| World Bank exact series | `macroatlas collect worldbank-series`는 country/source/indicator/year 범위를 검증한 뒤 `worldbank_series/1`로 원자료·manifest·typed artifact를 보존하고 parser/freshness 결과를 기록한다. | 연간 최대 100년·단일 series·단일 page만 허용. 자동 metadata 탐색/의미·단위 추론과 legacy CSV 전달은 없다. 완료·fresh typed artifact는 `export-xlsx` 대상이다. fixture 검증은 API live 증거가 아니다. |
| 로컬 후보 검색 | `macroatlas search`는 고정 WDI 후보와 저장된 hash-verified BLS/Census metadata를 `series_search/1`로 조회하고 versioned `semantic-disambiguation-v1` policy를 task에 기록한다. | network refresh가 없고 검색·선택·수집은 분리돼 있다. fixed 13-candidate v2 catalog에서만 검증됐다; ranking은 semantic equivalence를 증명하지 않는다. |
| 파일 용량 판정 | Iteration 29에서 transport·table parser·preflight가 공유 `CapacityFinding`과 고정 reason/observed/threshold/inspection point/disposition을 사용한다. Parser 용량 예외는 메시지 부분 문자열로 분류하지 않는다. | 새 용량 threshold와 scheduler는 추가하지 않았다. PR #64의 Linux/Windows × Python 3.11/3.12 CI 네 작업이 통과했다. |
| 검색 | CandidateSearchEngine은 Gate C candidate와 동일한 versioned lexical/semantic policy를 기본 경로에서 실행한다. `macro-gate-c`는 split/hash, ranking/state/abstention/false-exact/forbidden/field 지표, confirmation-boundary trace, 반복 local p50/p95·처리량·표본 수를 기록한다. | Gate C는 fixed v2 scope에서 2026-10-28 PASS, Gate D는 user-delegated AI acceptance를 append-only ledger에 기록했다. holdout rankable Top-1은 3→5, unrelated abstention은 0→8, near-match MRR은 유지, false-exact·금지 동작 위반은 0이다. candidate p95 1.508ms / baseline 1.273ms, 예산 100ms·상대 상한 1.5x 이내다. validation은 후보 조정에 사용되어 blind가 아니다. provider/API/raw-write/export 내부 동작은 미측정이다. |
| GPT 합성 사례 | 이 대화의 GPT가 만든 질문과 엔진 결과·피드백을 실제 사용자 원장과 분리해 기록한다. 별도 OpenAI API는 필요하지 않다. 새 AI 개발 사례 4건은 fixture에 보존하고 synthetic DB에 import했다. | 합성 기록은 AI 사례이며 실제 사용자 관찰이 아니다. 개발용으로만 비교하며 v2 quota, validation 또는 holdout 사례 수에 더하지 않는다. |
| 피드백 | SQLite FeedbackStore의 revision 원장, 명시 review와 incomplete case seed에 더해 전체 revision의 고정 snapshot과 수동 분류 batch import/list/show를 구현했다. 입력/출력 count·key·hash 및 원본 revision hash가 다르면 저장을 거부한다. | AI 호출과 비식별화는 운영자가 수동으로 수행한다. 실제 사용자 feedback의 AI 분류 batch와 자연 사용자 사례는 아직 검증되지 않았다. 지시문과 코드는 자동 수정되지 않는다. |
| 사례 | legacy split scaffold 6건, 역사적 v1 9건, GPT review ledger가 연결된 v2 36건이 분리돼 있다. v2는 schema, 원본·채택 case·근거 hash, split leakage를 검증한다. | v2 case review는 AI provenance이며 실제 사용자 관찰을 대체하지 않는다. |
| Freshness runtime | 공통 typed contract, freshness evaluator, API/file mapping 결과, success-only typed artifact와 stale/unverified 차단을 구현했다. BLS/Census exact override 후보는 비활성이고 frequency fallback은 operational default로만 남는다. | Census post-release sample은 미관측이지만 사용자의 명시 결정으로 별도 제품 Gate E는 제외됐다. Freshness 재평가는 F/G 실행에서 계속 적용되고 이 결정은 기관 발표 보증이나 freshness 완화를 뜻하지 않는다. |
| 출력 | completed typed-artifact raw XLSX와 reviewed-spec comparison XLSX를 제공하며 매번 artifact hash·source refs·freshness를 재검증한다. F는 BLS CPI live export, G는 같은 WDI `NY.GDP.MKTP.CD`의 2024 USA/Canada comparison 범위에서 AI review로 수용됐다. | Gate 판정은 해당 범위로 한정된다. G는 cross-provider 동등성·실질 GDP·PPP를 뜻하지 않으며 evidence/reviewer identity는 런타임에서 인증되지 않는다. |
| 성능 | monotonic stage/선택 phase 계측과 privacy-safe report가 있다. 저장 fixture 표본은 161개다. | live latency 표본은 승인된 자연 요청에서만 모은다. 측정 전 cache·SQLite·raw-write 최적화는 하지 않는다. |

2026-10-28의 bounded API live smoke, AI 개발 질문 비교, CLI·registry·테스트 환경 결과는 [엔진 실행 검증 기록](ENGINE_RUNTIME_SMOKE_2026_10_28.md)에 정리했다. 공통 typed series checkpoint는 [35회차 보고](ITERATION_35_REPORT.md), [36회차 보고](ITERATION_36_REPORT.md), [37회차 보고](ITERATION_37_REPORT.md)를 따른다.

## 제품 Gate

| Gate | 상태 | 완료 조건 |
|---|---|---|
| 사례 corpus A | 통과 (v2) | 36건 quota, 27 review ledger rows, original/case/evidence hash, privacy, split/family 검사를 통과 |
| feedback bridge B | **PASS — AI-simulated processing scope.** 3건으로 append-only revision → 고정 snapshot → 수동 AI classification batch를 실행했다. 모든 revision이 한 번씩 저장됐고 key/source hash가 일치한다. [Evidence](evidence/feedback_classification_ai_simulated_20261029.json) | 실제 사용자 검증은 미관측이다. raw feedback text와 AI ledger는 ignored local DB에 남고 tracked evidence에는 복사하지 않는다. AI/model identity는 인증되지 않음. OpenAI API는 요구되지 않음 |
| 평가 C | PASS — fixed v2 search scope, 2026-10-28. holdout lock은 `COMPLETED` | dev/validation/holdout 전체 false-exact·forbidden-exact 0. 금지 동작 위반 0; holdout 36 query에서 확인 없는 계획은 전부 차단. Holdout rankable Top-1 +2, unrelated abstention +8, near-match 유지, 유형 퇴행 없음. candidate p95 1.508ms/100ms, baseline 대비 1.184배/1.5배, 외부 호출·비용 0. 후보 자동 승격은 없으며 provider/raw/export 내부 동작·통계적 동등성·사람 관찰은 미측정 |
| 승격 D | PASS — AI 검토/결정/적용 기록, local search scope | `macro-promotion`은 C evidence와 적용 commit을 결합한 AI decision을 `reviewer_type=AI`, 모델·사용자 위임 참조·scope와 함께 hash-chain ledger에 기록한다. 동일 AI가 판단자와 검토자라는 점과 독립 human review 부재를 명시한다. rollback은 active acceptance 이후 새 commit으로만 기록된다. 도구는 AI/model identity를 인증하지 않는다. |
| Freshness runtime | E는 사용자 범위 결정으로 별도 제품 Gate에서 제외했다. 공통 typed contract와 freshness evaluator는 코드에 남고 F/G 실행에서 계속 동작한다. | ACS 2025 post-release sample은 수행·주장하지 않는다. 이 보류는 F/G 수용의 blocker가 아니며 freshness fallback/exact override 동작을 바꾸지 않는다. 사용자 scope decision은 [D-135](DECISION_LOG.md#d-135-gate-e-제품-판정-제외와-fg-ai-수용-범위)에서 기록한다. |
| 원자료 XLSX F | **AI PASS — BLS CPI live 범위.** BLS source response와 workbook의 9개 period/value/status를 대조하고 raw/manifest/XLSX/provenance hash, 재개방, FRESH recheck를 확인했다. [AI 판정](evidence/gate_f_bls_ai_review_20261029.json). | 이 판정은 live BLS CPI export와 generic fixture contract로 한정한다. 다른 기관의 live export와 사람의 usability observation은 포함하지 않는다. |
| 비교 XLSX G | **AI PASS — 같은 WDI 지표의 USA/Canada 2024 비교 범위.** official metadata source note에 근거한 exact USD mapping을 기록하고 원자료 sheet·typed period alignment·hash·provenance를 검증했다. [AI 판정](evidence/gate_g_wdi_gdp_ai_review_20261029.json). | Cross-provider 동등성, 다른 WDI indicator, 실질 GDP, PPP, welfare 비교는 승인하지 않는다. AI reviewer identity는 인증되지 않는다. |
| 통합 40 | **PASS — immutable candidate QA.** pytest 973건, Ruff, diff, CLI module/entrypoint/collect help, health가 통과했고 격리 worktree 정리도 통과했다. [QA evidence](evidence/gate_40_integration_qa_20261029.json). | QA는 provider 가용성·ACS 2025 공개 후 조회·분석가 사용성 검증을 대신하지 않는다. |
| 최종 41 | **Preflight READY; AI simulation pending.** `python scripts/run_gate_41_preflight.py`가 F/G workbook hash, freshness, formula·행 수와 value-free task card를 한 번에 확인한다. 결과가 `READY`면 AI가 두 task에 답한다. API/key·네트워크·DB 쓰기 없이 실행하며 dataset/unit/currency가 없는 BLS 메타데이터는 unknown으로 답한다. 인간의 인지시간/usability는 주장하지 않는다. 상세 기준은 [PROJECT_PLAN.md §11](../PROJECT_PLAN.md#11-남은-구현-순서와-완료-조건)이다. |

## 별도 workstream

반복 TIC/BIS 변경 감시는 범위에서 제외됐다. 대용량 처리 확인은 보존한 BIS GLI flat ZIP 한 건의 Linux 구조 보존 경로로 제한된다. Windows updater의 변경 후보·실패 복구와 실제 scheduler invocation은 미검증이고 scheduler는 꺼져 있다. 이 항목은 제품 A–G를 막지 않는다.

회차별 과거 수치와 실행 순서는 각 당시 보고서에 보존한다. 현재 상태와 다음 단계는 이 문서 및 위 두 기준 문서에서만 갱신한다.

## 다음 Gate

Gate D는 fixed v2 local-search 범위에서 AI acceptance를 적용했다. 사용자는 Gate E를 별도 제품 수용 조건에서 제외하고 freshness runtime은 유지하도록 범위를 정했다. F의 BLS live XLSX와 G의 동일 WDI GDP USA/Canada 2024 comparison은 [AI 판정](evidence/gate_f_bls_ai_review_20261029.json) 및 [AI 판정](evidence/gate_g_wdi_gdp_ai_review_20261029.json)에 reviewer type `AI`로 기록했고, 통합 검증 40도 [QA evidence](evidence/gate_40_integration_qa_20261029.json)와 같이 통과했다. 입력 raw values는 tracked evidence에 복사하지 않았다. 다음 단계는 AI 분석가 작업흐름 시뮬레이션 41이다. Census의 ACS 2025 데이터 요청과 post-release sample은 수행하지 않으며 F/G 판정의 조건으로도 두지 않는다.

기본 브랜치의 대조 기준 commit은 [`9d61865`](https://github.com/jaeu983-lang/MacroAtlas/commit/9d61865179dbe5af7ee7eed0678d3cf08bac095f)이다. 이 문서는 코드가 실제로 구현·검증된 뒤 상태를 갱신한다.
