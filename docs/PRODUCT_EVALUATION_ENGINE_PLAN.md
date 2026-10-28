# 남은 엔진 구현 순서

> 기준: 기본 브랜치 merge commit 4b26bc9, 2026-10-28. 제품 요구·정책은 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 현재 구현 상태는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)가 기준이다. 이 문서는 남은 작업만 정한다.

이미 구현된 공통 실행 제어, provider registry, 피드백 저장소, 검색 ranker, freshness 정책/판정 함수, CSV export를 다시 만들지 않는다. 기관별 transport·응답 parser는 유지한다. 남은 코드는 아래 의존 순서대로 네 개의 PR 묶음으로 제출한다.

2026-10-28 상태: base `4b26bc9`까지의 v2 corpus 36/36과 Actions matrix가 통과했다. 27개 draft에 대해 GPT-6가 case-by-case 검토를 완료했고, FeedbackStore에서 privacy-cleared development seed를 만드는 제한 bridge를 구현했다. 이 기록은 AI 검토·fixture bridge 검증이며 human review, 실제 사용자 관찰, engine 평가로 간주하지 않는다.

## 0. 기준선과 사례 판정 기록 — 완료

기준선은 base `825f2aa`에서 전체 `pytest` 및 `ruff check .` 통과로 기록했다. `src/`·`tests/`는 당시 base와 동일했다.

27개 draft 원본은 수정하지 않고 source file/case hash와 함께 [v2 review ledger](../tests/fixtures/evaluation/v2/review_ledger.jsonl)에 기록했다. 26건은 그대로 승인했고 1건은 candidate definition 기대값 두 곳을 고친 뒤 version 2로 승인했다. reviewer는 `GPT-6` / `ai_assistant`이며 검토 시각, 근거 ID·hash, privacy 판정, correction, limitation을 각 row에 남겼다. 생성 provenance의 `independent_review_pending`은 작성 당시 상태로 보존한다. AI 검토를 사람 검토나 실제 사용자 관찰로 바꾸어 표기하지 않는다.

## 1. 사례 corpus와 feedback bridge — PR 묶음 1, 제한 완료

초기 v1 JSONL corpus 9/36은 그대로 보존했다. 새 catalog snapshot과 review ledger를 포함하는 v2 corpus에 27개 GPT 검토 사례를 연결해 36/36을 채웠고 manifest validator는 original draft hash, adopted case hash, evidence hash, review record와 split leakage를 검증한다. corpus는 quota와 구조 기준 READY다.

`macro-eval feedback-draft`는 `feedback_id`와 현재 `expected_revision`을 명시해야 한다. source record가 `accepted`이고 `user_instruction`이어야 하며, 호출자가 `--privacy-cleared`, pseudonymous `--reviewer-id`, 비식별화한 `--sanitized-question`을 제공해야 한다. bridge는 원문, task ID, scope, source evidence를 저장하지 않고 `data/feedback_case_drafts/`에 no-overwrite local file로 development-only seed를 만든다. seed에는 provenance와 privacy attestation을 연결하지만 전체 EvaluationCase는 아니며, corpus에 자동 추가되지 않는다. 실제 사용자 feedback은 아직 seed하지 않았다.

통과 조건:
- 미수락·stale revision·inference/official evidence는 거부하고 최신 accepted user instruction만 받는다.
- 개인정보 확인 flag가 없거나 sanitized question/reviewer ID가 비어 있으면 seed를 만들지 않는다.
- 원본 feedback text, task ID, scope, evidence refs가 seed에 포함되지 않는다.
- 출력은 development seed이고 자동 승격·set/corpus 수정이 없다. 완성 사례는 근거 검증과 별도 검토를 거쳐야 한다.

이 제한 bridge 구현은 fixture 기반으로 검증됐다. 실제 사용 관찰이나 36-case v2 corpus 변경을 뜻하지 않는다.

통과 조건:
- fixed corpus 36건, development/validation/holdout 각각 12건, 각 case type은 split마다 3건
- 각 사례의 expected state·필드·후보·필수 근거·금지 행동·Excel 정책이 증거와 일치
- near-match family가 split을 가로지르지 않고 hash, privacy, family/similarity 검사가 통과
- candidate_found는 후보 발견일 뿐 수집 승인이라는 의미가 아님
- unrelated는 고정 catalog에 한정된 기대값
- review ledger의 accepted 사례만 개발 corpus로 승격하고 holdout은 이후 튜닝에 쓰지 않음

Gate가 실패하면 36건으로 간주하지 않고 evaluator 단계로 넘어가지 않는다.

## 2. 검색 평가기와 정책 비교 — PR 묶음 2, C

`macro-eval search-baseline`은 v2 development 사례의 모든 질문 변형에 기존 ranker를 offline 실행해 유형별 Top-1 분자·분모, MRR, unrelated 후보 반환과 false-exact 후보를 보고한다. 후보 반환은 확정이 아니다. 이 명령은 validation/holdout, field 정확도, 실제 확정·금지 동작과 정책 비교를 측정하지 않으므로 C gate 통과나 rule promotion을 뜻하지 않는다. 이 항목은 계속 구현해야 한다.

새 ranker를 만들지 않는다. 기존 discovery/series_search.py의 rank_candidates를 baseline으로 사용하고, candidate 변경은 SearchPolicy 버전 주입으로 분리한다. 평가 입력은 case, catalog, policy의 고정 snapshot이며 네트워크·자격증명·task/raw DB 쓰기·제품 export가 없어야 한다.

보고서에는 input/case/catalog/policy SHA, 전체 및 case type별 분자·분모, Top-1/MRR, 명시된 필드 exactness, abstention, false-exact, 금지 동작을 기록한다. 동일 입력의 보고서는 결정적이어야 한다. unknown을 정답으로 추측하거나 지원하지 않는 collector 경로를 성공으로 채점하지 않는다.

통과 조건은 목표 case type 개선, 비목표 유형 퇴행 0, false-exact 0, 금지 동작 0이다. 통과하지 못하면 policy를 승격하지 않는다.

## 3. 명시적 규칙 승격·rollback — PR 묶음 2, D

C의 validation gate가 통과한 frozen candidate만 holdout에서 한 번 확인한다. 결과를 본 뒤 같은 holdout에 맞춰 policy나 사례를 조정하지 않는다.

RulePromotionRecord에 from/to policy, case/split/catalog hash, 평가 보고서, 공식 근거, reviewer, 적용 commit, rollback commit을 연결한다. 명시 승인 없이는 기본 policy 변경을 거부한다. 자동 승격은 구현하지 않는다.

## 4. 공통 시계열과 freshness — PR 묶음 3, E

새 freshness 엔진을 중복 구현하지 않는다. 기존 ingestion/freshness.py의 FreshnessPolicy와 assess_freshness를 공통 pure decision service로 재사용·확장하고, typed TimeSeries/Observation에 붙인다. 원본 agency, dataset/series, dimensions, field, 값·상태, unit/currency, frequency/calendar, period, revision, raw/manifest/hash와 unknown을 보존한다.

최신성 우선순위는 출처가 증명한 release calendar, 검토·근거가 저장된 exact-series override, 마지막으로 명시된 provisional frequency default다. retrieval time을 observation period로 쓰지 않는다. historical-range intent에 latest freshness threshold를 잘못 적용하지 않는다. STALE/FRESHNESS_UNVERIFIED 최신 값은 normalized success와 export에서 제외한다.

provider adapter는 하나씩 순차 연결한다.
1. World Bank: 고정 GDP 경로에서 typed model과 quality/export 흐름을 검증한다.
2. BOJ: FM08/FXERD01의 기존 null 의미와 resume를 보존한다.
3. BLS: period token, 원래 값, credential 없는 provenance와 검증된 metadata를 보존한다.
4. Census: geography/table/variable과 원본 null을 보존하고 cadence를 추측하지 않는다.
5. 파일: 의미 매핑 전에는 UninterpretedTableArtifact로만 보존한다. TIC/BIS 반복 감시는 다시 켜지 않는다.

각 adapter 회귀가 통과한 뒤 다음 source로 진행한다. source adapter를 합치지 않는다.

## 5. 원자료와 비교 workbook — PR 묶음 4, F 다음 G

먼저 F 원자료 XLSX를 만든다. 현재 openpyxl 사용은 입력 parser이며 exporter가 아니다. 기존 CSV 규칙과 task DB read-only·raw 불변을 유지하는 별도 writer 경계를 둔다.

- 호환성이 확인된 원자료만 같은 sheet에 둔다. unit, currency, frequency, calendar, meaning이 다르거나 unknown이면 분리한다.
- 원래 값·결측 상태·period·provenance·quality/freshness 경고를 보존한다. 0과 결측을 섞지 않고 stale latest 값을 쓰지 않는다.
- no-overwrite, path/symlink, size/row limit, decimal precision, partial-file cleanup을 검증한다.

그 후 G 비교 workbook을 같은 bundle에서 순서대로 추가한다. Aligned_Data와 Comparison_Policy를 분리하고 source period를 기준으로 정렬한다. 허용 변환은 identity와 같은 series의 인접 검증 period difference/percent change로 제한한다. 서로 다른 calendar/frequency 자동 변환, aggregation, currency conversion, interpolation, forward-fill은 하지 않는다. 중첩 값 충돌은 덮어쓰지 않고 별도 보존하거나 review 상태로 남긴다.

## 6. 최종 분석가 관찰 — 40회차, PR 없음

1–5단계 gate를 모두 통과한 최신 기본 브랜치에서 실제 분석가 1–2명을 관찰한다. 동의와 익명 기록을 확보하고 업무 성공/실패, 경고 이해, 수동 시간, feedback 경로를 기록한다. 문서·fixture·내부 dry run은 실제 사용자 관찰을 대체하지 않는다.

## 실행 규칙

PR은 사례/feedback, 평가/승격, 시계열/freshness, workbook의 네 묶음만 만든다. 각 묶음 안의 단계는 순차 수행하며 gate 실패 뒤의 기능을 완료 처리하지 않는다. 28–39라는 회차 표기는 검증 checkpoint이며 별도 PR 목록이 아니다. 성능 최적화, Windows updater/scheduler pilot, 반복 TIC/BIS 감시는 이 A–G 경로와 분리한다.
