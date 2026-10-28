# 지식 조회 및 제한 재사용 — 통합 문서로 이관됨

현재 요구사항과 책임 경계는 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §7–8, 실행 순서는 §11에 통합했다.
실제 lookup/reuse 경계는 [`ENGINE_CONNECTIONS.md`](ENGINE_CONNECTIONS.md), 현재 상태는
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)를 참조한다.

지식 저장은 source collection을 대체하지 않는다. 검토된 근거와 scope-bound user instruction만 명시적 확인 후
허용 stage에서 재사용하며, current user instruction이 우선한다. 미검토 feedback, inference, stale index,
scope mismatch는 재사용·stage skip 근거가 아니다. 상세 구현·성능 이력은 iteration 11–13 보고서와
[`ENGINE_PERFORMANCE_BASELINE_2026_10_27.md`](ENGINE_PERFORMANCE_BASELINE_2026_10_27.md)에 보존한다.
