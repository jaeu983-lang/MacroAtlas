# 15회차 후속 — 네 갈래 검증·사용 경로 보완

기준일: 2026-10-26
범위: Gate C live watch 준비·실측, BOJ 한 시계열 collector, 구조화 CLI, Windows CI

## 결과

### 1. Gate C live watch

`macroatlas watch tic|bis --live`는 task/stage를 SQLite에 저장한 다음 공식 고정 URL에 GET 한 번을
보낸다. 응답은 기존 `TabularFileEngine` exact parser scope에 넣고 이전 raw/manifest와 비교한다.
서버의 retryable HTTP/transport 오류와 `Retry-After`는 stage 결과에 저장한다. 다음 실행은 같은 task ID로
`macroatlas resume <TASK_ID> --live`를 사용한다. 자동 retry는 없다.

2026-10-26 live 결과:

| Source | Task | Result | Comparison |
|---|---|---|---|
| TIC Table 5 | `dd5fc688-cdf7-4171-9e81-5f8992d3ae49` | HTTP 200, 36 × 14 | `unchanged`; raw/normalized hashes match baseline |
| BIS column ZIP | `395102cd-94e0-4001-86f8-bba0310ea5b9` | HTTP 200, 225 × 220 | `unchanged`; raw/normalized hashes match baseline |

두 요청 중 natural provider failure나 source revision은 발생하지 않았다. 그러므로 natural
failure→same-task resume와 changed live source 쌍은 계속 `NOT_RUN`이다. 자동 통합 fixture의 503/resume은
simulated evidence이며 Gate C의 D-067 제한 통과 범위도 변경하지 않는다. 상세: [source watch 기록](GATE_C_SOURCE_WATCH.md).

### 2. BOJ 제한 collector

BOJ `FM08/FXERD01`의 metadata와 한 달 observation을 각각 하나의 Orchestrator stage로 구현했다.
2026-09 요청은 `getMetadata`와 `getDataCode` 모두 HTTP/JSON STATUS 200이었다. task
`759540fe-3656-42d6-bbef-3d3f05f4a5f4`는 완료됐고 30개 날짜/값 중 11개 null을 그대로 보존했다.
raw hash는 `69a5d137e7b05e12e06ccd12059f24d98a4669b966bc05778058f2c48da275dc`이며 첫 collector capture여서
`source_change_status=first_observation`이다. 동일-request comparison에서는 응답의 동적 `DATE`만 제외하고
raw bytes/hash는 보존한다.

고정 series·한 달 외에는 거부한다. 변경 응답은 raw/manifest만 보존하고 `NEEDS_REVIEW`로 멈춘다. 단위,
주기와 경제적 outlier는 metadata 표시·구조 검사 외 판단하지 않는다. 상세: [BOJ connector](connectors/BOJ.md).

### 3. 구조화 CLI

설치 명령 `macroatlas`는 다음 경로와 task 동작을 제공한다.

- `collect worldbank-gdp --start-year ... --end-year ... --live`: 기존 confirmed workflow와 Gate A validation.
- `collect boj-fxer --month YYYYMM --live`: 제한 BOJ collector.
- `watch tic|bis --live`: exact-scope official file request.
- `status TASK_ID`: 로컬 조회 전용.
- `resume TASK_ID --live [--approve-review]`: 저장된 plan과 같은 task로 명시 재개.

일반 자연어 해석, 임의 URL, 전체 기관 검색, 자동 예약은 포함하지 않는다. 2026-10-26 World Bank CLI live
task `d853ce18-5ddf-4d1a-b2f4-789e087c6321`는 HTTP 200, 3 observations, quality `passed`,
`source_change_status=unchanged`로 완료됐다.

### 4. Gate E / Windows validation

`.github/workflows/ci.yml`은 Linux/Windows의 Python 3.11/3.12에서 full pytest, Ruff 및 설치된 CLI help를
검증하도록 추가했다. 로컬 Linux 검증은 전체 **609 tests passed**, Ruff 통과, `git diff --check` 통과다.
설치된 entry point의 `macroatlas --help`와 `macroatlas collect --help`도 실행했다. PR CI run
[`40336575209`](https://github.com/jaeu983-lang/MacroAtlas/actions/runs/40336575209)의 네 조합
(Ubuntu/Windows × Python 3.11/3.12) 모두 full test suite, Ruff, CLI help까지 통과했다.

첫 PR workflow에서는 Windows가 환경변수 이름의 대소문자를 구분하지 않는다는 점과 충돌하는 테스트
설정이 드러났다. 테스트가 `HTTP_PROXY`와 `http_proxy`에 서로 다른 값을 동시에 넣지 않도록 고친 뒤
재실행해 전체 네 조합이 통과했다.

## 변경 파일

- `src/macro_data_platform/connectors/boj.py`, `ingestion/boj.py`: verified series query, metadata/data parser,
  raw archival, quality guard, durable two-stage Orchestrator path.
- `src/macro_data_platform/storage/statistical_downloads.py`: BOJ canonical compare ignoring only volatile
  top-level `DATE`, while keeping original raw hashes.
- `src/macro_data_platform/connectors/official_files.py`, `ingestion/gate_c_watch.py`: proxy/CA-aware bounded
  TIC/BIS file transport and persist-before-request source watcher.
- `src/macro_data_platform/cli.py`, `pyproject.toml`: opt-in structured commands and installed `macroatlas` entry.
- `.github/workflows/ci.yml`: Linux/Windows Python CI.
- tests and user/connector/gate documentation describe fixture, live and unsupported boundaries separately.

## 한계와 안전성

Natural source revision과 natural provider failure/resume을 인위적으로 만들지 않았다. 이번 요청에서 둘 다
발생하지 않아 더 넓은 Gate C evidence는 미충족이다. Gitignored raw/SQLite/report 산출물은 로컬에 남고 Git에
포함되지 않는다. 이 작업은 실행 환경 publish/deploy를 수행하지 않는다. 일반 Windows 대화형 workflow,
다른 BOJ series, 기타 기관 전체 지원, natural-language interface는 미구현이다.
