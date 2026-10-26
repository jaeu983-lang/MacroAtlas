# 20회차 계획 — 검증된 task의 CSV 전달

상태: 구현·로컬 수용 및 PR CI 검증 완료. 통합 근거는 [20회차 보고서](ITERATION_20_REPORT.md)에 둔다. 19회차 BIS flat structural JSONL은 이 작업에서 처리하지 않는다.

## 목표

완료·quality-passed 상태인 지원 World Bank USA GDP 또는 BOJ FM08/FXERD01 task의 저장 관측값을
네트워크 없이 CSV로 전달한다. Export는 새 source request나 데이터 검증 결과를 만들지 않으며 원본과 task 이력을
읽기 전용으로 다룬다.

## 입력 범위

- World Bank WDI source 2, USA, `NY.GDP.MKTP.CD`; 동일 task에 성공한 collect/validate stage와 passed Gate A validation record가 있어야 한다.
- BOJ `FM08` / `FXERD01`의 한 달 observation task; metadata와 collect stage가 모두 성공하고 source raw·request manifest 및 quality report가 task 범위와 일치해야 한다.
- 두 경로 모두 task status `COMPLETED`, stage status `SUCCEEDED`, `quality.status=passed`, `source_change_status`가 `first_observation` 또는 `unchanged`여야 한다.
- failed, partial, needs-review, changed/unknown, unsupported provider, tampered raw/manifest, database/task 불일치는 export를 거부한다.

## 출력 계약

- CLI: `macroatlas export TASK_ID --format csv --output data/exports/result.csv`.
- CSV는 UTF-8, 표준 CSV quoting, 고정된 열 순서로 날짜·값·결측 상태·기관·dataset/series·단위·주기·수집 시각·source URL·raw/manifest 경로 및 SHA-256·source change status를 보존한다.
- 결측 숫자는 빈 cell로 쓰고 같은 행에 `value_status=missing`을 기록한다. 값을 반올림·보간하지 않으며 unknown unit/frequency는 빈 값으로 남긴다.
- sidecar provenance JSON은 task/stage, schema, row/missing counts, 열·인코딩, CSV hash, source identity, raw/manifest hash와 검증 상태를 기록한다.
- 출력은 workspace의 `data/exports/` 안에만 만들고 symlink, path traversal, 이미 존재하는 CSV/sidecar를 거부한다. 산출물은 Git에 포함하지 않는다.

## 검증과 제외

정상 fixture 두 provider, null 보존, raw/manifest tamper, stage/quality/source-change 거부, 경로·symlink·overwrite 방지, repeat-export 비덮어쓰기, 저장소 read-only, CLI help를 검증한다. XLSX, arbitrary provider, BIS flat JSONL, 새로운 normalize/quality 검사, network request, export task를 DB에 추가하는 기능은 제외한다.

## 실행·통합 순서

저장 payload 계약 확인 → provider별 검증 adapter → atomic CSV/sidecar 생성 → fixture 수용 검사·전체 test/Ruff/diff →
task branch commit/push 및 PR/CI 통합 → 기존 성공 World Bank/BOJ task를 로컬로 export하고 결과 hash·null·원본 불변성을
재확인 → 보고서와 현재 상태표 갱신. PR #9에서 Ubuntu/Windows × Python 3.11/3.12 검증을 마쳤다.
