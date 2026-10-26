# MacroAtlas

MacroAtlas는 공식 거시·금융 통계를 **요청한 범위 그대로 수집하고, 원본·근거·검증 이력을 함께 남기는**
Python 프로젝트입니다. 모든 기관을 자동 검색하는 챗봇보다, 지원 경로의 결과를 재현하고 불확실한 값은
안전하게 멈추는 데 먼저 집중합니다.

현재 진입점은 고정 범위 구조화 CLI와 Python API입니다. 자연어 채팅 UI, 기관 전체 검색, 정식 대용량
정규화, CSV/XLSX exporter는 완료된 제품 기능이 아닙니다. 비API 대용량 후보는 격리 qualification을 할 수
있지만, 시험 통과는 production 실행 승인이 아닙니다.

## 지금 시작하기

- 사용자는 [사용자 안내서](docs/USER_GUIDE.md)를 확인하세요.
- 개발자는 [개발자 안내서](docs/DEVELOPER_GUIDE.md)와 [개발 환경 설치](docs/INSTALLATION.md)를 따르세요.
- 다음 제품 우선순위는 [로드맵](docs/ROADMAP_2026_10_26.md), 목표 구조는
  [제품 및 시스템 아키텍처](docs/PRODUCT_ARCHITECTURE.md)를 보세요.
- 현재 Gate와 실제 검증 상태는 [구현 상태](docs/IMPLEMENTATION_PLAN.md), 미해결 원인 분류는
  [미해결 항목](docs/UNRESOLVED_ITEMS.md)를 기준으로 합니다.
- 전체 문서의 역할과 과거 보고서 읽는 법은 [문서 안내](docs/README.md)에 있습니다.

## 현재 지원 경로

- World Bank WDI: 미국 GDP `NY.GDP.MKTP.CD`, source 2, 1~10개 연도.
- BOJ: FM08/FXERD01 한 달.
- TIC/BIS: 지정한 공식 파일의 exact-scope watch.
- 제한된 BLS/Census connector는 Python API 경로이며 고정 `macroatlas` CLI 수집 명령은 아닙니다.
- task 상태 확인·같은 task 재개와 비API 파일 인계 목록·제한 격리 시험을 제공합니다.

Gate A/D는 해당 범위에서 통과, Gate B/C와 E는 제한 범위 판정입니다. TIC/BIS 자연 원자료 개정 및
자연 provider 장애 뒤 같은 task의 durable resume은 아직 실측 증거가 없습니다. 이 문구는 현재 검증한
범위를 뜻하며 다른 기관의 서버 상태를 진단하는 말이 아닙니다.

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
```

Windows PowerShell 설치 명령, task·오류·결과 확인, 보안과 데이터 한도는 [사용자 안내서](docs/USER_GUIDE.md)에
있습니다. 코드 검사 절차는 [개발자 안내서](docs/DEVELOPER_GUIDE.md)에 있습니다.

## 데이터와 상태 안전

`data/raw/`, `data/processed/`, SQLite DB와 live 수집 결과는 로컬 산출물입니다. 원본을 덮어쓰지 않고,
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
