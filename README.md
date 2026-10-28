# MacroAtlas

MacroAtlas는 공식 거시·금융 통계를 **요청한 범위 그대로 수집하고, 원본·근거·검증 이력을 함께 남기는**
Python 프로젝트입니다. 모든 기관을 자동 검색하는 챗봇보다, 지원 경로의 결과를 재현하고 불확실한 값은
안전하게 멈추는 데 먼저 집중합니다.

현재 진입점은 고정 범위 구조화 CLI와 Python API입니다. 자연어 채팅 UI, 기관 전체 검색, 정식 대용량
정규화, 범용 CSV/XLSX exporter는 제공하지 않습니다. 완료·검증된 World Bank/BOJ task에 한정한 CSV 전달은
지원합니다. 비API 대용량 후보는 격리 qualification을 할 수
있지만 시험 통과는 production 실행 승인이 아닙니다. 별도로 명시 승인·같은 raw qualification을 요구하는
BIS GLI flat ZIP 한 건 전용 Linux 경로가 구조 보존 JSONL을 만들며, 의미 정규화나 일반 CSV 전달을 제공하지 않습니다.

## 지금 시작하기

- 사용자는 [사용자 안내서](docs/USER_GUIDE.md)를 확인하세요.
- 개발자는 [개발자 안내서](docs/DEVELOPER_GUIDE.md)와 [개발 환경 설치](docs/INSTALLATION.md)를 따르세요.
- 통합 제품 범위·정책·남은 순서는 [제품 기획](PROJECT_PLAN.md), 현재 Gate와 검증 증거는
  [구현 현황](docs/IMPLEMENTATION_PLAN.md)을 기준으로 합니다.
- 실제 호출 경계와 기관별 접근 제한은 [엔진 연결표](docs/ENGINE_CONNECTIONS.md),
  [엔진 구현·데이터 접근 한계](docs/ENGINE_IMPLEMENTATION_STATUS.md)에 정리했습니다.
- 전체 문서의 역할과 과거 보고서 읽는 법은 [문서 안내](docs/README.md)에 있습니다.

## 현재 지원 경로

- World Bank WDI: 미국 GDP `NY.GDP.MKTP.CD`, source 2, 1~10개 연도.
- BOJ: FM08/FXERD01 한 달.
- TIC/BIS: 필요할 때 명시적으로 실행하는 지정 파일 intake. 자료 변경상태의 반복·예약 확인은 사용자
  요청에 따라 중지했다.
- BIS GLI flat ZIP: 같은 원본 qualification과 별도 승인을 통과한 보존 파일 한 건을 구조 보존 JSONL로 처리.
- BLS Public Data API v2와 Census ACS는 정확한 series/variable ID를 지정하는 제한 CLI·Python API 경로를 제공합니다.
- task 상태 확인·같은 task 재개와 비API 파일 인계 목록·제한 격리 시험을 제공합니다.
- 비API 대용량 qualification과 BIS production 실행은 worker 시작 직전에 예상 시간·범위·신뢰도·실측 수를 표시합니다.
  `large-estimate` preview는 task를 만들거나 실행하지 않고 예측만 확인합니다.

고정 v2 catalog 검색 범위의 제품 Gate C는 development/validation, 확인 경계 trace, 성능 예산과
일회 holdout 판정을 통과했습니다. 후보 정책은 평가 전용으로 남아 있고 자동 승격되지 않습니다.
이 Gate는 provider API, raw writer, exporter 내부 동작을 실행하지 않습니다. 결과는
[holdout 보고서](evaluation/results/gate_c_holdout_result.json), [구현 현황](docs/IMPLEMENTATION_PLAN.md),
[통합 제품 기획](PROJECT_PLAN.md)에서 확인하세요. Gate 상태는 기관 서버의 현재 가용성을 뜻하지 않습니다.

## 설치와 첫 명령

Python 3.11 이상에서 저장소 루트에 설치합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/macroatlas --help
```

실제 수집은 명시적으로 `--live`가 필요합니다. 예를 들어 지원하는 World Bank 범위는 다음과 같습니다.

```bash
.venv/bin/macroatlas collect worldbank-gdp --start-year 2020 --end-year 2022 --live
.venv/bin/macroatlas status <TASK_ID>
.venv/bin/macroatlas export <TASK_ID> --format csv --output data/exports/worldbank.csv
```

정확한 API 식별자를 알고 있으면 BLS와 Census ACS도 CLI로 수집할 수 있습니다. 기관 전체 검색이나
식별자 의미의 자동 판정은 포함하지 않습니다. 명령 형식·범위·API key 설정은
[사용자 안내서](docs/USER_GUIDE.md)를 참조하세요.

비API 대용량 작업의 예측만 확인하려면 `macroatlas large-estimate qualification <DEFERRAL_ID>` 또는
`macroatlas large-estimate production <DEFERRAL_ID> --event-seq <SEQ>`를 사용합니다. production 실행 전 예상은
qualification과 별도 명시 승인 조건을 대신하지 않습니다. 예측은 성공한 같은 엔진 task의 실측 시간을 축적하며,
이력이 적으면 낮은 신뢰도와 넓은 범위를 표시합니다. 상세 한도와 해석은 [사용자 안내서](docs/USER_GUIDE.md)를 보세요.

`export`는 저장된 완료 task만 로컬에서 검증해 CSV와 provenance sidecar를 생성하며 네트워크를 사용하지
않습니다. 기존 World Bank/BOJ 지원 범위와 파일 필드는 [사용자 안내서](docs/USER_GUIDE.md)를 확인하세요.

Windows PowerShell 설치 명령, task·오류·결과 확인, 보안과 데이터 한도는 [사용자 안내서](docs/USER_GUIDE.md)에
있습니다. 코드 검사 절차는 [개발자 안내서](docs/DEVELOPER_GUIDE.md)에 있습니다.

## 데이터와 상태 안전

`data/raw/`, `data/processed/`, `data/exports/`, SQLite DB와 live 수집 결과는 로컬 산출물입니다. 원본을 덮어쓰지 않고,
동일 범위의 원본이 바뀌면 이전·새 원본을 보존하며 검토 전 새 normalized 출력을 차단합니다. transient 실패는
저장된 동일 task로 `Retry-After`와 시도 예산을 지켜 재개합니다. 실제 키는 저장소·문서·로그에 넣지 않습니다.

## 개발 및 검수

```bash
python -m pytest
python -m ruff check src tests
git diff --check
```

테스트 통과만으로 모든 provider나 Gate 전체를 통과 처리하지 않습니다. 회차 보고서와 날짜가 붙은 실측은
그 당시 증거 기록이며 현재 기능 범위는 사용자 안내서와 구현 상태표에서 확인하세요.
