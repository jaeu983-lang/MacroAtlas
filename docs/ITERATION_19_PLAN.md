# 19회차 기획안 — BIS flat 대용량 production handoff

상태: **완료**. PR #6 통합·교차 플랫폼 CI와 보존 BIS flat 원본의 단일 production 실행 결과는
[19회차 보고서](ITERATION_19_REPORT.md)에 기록했다.

## 목표

16회차에서 정상적으로 분류된 BIS GLI flat ZIP 한 건에 대해, 기존 deferred event와 보존 raw를
검증한 뒤 명시 승인된 자식 task에서 구조를 보존한 chunk 산출물을 만든다. 기존 qualification 성공은
실행 허가로 자동 승격하지 않는다.

## 선행 상태

- PR #3/#4/#5가 기본 branch에 통합됐는지 원격 HEAD로 확인한다.
- 보존된 deferred event, origin task, inbox 사본, raw package 및 요청 manifest의 관계를 read-only로 확인한다.
- 기존 baseline을 다시 만들거나 덮어쓰지 않는다. TIC/BIS Gate C watch 대상과 BIS flat 처리 대상을 혼합하지 않는다.
- 일치하는 event·raw hash에 대한 성공 qualification이 있어야 한다. production은 별도 명시 승인으로 실행한다.

## 입력·출력

- 입력: immutable deferral event seq, NEEDS_REVIEW origin task, 같은 source URL의 보존 inbox/raw bytes,
  request manifest/hash, 일치하는 TRIAL_PASSED 기록, 고정 resource budget.
- 출력: `large-run`이 만든 동일 task의 task/event 이력, `handed_off`/`resolved` 상태 이력,
  문자열 값을 유지한 JSONL chunk와 hash·row/cell·출처가 기록된 output manifest.
- 다음 재개: 같은 child task의 `large-resume`. source, request manifest, event, parser engine version은 바꾸지 않는다.

## 범위·안전 경계

- BIS `WS_GLI_csv_flat.zip` 단일 프로필, ZIP 안 단일 CSV, UTF-8 CSV만 지원한다.
- Linux resource-isolated worker만 지원한다. 다른 OS는 무제한 fallback 없이 `NOT_EXECUTED`로 중단한다.
- chunk는 10,000행 단위며 각 완료 chunk를 SHA-256과 함께 checkpoint에 기록한다.
- 기본 최대치는 입력 128 MiB, 출력 192 MiB, 메모리 384 MiB, CPU 30초, wall 60초다.
- CSV는 최대 32열, 1 MiB/field, 8 MiB/row, 2,000,000 data rows, 20,000,000 cells로 제한한다.
- 구조가 rectangular인지 확인할 뿐 단위·빈도·경제 의미를 추론하거나 Gate C 증거를 승격하지 않는다.
- 자연 원본 변경·provider 장애를 인위적으로 만들지 않는다. production 처리는 이전 보존본을 읽고 새 산출물을 추가한다.

## 수용 조건

1. event seq와 같은 origin task, raw hash, request manifest, 승인·qualification 검증이 한 transaction에 묶인다.
2. 같은 event·scope는 같은 child task를 반환하고 중복 handoff/출력을 만들지 않는다.
3. 원본/manifest 변경, symlink, path escape, 비지원 OS/형식, 예산·보안 한도 초과는 `NOT_EXECUTED` 또는 review로 중단하며 complete manifest를 쓰지 않는다.
4. chunk/checkpoint는 crash 이후 재검증하고 같은 child task에서 재개할 수 있다.
5. 원본 bytes/hash는 전후 동일하며 output manifest와 deferred/task event 이력이 서로 연결된다.
6. 기존 지원 경로·Windows CI·전체 pytest/Ruff/diff 검사가 통과한다.

## 제외

다른 기관·파일 형식, 새 원격 다운로드, GB/TB 지원, 의미 정규화, XLSX, 기존 normalized table 수정,
CSV export, Gate C 확대 판정, 자동 resume/재시도, 환경 publish는 이 회차에 포함하지 않는다.

## 실행·기록 순서

코드/fixture 검토 → 전체 회귀와 교차 OS CI → 보존된 BIS flat event를 지정한 production 실행 → 원본 hash,
task/event, checkpoint/output manifest 재검증 → 회차 보고서와 현재 상태표 갱신 → commit/push 및 PR 검토.
production output은 Git에 추가하지 않는다.

## 완료 결과

PR #6은 merge commit `dfdfa307`로 통합됐고 Ubuntu/Windows × Python 3.11/3.12 CI 네 조합이 통과했다.
기존 event seq `1`을 child task `c244a486-17e5-4b60-a82b-287f8a37bbe7`에서 한 번 처리해
24,378×21의 문자열 JSONL을 만들었다. 원본과 manifest는 불변이었고 output manifest·chunk hash, child task 및
`handed_off/resolved` 이력을 확인했다. Gate C natural evidence로 사용하지 않는다.
