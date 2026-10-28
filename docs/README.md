# 문서 안내

> 기준: 2026-10-28. 계획과 상태가 다르면 요구·순서는 PROJECT_PLAN, 현재 코드 상태는 IMPLEMENTATION_PLAN이 기준이다.

| 알고 싶은 것 | 기준 문서 |
|---|---|
| 제품 범위, 정책, 완료 기준 | [PROJECT_PLAN.md](../PROJECT_PLAN.md) |
| 현재 구현·gate·증거 | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) |
| 남은 코드 순서와 수용 조건 | [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md) |
| 공통 엔진과 adapter 경계 | [ENGINE_CONSOLIDATION_PLAN.md](ENGINE_CONSOLIDATION_PLAN.md), [ENGINE_CONNECTIONS.md](ENGINE_CONNECTIONS.md) |
| 평가 사례와 두 schema 경로 | [EVALUATION_CASES.md](EVALUATION_CASES.md) |
| freshness와 출력 세부 정책 | [SERIES_FRESHNESS.md](SERIES_FRESHNESS.md), [OUTPUT_AND_VARIANT_POLICY.md](OUTPUT_AND_VARIANT_POLICY.md) |
| 실행 명령과 개발 절차 | [USER_GUIDE.md](USER_GUIDE.md), [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) |
| 결정 이유 | [DECISION_LOG.md](DECISION_LOG.md) |

## 현재 평가 상태

PR #50은 2026-10-28 기본 브랜치에 병합됐다. 초기 v1 corpus의 9/36 BLOCKED 상태는 이력으로 보존한다. 새 v2는 27개 GPT 검토 기록과 evidence hash를 연결해 36/36 READY다. 이는 사례 데이터 gate이며 engine evaluator·ranking 성능 검증 통과를 뜻하지 않는다. 원본 draft의 pending metadata는 생성 시점 기록이다.

## 기록 구분

PROJECT_PLAN은 현행 요구와 순서, IMPLEMENTATION_PLAN은 현행 상태, PRODUCT_EVALUATION_ENGINE_PLAN은 코드 단계, DECISION_LOG는 결정 이유를 관리한다. 회차·live 보고서, 2026-10-27 엔진 감사, UNRESOLVED_ITEMS snapshot은 작성 당시의 사실과 검증 결과를 보존한다. 날짜가 지난 보고서의 다음 단계 문구는 실행 지시가 아니다. 2026-10-27 엔진 감사는 병합 전 snapshot이다.
