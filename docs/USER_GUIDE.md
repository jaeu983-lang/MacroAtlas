# MacroAtlas 사용자 안내서

기준일: **2026-10-28**. 현재 사용자 명령은 [`cli.py`](../src/macro_data_platform/cli.py), 대용량 용량 판정은
[`capacity.py`](../src/macro_data_platform/capacity.py) 및 [구현 현황](IMPLEMENTATION_PLAN.md)과 대조했습니다.

제품 범위·정책·작업 순서는 [통합 제품 기획](../PROJECT_PLAN.md), 실제 Gate 및 구현 상태는
[구현 현황](IMPLEMENTATION_PLAN.md), 실행 경계는 [엔진 연결표](ENGINE_CONNECTIONS.md)와
[엔진별 구현·접근 한계](ENGINE_IMPLEMENTATION_STATUS.md)를 기준으로 합니다. 개발 절차는
[개발자 안내서](DEVELOPER_GUIDE.md)에 있습니다. 축약된 옛 계획 문서는 색인이고, 회차 보고서는 작성 당시 증거입니다.

MacroAtlas는 Python 기반 국제통계 자료 탐색·수집 도구입니다. 고정된 World Bank 경로, BOJ의 단일
시계열, TIC/BIS 지정 파일 intake를 위한 구조화 CLI를 제공합니다. 일반 자연어 해석, 대화형 UI,
기관 전반 검색과 제품 자체 무인 스케줄링은 제공하지 않습니다. TIC/BIS 변경상태의 반복 확인은 현재 필요하지
않다는 요청에 따라 중지했으며, `watch` 명령은 사용자가 단발 실행을 요청할 때만 사용합니다.

처음 사용하는 경우 아래 순서로 진행하세요.

1. `macroatlas --help`로 현재 설치본이 제공하는 명령을 확인합니다.
2. 지원하는 기관·지표·기간인지 확인한 뒤 예시의 범위만 바꿉니다.
3. 실제 외부 요청 명령에는 `--live`를 붙입니다. 요청은 task ID를 먼저 저장하고 실행합니다.
4. 출력의 상태를 읽습니다. `COMPLETED`는 해당 제한 경로 완료, `NEEDS_REVIEW`는 검토 대기,
   `FAILED_RETRYABLE`은 같은 task 재개 검토, `NOT_EXECUTED`는 본 처리가 시작되지 않았음을 뜻합니다.
5. 완료된 지원 task는 JSON 요약·저장 artifact를 확인하거나, 로컬 CSV export 명령으로 분석 파일을 생성합니다.
   CSV export는 World Bank/BOJ의 명시 지원 task만 받으며 일반 CSV/XLSX 변환기는 아닙니다.

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
.\.venv\Scripts\macroatlas.exe export <TASK_ID> --format csv --output data/exports/result.csv
```

Linux/macOS에서는 `.venv/Scripts/macroatlas.exe` 대신 `macroatlas`를 실행합니다. World Bank 명령은
미국 GDP(current US$), WDI source 2, `NY.GDP.MKTP.CD`만 지원하며 1~10개 연도 범위로 제한됩니다.
BOJ 명령은 FM08/FXERD01의 한 달만 지원합니다. TIC/BIS `watch`는 지정된 공식 파일 URL과 기존 parser
범위만 확인합니다. 자동 예약 실행은 없고 현재 반복 감시도 중지된 상태입니다. 명령은 URL이나 임의 기관을
입력받지 않습니다.

각 실행은 JSON 요약에 task ID, 상태, stage, 품질 상태, 저장 경로를 표시합니다. `status`는 네트워크를
사용하지 않고 task를 조회합니다. transient 실패가 생기면 프로세스를 다시 연 뒤 같은 task ID로
`resume`하세요. 서버가 `Retry-After`를 제공하면 Orchestrator가 대기시간 이전 resume을 차단합니다.
`NEEDS_REVIEW`는 원인을 확인하고 사람이 재개를 승인할 때만 `--approve-review`를 추가합니다. 이 flag는
승인 기록이며 원인 해결이나 데이터 검증을 대신하지 않습니다. `--live`는 저장된 외부 요청을 다시 허용합니다.
자동 재시도는 없습니다. 전체 옵션은 [CLI parser](../src/macro_data_platform/cli.py)를 확인하세요.

## 검증된 task를 CSV로 저장하기

완료된 World Bank USA GDP 또는 BOJ FM08/FXERD01 task의 ID로 export합니다. 이 명령은 SQLite task 이력,
품질 기록, raw 응답과 request manifest를 읽어 무결성과 지원 범위를 확인하고, 네트워크 요청 없이 CSV와
`<파일명>.provenance.json`을 `data/exports/`에 새로 만듭니다. 같은 경로가 이미 있으면 덮어쓰지 않습니다.

```powershell
.\.venv\Scripts\macroatlas.exe export <TASK_ID> --format csv --output data/exports/result.csv
```

CSV는 UTF-8이고 날짜·값·결측 상태, 기관·dataset/series, 단위·주기, 조회 시각, source URL, raw와 manifest의
상대 경로·SHA-256, source 변경 상태를 담습니다. `null`은 빈 값과 `value_status=missing`으로 구분하며 0은
문자열 `0`으로 남깁니다. 원본 값은 반올림·보간하지 않습니다. 단위나 주기가 원자료에서 확인되지 않으면
빈 칸으로 둡니다. sidecar에는 검증 품질 요약, task/stage 이력, CSV hash와 source manifest의 검증 수준을
기록합니다. BOJ request manifest에는 저장 당시 manifest 자체의 digest가 없으므로, export 시 manifest 필드와
raw hash를 검증했다는 점을 sidecar에 명시합니다.

미완료·미지원 task, 품질 미통과, source가 `changed` 또는 비교 불가인 경우, 손상된 파일·manifest,
경로 탈출·symlink는 export하지 않습니다. 결과와 sidecar는 로컬 산출물이고 Git에 포함되지 않습니다.

World Bank 이전 검증 스크립트도 유지됩니다.

```text
python scripts/verify_worldbank.py --live --gate-a
```

이 경로는 HTTPS, 설정된 HTTP(S) 프록시와 CA bundle, TLS 검증, timeout, redirect 차단, 자동 재시도
없음, 1 MiB 응답 상한을 사용합니다. 단위·주기, 경제 이상치, 개정 역사, 기관 간 동등성은 이 검증 범위가
아닙니다. `source_change_status=first_observation`은 과거 원본과의 변경 비교를 뜻하지 않습니다.

## 결과와 이력 확인

- 원본·요청 manifest: source별 `data/raw/` 하위. 정확한 저장 경로는 각 실행의 JSON 요약에 표시됩니다.
- task, stage, attempt/event 이력: `data/catalog.sqlite`
- Gate A legacy 검증 스크립트를 직접 실행한 경우에만 별도 `reports/iteration_04_live_<id>.json`이 생성됩니다.

`data/`, `reports/`의 실행 산출물은 Git에 포함되지 않습니다. 원본 응답은 정규화된 관측치와 별도이며,
원본 hash와 manifest를 확인한 뒤 SQLite 검증 기록의 `status`, `issues`, `warnings`, 요청·관측 기간을
검토합니다. 전체 통계 이상치, 시계열 개정 역사, 다른 기관 자료와의 통계적 동등성은 이 고정 검증기의
검사 범위가 아닙니다. World Bank 이용 조건은 자료별로 확인해야 하며, 이 도구가 재배포 권한을
보증하지 않습니다.

표 형식 자료는 `data/inbox/` 아래 명시적으로 선택한 기존 파일을 Python API의
`TabularFileEngine`으로 처리할 수 있습니다. 자동 파일 탐색과 일반 파일 가져오기 CLI는 없습니다. 지원된
World Bank/BOJ task CSV export 외의 범용 CSV/XLSX 변환기는 제공하지 않습니다. 파일 형식·시트·ZIP member가
모호하면 `NEEDS_REVIEW`로 멈춥니다.

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

## Codex 사용

Codex 데스크톱에서 이 저장소 작업을 요청할 수 있지만, MacroAtlas에 별도 채팅 UI나 ChatGPT 계정
연동이 들어 있는 것은 아닙니다. 예를 들어 “`python -m pytest -o addopts=''`를 실행하고 실패를
설명해줘”처럼 요청하면 작업 도구가 현재 저장소에서 해당 명령을 실행합니다. 실제 수집은 외부 요청이므로
요청 범위, 키 사용 여부, 산출물 경로를 확인하고 명시적 실행 지시를 하세요.

## 비API 대용량 인계 목록

파일 크기·행·셀·압축 한도에 도달하면 NEEDS_REVIEW로 중단하고 SQLite 인계 목록에 남깁니다.
`macroatlas deferred`로 최대 100건, `macroatlas deferred ID`로 해당 대상의 최근 판정 이력을 조회합니다.
API 수집은 이 분류 대상이 아닙니다. 인계 목록 등록 후 별도 대용량 엔진은 자동 실행되지 않습니다.
판정의 공통 자료형은 [`CapacityFinding`](../src/macro_data_platform/capacity.py)이며, 인계 흐름은
[`non_api_capacity.py`](../src/macro_data_platform/ingestion/non_api_capacity.py)에 있습니다.

## 대용량 후보의 격리 시험

`macroatlas large-check <DEFERRAL_ID> [--event-seq N]`으로 저장된 후보를 명시적으로 시험합니다.
Linux에서 입력 128 MiB 미만·출력 192 MiB 미만·가상 메모리 384 MiB·CPU 15초·wall 20초로 제한합니다.
지원 파일은 UTF-8 CSV/TSV/TXT·ZIP 단일 표이며, 애매한 TXT 구분자는 시험 시 추정 여부를 표시합니다.
실패·예산 초과·격리 미지원 환경은 `NOT_EXECUTED`와 `미실행: <이유>`를 반환합니다.
시험이 중간에 멈춘 경우 trial_attempted=true로 표시합니다. 원본을 삭제하지 않고 시험 scratch만 정리합니다.
`TRIAL_PASSED`도 본 실행 승인이 아니며 production_execution=NOT_EXECUTED입니다.
같은 후보·코드·예산은 기존 결과를 반환하고 원본이 바뀌면 재사용하지 않습니다.
상세 조사·실측·한계는 [대용량 엔진 설정](LARGE_FILE_ENGINE.md)을 참조하세요.

### 실행 전 예상 시간

`large-check`와 승인된 `large-run`은 task를 저장한 뒤 worker를 시작하기 직전에 예상 시간, 예상 범위, 신뢰도,
비슷한 성공 실측 수, worker 제한 시간을 stderr로 알립니다. 결과 JSON에는 사용된 예측과 완료된 stage의 실제
경과 시간(`actual_stage_seconds`)이 포함됩니다. 예상은 대용량 stage 실행 시간이며, 사람 검토와 별도 준비 시간은
포함하지 않습니다. 실측이 적거나 입력 표본이 불완전하면 신뢰도 `low`와 넓은 범위를 표시합니다.
범위는 저장된 이력과 표본에서 만든 작업 추정이며, 완료 시간을 보증하는 통계적 신뢰구간은 아닙니다.

작업 없이 미리 확인할 때는 다음 명령을 씁니다.

```text
macroatlas large-estimate qualification <DEFERRAL_ID> [--event-seq N]
macroatlas large-estimate production <DEFERRAL_ID> --event-seq <N>
macroatlas large-estimate resume <PRODUCTION_TASK_ID>
```

이 명령은 task/event를 만들지 않고 로컬 DB와 입력 파일을 읽기만 합니다. 예상 시간이 worker 상한을 넘을 수 있다고
표시해도 예산을 늘리거나 자동으로 별도 엔진에 보내지 않습니다. 실제 `large-check` 결과와 production의 동일 raw
qualification·`--approve-production` 승인 조건을 그대로 따릅니다. 예측 모델은 각 엔진의 성공 task stage 시간으로
보정하며, baseline과 유사 실측 예측을 모두 저장해 실제 결과와 shadow 비교합니다. 오차가 더 낮은 후보를 충분한
paired 실측 후 선택하며, 무작위 production A/B 실험은 하지 않습니다.

### BIS flat 파일의 별도 대용량 실행

현재 별도 production 경로는 BIS GLI flat ZIP 한 건만 지원합니다. 보존 원본의 단일 실행은 child task
`c244a486-17e5-4b60-a82b-287f8a37bbe7`에서 성공했고, 24,378행·21열의 구조 보존 JSONL을 만들었습니다.
실행 전 불변 event 순번을 확인하고,
일치하는 raw/hash qualification이 있어야 합니다. `--approve-production`은 별도 실행 승인을 뜻합니다.

```text
macroatlas deferred <DEFERRAL_ID> --events
macroatlas large-run <DEFERRAL_ID> --event-seq <SEQ> --approve-production
macroatlas status <CHILD_TASK_ID>
macroatlas large-resume <CHILD_TASK_ID>
```

Linux에서 입력 128 MiB, 출력 192 MiB, 메모리 384 MiB, CPU 30초, wall 60초 상한의 worker가
원본 값을 문자열로 보존한 JSONL chunk를 생성합니다. 원본과 요청 manifest는 변경하지 않습니다.
완료 manifest는 구조·출처·hash만 검증하며 통계 단위·빈도·경제적 의미를 판정하지 않습니다.
Windows나 미지원 포맷은 실행하지 않습니다. 결과 artifact는 `data/large_artifacts/` 아래에 남습니다.
이 JSONL은 현재 CSV exporter 입력이 아니며, 범용 CSV/XLSX export도 제공하지 않습니다.
