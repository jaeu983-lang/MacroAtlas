# 22회차 보고서 — 비API 대용량 시간 예측

기준일: 2026-10-26. `large-check` qualification, BIS `large-run` production, `large-resume`에 실행 전 시간 예측을 연결했다.
이번 검증은 예측 기능을 확인했으며 기존 실측 task를 다시 처리하지 않았다.

## 구현

- 두 엔진 task plan에 bounded workload profile, baseline/경험 예측 후보, 선택 근거, 유사 표본 수와 worker wall 상한을 저장한다.
- task 저장 뒤 worker 시작 직전에 stderr로 예상 시간·범위·신뢰도·유사 실측 수·wall 상한 및 상한 도달 가능성을 표시한다.
- `macroatlas large-estimate qualification|production <ID> [--event-seq N]`와
  `large-estimate resume <TASK_ID>`는 기존 SQLite를 read-only로 열고 task/event를 만들지 않는다.
- profiling은 파일 metadata와 최대 256 KiB 표본을 사용하며 셀 문자열은 저장하지 않는다. 사용자 요약은 예측과
  완료된 worker stage의 actual wall seconds를 함께 제시한다. resume 예측은 안전하게 읽을 수 있는 checkpoint를 반영한다.
- 성공한 task의 실제 stage wall time만 qualification/production별 최대 최근 500개까지 사용한다. 유사 성공 실측이
  3건 미만이면 baseline prior를 사용하고, 3건 이상이면 입력 workload가 가까운 경험 모델을 사용할 수 있다. 두 예측은
  새 성공 결과에 대해 함께 보존되어 shadow 비교를 쌓는다. paired forecast 3건 이후 중앙 APE가 낮은 후보를 택한다.
  무작위 production A/B 분할이나 인위적인 지연은 없다.
- 예측은 승인을 자동화하지 않고 worker 예산, 포맷·크기 한도, Gate C 증거를 변경하지 않는다.

## 검증

- 전체 `python -m pytest -o addopts='' -q`: **675 passed**.
- `python -m ruff check .`와 `git diff --check`: 통과.
- 완료된 격리 trial 및 production fixture에서 worker 직전 안내, 저장 예측, 실제 stage 시간 출력을 확인했다.
- ZIP profile의 256 KiB 제한, 원문 값 비저장, CSV 마지막 행 계산, ZIP/경로 검증, shadow 모델 선택 및 parent path
  traversal 거부를 테스트했다.
- 기존 보존 deferral ID `e65971b7…`, event seq `26`에 대해 두 `large-estimate` 명령을 실행했다. 이는 read-only
  preview였다. SQLite SHA-256은 전후 동일했다. Qualification 예상은 **0.326초** (범위 **0.163–0.652초**), 유사 표본
  5/15건, 신뢰도 낮음이었다. Production 예상은 **0.479초** (범위 **0.240–0.958초**), 유사 표본 1/1건, 신뢰도 낮음이었다.
  256 KiB에서 501행을 읽어 예상한 24,477행은 기존 production의 24,378행과 약 0.4% 차이였다. Production 완료 실측
  한 건은 약 **0.593초**로 예상 범위 안에 있다. 이 한 번의 재조회는 예측 정확도를 입증하는 독립 검증으로 보지 않는다.

## 남은 한계

기존 DB의 완료 qualification 표본은 15건이며 합성·fixture 실행이 섞여 있다. production 완료 실측은 1건뿐이다. 새 모델로
저장된 paired forecast는 아직 0건이므로 shadow A/B 오차 비교는 warm-up 상태다. 따라서 초기 표시 신뢰도는 낮고,
실제 유사 workload가 축적돼야 엔진별 오차와 보정 정확도를 평가할 수 있다. 큰 파일의 row-count extrapolation도
bounded prefix 기준이며, preview가 원본 무결성이나 실행 적격성을 검증하지 않는다.

이번 회차는 외부 수집, 실제 보존 원본 production 재실행, Gate C 재판정, merge 또는 publish를 수행하지 않았다.
구현은 리뷰 branch/PR에 제출하며 병합 전 사람 검토를 기다린다.
