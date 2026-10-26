# MacroAtlas

MacroAtlas는 국제금융·거시경제 통계를 공식 출처에서 찾고, 의미와 수집 결과를 근거와 함께
보존하는 Python 프로젝트입니다. 현재 사용 인터페이스는 Python API와 범위가 고정된 구조화
CLI이며 자연어 채팅 제품은 아직 없습니다.

## 현재 상태

2026-10-26 기준, Gate A 통과, Gate B/C는 **제한 범위 통과**, Gate D 통과,
Gate E는 **제한 범위 로컬 v1 검토 통과**입니다. Gate C의 자연 원자료 개정 및 실제 provider 장애 후
재개는 검증하지 않았습니다. 현재 확인된 사용자 경로와 구현·인계·미관측 범위는
[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)와
[`docs/GATE_REAUDIT_AFTER_ITERATION_16.md`](docs/GATE_REAUDIT_AFTER_ITERATION_16.md)를 참조하세요.

MacroAtlas는 고정된 World Bank USA GDP 수집, BOJ FM08/FXERD01 월별 수집, TIC/BIS exact-scope
파일 감시, task status/resume를 위한 `macroatlas` CLI를 제공합니다. 일반 자연어 검색, 자체 채팅 UI,
기관 전반 자동 검색은 지원하지 않습니다. 제한 BLS/Census API 부품, 명시 파일 파서,
task-linked feedback CLI와 read-only pattern CLI도 제공합니다. 게이트의 현행 상태와 다음 허용 작업은
[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md), 시나리오별 증거는
회차 보고서를 기준으로 합니다.

## 어디서 무엇을 볼까

- [`START_HERE.md`](START_HERE.md): 현재 저장소에서 작업을 시작하는 순서
- [`PROJECT_PLAN.md`](PROJECT_PLAN.md): 제품 범위와 정책 요구사항
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md): 완료 상태, 게이트, 다음 허용 작업의 단일 기준
- [`docs/INSTITUTION_CATALOG.md`](docs/INSTITUTION_CATALOG.md): 공식 기관 자료와 확인 한계
- [`docs/REFERENCE_SCENARIOS.md`](docs/REFERENCE_SCENARIOS.md): 제품 수용 시나리오
- [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md): 변경 선택의 이력
- [`docs/PLAN_IMPLEMENTATION_AUDIT.md`](docs/PLAN_IMPLEMENTATION_AUDIT.md): 2026-10-26 계획 정합성 점검 기록
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md): 설치와 현재 지원 경로 안내
- [`docs/MacroAtlas_User_Guide.pptx`](docs/MacroAtlas_User_Guide.pptx): 사용자 안내 요약

## 설치와 검사

Python 3.11 이상을 사용합니다. Windows PowerShell에서는 다음과 같이 설치합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\macroatlas.exe --help
```

Linux/macOS에서는 가상환경을 만든 뒤 `python -m pip install -e ".[dev]"`,
`python -m pytest`, `python -m ruff check src tests`를 실행합니다.

## 지원 범위와 보안

수집기는 명시적으로 계획된 World Bank GDP, BLS Public Data API, Census ACS 경로를 지원합니다.
외부 API는 설정과 등록된 엔진이 있어야 실행됩니다. BLS 일반 시계열 조회 키는 선택 사항이고,
BLS의 `catalog=true` 메타데이터 조회는 등록 키를 요구합니다. Census Data API는 공식 안내에 따라
`CENSUS_API_KEY`가 필요합니다. `.env.example`은 이름 예시일 뿐이며 자동 `.env` 로더는 없습니다.
실제 키는 채팅, 저장소, 원본 응답, 로그에 넣지 마세요.

`data/raw/`, `data/processed/`, SQLite DB는 로컬 산출물이며 Git에서 제외됩니다. 환경 설정이나
게시, 원격 push는 이 저장소 변경만으로 자동 수행되지 않습니다.
