# 20회차 보고서 — 검증된 task의 CSV 전달

기준일: 2026-10-26. 목표는 완료·품질 통과된 World Bank USA GDP 및 BOJ FM08/FXERD01 task를
네트워크 없이 CSV와 provenance sidecar로 전달하는 것이다. 이 결과는 source 수집이나 통계 의미 검증을
추가하지 않으며 Gate C 판정을 바꾸지 않는다.

## 구현

- `macroatlas export TASK_ID --format csv --output data/exports/name.csv`를 추가했다.
- exporter는 HistoryStore를 열지 않고 SQLite read-only/query-only 연결로 task와 Gate A audit evidence를 읽는다.
  완료 상태, 고정 provider/series, stage·engine version, quality, normalized history, raw/manifest hash와 요청
  범위를 재검증한 후 저장된 raw를 다시 파싱해 값이 기록과 일치하는지 확인한다.
- CSV는 UTF-8이며 날짜, 원본 값, `value_status`, 기관·dataset/series, 단위·빈도, source 정보·hash,
  source-change 상태를 보존한다. null은 빈 값과 `missing`, 숫자 0은 `0`으로 기록한다. unknown unit/frequency는
  빈 칸이며 보정·반올림·보간하지 않는다.
- sidecar는 task/stage attempt lineage, 품질 요약, source raw·manifest 참조와 hash, CSV hash/count를 담는다.
  BOJ manifest는 수집 당시 manifest digest가 task에 저장되지 않아 raw hash와 manifest 필드를 대조한다는
  한계를 명시한다. World Bank manifest digest는 Gate A audit record와 대조한다.
- 출력은 workspace `data/exports/` 아래에서만 허용하고 symlink, traversal, CSV/sidecar 덮어쓰기를 막는다.
  CSV와 sidecar는 임시 파일을 준비한 뒤 no-overwrite hard link로 게시하며 실패하면 부분 게시 파일을 정리한다.
  결과 폴더는 Git ignore 대상이다.
- BIS flat JSONL, 다른 provider, XLSX, 새로운 live 수집·normalize·quality task는 이 명령에서 지원하지 않는다.

## 검증

- Fixture 수용 검사로 World Bank의 0/null/unknown metadata, BOJ의 null 보존, task/stage/quality/source-change
  거부, raw/manifest 변조, traversal/symlink, CSV·sidecar 덮어쓰기, 미완료 task를 확인했다.
- 저장소 전체 pytest **666개 통과**, Ruff, `git diff --check` 통과.
- 실제 보존된 성공 task 두 개를 local export했다. 실행 중 네트워크 요청은 없었다.

| Provider/task | 출력 | 행 / 결측 | CSV / provenance SHA-256 | 원본 / request manifest SHA-256 |
|---|---|---:|---|---|
| World Bank `0f968a54-9855-439c-aaf2-bb7022fb5c8c` | `data/exports/worldbank-usa-gdp.csv` | 3 / 0 | `2fdc918d810cd676eeb5ca0ea106fc991c461e8d37c4953e43442ed3c838f942` / `7637e68cc294c19865ed8ae7556be1d2c4edcf7f0214bdf28ef2df4659684ba6` | `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1` / `c8df61cb996e3a5fa3049bc3a4d7fbe3dc042fd2a6d6d22fc1d4d861359ebaff` |
| BOJ `96f82a80-e84b-4b34-b282-204fb642afae` | `data/exports/boj-fm08-fxer.csv` | 30 / 11 | `e5021e8d8e6009ae2ecfcecdc74e0d4aaa940b78da42a6328864ee512abd1ee8` / `2e8dff24c0dcb2ffe924836de90ceb822780af161ff6f6289f47b862ce31464f` | `51392e2216945a05ed102d209217fd0344f7d78780e23eaf784a0ae3ad193dac` / `86e9b886288a38351dbe4418f4f5459bdef3ffeafd3263706c4f5343d0b0048e` |

두 산출물의 실제 CSV·sidecar hash를 다시 계산했고 각 source raw/manifest hash와 일치했다. export 전후
`data/catalog.sqlite` SHA-256은 바뀌지 않았다. local export 파일은 Git에 포함하지 않는다.

## 판정과 남은 범위

20회차 제한 CSV 전달 기능은 검증됐다. Gate C는 이번 작업의 범위가 아니며 자연 source revision·자연 장애 후
같은 task/stage 재개의 관측 증거는 여전히 없다. 기존 baseline과 Gate C 상태를 수정하지 않았다. 다음 순서는
[제품 로드맵](ROADMAP_2026_10_26.md)의 사용자 업무 흐름 검증이다. XLSX·BIS JSONL 전달·새 provider는
실제 수요와 수용 기준을 정한 뒤 별도 계획으로 다룬다.

구현 commit `cb7fdcd`는 PR [#9](https://github.com/jaeu983-lang/MacroAtlas/pull/9)에서 Ubuntu/Windows ×
Python 3.11/3.12 CI를 통과했다. 실행 `40383805569`와 push 이벤트의 중복 실행 `40383791920`에서 네 조합이
모두 성공했다. 최초 Windows CI는 test의 SQLite connection이 닫히지 않아 임시 폴더 cleanup이 실패했으며,
test helper가 연결을 명시적으로 닫도록 수정한 commit `cb7fdcd`에서 재검증했다.
