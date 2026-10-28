# 평가·시계열 엔진 작업 순서 — 통합 문서로 이관됨

활성 제품 계획·순서·완료 조건은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §7, §11에만 둔다.
현재 구현 및 Gate 판정은 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), source별 코드 경로와
한계는 [`ENGINE_CONNECTIONS.md`](ENGINE_CONNECTIONS.md) 및 [`ENGINE_IMPLEMENTATION_STATUS.md`](ENGINE_IMPLEMENTATION_STATUS.md)를 참조한다.

현재 다음 코드 작업은 제품 Gate와 독립된 Iteration 29 파일 용량 typed contract 정비다. 제품 Gate는
feedback/case bridge 제한 완료 → C 검색 평가(부분 구현, Gate 미통과) → D 명시 승격·rollback →
E typed series/freshness → F 원자료 XLSX → G 비교 XLSX → 마지막 분석가 관찰 순서다.
이 순서는 기획서에서만 갱신하며 이 파일은 별도 PR 목록이나 또 다른 backlog가 아니다.

기존 v2 corpus 36/36과 GPT review, candidate v2 평가, feedback draft bridge의 수치·실행 이력은
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), [`DECISION_LOG.md`](DECISION_LOG.md),
회차 보고서에 보존한다. AI 검토는 human review나 실제 분석가 관찰을 대체하지 않는다.
