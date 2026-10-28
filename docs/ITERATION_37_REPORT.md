# Iteration 37 — explicit local-file series mapping

기준: 2026-10-28, PR #81 merge commit `30f910f` 이후 E 구현 checkpoint.

## 변경

- `TabularFileEngine`은 입력에 명시적 `series_mapping`이 있을 때만 하나의 series를 typed 계약으로 검증한다.
  series/dataset ID, period/value column, dimension column, unit/currency, frequency, calendar를 mapping으로
  지정한다. mapping이 없으면 기존과 같이 표를 보존할 뿐 통계 series라고 추정하지 않는다.
- mapped period는 선언된 표준 frequency와 일치해야 하고 중복 period·차원값 변경은 `NEEDS_REVIEW`로
  멈춘다. 파일은 먼저 보존되어 raw/normalized artifact와 함께 검토 참조가 남는다.
- 검증 결과는 원본 값을 복제하지 않는 `time-series-v1` 요약, raw/manifest ref와 task에 보존된 mapping으로
  기록한다. 전체 typed observation JSON을 별도 저장/export하는 기능은 아직 없다.
- local file은 공식 URL이 없을 수 있어 공통 타입의 `source_url`을 optional로 허용한다. raw/manifest reference는
  계속 필수다.

## 검증

- fixture 기반 explicit mapping, zero/empty 구분, frequency/period 불일치, 중복 period, 차원 보존을 시험했다.
- 전체 offline suite **930 tests passed**. `ruff check .`와 `git diff --check`도 통과했다. 이번 checkpoint에서 live API를 호출하지 않았다.

## 남은 범위

Gate E는 미완료다. 공식 release evidence를 인용한 exact-series freshness policy와 provider별 지연/주말/휴일 경계,
typed observation 영속화, stale/unverified 입력의 최종 결과 차단과 export 연결이 남아 있다. 현재 파일 mapping은
명시적 구조 검사일 뿐 자동 의미 해석이나 freshness 평가가 아니다.
