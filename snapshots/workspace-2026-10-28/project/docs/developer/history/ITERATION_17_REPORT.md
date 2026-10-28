# Iteration 17 — 성능 기준선·기관별 장기 검증 계획

**Date:** 2026-10-25
**Result:** Gate H PASS
**Scope:** 진단/측정 도구와 계획 문서. 제품 코드 성능 변경과 live API 호출은 없음.

## 요약

사용자 요청에 따라 성능 개선 전에 실행 구조를 확인하고, 동일 로컬 테스트를 반복해 수정 전 기준선을 만들고, 기관/API/엔진별로 측정 가능한 병목과 미측정 범위를 분리했다. 사용자가 말한 fine-tune은 실제 공개 dataset을 무작위로 골라 검색부터 API 수집, 파싱·검증, 로컬 저장, read-back, 오류 복구까지 장기간 검증하고 보정하는 것으로 계획했다.

한국/외부 agent는 저장소 코드에 포함돼 있지 않다. 자연어 agent 평가·LLM tokens/cost/human intervention은 아직 계측할 수 없으며, Python 수집 엔진 성능과 별도 평가할 계획이다. 영어 API/metadata 우선, 영어 정보 부재 시 일본 기관의 일본어·중국 기관의 중국어 원문을 보존해 영어 canonical metadata를 만든 뒤 한국어로 표시하는 규칙을 문서화했다.

## 파일 변경

- `scripts/measure_performance_baseline.py`: fixture/mock 기반 parser, discovery, metadata, BEA/e-Stat client microbenchmark 및 assertion.
- `scripts/measure_test_suite.py`: pytest call/module별·전체 wall/CPU 계측. 현재 repository의 `src`/`tests` import 경로를 우선한다.
- `scripts/measure_test_suite.ps1`, `scripts/measure_test_suite_console.ps1`: 검증되지 않은 RSS/CPU polling을 결과로 쓰던 실험용 harness를 제거했다.
- `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`: 21개 기관 coverage, API 분류, agent/Python engine 구분, 공통/기관별 문서 방식, language fallback, seed 기반 랜덤 표본, 시간 제한 live soak, 통과 조건 및 후속 iteration.
- `docs/developer/performance/BASELINE_REPORT.md`, `docs/developer/performance/BOTTLENECK_ANALYSIS.md`, `docs/developer/performance/OPTIMIZATION_LOG.md`, `docs/developer/performance/BENCHMARK_COMPARISON.md`, `docs/developer/testing/REGRESSION_REPORT.md`: 기준선·우선순위·미측정 영역·전후 비교 규칙.
- `reports/performance_baseline_2026-10-25.json`: suite 3회 raw aggregates와 microbenchmark 측정 결과.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `PROJECT_PLAN.md`, `docs/developer/history/DECISION_LOG.md`: Gate H, 결정 D-075 및 새 계획 링크.

## 측정 결과

- 전체 pytest 계측 스크립트를 3회 실행: 매회 625 passed, 1 skipped, 0 failed (626 collected).
- 전체 wall: 36.7231s, 37.3573s, 36.7677s; p50 36.7677s, 3-run p95 37.3573s.
- process CPU: 25.0156s, 25.2500s, 26.4844s; p50 25.2500s, 3-run p95 26.4844s.
- `ruff check --no-cache .`: 통과.
- `git diff --check`: 통과. Git은 pre-existing modified file들의 LF→CRLF 변환 경고를 출력했다.
- fixture/mock microbenchmark 7개 assertion 통과. 전체 값은 `docs/developer/performance/BASELINE_REPORT.md` 및 raw JSON에 기록했다.
- live API call 0회, live payload 0 bytes. suite RSS와 native SQLite memory는 신뢰할 수 있는 계측이 없어 미측정.

## 확인된 현황과 병목 우선순위

- A–H 실행 레지스트리 14개와 초기 institution catalog 21개가 일치하지 않아 7개 정식 기관의 API status/adapter 범위가 registry에서 빠져 있다. 이것은 “API 없음” 판정이 아니다.
- Registry의 상태는 documented 9, unconfirmed 5, explicitly no API 0이다. BEA/e-Stat clients는 mock 상태이고 workflow 연결 및 live 검증이 아니다.
- 무작위 API 요청의 중복·전송량·실제 기관 지연은 미측정이다. mock benchmark의 반복 39/40은 의도적으로 반복한 harness 동작이다.
- 제품 코드에서 먼저 확인해야 할 것은 통합 stage telemetry와 source adapter 연결 경계다. 작고 합성된 parser 지연만으로 제품 병목을 선언하지 않았다.

## 정확성·보안 한계

- pytest 첫 실행은 다른 OneDrive checkout을 Python import path에서 먼저 찾으며 12개 collection error를 냈다. 측정 스크립트가 자기 checkout의 `src`/`tests`를 우선하도록 한 뒤 올바른 repository에서 3회 통과했다.
- `.env` 값은 읽거나 출력하지 않았으며 기관 API를 호출하지 않았다. live 부하·인증·source terms를 검증한 것으로 표현하지 않는다.
- Windows symlink 생성 제한으로 기존 symlink 보호 test 하나가 skip 상태다.
- worktree 시작 상태가 dirty였고 기존 변경을 보존했다. 다른 변경이 섞일 위험 때문에 stage/commit하지 않았다.

## 다음 작업의 선행 조건

Iteration 18은 별도 회차로 공통 redacted telemetry와 실측된 병목 한 가지를 다룬다. 그 후 전체 21개 기관 registry 정합성, 기관별 API 커넥터·conformance fixture, 공식 request budget, 영문 우선 언어 처리, live canary와 seeded 2h/6h soak를 순차 진행한다. live 실행은 명시적 네트워크 설정과 각 기관의 문서화된 호출 제한이 확인된 뒤다.
