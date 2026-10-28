# CSV 전달 계획 — 구현 완료 기록으로 이관됨

현재 CSV/Excel 출력 요구와 향후 F/G 순서는 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §9 및 §11이 기준이다.
현재 지원 범위와 한계는 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) 및
[`ENGINE_IMPLEMENTATION_STATUS.md`](ENGINE_IMPLEMENTATION_STATUS.md)를 참조한다.

World Bank/BOJ 검증 task용 read-only CSV exporter는 iteration 20에서 구현·검증했다. raw/manifest/hash,
task 상태, quality/freshness와 출력 경로를 재검증하고 overwrite·network·task DB write를 허용하지 않는다.
실행 근거는 [`ITERATION_20_REPORT.md`](ITERATION_20_REPORT.md)에 둔다. XLSX와 다중 series 비교는 미구현이며
이 축약 계획은 추가 export 범위를 만들지 않는다.
