# 엔진 요구사항 대조 감사 — 2026-10-27

> 병합 전 날짜 고정 snapshot이다. 현재 코드 상태와 사용자가 확인한 검토 상태는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), 남은 수정 순서는 [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md)를 따른다. 아래 당시 결과와 수치는 소급 수정하지 않는다.

이 문서는 이전에 합의한 엔진 통합·피드백·평가·시계열 출력 요구사항을 현재 코드와 테스트에 대조한다. 계획 문서나 시나리오에 적혀 있다는 이유만으로 구현 완료로 판정하지 않는다.

## 현재 구현 여부

| 영역 | 판정 | 코드·검증에서 확인한 내용 | 남은 조건 |
|---|---|---|---|
| 공통 데이터 실행 엔진 | **provider composition 통합** | `EngineRegistry`가 World Bank·BOJ·BLS·Census·Gate C adapter factory를 `(engine, version)`으로 등록하고 saved plan에 맞는 공통 `Orchestrator`를 조립·재개한다. Workflow confirmation은 dispatcher에서 다시 검사한다. | 대용량 trial/production은 worker lock·checkpoint 복구가 달라 전용 runner를 유지한다. BLS/Census는 registry/Python API 대상이며 고정 CLI collect 명령이나 live fixture evidence가 추가된 것은 아니다. adapter는 출처별 전송·응답 차이 때문에 유지한다. |
| 엔진별 성능·병목 계측 | **공통 계측 구현, 자연 기준선 수집 중** | Orchestrator stage monotonic wall, API network/raw/parse/quality/SQLite, CSV export timing을 privacy-safe `performance.sqlite`에 둔다. knowledge 결과에 `latency_ns`가 추가되고 hit/miss 및 SQLite 시간이 집계된다. `macro-perf report`는 read-only다. [offline fixture 161개 표본](ENGINE_PERFORMANCE_BASELINE_2026_10_27.md)은 경로 검증이며 live network 기준선이 아니다. | live network는 승인된 자연 요청에서만 표본화한다. 실사용 workload와 production 대용량 비교는 남아 있으며, worker qualification/production 시간은 scope를 분리한다. |
| 피드백 별도 로그 | **구현됨** | `FeedbackStore`가 task/stage 연결, append-only revision, review 상태, 철회, 범위 필터를 SQLite에 기록하고 `macro-feedback` CLI가 관리한다. | 사용자가 검토하지 않은 내용은 지식 재사용에 쓰지 않는다. 로그에서 평가 사례나 공통 코드 규칙을 자동 생성하지 않는다. |
| 주기별 최신성 | **구현됨, 기본 정책 제한** | 공통 `assess_freshness`가 daily/weekly/monthly/quarterly/semiannual/annual 허용일, period-end, exact series override, 정책 fingerprint를 기록하고 오래되거나 확인 불가한 결과를 차단한다. World Bank·BOJ·BLS·Census 경로에 연결돼 있다. | 기본 허용일은 운용상 기본값이지 각 시리즈 공표 달력 보증이 아니다. 실제 series별 공표 일정 검증과 모든 generic tabular 경로 적용은 남았다. |
| A. 평가 사례 형식 | **계약 구현, evidence gate 차단** | 기존 `evaluation/sets/` synthetic scaffold 6건과 별도의 evidence-backed v1 계약·고정 corpus 9건·assistant draft 27건이 있다. v1 manifest와 evidence hash를 검증한다. | fixed corpus는 9/36이고 near-match가 없다. 27 drafts는 assistant-simulated·독립 검토 전이다. 구조/해시 검증은 의미 검토나 engine evaluation이 아니다. |
| B. 개발·검증·보류 세트 분리 | **텍스트 구조 검사 통과, 독립 검토 대기** | scaffold validator와 v1 split leakage audit가 exact/template/family 누수를 검사하고 manifest hash를 고정한다. v1 fixed 9건과 drafts 27건은 분리 보관한다. | 의미상 유사성은 자동 audit으로 확정되지 않는다. holdout hash는 비밀성·anti-overfitting을 보증하지 않는다. 검토된 사례를 반영한 후 고정 세트 gate를 통과해야 한다. |
| C. 기준안·후보안 전후 평가 | **미구현** | 일반 코드 테스트와 반복 시나리오가 존재하지만 이는 제품 사례별 후보안 비교기가 아니다. | 엔진 공통 outcome(답 상태, target, ranking, evidence, forbidden action) 계약과 같은 사례 버전의 비교 실행기가 필요하다. 유형별 정확도·오확정·금지 동작을 계산해야 한다. |
| D. 규칙 반영 심사 | **부분 구현** | 피드백 검토/지식 범위·사용자 확인 흐름이 있고, pattern analyzer는 `draft` 제안만 만든다. 자동 승격은 하지 않는다. | 코드 규칙의 근거 case/version, 전후 지표, 리뷰 승인, applied commit, rollback을 묶는 promotion record/절차는 없다. |
| E. 공통 시계열 정규화 | **부분 구현** | 수집기별 normalized observation에는 날짜·값·단위/주기(가능한 경우)와 source provenance를 보존한다. 최신성 evaluator는 period와 override를 별도 기록한다. | 종목·필드·통화·단위·주기·달력·override·출처/원본을 모든 provider에 걸쳐 표현하는 공통 typed series/batch 계약은 없다. 미제공 메타데이터는 기존처럼 unknown이어야 한다. |
| F. 원자료 Excel 출력 | **미구현** | 현재 로컬 CSV export는 완료된 World Bank GDP와 BOJ FXERD01 task만 지원한다. | 호환 정의의 series를 한 sheet에 두고, 단위·통화·주기·의미가 다르면 sheet를 나누는 검증된 XLSX exporter가 없다. 기존 task CSV를 Excel 지원으로 세지 않는다. |
| G. 정렬·가공 비교 출력 | **미구현** | 현재 exporter는 개별 task를 read-only CSV로 출력한다. | 다중 series 정렬 sheet, 날짜 기준, 집계·결측 처리·변환식 provenance가 없다. 기본 결측은 빈칸이며 interpolation/forward-fill 금지를 출력 경로에서 아직 적용할 기회가 없다. |

## 이번 수정

이번 수정은 계약 동작을 연습하는 synthetic 사례 6개와 provenance 보고를 추가했다. `macro-eval validate`는 구조 오류, 중복 사례 ID, split 간 정확 질문 중복, contrast group 누수, validation/holdout의 frozen hash 변경을 검출하고 set별 `synthetic`·`reviewed_feedback`·`official_reference` 개수를 보여준다. 현재 세 set은 구조상 `READY`지만 전부 synthetic이며 선언된 reviewed-feedback split coverage는 `none`이다. 이 coverage는 feedback ID를 SQLite와 대조하지 않는다. 이것은 engine 평가 통과가 아니며 검증기는 엔진 실행·점수 산출·규칙 승격을 하지 않는다.

검증은 `tests/test_evaluation_cases.py`의 빈/populated set, provenance 집계와 선언된 feedback coverage, split 누수, 개인정보 확인, frozen hash 변경 사례를 대상으로 한다. 상세 필드와 사용법은 [평가 사례 규약](EVALUATION_CASES.md)을 따른다.

## 통합 기획서의 미완료 조건 대조

아래 항목은 통합 순서를 새로 정하지 않는다. 작업 우선순위와 완료 조건은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §11을 따른다.

통합 실행 순서 7의 공통 stage/선택 phase 수집과 privacy-safe read-only 보고는 구현됐다. 기존 duration forecast는 대용량 qualification/production만 다루므로 일반 connector·discovery·export의 기준선과 혼합하지 않는다. live network 표본은 사용자가 승인한 자연 요청에서만 얻으며 성능 측정을 위한 요청을 반복하지 않는다.

## 성능 계측 반영

`HistoryStore`의 task 이력은 유지하고 `Settings.performance_database_path` 아래 별도 DB에 숫자 크기, 고정 상태·engine/version/stage label, 시도 번호, monotonic duration, 선택 phase, evidence class, workload tier, code SHA, Python/platform 정보만 저장한다. URL, 요청, task ID, 응답 본문/값, credential은 projection 대상이 아니다. 작업 tree가 dirty면 code SHA를 `unknown`으로 둔다. HistoryStore stage DB 접근은 활성 계측 안에서 SQLite phase로 누적된다.

World Bank/BOJ/BLS/Census 공통 transport, raw 저장, parser, freshness/quality 경계와 CSV exporter에 선택 계측을 붙였다. CSV export 표본은 별도 DB를 써서 exporter의 task DB 읽기 전용·hash 불변 조건을 보존한다. KnowledgeStore는 기존 cache 및 candidate rows/bytes에 latency를 더해 반환하고, scope/text 없는 hit/miss 표본을 저장한다. `macro-perf report --project-root .`는 execution scope, engine/version, stage, workload tier, sample/evidence/cache class, code SHA, 환경별 p50/p95·처리량·표본 수를 보여주며 p95는 n≥20에서만 확정한다. phase는 inclusive 경계로 겹칠 수 있어 합산하지 않는다.

fixture 기반 API 실행, 보존 task exporter, knowledge lookup으로 offline 표본을 모았다. 이는 live network latency를 입증하지 않으며 자연 사용자 요청 전송도 발생시키지 않는다. 계측 이후 통합 기획 §11 순서 8에 따라 registry/composition을 연결했지만, 이는 성능 최적화가 아니다. 대용량 qualification·production 기록은 기존 시간/메모리 보고에서 관리하고 일반 stage duration과 한 표본군에 합치지 않는다. catalog/task 저장 최적화는 실제 workload에서 큰 비용이 재현될 때까지 수행하지 않는다.

1. 사용자가 명시적으로 검토한 피드백 또는 공개 근거에서 개인정보를 제거한 사례를 개발 세트에 추가한다. 유사하지만 정답이 다른 질문은 같은 contrast group에 넣는다. 검토 전 피드백은 옮기지 않는다.
2. 실제 engine output을 사례 기준으로 정규화하는 outcome adapter와 기준안/후보안 비교기(C)를 만든다. validation·holdout 결과, false-confirmation 0건, forbidden action 0건이 확인되기 전에는 규칙을 반영하지 않는다.
3. 규칙 승격 기록(D)을 case version, 데이터 지표, reviewer, candidate commit, rollback commit과 결합한다.
4. 공통 typed series/batch 계약(E)을 설계하고 우선 World Bank와 BOJ에 연결한 뒤, 호환성 증명 없이 provider들을 합치지 않는다.
5. 같은 series의 원자료 출력(F)을 XLSX로 추가하고, 이후에만 여러 series 정렬·가공 출력(G)을 별도 기능으로 구현한다. 결측은 기본 빈칸이며 보간/forward-fill은 명시 근거 없이는 금지한다.
6. 실제 분석가 1–2명 관찰(기존 23회차 명칭)은 A–G gate 뒤 40회차 마지막 제품 검증으로 유지한다. 상세 기준은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §11을 따른다. 사용자 관찰 결과를 synthetic fixture 또는 통과 지표로 대체하지 않는다.

따라서 엔진 통합과 freshness/feedback 기반은 일부 동작하지만, 전체 평가-승격 루프 및 다중 시계열 Excel 흐름은 아직 완료되지 않았다.
