# MacroAtlas 개발자 안내서

기준일: 2026-10-26. 사용자가 실행하는 기능은 [사용자 안내서](USER_GUIDE.md), 구현 순서는
[제품 로드맵](ROADMAP_2026_10_26.md), 목표 구조는 [제품 및 시스템 아키텍처](PRODUCT_ARCHITECTURE.md)를
참조합니다. 과거 보고서의 상태 문구를 현재 구현 여부로 사용하지 않습니다.

## 개발 환경 준비

Python 3.11 이상과 Git을 준비하고 저장소 루트에서 설치합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/macroatlas --help
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\macroatlas.exe --help
```

## 코드 지도

| 경로 | 역할 |
|---|---|
| `src/macro_data_platform/cli.py` | 명시적으로 지원한 구조화 CLI와 고정 진입 경로 |
| `contracts.py`, `workflow_contracts.py`, `workflow_extensions.py` | 요청·근거·결과·선택의 값 계약 |
| `orchestration/` | task plan, stage runner, resume 및 실행 이력 연결 |
| `storage/` | SQLite task, raw-download, feedback, deferred record, artifact 관련 저장 |
| `connectors/` | 기관 전송과 parser adapter |
| `ingestion/` | connector를 실행 가능한 stage/engine으로 연결 |
| `ingestion/csv_export.py` | 완료된 World Bank/BOJ task와 저장 원본을 읽기 전용 검증한 뒤 CSV/provenance 파일 생성 |
| `discovery/` | 근거가 붙은 제한 후보 찾기와 명시 선택 보조 |
| `analysis/` | 기록을 읽는 pattern 분석. 결과는 검토 후보이지 자동 지식이나 코드가 아님 |
| `tests/` | offline fixture, 계약, 상태 전이, 제한된 live 관련 단위 검증 |
| `docs/` | 제품 범위, 실제 상태, 개발 설계, 날짜가 붙은 증거 |

현재 실제 호출표는 [ENGINE_CONNECTIONS.md](ENGINE_CONNECTIONS.md)를, 공통 모델과 초기 구현 이력은
[ARCHITECTURE.md](ARCHITECTURE.md)를 참조합니다.

## 요청에서 결과까지

1. CLI/Python API가 명시된 요청·출력 조건을 검증합니다.
2. 허용 경로는 네트워크나 파일을 처리하기 전에 task와 계획을 영속화합니다.
3. Orchestrator가 등록된 engine/version을 순차로 호출하고 stage 시작·종료 및 attempt/event를 저장합니다.
4. connector는 source별 transport/parser 범위에서 raw와 manifest를 보존하고 검증된 값만 반환합니다.
5. changed, schema/meaning ambiguity, capacity, auth, retryable failure는 구체 상태로 멈춥니다.
6. 성공 결과는 다음 stage에 전달됩니다. 저장된 artifact를 외부로 내보낼 때도 exporter는 검증 상태를 다시 확인해야 합니다.

현재 `export` 경로는 task/stage·quality·raw/manifest 해시를 다시 확인하고 read-only SQLite 연결을 사용합니다.
출력은 `data/exports/` 아래에서 덮어쓰지 않는 CSV/sidecar 쌍으로 생성됩니다. provider별 adapter만 허용하며,
BIS flat JSONL과 임의 provider는 받지 않습니다. BOJ manifest digest는 수집 시 저장되지 않으므로 raw hash와
manifest 필드를 대조하고 해당 한계를 sidecar provenance에 기록합니다.

이 구조는 분산 queue, exactly-once 외부 부작용, 범용 planner를 제공하지 않습니다. 재시도 가능한 외부 요청은
같은 task ID로 명시 재개하고 `Retry-After`와 예산을 준수합니다. 새 요청 범위는 새 task여야 합니다.

## 데이터와 보안 불변 조건

- secret은 코드·테스트 fixture·문서 예시·원본 요청 URL·로그에 넣지 않습니다. `.env`는 자동 로드되지 않습니다.
- `data/`와 실수집 원본은 로컬 산출물입니다. 테스트 원본을 Git에 추가하지 않습니다.
- 같은 source scope가 바뀌면 양쪽 raw와 manifest/hash를 보존하고 검토가 끝날 때까지 새 normalized 결과를 만들지 않습니다.
- API 전송 오류는 parser 오류와 분리합니다. 로컬 용량 한도는 서버 연결 실패가 아닙니다.
- 용량 제한은 상향해 우회하지 않습니다. 작은 parser에서 멈춘 비API 파일은 별도 인계 경로로 갑니다.
- `TRIAL_PASSED`는 qualification 결과이며 production 승인·정규화 완료가 아닙니다.
- `large-run`은 성공한 동일 event/hash qualification, 고정된 BIS flat source scope, 명시 승인 이후에만 child task를 실행합니다.
  현재 이 경로는 Linux에서 BIS GLI flat ZIP 한 건의 문자열 JSONL 출력까지 지원하며 경제 의미를 추론하지 않습니다.
- 대용량 worker는 입력 128 MiB, 출력 192 MiB, 메모리 384 MiB, CPU 30초, wall 60초 예산을 적용하고,
  원본 hash·request manifest·chunk checkpoint를 resume 전에 검증합니다. Windows에서 무제한 fallback을 하지 않습니다.
- 자연 live evidence, fixture, synthetic benchmark, simulated failure는 서로 다른 종류로 기록합니다.

## 로컬 검증

```bash
python -m pytest
python -m ruff check src tests
git diff --check
```

개별 테스트는 해당 테스트 모듈/이름으로 좁힌 뒤 마지막에 전체 suite를 실행합니다. 새 테스트는 사용자에게
보이는 결과 계약, 상태 전이, 안전 경계를 검증해야 합니다. 구현 코드를 그대로 반복하는 테스트만 추가하지 않습니다.
문서 전용 변경은 링크·경로·diff 검사를 수행하고 전체 테스트를 불필요하게 다시 돌리지 않습니다.

외부 수집은 기본 자동 검사가 아닙니다. live 요청에는 대상·scope·키 사용 여부·원본 저장 위치·요청 횟수가
명시돼 있어야 합니다. 네트워크 fixture는 실제 기관 장애나 자연 source revision의 증거가 아닙니다.

## 제품 Gate와 증거

Gate는 해당 범위의 구현·운영 증거가 수용 기준을 충족했는지 판정합니다. 테스트 전체가 통과했다는 사실만으로
Gate가 통과되거나 다른 provider를 지원하게 되지 않습니다. Gate C의 natural revision/recovery는 자연 이벤트를
기다리며 인위적으로 만들지 않습니다. 판정 근거는 [구현 상태](IMPLEMENTATION_PLAN.md), [시나리오](REFERENCE_SCENARIOS.md),
해당 Gate 증거 문서를 함께 확인합니다.

## 유지보수 및 QA 엔진

현재 `python -m macro_data_platform.pattern_cli --project-root .`는 SQLite 이력을 읽는 제한된 분석기입니다.
보고서가 0 proposals 또는 insufficient evidence를 보이면 해당 입력 기준의 분석 결과입니다. 이는 코드 수정,
테스트 수행, 품질 승인 또는 자동 업데이트를 뜻하지 않습니다.

PowerShell 기반 `scripts/run_improvement.ps1`은 `pwsh` 필요 조건과 `main/master` branch 전제가 현재 환경과
맞지 않아 일반 재현 가능한 runner로 확인되지 않았습니다. 새 유지보수 실행 경로를 만들 때는 깨끗한 격리 worktree,
commit hash, 환경 fingerprint, 전체 검사 결과, 변경 diff, 수동 검토 지점을 하나의 결과물로 남깁니다.
실행기가 검사 실패를 숨기거나 자동 merge/publish 하지 않도록 합니다. 우선순위와 완료 조건은
[로드맵의 QA 계약](ROADMAP_2026_10_26.md#유지보수-엔진의-qa-계약)을 따릅니다.

## 변경 작업과 문서

- 먼저 `AGENTS.md`, `GUIDELINES.md`, 이 문서와 [PROJECT_PLAN.md](../PROJECT_PLAN.md)를 읽습니다.
- 변경 전 사용자 입력/출력, 위험·실패 동작, 완료 조건을 한두 문장으로 고정합니다.
- 한 작업에는 한 High 우선순위 회차를 수행하고, 불필요한 데이터 모델 확장을 피합니다.
- 실제 제품 범위가 바뀌면 사용자 안내서·구현 상태·로드맵·아키텍처를 일치시킵니다. 역사 보고서의 결과를 현재 값으로 덮어쓰지 않습니다.
- 검사 결과와 제한은 날짜·commit에 묶어 기록합니다. branch push는 main 병합·환경 publish가 아닙니다.
- 이 저장소의 작업 관행상 task branch에 commit/push는 기록할 수 있지만, merge와 deploy/publish는 별도 유지관리 검토입니다.

## 공통 유지보수 QA 실행기

`python scripts/run_maintenance_qa.py`는 clean commit에서 detached worktree를 만들고 pytest, Ruff, diff, CLI 도움말을 검사합니다. 보고서는 `reports/maintenance_qa_<id>/report.json`과 개별 로그입니다. 실패/timeout/cleanup 실패는 성공으로 처리하지 않습니다. 현재 Python 환경에 pytest·Ruff와 프로젝트 의존성이 설치돼 있어야 합니다. 네트워크 호출이나 코드 수정·병합은 실행하지 않습니다. Windows에서는 Python 실행 경로를 그대로 사용하지만 실제 Windows 실행 증거는 CI에서 별도로 확인합니다.

수정 흐름은 증거 기반 이슈 → 전용 branch → 수정 및 테스트 → commit → 격리 QA → push → PR 검토입니다. 읽기 전용 분석의 빈 후보는 품질 승인과 구분합니다. TIC/BIS watcher와 BOJ 고정 시리즈의 저장된 기관·dataset을 분석기에 연결했으며, 경제 concept은 추정하지 않아 unknown이면 반복 제안을 계속 차단합니다.
