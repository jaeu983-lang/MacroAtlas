# Iteration 42 — 제한된 BLS metadata·freshness·성능 증거

기준선 `codex/iteration-04-gate-a` / `7c807cc`에서 BLS 공식 catalogue metadata의 XLSX 표시, 한 개 추가 BLS 시리즈, 공개 일정과 실제 조회 시점의 대조, 실제 API 및 저장 XLSX 처리시간을 확인했다. 이 회차는 기관 전체 coverage나 새로운 제품 Gate를 승인하지 않는다.

## 실행 결과

1. **BLS XLSX metadata — 구현 및 검증 완료.** 등록 키가 설정된 일반 BLS 요청에 `catalog=true`를 추가하고, 반환된 공식 series title·survey·계절조정·측정 유형·지역·품목 등만 source pointer와 함께 정규화했다. XLSX의 `Series metadata` 탭은 출처가 준 속성과 정규화 상태를 행별로 보여주며, 관측 시트에도 시리즈 제목을 표시한다. 이 표본에서 dataset ID, unit, currency는 `unknown`으로 남겼다. catalogue 없는 요청은 기존 일반 series 경로를 사용한다.
2. **범위 확장 — BLS 한정 표본.** 기존 CPI-U `CUUR0000SA0`와 추가 실업률 `LNS14000000`을 한 번의 API 요청으로 확인했다. 각각 월별 9개 관측치가 있었고 최신 period는 2026-09였다. 이 결과는 다른 기관, 모든 BLS series, 공식 metadata catalog 전체를 검증하지 않는다.
3. **출처별 freshness 근거 — 일정 대조만 완료.** BLS 공식 일정은 2026년 9월 Employment Situation을 10월 2일 08:30 ET, CPI를 10월 14일 08:30 ET로 안내했다. 10월 29일 03:56 UTC 단일 조회에서 두 9월 series를 확인했다. 따라서 데이터가 해당 조회 시각까지는 이용 가능했음을 보이며 최초 이용 시각은 알 수 없다. 두 series는 기존 `monthly` `frequency_fallback` 120일 정책에서 `FRESH`였다. exact override, release-lag 보증, freshness 기본값 변경은 하지 않았다.
4. **실제 API·로컬 처리 시간 — 단일 진단 표본.** BLS 요청 총 473.079 ms 중 network 469.993 ms, parse 0.233 ms, quality 0.258 ms, raw write 0.952 ms였다. 저장된 typed artifact의 XLSX 생성은 14.880 ms였으며 parse 1.017 ms, quality 0.219 ms, export 13.345 ms로 계측됐다. export는 네트워크 요청을 하지 않았다. 각 단계는 표본 1개이므로 p50/p95와 production 기준선을 계산하지 않았고 최적화 근거로 사용하지 않는다. 두 성능 row의 `code_sha`는 working tree가 변경 중이어서 telemetry에서 `unknown`이다.
5. **실제 분석가 관찰 — 미실행, 준비 완료.** 현재 실행 환경에서 동의한 실제 분석가 참가자를 확보할 수 없어 관찰이나 실제 사용자 피드백을 만들지 않았다. BLS·WDI 과제, 준비 절차, 익명 기록 양식을 [선택 연구 계획](ITERATION_23_PLAN.md)과 [기록 양식](ANALYST_OBSERVATION_RECORD_TEMPLATE.md)에 정리했다. 참가자 세션은 여전히 제품 Gate가 아니다.

## 근거와 재현성

수치 없는 요약과 artifact hash는 [evidence JSON](evidence/iteration_42_bls_live_metadata_freshness_performance_20261029.json)에 기록했다. 공식 BLS 일정은 [capture manifest](evidence/freshness_bls_october_schedule_20261029.json) 및 보존한 HTML hash로 연결했다. raw API 응답, 관측값, workbook, 성능 SQLite는 로컬 `data/iteration-42-validation/`에만 보존하며 저장소에 포함하지 않는다. API key, 요청 body, task ID, 원자료 관측값은 tracked evidence에 없다.

## 남은 일

- 다른 기관은 구체적인 실제 요청이 정해질 때 공식 접근 경로, 인증, 응답, 품질 및 출력 단계를 각각 검증한다.
- BLS를 포함한 기관별 freshness 정책은 반복적인 출처별 공개 근거가 필요하다. 단일 시점의 확인으로 최초 공표나 허용 지연을 추정하지 않는다.
- provider별 성능 분포는 표본을 분리해 계속 모은다. p95는 충분한 반복 자료가 쌓인 뒤 계산하고, 계측에서 큰 병목이 반복될 때만 최적화한다.
- 분석가 관찰은 참여자가 확보된 뒤 동의와 실제 세션 기록으로 수행한다. AI나 이 보고서는 그 세션을 대신하지 않는다.

검증: 전체 pytest **978 passed**, `ruff check .`, `python -m compileall -q src scripts`, `git diff --check`가 통과했다. 이번 BLS 표본은 Gate F의 기존 AI 수용 범위를 넓히지 않는다.
