# MacroAtlas 사용자 안내서

기준 버전: **16회차 반영 제한 범위 로컬 v1**, 2026-10-26

현재 지원·실측·미관측 상태는 [16회차 이후 재검증](GATE_REAUDIT_AFTER_ITERATION_16.md)을 참조합니다.
14회차 보고서는 당시 검수 기록이며 현재 미해결 목록으로 읽지 않습니다.

MacroAtlas는 Python 기반 국제통계 자료 탐색·수집 도구입니다. 고정된 World Bank 경로, BOJ의 단일
시계열, TIC/BIS 기준 파일 감시를 위한 구조화 CLI를 제공합니다. 일반 자연어 해석, 대화형 UI,
기관 전반 검색과 제품 자체 무인 스케줄링은 제공하지 않습니다. Codex의 별도 일일 감시는 제품 기능과 구분합니다.

## 설치

Python 3.11 이상과 Git을 준비한 뒤 저장소 루트에서 실행합니다.

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

로컬 회귀 검사는 다음과 같습니다.

```text
python -m pytest -o addopts=''
python -m ruff check .
git diff --check
```

설치된 명령의 지원 범위는 `macroatlas --help`로 확인할 수 있습니다.

## 구조화 CLI로 지원 경로 실행하기

`macroatlas`는 각 요청을 SQLite에 먼저 저장하고, `--live`가 있을 때만 외부 요청을 보냅니다.
현재 지원 범위와 문서화된 예시는 다음과 같습니다.

```powershell
.\.venv\Scripts\macroatlas.exe collect worldbank-gdp --start-year 2020 --end-year 2022 --live
.\.venv\Scripts\macroatlas.exe collect boj-fxer --month 202609 --live
.\.venv\Scripts\macroatlas.exe watch tic --live
.\.venv\Scripts\macroatlas.exe watch bis --live
.\.venv\Scripts\macroatlas.exe status <TASK_ID>
.\.venv\Scripts\macroatlas.exe resume <TASK_ID> --live
```

Linux/macOS에서는 `.venv/Scripts/macroatlas.exe` 대신 `macroatlas`를 실행합니다. World Bank 명령은
미국 GDP(current US$), WDI source 2, `NY.GDP.MKTP.CD`만 지원하며 1~10개 연도 범위로 제한됩니다.
BOJ 명령은 FM08/FXERD01의 한 달만 지원합니다. TIC/BIS `watch`는 지정된 공식 파일 URL과 기존 parser
범위만 확인합니다. 명령은 URL이나 임의 기관을 입력받지 않습니다.

각 실행은 JSON 요약에 task ID, 상태, stage, 품질 상태, 저장 경로를 표시합니다. `status`는 네트워크를
사용하지 않고 task를 조회합니다. transient 실패가 생기면 프로세스를 다시 연 뒤 같은 task ID로
`resume`하세요. 서버가 `Retry-After`를 제공하면 Orchestrator가 대기시간 이전 resume을 차단합니다.
`NEEDS_REVIEW`는 결과를 검토하고 승인한 뒤 `--approve-review`를 붙여야 재개됩니다. 자동 재시도는
없습니다.

World Bank 이전 검증 스크립트도 유지됩니다.

```text
python scripts/verify_worldbank.py --live --gate-a
```

이 경로는 HTTPS, 설정된 HTTP(S) 프록시와 CA bundle, TLS 검증, timeout, redirect 차단, 자동 재시도
없음, 1 MiB 응답 상한을 사용합니다. 단위·주기, 경제 이상치, 개정 역사, 기관 간 동등성은 이 검증 범위가
아닙니다. `source_change_status=first_observation`은 과거 원본과의 변경 비교를 뜻하지 않습니다.

## 결과와 이력 확인

- 원본 응답과 요청 manifest: `data/raw/worldbank/<package-id>/response.json` 및 `request.json`
- task history와 Gate A 검증 기록: `data/catalog.sqlite`
- 실행 요약: `reports/iteration_04_live_<id>.json`

`data/`, `reports/`의 실행 산출물은 Git에 포함되지 않습니다. 원본 응답은 정규화된 관측치와 별도이며,
원본 hash와 manifest를 확인한 뒤 SQLite 검증 기록의 `status`, `issues`, `warnings`, 요청·관측 기간을
검토합니다. 전체 통계 이상치, 시계열 개정 역사, 다른 기관 자료와의 통계적 동등성은 이 고정 검증기의
검사 범위가 아닙니다. World Bank 이용 조건은 자료별로 확인해야 하며, 이 도구가 재배포 권한을
보증하지 않습니다.

표 형식 자료는 `data/inbox/` 아래 명시적으로 선택한 기존 파일을 Python API의
`TabularFileEngine`으로 처리할 수 있습니다. 자동 파일 탐색, 일반 파일 가져오기 CLI, CSV/XLSX exporter는
없습니다. 파일 형식·시트·ZIP member가 모호하면 `NEEDS_REVIEW`로 멈춥니다.

## 기관별 연결 및 API 키

| 접근 경로 | 현재 범위 | 키 정책 |
|---|---|---|
| World Bank WDI | 위에 적힌 미국 GDP 고정 수집 경로 | 키 불필요 |
| BLS Public Data API v2 | 선택한 series ID의 제한된 Python API 수집; metadata와 통계 의미는 별도 확인 | 일반 series-data 조회는 `BLS_API_KEY` 선택 사항. 일부 catalogue 요청은 등록 키 필요 |
| Census ACS API | 제한된 ACS query connector | `CENSUS_API_KEY` 필수 |
| TIC/BIS 파일 | 고정 URL live 재수집·로컬 intake·대용량 인계 목록. BIS flat은 현재 정책에 따라 deferred | API 키 없음 |
| BOJ JSON API | FM08/FXERD01 한 달 metadata·observations collector와 durable task 연결 | 키를 보내지 않음 |
| IMF·BEA·ECB/Eurostat·중국 기관 등의 전체 수집 | 현행 connectors/CLI에 해당 observation 경로가 미구현. 현재 서버 접근 차단 판정이 아님 | 문서·키 설정만으로 수집 성공을 주장하지 않음 |

필요한 키만 승인된 secret manager 또는 현재 프로세스 환경변수로 제공합니다. 프로젝트는 `.env`를
자동 로드하지 않습니다. 키 값은 저장소, 코드, 테스트, URL, 채팅, 문서 예시에 넣지 마세요. 실제 인증
성공은 설정돼 있다는 사실만으로 표시하지 않고 응답 결과로 확인해야 합니다.

## 실패 처리와 안전한 재개

- `FAILED_RETRYABLE` 또는 `TRANSIENT`: 완전한 응답이 보존되지 않았을 수 있습니다. 동일 task와 요청
  범위를 확인하고, 서버가 `Retry-After`를 주면 그 최소 대기시간이 지난 뒤 명시적으로 resume합니다.
  커넥터 내부 자동 재시도는 하지 않습니다.
- `NEEDS_REVIEW`: 인증 거부, redirect, schema drift, 의미/품질 불확실성 등을 검토합니다. 입력이나
  경로를 확인하기 전 강제로 resume하지 않습니다.
- `FAILED_TERMINAL`: 입력 오류 또는 지원하지 않는 경로를 수정한 뒤 새 검증된 작업으로 시작합니다.
- 같은 범위의 원본이 바뀌면 이전·새 raw를 보존하고 검토가 끝날 때까지 새 normalized 출력을 만들지
  않습니다. `null`과 0은 다른 값입니다.

task ID는 외부 수집 전 저장됩니다. 같은 ID로 재개해야 이전 시도와 이력이 이어집니다. 변경된 조건은
새 task로 시작합니다. `watch`는 수동 실행이며 정기 스케줄을 만들지 않습니다. 자연 원본 변경이나
provider 장애가 발생하지 않으면 해당 live 증거는 미확인으로 남습니다.

## 피드백과 개선 제안

먼저 task가 있어야 task에 연결된 피드백을 기록할 수 있습니다. 모듈 명령은 `python -m`으로 실행할 수
있습니다.

```text
python -m macro_data_platform.feedback_cli --project-root . add --task-id <TASK_ID> --text "이 범위에서는 확인한 World Bank source method를 사용" --category source_method --knowledge-kind user_instruction --scope-json '{"institution_id":"worldbank","dataset_id":"2"}'
python -m macro_data_platform.feedback_cli --project-root . list --task-id <TASK_ID>
```

새 피드백은 자동 승인되지 않습니다. 출력된 feedback ID를 검토한 뒤 필요할 때 revision을 지정해
승인·거부·철회합니다.

```text
python -m macro_data_platform.feedback_cli --project-root . review --feedback-id <FEEDBACK_ID> --expected-revision 1 --status accepted --note "범위와 근거를 확인함"
```

반복 패턴 분석은 읽기 전용입니다.

```text
python -m macro_data_platform.pattern_cli --project-root .
```

분석기는 범위가 일치하는 서로 다른 task가 3개 이상일 때만 반복 후보를 만들고, 제안은 항상 `draft`로
남깁니다. task·피드백·원본을 고치거나 코드를 자동 수정하지 않습니다.

## Codex 사용

Codex 데스크톱에서 이 저장소 작업을 요청할 수 있지만, MacroAtlas에 별도 채팅 UI나 ChatGPT 계정
연동이 들어 있는 것은 아닙니다. 예를 들어 “`python -m pytest -o addopts=''`를 실행하고 실패를
설명해줘”처럼 요청하면 작업 도구가 현재 저장소에서 해당 명령을 실행합니다. 실제 수집은 외부 요청이므로
요청 범위, 키 사용 여부, 산출물 경로를 확인하고 명시적 실행 지시를 하세요.

## 비API 대용량 인계 목록

파일 크기·행·셀·압축 한도에 도달하면 NEEDS_REVIEW로 중단하고 SQLite 인계 목록에 남깁니다.
`macroatlas deferred`로 최대 100건, `macroatlas deferred ID`로 해당 대상의 최근 판정 이력을 조회합니다.
API 수집은 이 분류 대상이 아닙니다. 인계 목록 등록 후 별도 대용량 엔진은 자동 실행되지 않습니다.

## 대용량 후보의 격리 시험

`macroatlas large-check <DEFERRAL_ID> [--event-seq N]`으로 저장된 후보를 명시적으로 시험합니다.
Linux에서 입력 128 MiB 미만·출력 192 MiB 미만·가상 메모리 384 MiB·CPU 15초·wall 20초로 제한합니다.
지원 파일은 UTF-8 CSV/TSV/TXT·ZIP 단일 표이며, 애매한 TXT 구분자는 시험 시 추정 여부를 표시합니다.
실패·예산 초과·격리 미지원 환경은 `NOT_EXECUTED`와 `미실행: <이유>`를 반환합니다.
시험이 중간에 멈춘 경우 trial_attempted=true로 표시합니다. 원본을 삭제하지 않고 시험 scratch만 정리합니다.
`TRIAL_PASSED`도 본 실행 승인이 아니며 production_execution=NOT_EXECUTED입니다.
같은 후보·코드·예산은 기존 결과를 반환하고 원본이 바뀌면 재사용하지 않습니다.
상세 조사·실측·한계는 [대용량 엔진 설정](LARGE_FILE_ENGINE.md)을 참조하세요.
