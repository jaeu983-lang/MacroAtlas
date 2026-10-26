# 19회차 보고서 — BIS flat 대용량 production handoff

기준: 2026-10-26. 이 보고서는 task branch 구현 및 로컬 검증 결과다. PR 통합·원본 production 실행·artifact 확인은
아직 끝나지 않았다. 이 변경은 Gate C natural source-change나 failure/resume 증거를 만들거나 승격하지 않는다.

## 목표와 구현

16회차가 `cells=500010`에서 정상적으로 보류한 BIS GLI flat ZIP을 기존 immutable event, origin task,
보존 raw/request manifest 및 일치하는 qualification에 묶어 별도 child task로 처리하는 경로를 추가했다.

- `deferred ID --events`는 변경하지 않는 event 순번과 이력을 read-only로 보여준다.
- `large-run ID --event-seq N --approve-production`은 같은 event/hash의 `TRIAL_PASSED`와 명시 승인을 요구한다.
  task·parent·raw/hash·budget·worker version이 저장되고, child 생성과 `handed_off` event는 한 SQLite transaction에서 기록된다.
- Linux worker는 ZIP/CSV 경로·압축·입력·행·셀·출력 한도와 128 MiB input/192 MiB output/384 MiB memory/
  30초 CPU/60초 wall budget을 적용한다. 문자열 행을 10,000개씩 JSONL chunk로 기록하고 hash checkpoint를 남긴다.
- CSV는 최대 32열, 1 MiB/field, 8 MiB/row, 2,000,000 data rows, 20,000,000 cells로 제한한다.
- `large-resume`은 같은 child plan, raw/request hash, checkpoint와 완료 chunk를 검증한 후 이어간다. output manifest는
  task success와 `resolved` event에 연결된다. Windows는 무제한 fallback 없이 `NOT_EXECUTED`다.
- output은 구조 보존 파일이며 단위·빈도·경제 의미를 추론하지 않는다. 일반 CSV exporter와 Gate C 판정에는 연결하지 않는다.

## 보존된 입력 상태

read-only 확인에서 기존 deferral event `e65971b7b561a0774c786938334a86e59d49a3e0d2c6432148d58a9a3ee27824`
의 event seq는 `1`이었다. origin task `2797e6d0-a8ac-40e5-aca4-066991a7c2e1`은 `NEEDS_REVIEW`, reason은
`cells=500010`이었다. inbox raw와 보존 package raw는 각각 256,334 bytes, SHA-256
`0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5`로 일치했다. 기존 request manifest는
`data/raw/tabular/9594fab099de46d89bac7ba97a26b8e1/request.json`이다. 이 확인에서는 baseline을 생성·수정하지 않았다.

## 로컬 검증

- `python -m pytest -o addopts='' -q`: **656 passed**.
- `python -m ruff check src tests`: 통과.
- `git diff --check`: 통과.
- `macroatlas --help`에 `large-run`, `large-resume` 노출 확인.
- synthetic fixture는 승인 거부, qualification/hash binding, source 변경 차단, 구조 문자열 출력, manifest 무결성,
  checkpoint 재개, 미지원 OS에서의 미실행 응답을 확인했다. 실제 보존 원본 production run은 integration 후 실행한다.

## 남은 확인

이 시점에는 PR CI와 merge 확인, 동일 기존 event/raw에 대한 단 한 번의 production run, 실제 output manifest/chunk 및
원본 불변성 확인이 남아 있다. 해당 실행에서 자연 provider 장애가 발생하지 않으면 Gate C durable resume 증거는 계속
미관측이다. 실제 source 변경 또한 별도 watch 이벤트로만 판단한다.
