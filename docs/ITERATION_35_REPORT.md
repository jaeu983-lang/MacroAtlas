# Iteration 35 — typed series contract checkpoint

기준: 2026-10-28, PR #79 병합 이후 `b6a25e1`에서 시작한 E 구현 checkpoint.

## 변경

- `TimeSeries`와 `Observation` 공통 타입을 추가했다. 기관/dataset/series 식별, dimension, calendar, period,
  원 source scalar와 결측 상태, unit/currency/frequency와 frequency 근거, source revision, UTC 수집 시각,
  source URL, raw/manifest 참조를 담는다.
- World Bank GDP/WDI와 BOJ FXERD01 월별·범위 collector가 성공 payload를 typed 계약으로 검사한다. 기존 SQLite
  task payload 형식은 바꾸지 않아 CLI와 CSV exporter 저장 호환성을 유지한다.
- `0`은 관측값, `null`은 missing으로 구분한다. 단위·통화·release vintage를 추정하지 않는다. 보존 원본 byte가
  숫자의 텍스트 표기 authority이고 typed 값은 파싱된 scalar로 표시한다.
- freshness 결과에 선택된 정책 근거(`series_override`, `frequency_fallback`, `unconfigured`)를 추가했다.
  frequency 기준 일수는 provider별 배포일이 검증된 정책이 아니라 기존 operational fallback이다.

## 검증

- 전체 offline suite: 922 tests passed.
- `ruff check .`: 통과.
- `git diff --check`: 통과.
- World Bank/BOJ fixture collector 및 freshness 회귀를 포함했다. 이번 checkpoint에서는 live API를 호출하지 않았다.

## 남은 범위

이 checkpoint는 Gate E 통과가 아니다. BLS·Census·파일 입력 및 저장 artifact/export 경로는 아직 typed 계약을 쓰지
않는다. official release calendar 근거와 exact-series policy, frequency fallback의 출처 검증, latest 결과 차단을
모든 지원 adapter에 적용하는 일이 남았다. Gate D도 독립적인 실제 사람 결정이 기록되지 않아 미완료다.
