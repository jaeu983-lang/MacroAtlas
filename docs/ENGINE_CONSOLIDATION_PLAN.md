# 엔진 통합 계획 — 통합 문서로 이관됨

현재 엔진 책임 경계와 우선순위의 단일 기준은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §4 및 §11이다.
현재 코드 연결은 [`ENGINE_CONNECTIONS.md`](ENGINE_CONNECTIONS.md), 구현 한계는
[`ENGINE_IMPLEMENTATION_STATUS.md`](ENGINE_IMPLEMENTATION_STATUS.md), 현재 검증 상태는
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)를 참조한다.

공통 Orchestrator/EngineRegistry/composition root는 이미 연결됐다. source별 transport·parser는 유지하고,
대용량 worker는 별도 recovery 경계를 쓴다. 파일 용량 판정의 typed reason 통합(Iteration 29)도 완료됐다.
현재 엔진 책임과 한계는 위의 연결·구현 상태 문서가 기준이다. 이 파일은 별도 요구사항이나 추가 backlog를 만들지 않는다.
