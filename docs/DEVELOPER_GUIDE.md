# MacroAtlas 개발자 안내서

기준일: 2026-10-28. 통합 범위·우선순위는 [제품 기획](../PROJECT_PLAN.md), end-user 명령은
[사용자 안내서](USER_GUIDE.md), 현재 Gate와 코드 상태는 [구현 현황](IMPLEMENTATION_PLAN.md), 목표 구조는
[엔진 연결표](ENGINE_CONNECTIONS.md)를 참조합니다. 축약된 옛 계획 문서는 색인이고 과거 보고서는 당시 증거입니다.

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
| `evaluation/` | 사례 split/hash 검증, development/validation 검색 ranker 비교, feedback에서 불완전 draft 생성. 규칙 승격/rollback은 미구현 |
| `tests/` | offline fixture, 계약, 상태 전이, 제한된 live 관련 단위 검증 |
| `docs/` | 제품 범위, 실제 상태, 개발 설계, 날짜가 붙은 증거 |

실제 호출표는 [ENGINE_CONNECTIONS.md](ENGINE_CONNECTIONS.md)를, 엔진별 코드·접근 한계는
[ENGINE_IMPLEMENTATION_STATUS.md](ENGINE_IMPLEMENTATION_STATUS.md)를, 공통 모델과 초기 구현 이력은
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
macro-eval search-compare --candidate-min-score 37.5
macro-eval search-validation --candidate-min-score 37.5
git diff --check
```

`macro-eval validate`의 `READY`는 세 split의 구조·분리·hash 검증만 통과했다는 뜻이며 엔진 평가가 아닙니다. 현재 포함된 사례는 synthetic fixture라 `reviewed_feedback_split_coverage`가 `none`입니다. validation/holdout hash도 blind holdout이나 일반화 성능의 증거가 되지 않습니다. 상태 정의는 [평가 사례 규약](EVALUATION_CASES.md)을 확인하세요.

`search-baseline`과 `search-compare`는 고정 corpus의 development split만 엔진 평가에 사용합니다. `search-validation`은 같은 baseline/candidate를 validation split에서 비교하고 holdout을 엔진 평가에 넣지 않습니다. `--candidate-policy semantic-v1`은 measure/basis 단서를 반영하는 새 평가용 후보이며, 기본값 `threshold-v2`는 이전 비교를 재현합니다. 출력의 정책 hash와 delta는 오프라인 측정이며 제품 기본 정책 변경, 확정 판정 또는 Gate C 승격 승인을 의미하지 않습니다.

### Gate C 자격 확인과 일회 holdout

Gate C의 전체 개발·검증·안전 경계·시간/비용 측정은 `macro-gate-c`로 실행합니다. 현재 semantic candidate는 평가 전용이며 제품 기본 검색 규칙을 바꾸지 않습니다.

```text
python -m macro_data_platform.evaluation.gate_c qualify --project-root .
```

이 단계는 development와 validation만 실행하고 GPT가 작성한 development 사례 네 건도 다시 비교합니다. 다섯 금지 동작 유형을 기록합니다. 확인 누락·미선택 후보는 실제 계획 생성 경계에서 거부되는지, 미상 필드는 응답에 추정값으로 노출되지 않는지 검사합니다. raw/export 덮어쓰기와 계열 병합·보간은 계획 생성 실패로 평가 경로에서 도달하지 않았다고 기록합니다. 이는 writer/exporter 내부의 별도 동작 검증을 대신하지 않습니다. 고정 catalog 검색의 p50/p95·처리량은 열 번 반복하며, 상한은 versioned `tests/fixtures/evaluation/gate_c_budget_v1.json`에 있습니다. source API나 외부 모델 호출은 0회입니다. 결과와 후보 manifest는 `evaluation/results/`에 생성됩니다. 현재 validation 사례는 후보 조정 중 살펴봤기 때문에 blind 증거로 취급하지 않습니다.

후보 자격과 hash를 검토한 뒤 결과와 manifest를 먼저 커밋하고 다음 명령으로 holdout lock을 만듭니다. 생성된 lock도 커밋한 뒤에만 holdout 실행을 허용합니다.

```text
python -m macro_data_platform.evaluation.gate_c initialize-holdout --project-root .
python -m macro_data_platform.evaluation.gate_c holdout --project-root .
```

holdout 명령은 고정 case/catalog/policy/code/budget hash를 확인하고 실행 전에 잠금을 소비합니다. 성공·실패·중단을 모두 1회 사용으로 기록하며 같은 holdout은 다시 실행하지 않습니다. 보고서 결과가 Gate C `PASS`여도 자동 승격은 없고 D의 명시 승인·rollback 절차가 남습니다. 저장소가 공개되어 있으므로 holdout은 분리·고정된 평가 split이지 비밀 데이터는 아닙니다.

2026-10-28의 v2 holdout은 이미 한 번 실행되어 잠금이 `COMPLETED`입니다. 결과는 [`gate_c_holdout_result.json`](../evaluation/results/gate_c_holdout_result.json)에 있고 같은 split을 재실행하지 마세요. 후보를 더 수정하려면 holdout 내용을 development/validation으로 재분류하고 새 corpus/split version을 만든 뒤 새 hash와 새 one-use lock으로 시작해야 합니다.

`macro-perf report --project-root .`는 `data/performance.sqlite`만 읽어 engine/version/scope/workload별 성능 표본을 집계합니다. p95는 각 그룹 표본이 20개 미만이면 `INSUFFICIENT_SAMPLE`이며, fixture·stored·live_api 표본은 별도 그룹입니다. report는 task DB를 만들거나 수정하지 않습니다. 성능 계측의 범위와 해석은 [엔진 연결 설계](ENGINE_CONNECTIONS.md)를 확인하세요.

개별 테스트는 해당 테스트 모듈/이름으로 좁힌 뒤 마지막에 전체 suite를 실행합니다. 새 테스트는 사용자에게
보이는 결과 계약, 상태 전이, 안전 경계를 검증해야 합니다. 구현 코드를 그대로 반복하는 테스트만 추가하지 않습니다.
문서 전용 변경은 링크·경로·diff 검사를 수행하고 전체 테스트를 불필요하게 다시 돌리지 않습니다.

외부 수집은 기본 자동 검사가 아닙니다. live 요청에는 대상·scope·키 사용 여부·원본 저장 위치·요청 횟수가
명시돼 있어야 합니다. 네트워크 fixture는 실제 기관 장애나 자연 source revision의 증거가 아닙니다.

## 피드백 검토와 사례 초안

### 대화형 GPT가 작성하는 합성 질문·피드백

별도 OpenAI API나 `OPENAI_API_KEY` 없이 이 대화의 GPT가 시험 질문을 만들고, 고정된 로컬 엔진의 실제 결과를 읽어
가상 사용자의 피드백을 작성할 수 있습니다. 충분한 결과에는 피드백을 강제로 붙이지 않습니다. 기록은 실제 사용자
피드백 원장과 분리된 `data/synthetic_feedback.sqlite`에 저장하며, `answer_origin`과 AI 출처를 명시합니다.
합성 기록은 실제 사용자 기록이나 평가 corpus로 자동 전환되지 않습니다.

검토한 대화 사례를 개발용 fixture로 저장한 뒤 아래 명령으로 import하고 비교합니다. 사례는 Gate 개발 증거로 쓸 수
있지만 실제 사용자 관찰을 대신하거나 전체 Gate를 통과시키지는 않습니다.

```text
python -m macro_data_platform.evaluation.synthetic_feedback --project-root . import --file tests/fixtures/evaluation/chatgpt_engine_smoke_examples_2026_10_28.json
python -m macro_data_platform.evaluation.synthetic_feedback --project-root . list
python -m macro_data_platform.evaluation.synthetic_gate_evidence --project-root . --cases tests/fixtures/evaluation/chatgpt_engine_smoke_examples_2026_10_28.json --expectations tests/fixtures/evaluation/chatgpt_engine_smoke_expectations_2026_10_28.json
```

현재 고정 catalog 검색 사례는 후보 검색만 측정하며 실제 수치 수집이나 완전한 답변 검증이 아닙니다. 사례·관측 결과·기대
판정을 사람이 함께 검토한 뒤 development에만 둘 수 있습니다. 더 엄밀한 검색·실행 안전 평가와 holdout은 별도 Gate C
조건을 따라야 합니다.

### 수동 분류 batch (30회차)

`python -m macro_data_platform.feedback_cli --project-root . classification-snapshot`은 전체 피드백 revision의
고정 snapshot을 SQLite에 기록하고 ID·revision·문서 hash만 출력합니다. 원문은 출력하지 않습니다. 운영자는 필요한
revision을 `history --feedback-id <ID>`로 로컬에서 확인하고, 외부 AI에 제공할 내용은 직접 비식별화합니다.
안전하게 제공할 수 없는 revision은 결과에 `unclassified` / `privacy_excluded`로 남깁니다.

운영자가 만든 결과 JSON은 snapshot 출력의 `snapshot_id`, `key_hash`, `source_hash`와 함께 `prompt_version`,
`model_version`, `reviewer_id`, `privacy_cleared: true`, `elapsed_ms`, `cost_usd`, `rows`를 담습니다.
각 row는 `feedback_id`, `revision`, `label`, `reason` 네 필드이며, label은 기존 feedback category 또는
`unclassified`입니다. 분류된 row의 reason은 `null`, 미분류 reason은 `privacy_excluded`, `ambiguous`,
`unsupported`, `model_error` 중 하나입니다. 비용/시간을 모르면 `null`로 남깁니다. 원문은 결과 JSON에 넣지 않습니다.
아래의 `rows`에는 snapshot의 **모든** revision을 각각 넣어야 합니다.

```json
{
  "snapshot_id": "SNAPSHOT_ID", "key_hash": "SNAPSHOT_KEY_HASH", "source_hash": "SNAPSHOT_SOURCE_HASH",
  "prompt_version": "manual-v1", "model_version": "model-v1", "reviewer_id": "reviewer-1",
  "privacy_cleared": true, "elapsed_ms": null, "cost_usd": null,
  "rows": [{"feedback_id": "FEEDBACK_ID", "revision": 1,
            "label": "unclassified", "reason": "privacy_excluded"}]
}
```

```text
python -m macro_data_platform.feedback_cli --project-root . classification-import --results data/classification-result.json --privacy-cleared
python -m macro_data_platform.feedback_cli --project-root . classification-list
python -m macro_data_platform.feedback_cli --project-root . classification-show --batch-id <BATCH_ID>
```

`--privacy-cleared`와 JSON의 확인은 운영자의 수동 검토 확인이며 자동 개인정보 탐지나 reviewer 인증이 아닙니다.
가져오기는 snapshot의 key/count/hash와 원본 revision hash를 검사하고 전부 일치할 때만 별도 batch를 저장합니다.
AI 호출이나 prompt/코드 수정은 자동화하지 않습니다. 이후 추가된 revision은 다음 snapshot에서 다룹니다.

이 절차는 운영자·개발자가 사용합니다. 먼저 저장된 task에 피드백을 연결합니다. 로그는 별도 텍스트 파일이 아니라
`data/catalog.sqlite`의 append-only revision 원장과 current snapshot에 남습니다. 다른 저장소나 대화의 내용은 자동 수집되지 않습니다.

```text
python -m macro_data_platform.feedback_cli --project-root . add --task-id <TASK_ID> --text "확인된 source method를 사용" --category source_method --knowledge-kind user_instruction --scope-json '{"institution_id":"worldbank","dataset_id":"2"}'
python -m macro_data_platform.feedback_cli --project-root . list --task-id <TASK_ID>
python -m macro_data_platform.feedback_cli --project-root . review --feedback-id <FEEDBACK_ID> --expected-revision 1 --status accepted --note "범위와 근거를 확인함"
```

피드백은 자동 승인·사례 채택·규칙 변경되지 않으며, AI 일괄 분류도 미구현입니다. accepted/current `user_instruction`을
평가 초안으로 넘길 때는 원문을 검토하고 직접 비식별화한 질문, reviewer ID, privacy clearance를 제공해야 합니다.
결과는 불완전한 development seed이며 사례 corpus에 자동 추가되지 않습니다.

```text
python -m macro_data_platform.evaluation.cli feedback-draft --project-root . --feedback-id <FEEDBACK_ID> --expected-revision 2 --sanitized-question "Show annual GDP values for the requested period." --reviewer-id reviewer-01 --privacy-cleared
python -m macro_data_platform.pattern_cli --project-root .
```

AI 지시문 수정은 자동화하지 않습니다. 운영자가 별도 지시한 경우에만 사람이 수동 편집하고 버전을 고정합니다. 같은 고정
사례에서 답변 품질·지시 준수·실행 시간·모델 비용을 변경 전후 비교하며 적용 여부는 운영자가 결정합니다. 코드 수정은 별도
변경 요청, 코드 검토, 회귀 검사를 거칩니다. 구현 위치는 [`feedback_cli.py`](../src/macro_data_platform/feedback_cli.py),
[`storage/feedback.py`](../src/macro_data_platform/storage/feedback.py),
[`evaluation/feedback_bridge.py`](../src/macro_data_platform/evaluation/feedback_bridge.py),
[`pattern_cli.py`](../src/macro_data_platform/pattern_cli.py)입니다.

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
