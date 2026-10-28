# 엔진 책임 경계

> 제품 범위와 우선순위는 [PROJECT_PLAN.md](../PROJECT_PLAN.md), 현재 구현 여부는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), 남은 순서는 [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md)가 기준이다. 이 문서는 엔진 통합을 반복 계획하지 않고 코드 경계만 고정한다.

## 공통으로 묶는 것

- EngineRegistry와 composition root가 저장된 engine/version에 맞는 실행기를 조립한다.
- Orchestrator가 stage lifecycle, attempt, 상태, 저장 이력, 명시적 resume를 관리한다.
- 공통 품질·freshness·raw provenance·성능 metric은 typed contract로 전달한다.
- FeedbackStore는 피드백의 append-only 기록이다. case review ledger, 평가 결과, rule promotion은 별도 기록이다.
- Export는 검증된 저장 결과를 읽고 새 산출물을 만든다. 저장된 raw와 task history를 수정하지 않는다.

## 출처별로 유지하는 것

World Bank, BOJ, BLS, Census adapter는 endpoint, 인증, paging, 응답 schema와 period 표현이 다르므로 각각 유지한다. 공통 registry는 실행 lifecycle을 공유할 뿐 출처 의미를 합치지 않는다. 파일 parser는 처음에는 구조를 보존하며, 공식 의미가 확인되기 전에는 economic TimeSeries라고 선언하지 않는다.

대용량 trial/production worker는 자원 한도, 잠금, checkpoint 복구가 일반 API/tabular 경로와 달라 전용 실행 경계를 유지한다. TIC/BIS 반복 변경 감시는 현재 범위에서 제외한다.

## 남은 구현 경계

- 사례 검토 ledger는 초안 파일을 덮어쓰지 않고 원본 hash와 reviewer decision을 연결한다.
- evaluator는 기존 rank_candidates를 불러 같은 case/catalog snapshot에 대한 결과를 비교한다. 두 번째 독립 ranker를 만들지 않는다.
- freshness 구현은 기존 FreshnessPolicy와 assess_freshness를 확장한다. 별도 threshold 엔진을 병렬 추가하지 않는다.
- typed series model은 source adapter를 대체하지 않고 adapter 결과를 정규화하는 공통 계약이다.
- XLSX writer는 기존 입력용 parser와 구분한다. 원본 전달과 다중 series 정렬을 같은 출력 기능으로 뭉치지 않는다.

성능 report는 fixture·저장 자료 161개를 offline 기준으로만 설명한다. live API latency를 증명하지 않으며 측정된 병목 전에는 cache, SQLite, raw-write 최적화를 하지 않는다. Windows updater/scheduler는 제품 데이터 engine과 분리된 maintenance workstream이다.
