# 17회차 보고서 — 대용량 비API 시험 엔진과 미실행 판정

2026-10-26. 공식 사례 조사와 현재 환경의 격리 용량 시험을 완료했다. 정식 수집/정규화 엔진 승인은 후속 범위다.

## 실험 환경·예산

Linux managed workspace, cgroup memory.max=8 GiB, CPU quota=2 cores, os.cpu_count=3.
단일 worker, 입력 <128 MiB, 출력 <192 MiB, RLIMIT_AS=384 MiB, CPU 15초, wall 20초.
합성 입력은 임시 생성하고 실제 기관 원본은 수정·삭제하지 않았다. 수치는 이 환경의 표 형태별 관측이며 보편 처리 한계가 아니다.

## 합성 용량 실험

각 일반 CSV 형태는 두 번 실행했다. warm filesystem cache 등 실험 조건을 통제한 산업 benchmark는 아니다.

| 사례 | 시험 수 | 결과 | 처리시간 범위(초) | 최대 RSS(MiB) |
|---|---:|---|---:|---:|
| csv_1MiB_10cols | 2 | TRIAL_PASSED | 0.051–0.053 | 36.6 |
| csv_16MiB_10cols | 2 | TRIAL_PASSED | 0.803–0.900 | 36.6 |
| csv_64MiB_10cols | 2 | TRIAL_PASSED | 3.425–4.408 | 36.6 |
| csv_16MiB_512cols | 2 | TRIAL_PASSED | 0.379–0.385 | 50.6 |
| csv_96MiB_10cols | 2 | TRIAL_PASSED | 5.674–5.697 | 50.6 |
| csv_127MiB_10cols | 2 | TRIAL_PASSED | 6.326–7.041 | 50.6 |
| zip_single_table | 1 | TRIAL_PASSED | 0.818–0.818 | 50.6 |
| ambiguous_delimiter | 1 | TRIAL_PASSED | 0.001–0.001 | 50.6 |

19개 합성 사례 중 14개 시험 통과, 5개 미실행 판정을 확인했다.
128 MiB sparse 입력은 본문을 읽기 전에 차단했다. 행 길이 불일치, 출력 4 KiB 예산,
메모리 8 MiB 예산, wall 1초 예산 사례는 각각 ragged_rows/output_budget/memory_budget/wall_time_budget으로 중단했다.
이 실패들은 제한 설정을 검증한 합성 실험이며 자연 provider 장애 증거가 아니다.

## 보존된 공식 BIS flat 원본의 현재 시험

task `6b22549f-d86b-4ae4-976c-3a8df2da83a5`, parent `2797e6d0-a8ac-40e5-aca4-066991a7c2e1`, deferral event `1`.
24,378행·21열, 0.262초, peak RSS 43.5 MiB로 시험 통과했다.
ZIP 원본은 256,334 bytes, 내부 CSV는 이전 보존 기록상 9,403,437 bytes이다.
raw SHA256 `0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5` 일치.
모든 값은 문자열로 보존했고 zero와 empty 표현을 구분했다. 경제 의미·단위·개정 비교·공식 normalized 출판은 수행하지 않았다.

## 구현·검증

- large-check CLI → 저장된 인계 event 선택 → atomic 부모/자식 시험 task → resource-limited worker → StageResult 이력.
- 입력 stat과 실행 코드 fingerprint를 고정하고 같은 후보·예산·코드 요청은 재실행하지 않는다.
- TXT 구분자 불명 후보를 제한적으로 시험하고 추정 여부를 보존한다. 보안 검토 대상은 시험으로 우회하지 않는다.
- 실패·예산 초과·OS 격리 불가·저장소 문제는 미실행/NOT_EXECUTED 응답. trial_attempted로 실행 전 차단과 시험 중 중단을 구분한다.
- scratch만 정리하고 원본·판정·작업 이력은 보존한다. 성공한 시험도 production_execution=NOT_EXECUTED.
- 전체 pytest **640 passed**, Ruff 통과. Windows에서 격리 미지원 시의 미실행 분기도 검증하며 Linux 전용 worker 시험은 Windows에서 skip한다.
- 실제 Windows 자원 제한 worker는 구현하지 않았다. Windows에서 무제한 fallback하지 않는다.

## 결과 해석과 다음 단계

128 MiB는 현재 시험의 중단 상한이다. 127 MiB 합성 CSV 성공은 GB/TB·모든 형식·모든 schema 지원을 뜻하지 않는다.
정식 실행은 검증된 schema, immutable artifact manifest, source-change guard, chunk checkpoint/resume,
quality/export 연결을 별도 수용 기준으로 구현한 뒤 승인한다. 이번 시험 임시 chunk는 정식 출력으로 승격하지 않는다.

조사 원문·설정·CLI: [대용량 엔진 설정](LARGE_FILE_ENGINE.md). 상세 수치: [실험 JSON](LARGE_FILE_QUALIFICATION_RESULTS.json).

## 후속 보완 — 강제 종료·resume 안전성

후속 코드 검토에서 parent process가 강제 종료되면 child worker가 계속 실행되는 동안 기존 lock은 먼저
풀릴 수 있고, 시험 task의 `RUNNING` 상태를 복구하는 CLI 경로도 없다는 점을 확인했다. 이를 같은 17회차
범위에서 보완했다.

- Orchestrator가 trial task를 claim하기 전 workspace lock을 얻고 worker child에 descriptor를 상속한다.
  child가 살아 있으면 다른 시험 또는 recovery는 `engine_busy`/`worker_still_active`로 멈춘다.
- lock이 풀린 뒤 `macroatlas resume <TRIAL_TASK_ID> --live`를 실행하면 marked orphan scratch만 정리하고
  중단 결과를 `NEEDS_REVIEW`, `trial_state=UNKNOWN`, `execution_state=NOT_EXECUTED`로 남긴다. 원본은 다시
  처리하지 않고 같은 task를 자동 재실행하지 않는다.
- 표시 파일이 없는 디렉터리와 symlink된 scratch root는 청소하지 않고 접근을 미실행 처리한다.
- 추가 회귀 검증: parent descriptor close 뒤 child의 lock 유지, 표시된 orphan만 청소, active lock 중 recovery
  차단, 중단 결과 기록, symlink root 거부.

후속 전체 pytest **645개 통과**, Ruff와 `git diff --check` 통과. 이 수정은 현재 task branch에 있으며
remote PR CI 결과는 push 이후 별도 확인 대상이다. 정식 대용량 정규화·checkpoint/resume·CSV 전달은
여전히 후속 구현이다.
