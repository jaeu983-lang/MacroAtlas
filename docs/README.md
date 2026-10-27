# 문서 안내

> 기준일: 2026-10-27. 이 문서는 현행 기준과 역사 기록을 구분합니다. 요구사항·완료 기준이 겹치면 `PROJECT_PLAN.md`가 우선합니다.

## 현행 문서

| 질문 | 기준 문서 |
|---|---|
| 제품 목표·지원 범위·우선순위 | [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) |
| 지금의 구현·gate·검증 상태 | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) |
| 다음 단계와 PR 묶음 요약 | [`ROADMAP_2026_10_26.md`](ROADMAP_2026_10_26.md) |
| A–G의 상세 수용 기준 | [`PRODUCT_EVALUATION_ENGINE_PLAN.md`](PRODUCT_EVALUATION_ENGINE_PLAN.md) |
| 엔진 요구사항과 실제 코드의 대조 | [`ENGINE_REQUIREMENTS_AUDIT_2026_10_27.md`](ENGINE_REQUIREMENTS_AUDIT_2026_10_27.md) |
| 엔진 호출·저장 경계 | [`ENGINE_CONNECTIONS.md`](ENGINE_CONNECTIONS.md), [`ENGINE_CONSOLIDATION_PLAN.md`](ENGINE_CONSOLIDATION_PLAN.md) |
| 사례 schema와 corpus 상태 | [`EVALUATION_CASES.md`](EVALUATION_CASES.md) |
| 사용 가능한 명령 | [`USER_GUIDE.md`](USER_GUIDE.md) |
| 개발 환경·기여 절차 | [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) |
| 목표 아키텍처 | [`PRODUCT_ARCHITECTURE.md`](PRODUCT_ARCHITECTURE.md) |
| 설계 변경 이유 | [`DECISION_LOG.md`](DECISION_LOG.md) |

## 현재 평가 gate

v1 evidence-backed fixed corpus는 9/36이며 `BLOCKED`입니다. 별도 27 draft는 독립 검토 대기라 고정 corpus나 candidate catalog에 포함되지 않았습니다. 기존 `evaluation/sets/`에는 synthetic scaffold 6건이 있습니다. 두 schema 경로는 목적과 계약이 달라 자동 변환하지 않습니다. 검증기가 `READY`라고 보고해도 구조·hash 검증 상태만 의미하며 엔진 평가 통과를 뜻하지 않습니다.

## 설계·배경 자료

- [`PRODUCT_ARCHITECTURE.md`](PRODUCT_ARCHITECTURE.md): 목표 시스템·사용자 아키텍처.
- [`SERIES_FRESHNESS.md`](SERIES_FRESHNESS.md), [`OUTPUT_AND_VARIANT_POLICY.md`](OUTPUT_AND_VARIANT_POLICY.md): 최신성과 원본/비교 출력 계약.
- [`ENGINE_PERFORMANCE_BASELINE_2026_10_27.md`](ENGINE_PERFORMANCE_BASELINE_2026_10_27.md): offline 표본 및 한계.
- [`KNOWLEDGE_ENGINE_PLAN.md`](KNOWLEDGE_ENGINE_PLAN.md): 검토된 feedback의 제한 재사용.

## 역사 보고서와 원본 계획

`ITERATION_*_REPORT.md`, `GATE_*`, live 기록과 `ROADMAP_2026_10_27_SNAPSHOT.md`는 작성 당시의 실행 결과·계획을 보존합니다. 그 안의 다음 단계 제안은 현행 지시가 아닙니다. 이전의 제품 원문은 [`PROJECT_PLAN_ORIGINAL_2026_10_24.md`](../PROJECT_PLAN_ORIGINAL_2026_10_24.md)에, 과거 회차별 구현·검증은 해당 보고서에 남아 있습니다. 사실·측정값을 소급 변경하지 않고, 현재 상태와 다음 작업은 위 현행 문서만 갱신합니다.
