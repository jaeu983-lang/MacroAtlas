# 19회차 보고서 — BIS flat 대용량 production handoff

기준: 2026-10-26. **구현·검토·통합 및 보존 원본 단일 production 실행 완료.** PR #6은
[`01b0850`](https://github.com/jaeu983-lang/MacroAtlas/commit/01b0850b7edfbf57dfea9abb814d3e6ff01e0e12)에서
[`codex/iteration-04-gate-a`](https://github.com/jaeu983-lang/MacroAtlas/tree/codex/iteration-04-gate-a)에
merge commit `dfdfa307534c504f8c740fe1a154a7ba47945e10`으로 통합됐다.
[PR #6](https://github.com/jaeu983-lang/MacroAtlas/pull/6)의 Ubuntu/Windows × Python 3.11/3.12 CI 네 조합이
모두 통과했다. 이 회차는 Gate C natural source-change나 자연 장애 후 resume 증거를 만들거나 승격하지 않는다.

## 목표와 구현

16회차가 `cells=500010`에서 정상적으로 보류한 BIS GLI flat ZIP을 기존 immutable event, origin task,
보존 raw/request manifest 및 일치하는 qualification에 묶어 별도 child task로 처리했다.

- `deferred ID --events`는 변경하지 않는 event 순번과 이력을 read-only로 보여준다.
- `large-run ID --event-seq N --approve-production`은 같은 event/hash의 `TRIAL_PASSED`와 명시 승인을 요구한다.
  task·parent·raw/hash·budget·worker version이 저장되고, child 생성과 `handed_off` event는 한 SQLite transaction에서 기록된다.
- Linux worker는 ZIP/CSV 경로·압축·입력·행·셀·출력 한도와 128 MiB input/192 MiB output/384 MiB memory/
  30초 CPU/60초 wall budget을 적용한다. 문자열 행을 10,000개씩 JSONL chunk로 기록하고 hash checkpoint를 남긴다.
- CSV는 최대 32열, 1 MiB/field, 8 MiB/row, 2,000,000 data rows, 20,000,000 cells로 제한한다.
- `large-resume`은 같은 child plan, raw/request hash, checkpoint와 완료 chunk를 검증한 후 이어간다. output manifest는
  task success와 `resolved` event에 연결된다. Windows는 무제한 fallback 없이 `NOT_EXECUTED`다.
- output은 구조 보존 파일이며 단위·빈도·경제 의미를 추론하지 않는다. 일반 CSV exporter와 Gate C 판정에는 연결하지 않는다.

## 실행 입력과 보존 상태

기존 deferral ID `e65971b7b561a0774c786938334a86e59d49a3e0d2c6432148d58a9a3ee27824`의 원래 event seq는 `1`이고,
origin task `2797e6d0-a8ac-40e5-aca4-066991a7c2e1`은 `NEEDS_REVIEW`, reason은 `cells=500010`이었다.
실행 직전 inbox raw와 package raw는 각각 256,334 bytes, SHA-256
`0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5`로 일치했다. 기존 request manifest
`data/raw/tabular/9594fab099de46d89bac7ba97a26b8e1/request.json`의 SHA-256은
`ca5ccd38d6856aa8c832db9d6b45351b8bf12a352435e725401aa791eb3c243e`였다.
일치하는 기존 성공 qualification을 사용했으며 새 baseline이나 원격 다운로드를 만들지 않았다.

## 실제 실행 결과

통합 HEAD `dfdfa307534c504f8c740fe1a154a7ba47945e10`에서 다음 명령을 한 번 실행했다.

```text
python -m macro_data_platform.cli --project-root /workspace/MacroAtlas large-run \
  e65971b7b561a0774c786938334a86e59d49a3e0d2c6432148d58a9a3ee27824 \
  --event-seq 1 --approve-production
```

- child task `c244a486-17e5-4b60-a82b-287f8a37bbe7`: `COMPLETED`, task attempt 1회, `materialize` stage 성공.
- 입력 member `WS_GLI_csv_flat.csv`: 24,378 data rows × 21 columns (511,938 cells).
- 산출물은 원본 표현을 문자열로 보존한 JSONL chunk 3개(10,000 + 10,000 + 4,378행)이며 총 10,388,510 bytes다.
- output manifest: `data/large_artifacts/c244a486-17e5-4b60-a82b-287f8a37bbe7/output_manifest.json`, SHA-256
  `bc0e7434765b03aa0dc78e9bae684abd02cfd5e083387ba950697b4a91151e88`.
- chunk SHA-256: `chunk-0001.jsonl` `df83618ab70237a56508646c174cf6ebdf520a2bd38f5173c8b8b6aad1a7dceb`,
  `chunk-0002.jsonl` `8a4df59a80bfab32091b4ed5f03ffd0d4bba62ce320a1c0a0dc5463e96ebec9a`,
  `chunk-0003.jsonl` `8bff65923dcb8943b3d92c6c9f2bce04abafbfab653536a32ff363de835fb6e1`; 전부 manifest와 대조했다.
- 실행 후 inbox raw, archived raw, request manifest 해시는 실행 전 값과 모두 같았다.
- deferral 이력은 `handed_off` → `resolved`로 추가됐고, 완료 event는 child task와 manifest 경로/hash를 가리킨다.
- 출력 품질 범위는 직사각형 CSV 구조와 파일 무결성뿐이다. 의미·단위·빈도 정규화 또는 Gate C 판정은 수행하지 않았다.

실행 산출물은 `.gitignore` 대상인 `data/large_artifacts/`에 두어 원본·결과 데이터를 Git에 올리지 않았다.

## 검증

- `python -m pytest -o addopts='' -q`: **656 passed**.
- `python -m ruff check src tests`: 통과.
- `git diff --check`: 통과.
- PR #6 CI: run [`40369653182`](https://github.com/jaeu983-lang/MacroAtlas/actions/runs/40369653182)와
  [`40369693950`](https://github.com/jaeu983-lang/MacroAtlas/actions/runs/40369693950)에서 Ubuntu/Windows ×
  Python 3.11/3.12 네 조합 모두 통과.
- fixture는 승인·qualification/hash binding, source 변경 차단, 문자열 출력, manifest 무결성,
  checkpoint 재개, 미지원 OS의 미실행 응답을 확인했다.
- production 실행 뒤 manifest·세 chunk 해시, task attempt/stage, deferral event lifecycle 및 원본 해시를 다시 읽어 확인했다.

## 남은 일과 해석 경계

이 회차에서 BIS GLI flat 보존본의 제한된 구조 materialization과 상태 추적은 실제 실행으로 완료했다. 이는
다른 기관·파일의 정식 처리를 열지 않으며 World Bank/BOJ 관측값 CSV exporter와는 별도다. 검증된 World Bank/BOJ
task의 사용자 전달용 CSV exporter는 다음 제품 회차로 남는다. Windows 자원 제한 worker, 더 큰 입력, 새로운 포맷도
현재 지원 범위 밖이다.

Gate C는 기존 제한 범위를 유지한다. 이번 로컬 보존본 처리는 TIC/BIS exact-scope 자연 원자료 변경 비교가 아니며
자연 provider 장애도 발생하지 않았다. 따라서 실제 변경 쌍과 자연 장애 후 같은 task/stage 재개는 계속 미관측이다.
