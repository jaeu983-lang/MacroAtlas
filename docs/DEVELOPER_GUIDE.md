# MacroAtlas 개발자 안내서

기준일: 2026-10-27. 통합 범위·우선순위는 [제품 기획](../PROJECT_PLAN.md), 사용자가 실행하는 기능은
[사용자 안내서](USER_GUIDE.md), 간단 실행 요약은 [제품 로드맵](ROADMAP_2026_10_26.md), 목표 구조는
[제품 및 시스템 아키텍처](PRODUCT_ARCHITECTURE.md)를 참조합니다. 과거 보고서의 상태 문구를 현재 구현 여부로 사용하지 않습니다.

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
| `performance/` | privacy-safe monotonic stage/phase 표본 저장과 read-only `macro-perf` 집계 |
| `storage/` | SQLite task, raw-download, feedback, deferred record, artifact 관련 저장 |
| `connectors/` | 기관 전송과 parser adapter |
| `ingestion/` | connector를 실행 가능한 stage/engine으로 연결 |
| `ingestion/csv_export.py` | 완료된 World Bank/BOJ task와 저장 원본을 읽기 전용 검증한 뒤 CSV/provenance 파일 생성 |
| `discovery/` | 근거가 붙은 제한 후보 찾기와 명시 선택 보조 |
| `analysis/` | 기록을 읽는 pattern 분석. 결과는 검토 후보이지 자동 지식이나 코드가 아님 |
| `evaluation/` | 검토 사례와 development/validation/holdout split 형식 및 hash 검증기. 사례 채점·규칙 승격은 제공하지 않음 |
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
macro-eval validate
macro-eval search-baseline
macro-eval search-compare --candidate-min-score 70
git diff --check
```

`macro-eval validate`의 `READY`는 세 split의 구조·분리·hash 검증만 통과했다는 뜻이며 엔진 평가가 아닙니다. 현재 포함된 사례는 synthetic fixture라 `reviewed_feedback_split_coverage`가 `none`입니다. validation/holdout hash도 blind holdout이나 일반화 성능의 증거가 되지 않습니다. 상태 정의는 [평가 사례 규약](EVALUATION_CASES.md)을 확인하세요.

`search-baseline`과 `search-compare`는 고정 corpus의 development split만 읽습니다. 현재 비교 후보는 ranker의 최소 lexical score를 적용하는 평가용 정책 wrapper입니다. 출력의 정책 hash와 delta는 오프라인 측정이며 제품 정책 변경, 확정 판정, Gate C 통과 또는 승격 승인을 의미하지 않습니다.

`macro-perf report --project-root .`는 `data/performance.sqlite`만 읽어 engine/version/scope/workload별 성능 표본을 집계합니다. p95는 각 그룹 표본이 20개 미만이면 `INSUFFICIENT_SAMPLE`이며, fixture·stored·live_api 표본은 별도 그룹입니다. report는 task DB를 만들거나 수정하지 않습니다. 성능 계측의 범위와 해석은 [엔진 연결 설계](ENGINE_CONNECTIONS.md)를 확인하세요.

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

## 유지보수 분석·업데이트·QA 흐름

현재 `python -m macro_data_platform.pattern_cli --project-root .`는 SQLite 이력을 읽는 제한된 분석기입니다.
read-only 결과는 코드 변경이나 품질 승인이 아닙니다. 2026-10-27 첫 실행의 insufficient-evidence 7개는 재검토 후
합성 qualification fixture와 manifest가 보존된 BIS 오류로 분리됐습니다. 현재 49 tasks/57 stages snapshot은 fixture 15건,
보존 파일 qualification trial 5건, operational stage 37건을 구분하고, BIS 두 건의 기관·dataset만 검증 projection으로
복구합니다. 이어 BLS·Census API의 exact manifest/raw 및 large-file production의 plan hash를 확인해 성공 stage의 scope
projection을 보완했습니다. 재검증에서 institution unknown은 0건이며 BLS 응답 두 건의 dataset은 provider가 null로
남겨 미상 상태를 유지합니다. 별도 full-catalog audit은 69 task/57 stage 전체를 읽어 운영 오류 3건(BIS 2, World Bank 1)을
확인했고 미상 institution/dataset 오류는 찾지 못했습니다. BLS 공식 문서상 registered API v2의 series description과 일부 survey catalog가 있지만 전체 series catalogue는 없습니다. 다음 재검토는 등록 metadata가 보존된 정상 수집 응답이 생길 때이며, 그전에는 `dataset_id=null`을 유지합니다.
상세 범위와 근거는 [scope 재검토](SCOPE_EVIDENCE_RECOVERY_PLAN.md)와
[engine×institution 감사](ENGINE_INSTITUTION_ERROR_AUDIT_2026_10_27.md)를 참고하세요.

`python scripts/run_maintenance_qa.py`가 공통 local check entrypoint입니다. 기본 실행은 clean commit을 detached worktree에
checkout해 pytest, Ruff, commit whitespace, Python/installed CLI help, health 검사를 실행하고 check별 log와 JSON report를
남깁니다. 수정 candidate는 `python scripts/run_maintenance_qa.py --base <full-sha> --candidate <full-sha>`로 검사할 수
있습니다. 이 모드는 base가 candidate의 조상인지 확인하고 같은 candidate SHA를 detached worktree에서 검사하므로 원
checkout이 dirty여도 결과가 섞이지 않습니다. Windows의 `scripts/run_checks.ps1`도 `-Base`와 `-Candidate` 인자를 전달합니다.
저장소 업데이트 script `scripts/run_improvement.ps1`은 `scripts/run_improvement.py`의 Windows wrapper입니다. 기본 base는
`origin/HEAD`이며 설정이 없으면 `-BaseRef`로 branch를 지정해야 합니다. Codex는 source checkout의 ignored 파일과 분리된
Git worktree에서 실행됩니다. 변경 경로 allowlist를 통과한 candidate만 commit하며, 동일 SHA QA 실패 시 push하지 않습니다.
QA가 통과하면 원격 branch와 검토 PR을 생성하지만 자동 merge/publish는 하지 않습니다. `-DryRun`은 Codex 없이 base와 prompt만
확인하며 worktree나 report를 만들지 않습니다. 2026-10-27 첫 Linux 재시도는 token refresh `401`로 막혔지만, device-code 재인증 뒤
updater가 candidate QA와 PR handoff에 성공했습니다. Windows 사용자 세션의 no-op/cleanup도 통과했습니다. Scheduler installer는
`-BaseRef <branch> -PythonPath <python.exe> -DryRun`으로 설치 없이 action·trigger·principal을 확인할 수 있습니다.
실제 설치는 별도 운영 결정이며 현재 예약 task는 등록하지 않았습니다. 최신 상태와 다음 조건은
[27회차 pilot 보고서](ITERATION_27_PILOT_REPORT.md)를 참고하세요.

### Windows에서 Codex CLI shim이 차단될 때

npm으로 설치한 Codex CLI의 `codex.ps1`을 불러올 때 `PSSecurityException`이 나면 PowerShell이 shim 실행을 차단한 것입니다. 이 오류만으로 Codex 로그아웃을 뜻하지는 않습니다. 프로세스 범위에서 로그인 상태를 확인하려면 다음을 실행하세요. 이 명령은 영구 실행 정책을 바꾸지 않습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "codex login status"
```

계속 차단되면 `Get-Command codex -All`로 명령 경로를 확인하고, 실행 정책을 바꾸거나 소프트웨어를 재설치하기 전에 멈춰 원인을 확인하세요. Codex와 GitHub CLI 인증은 별도이며, `gh auth status`는 GitHub CLI 인증 상태를 확인합니다. 토큰을 출력하거나 공유하지 마세요.

이 경로를 통합하면서 제품 runtime engine은 전문 adapter로 분리 유지하는 목표, 안전 경계, 24–27회차 순서는
[엔진 통합·분리 개선안](ENGINE_CONSOLIDATION_PLAN.md)에 정리했습니다. 구현 전까지는 기존 스크립트가 서로 연결된
완성형 자동 업데이트 엔진이라고 간주하지 않습니다. 공통 check entrypoint, candidate SHA QA, 격리 updater 및 QA 성공 시
push/PR handoff는 구현됐습니다. scope-aware 분석의 미상 범위는 보수적으로 차단하며, Windows changed/failure pilot은
남았습니다. Updater는 같은 repository에서 동시에 실행되지 않으며 완료된 일반 no-op/check 결과만 90일 뒤 정리합니다.
후보 QA와 실패·불완전 정리 증거는 보존합니다. 자동화가 만들 수 있는 최종 결과는 사람 검토용 branch/PR이고
merge/publish가 아닙니다.

## 변경 작업과 문서

- 먼저 `AGENTS.md`, `GUIDELINES.md`, 이 문서와 [PROJECT_PLAN.md](../PROJECT_PLAN.md)를 읽습니다.
- 변경 전 사용자 입력/출력, 위험·실패 동작, 완료 조건을 한두 문장으로 고정합니다.
- 한 작업에는 한 High 우선순위 회차를 수행하고, 불필요한 데이터 모델 확장을 피합니다.
- 실제 제품 범위가 바뀌면 사용자 안내서·구현 상태·로드맵·아키텍처를 일치시킵니다. 역사 보고서의 결과를 현재 값으로 덮어쓰지 않습니다.
- 검사 결과와 제한은 날짜·commit에 묶어 기록합니다. branch push는 main 병합·환경 publish가 아닙니다.
- 이 저장소의 작업 관행상 task branch에 commit/push는 기록할 수 있지만, merge와 deploy/publish는 별도 유지관리 검토입니다.

## 공통 유지보수 QA 실행기

`python scripts/run_maintenance_qa.py`는 clean commit에서 detached worktree를 만들고 pytest, Ruff, commit whitespace,
CLI help와 project health를 검사합니다. 보고서는 `reports/maintenance_qa_<id>/report.json`과 check별 log입니다.
실패·timeout·실행 파일 부재·cleanup 실패를 성공으로 취급하지 않고, 가능한 후속 검사는 계속 수행합니다. Python 환경에
pytest·Ruff·프로젝트 설치가 필요합니다. 네트워크 호출이나 코드 수정·병합은 하지 않습니다. 수정 candidate를 검증하는
연결은 [엔진 통합 계획](ENGINE_CONSOLIDATION_PLAN.md)의 후속 회차입니다.

수정 흐름은 증거 기반 이슈 → 전용 branch → 수정 및 테스트 → commit → 격리 QA → push → PR 검토입니다. 읽기 전용 분석의 빈 후보는 품질 승인과 구분합니다. TIC/BIS watcher와 BOJ 고정 시리즈의 저장된 기관·dataset을 분석기에 연결했으며, 경제 concept은 추정하지 않아 unknown이면 반복 제안을 계속 차단합니다.
