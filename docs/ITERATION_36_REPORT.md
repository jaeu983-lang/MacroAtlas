# Iteration 36 — BLS and Census typed adapters

기준: 2026-10-28, PR #80 merge commit `c5c7886` 이후 E 구현 checkpoint.

## 변경

- BLS 수집은 series별 `TimeSeries`로 검증한다. 월·분기·반기·연간 코드가 단일 주기로 일치할 때만 period를
  표준형으로 정규화하고 `frequency_basis=period_format`을 표시한다. 원본 `year:period`도 `source_period`로
  함께 보존한다. 주기 코드가 섞이거나 모르면 frequency를 unknown으로 둔다. API가 제공하지 않는 dataset ID,
  unit, currency, source revision은 추정하지 않는다.
- Census는 variable마다 별도 `TimeSeries`를 만들고 geography를 dimension으로 둔다. 원본 reference year와
  값은 보존하지만 ACS 1-year/5-year 차이를 포함한 frequency, unit, variable definition은 여기서 추정하지 않는다.
- 빈 문자열과 null은 `missing` 상태로 구분 표시하고 source scalar 자체는 유지한다. `0`은 missing으로 처리하지
  않는다. 현행 SQLite task payload는 저장 호환성 때문에 기존 schema로 유지한다.

## 검증

- 전체 offline suite **925 tests passed**. `ruff check .`와 `git diff --check`도 통과했다.
- Fixture 기반 BLS/Census adapter 및 ingestion 회귀를 수행했다. 실기관 API 호출은 하지 않았다.

## 남은 범위

Gate E는 미완료다. 파일 입력, typed artifact 저장/export, official release evidence를 인용한 exact-series
freshness policy, release lag/휴일 경계 검증이 남아 있다. frequency fallback은 출처별 release calendar가 검증된
정책으로 취급하지 않는다.
