# 엔진 요구사항 대조 감사 — 2026-10-27

이 문서는 이전에 합의한 엔진 통합·피드백·평가·시계열 출력 요구사항을 현재 코드와 테스트에 대조한다. 계획 문서나 시나리오에 적혀 있다는 이유만으로 구현 완료로 판정하지 않는다.

## 현재 구현 여부

| 영역 | 판정 | 코드·검증에서 확인한 내용 | 남은 조건 |
|---|---|---|---|
| 공통 데이터 실행 엔진 | **부분 통합** | `Engine`/`StageResult` 계약과 공통 `Orchestrator`가 stage·attempt·retry/resume·task history를 관리한다. World Bank, BOJ, BLS/Census, 파일, 대용량 작업은 이 계약에 맞춘 adapter/worker다. | CLI와 provider별 runner factory가 각각 엔진 mapping을 구성한다. 전역 단일 registry/control-plane wiring은 아직 완전히 공통화되지 않았다. provider adapter는 출처별 전송·응답 차이 때문에 유지하는 편이 맞다. |
| 피드백 별도 로그 | **구현됨** | `FeedbackStore`가 task/stage 연결, append-only revision, review 상태, 철회, 범위 필터를 SQLite에 기록하고 `macro-feedback` CLI가 관리한다. | 사용자가 검토하지 않은 내용은 지식 재사용에 쓰지 않는다. 로그에서 평가 사례나 공통 코드 규칙을 자동 생성하지 않는다. |
| 주기별 최신성 | **구현됨, 기본 정책 제한** | 공통 `assess_freshness`가 daily/weekly/monthly/quarterly/semiannual/annual 허용일, period-end, exact series override, 정책 fingerprint를 기록하고 오래되거나 확인 불가한 결과를 차단한다. World Bank·BOJ·BLS·Census 경로에 연결돼 있다. | 기본 허용일은 운용상 기본값이지 각 시리즈 공표 달력 보증이 아니다. 실제 series별 공표 일정 검증과 모든 generic tabular 경로 적용은 남았다. |
| A. 평가 사례 형식 | **기반 구현, 실제 사례 없음** | `evaluation/sets/*.json`에서 버전, 질문 변형, 기대 상태·기관/dataset/series/field, 필수 근거, 금지 동작, Excel 정책, 검토·개인정보 확인을 요구한다. `macro-eval validate`가 형식을 검사한다. | 세 set에 사례가 없어 상태는 `VALID_BUT_EMPTY`다. 사람이 승인·비식별화한 사례를 채워야 한다. |
| B. 개발·검증·보류 세트 분리 | **구조 구현, 실행 불가** | development/validation/holdout 파일을 분리하고 validation/holdout은 SHA-256 lock 및 set version으로 고정한다. 중복 질문과 contrast group의 split 횡단을 차단한다. | set이 모두 비어 있고 의미상 유사성은 사람이 contrast group으로 표시해야 한다. lock hash 변경은 사례 변경을 검토하는 PR과 함께 해야 한다. |
| C. 기준안·후보안 전후 평가 | **미구현** | 일반 코드 테스트와 반복 시나리오가 존재하지만 이는 제품 사례별 후보안 비교기가 아니다. | 엔진 공통 outcome(답 상태, target, ranking, evidence, forbidden action) 계약과 같은 사례 버전의 비교 실행기가 필요하다. 유형별 정확도·오확정·금지 동작을 계산해야 한다. |
| D. 규칙 반영 심사 | **부분 구현** | 피드백 검토/지식 범위·사용자 확인 흐름이 있고, pattern analyzer는 `draft` 제안만 만든다. 자동 승격은 하지 않는다. | 코드 규칙의 근거 case/version, 전후 지표, 리뷰 승인, applied commit, rollback을 묶는 promotion record/절차는 없다. |
| E. 공통 시계열 정규화 | **부분 구현** | 수집기별 normalized observation에는 날짜·값·단위/주기(가능한 경우)와 source provenance를 보존한다. 최신성 evaluator는 period와 override를 별도 기록한다. | 종목·필드·통화·단위·주기·달력·override·출처/원본을 모든 provider에 걸쳐 표현하는 공통 typed series/batch 계약은 없다. 미제공 메타데이터는 기존처럼 unknown이어야 한다. |
| F. 원자료 Excel 출력 | **미구현** | 현재 로컬 CSV export는 완료된 World Bank GDP와 BOJ FXERD01 task만 지원한다. | 호환 정의의 series를 한 sheet에 두고, 단위·통화·주기·의미가 다르면 sheet를 나누는 검증된 XLSX exporter가 없다. 기존 task CSV를 Excel 지원으로 세지 않는다. |
| G. 정렬·가공 비교 출력 | **미구현** | 현재 exporter는 개별 task를 read-only CSV로 출력한다. | 다중 series 정렬 sheet, 날짜 기준, 집계·결측 처리·변환식 provenance가 없다. 기본 결측은 빈칸이며 interpolation/forward-fill 금지를 출력 경로에서 아직 적용할 기회가 없다. |

## 이번 수정

이번 회차는 사람이 검토한 사례를 안전하게 분리할 선행 기반(A–B)만 구현했다. `macro-eval validate`는 구조 오류, 중복 사례 ID, split 간 정확 질문 중복, contrast group 누수, validation/holdout의 frozen hash 변경을 검출한다. 세 manifest는 현재 빈 상태로 고정돼 있으므로 평가를 통과한 것으로 간주하지 않는다. 검증기 자체는 엔진 실행·점수 산출·규칙 승격을 하지 않는다.

검증은 `tests/test_evaluation_cases.py`의 빈 set, 준비 완료 set, split 누수, 개인정보 확인, feedback 참조, frozen hash 변경 사례를 대상으로 한다. 상세 필드와 사용법은 [평가 사례 규약](EVALUATION_CASES.md)을 따른다.

## 통합 기획서의 미완료 조건 대조

아래 항목은 통합 순서를 새로 정하지 않는다. 작업 우선순위와 완료 조건은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §11을 따른다.

1. 사용자가 명시적으로 검토한 피드백 또는 공개 근거에서 개인정보를 제거한 사례를 개발 세트에 추가한다. 유사하지만 정답이 다른 질문은 같은 contrast group에 넣는다. 검토 전 피드백은 옮기지 않는다.
2. 실제 engine output을 사례 기준으로 정규화하는 outcome adapter와 기준안/후보안 비교기(C)를 만든다. validation·holdout 결과, false-confirmation 0건, forbidden action 0건이 확인되기 전에는 규칙을 반영하지 않는다.
3. 규칙 승격 기록(D)을 case version, 데이터 지표, reviewer, candidate commit, rollback commit과 결합한다.
4. 공통 typed series/batch 계약(E)을 설계하고 우선 World Bank와 BOJ에 연결한 뒤, 호환성 증명 없이 provider들을 합치지 않는다.
5. 같은 series의 원자료 출력(F)을 XLSX로 추가하고, 이후에만 여러 series 정렬·가공 출력(G)을 별도 기능으로 구현한다. 결측은 기본 빈칸이며 보간/forward-fill은 명시 근거 없이는 금지한다.
6. 실제 분석가 1–2명 관찰(23회차)은 위의 기술 기반 다음, [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §11의 마지막 순서로 유지한다. 사용자 관찰 결과를 synthetic fixture 또는 통과 지표로 대체하지 않는다.

따라서 엔진 통합과 freshness/feedback 기반은 일부 동작하지만, 전체 평가-승격 루프 및 다중 시계열 Excel 흐름은 아직 완료되지 않았다.
