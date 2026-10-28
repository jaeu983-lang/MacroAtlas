# Iteration 21 — Offline 기준선 재현성 기록

**Date:** 2026-10-25\
**Result:** Gate L PASS\
**Track:** M — 측정 재현성\
**Scope:** 고정 World Bank fixture E2E 결과에 실행환경, Git HEAD, source/test/fixture/script fingerprint와 표본별 측정값을 기록했다. 제품 엔진 코드는 변경하지 않았다.

## 측정 결과

각 run은 독립된 Python 프로세스로 실행했으며 30개 sample을 기록했다.

| run | dispatcher p50 / p95 (ms) | dispatcher CPU p50 (ms) | read-back p50 (ms) | 완료 | live HTTP |
|---|---:|---:|---:|---:|---:|
| 1 | 143.2193 / 183.3994 | 93.7500 | 5.6087 | 30/30 | 0 |
| 2 | 150.7658 / 189.8372 | 109.3750 | 5.7197 | 30/30 | 0 |

두 run은 같은 Git HEAD `778ab412d3076aad4a37d6f3140b6ced54b56d26`와 같은 code fingerprint `f5d78372974f6f19bfd5df2ee9461a2cb029703956dd976dc95743a192d68b46`를 기록했다. 환경은 Windows 11, Python 3.12.14, AMD64, 12 logical CPUs다. fingerprint는 현재 `src/`, `tests/`, `tests/fixtures/`, `pyproject.toml`, 이 benchmark script를 포함한다.

## Gate 증거

- 각 30개 sample 완료, fixture mode, sample당 mock API call 1회.
- 모든 run에서 raw SHA256이 read-back과 일치하고 동일 fixture hash가 유지됐다.
- `[123.5, missing, 0]` 값과 `[reported, missing, reported]` 상태가 전 sample에서 보존됐다.
- 각 JSON에 개별 sample, Python/OS/CPU 환경, HEAD, fingerprint, 요청·fixture byte 및 정확성 invariant를 저장했다.
- JSON 결과 파일: [`run 1`](../../../reports/iteration_21_baseline_run_1.json), [`run 2`](../../../reports/iteration_21_baseline_run_2.json).
- 첫 실행 시 신규 invariant 코드가 결과 객체 초기화 전 `result`를 참조해 실패했다. 같은 Iteration 21 안에서 fingerprint 지역변수를 초기화하도록 수정한 뒤 두 최종 run이 통과했다. 제품 경로나 원자료는 바뀌지 않았다.

## 해석과 미검증 범위

이 수치는 동일 코드 snapshot의 새 재현 기준입니다. Iteration 18·20에는 동일한 source fingerprint가 없어 과거 run과 코드·환경이 동등하다고 확인할 수 없으므로 이전 수치 대비 개선율이나 회귀율을 계산하지 않았다. Run 1과 run 2의 차이도 추가 반복 없이 안정성 통과로 선언하지 않는다.

OS RSS, Python allocation, native SQLite memory는 측정하지 않았다. 자연어 에이전트, 다른 기관, 실제 API, credential, API latency/bytes, 랜덤 데이터셋, 저장 후 재개 및 장기 soak도 이 작업 범위가 아니다.

## 파일과 후속 단계

- `scripts/benchmark_workflow_e2e.py`: schema v2 환경/코드 identity, raw hash와 값 상태, sample 번호 및 sample-level 결과를 추가했다.
- `reports/iteration_21_baseline_run_1.json`, `reports/iteration_21_baseline_run_2.json`: 원시 측정 결과.
- 기준선·비교·병목·최적화 문서에 이 결과와 해석 한계를 기록했다.
- 후속 우선순위는 BIS 공식 API/dataflow와 정확한 debt/credit series 후보 조사다. 이 보고서는 BIS 선택, 변환식, 위험 weight 또는 live 접근을 승인하지 않는다.

## 실행 여부

전체 pytest와 live API는 실행하지 않았다. Iteration 21의 고정 fixture benchmark 2회가 이 작업의 통제 측정이며, 양쪽 프로세스에서 내부 완료·데이터·raw hash invariant가 통과했다. 이 변경은 stage/commit하지 않았고 사람 diff review가 남아 있다.
