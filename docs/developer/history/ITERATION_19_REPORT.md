# Iteration 19 — 전체 기관 API 상태·실행 레지스트리 정합화

**Date:** 2026-10-25\
**Result:** Gate J PASS\
**Scope:** 카탈로그 21개 출처를 실행 레지스트리와 맞추고, 공식 문서에서 확인한 API 제공·인증 상태를 기록했다. 기관별 신규 어댑터, fixture 추가, live 요청은 범위에 포함하지 않았다.

## 사용자 가치

- 초기 카탈로그, 실행 상태 스냅샷, 공식 API 감사표, Python 실행 레지스트리의 기관 ID 집합이 모두 21개로 일치한다.
- API 상태는 `documented` 15개, `unconfirmed` 6개, `not_offered` 0개다. 공식 명세를 찾지 못한 경우 API 부재로 단정하지 않는다.
- 기존 A–H 시나리오 연결 14개를 유지하고, 아직 시나리오가 없는 7개 기관은 잘못된 시나리오에 임의 배정하지 않고 빈 `scenario_ids`로 기록한다.
- 기관/통계의 원 제공자와 API 운용 제공자가 다른 Federal Reserve Board 자료는 FRED 경유로 별도 표기한다.
- API 문서 상태, 인증 요구, 구현·fixture 범위, live 검증 상태를 서로 독립적으로 볼 수 있다.

## API 분류 결과

`documented` 15개: INT-01, INT-02, INT-03, INT-04, US-01, US-02, US-04, US-05, US-06, EU-01, EU-02, EU-03, EU-05, JP-01, JP-03.

`unconfirmed` 6개: US-03, EU-04, JP-02, CN-01, CN-02, CN-03. 이번 공식 문서 검토 범위에서 일반 공개 API 명세를 찾지 못한 상태다. 이 결과는 API가 없다는 증거가 아니다.

`not_offered`는 공식 문서가 공개 API 미제공을 명시한 기관이 없어 0개다. 확인된 자격 증명 정책과 API 운용 제공자, 기관별 공식 링크는 [기관 API 감사표](../../operator/reference/INSTITUTION_API_AUDIT.md) 및 [기관 카탈로그](../../operator/reference/INSTITUTION_CATALOG.md)에 기록했다.

## 변경 파일

- `src/macro_data_platform/discovery/source_registry.py`: 전체 21개 profile, 문서 기반 API 상태, API 운용 제공자, 선택 자격 증명 변수를 표현하고 검증하도록 확장했다.
- `tests/test_source_registry.py`: catalog/registry 집합, 상태 집계, 시나리오 미배정, 제공자 및 자격 증명 검증을 추가했다.
- `docs/operator/reference/INSTITUTION_CATALOG.md`: 21개 상태 스냅샷을 추가하고 초기 목록 설명을 최신 공식 근거로 보정했다.
- `docs/operator/reference/INSTITUTION_API_AUDIT.md`: 21개 기관의 공식 링크와 확인 범위·인증·미검증 한계를 기록했다.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`, `PROJECT_PLAN.md`: Gate J, 진행 순서, 결정 및 감사 문서 인덱스를 반영했다.

## 검증 결과

- 기관 레지스트리 대상 테스트: **9 passed**.
- 전체 local pytest 계측 harness: **626 collected; 625 passed, 1 skipped, 0 failed**. Wall time **52.1522초**, process CPU **37.1406초**. 메모리/RSS는 계측하지 못했다.
- 전체 Ruff: `ruff check --no-cache .` **통과**.
- 독립 정합성 확인: catalog 초기 목록 21개, catalog 상태표 21개, API 감사표 21개, registry 21개가 동일 ID 집합. API 집계 15/6/0, A–H 미배정 7개.
- suite harness는 `network_used: false`로 기록됐다. 기관 API live 호출은 **0회**다.
- 전체 테스트 harness가 저장소의 `src`·`tests`를 먼저 import하도록 실행됐다. 일반 pytest 진입점은 이 환경에서 ambient Python path의 다른 MacroAtlas checkout을 선택할 수 있어 경로 고정 harness를 사용했다.

## 미검증 사항과 한계

- `documented`는 공식 API 문서 확인이며 endpoint 응답 성공, 자격 증명 인증 성공, 응답 스키마/데이터 품질 검증을 의미하지 않는다.
- `unconfirmed` 6개는 API 부재 확정이 아니다. 표별·dataset별 재조사가 필요하다.
- 새로 등록한 source의 기관 전용 adapter와 source-specific fixture는 아직 없다. 기존 일부 generic fixture 또는 World Bank 고정 경로 상태는 카탈로그에 구분해 기록했다.
- 7개 profile은 A–H 참조 시나리오에 아직 연결되지 않았다. 별도 사용자 업무 사례와 adapter가 준비될 때 연결을 결정해야 한다.
- 실행환경의 테스트 RSS/최대 메모리, 네트워크 외부 latency 및 live API 호출량은 측정하지 않았다. 이 회차에서 성능 개선율을 주장하지 않는다.

## 보안·데이터 무결성

- 사용자의 실제 `.env`를 읽지 않았고 API 키 값을 저장하거나 로그에 출력하지 않았다. 레지스트리에는 필요한 환경 변수 이름만 둔다.
- 공식 출처 URL은 HTTPS로 제한하고 URL credential을 허용하지 않는다.
- 문서 조사 상태와 fixture/live 상태를 별도 필드로 유지한다. 원자료의 의미, 값, 결측·0, 단위 또는 vintage 변환은 수행하지 않았다.
- 실 API 호출과 외부 네트워크 수집이 없어 기관 이용량·약관을 넘는 부하는 발생시키지 않았다.

## 다음 회차

Gate J를 통과했다. Iteration 20에서는 측정과 복구 회귀 근거가 있는 공통 경로 하나만 선택해 단순화한다. 그 gate가 통과한 뒤에야 Iteration 21+에서 source adapter와 기관 fixture를 한 기관씩 추가한다. 이 결과는 stage/commit하지 않았으며 사람의 diff 검토가 남아 있다.
