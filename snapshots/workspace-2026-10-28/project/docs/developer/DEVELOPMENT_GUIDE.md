# MacroAtlas 개발자 안내

**대상:** 저장소 코드를 구현·검증·유지하는 개발자
**실기관 사용:** 이 문서의 설치와 검사 명령은 기본적으로 네트워크 fixture/mock만 사용합니다. 실기관 요청은 [운영자 runbook](../operator/OPERATOR_RUNBOOK.md) 및 source gate를 따릅니다.

## 먼저 읽을 문서

프로젝트 루트의 AGENTS.md와 GUIDELINES.md를 먼저 확인하세요. 구현 전에는 PROJECT_PLAN.md, 해당 번호의 [구현 계획](IMPLEMENTATION_PLAN.md), 관련 기관 문서와 테스트를 읽습니다. 작업은 High iteration 하나와 gate 하나씩 진행하고, 실패한 gate를 넘지 않습니다.

- 제품 scope: [PROJECT_PLAN.md](../../PROJECT_PLAN.md)
- 현재 구조/목표 구조: [ARCHITECTURE.md](ARCHITECTURE.md)
- 기관 연결 상태: [INSTITUTION_CATALOG.md](../operator/reference/INSTITUTION_CATALOG.md), [INSTITUTION_API_AUDIT.md](../operator/reference/INSTITUTION_API_AUDIT.md)
- 현재 작업 queue: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- 출처별 connector 문서: [connectors/](connectors/README.md)
- 결정과 이전 증거: [DECISION_LOG.md](history/DECISION_LOG.md), iteration/benchmark/regression reports

## 로컬 설치와 검사

Windows PowerShell에서 저장소 루트에서 실행합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```

fixture와 mocked HTTP를 기본으로 사용합니다. 네트워크를 쓰지 않는 검사와 source live 시험은 별개로 기록합니다. 테스트나 lint가 실행되지 않으면 이유를 쓰고 성공으로 보고하지 않습니다.

Windows의 기존 `pytest-of-<사용자>` Temp가 접근 거부로 막히면 저장소 내부의 고유 `--basetemp`로 검증합니다. 기존 사용자 Temp의 ACL이나 내용을 변경하지 않습니다.

```powershell
$taskTestRoot = Join-Path (Get-Location) ('reports\pytest_' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $taskTestRoot -p no:cacheprovider -ra
```

## 구현 경계

- 공통 workflow·validation·storage/recovery는 공통 엔진에 둡니다.
- API endpoint, 인증, paging, source schema, revision 차이는 기관 connector와 fixture에 둡니다.
- 원문 metadata와 관측값 provenance를 보존합니다.
- 방법론·비교가능성 엔진(작업명)은 공식 근거로 비교/정렬 feasibility를 평가하고, deterministic transformation engine은 승인된 규칙만 실행하도록 분리하는 기획 단계입니다.
- 추정 API, label-only equivalence, missing-to-zero, 무단 interpolation/fill을 추가하지 않습니다.
- API docs, fixture, live API, live ingestion 결과를 구별합니다.

## 엔진·모듈 단위 수정과 모델 배정

변경 단위는 막연한 “엔진별”보다 **엔진·모듈별**로 지정합니다. 엔진은 책임과 입출력 계약을, 모듈은 실제 수정할 코드·테스트·문서 묶음을 뜻합니다. 작업 요청에는 대상 엔진/모듈, 바꿀 계약, 유지할 동작, 허용 파일, fixture와 gate를 씁니다. 한 task는 High iteration 하나와 gate 하나를 다룹니다.

모델은 엔진에 영구 고정하지 않고 task의 범위와 위험도에 맞춰 시작 전에 배정합니다.

| 작업 형태 | 계획상 배정 |
|---|---|
| 안정된 계약 안의 제한된 단일 모듈 변경 | 사용자가 task 시작 때 지정한 기본 모델. 현재 전기관 검증 계획은 Luna Max 기준 |
| 공통 API 계열/전기관 audit | Max로 관련 기관을 묶어 분석하되 기관별 dataset, fixture, live verdict는 각각 독립 유지 |
| 기관 connector | 공식 근거가 확인된 API 계열 단위로 호환 source를 batch할 수 있음. 각 기관의 구체 dataset/table 문서·fixture·결과를 포함 |
| 방법론 의미·비교가능성·계산 공식 | 더 강한 추론 모델을 고려하고, 출처와 통계적 가정은 사람이 확인 |
| 여러 엔진 계약이나 오케스트레이터 변경 | 강한 모델을 사용자가 지정하고, 각 엔진 gate 이후 별도 통합·회귀 작업 |
| 큰 구조 변경 | 자동화 작업에 맡기지 않고 사용자가 지정한 모델과 사람 주도로 별도 수행 |

오케스트레이터는 엔진이 바뀔 때마다 함께 수정하지 않습니다. 엔진 입력/출력 계약, 단계 순서나 병렬성, 사용자 확인, 상태·오류 전파, retry/cancel/resume, budget 또는 provenance가 바뀌는 경우에만 통합 task에서 수정합니다. 엔진 내부 구현이 기존 계약을 지키면 오케스트레이터는 그대로 둡니다.

이 절은 향후 운영 방식에 대한 계획입니다. 현재 모델 자동 배정/라우팅이나 엔진별 agent 분할을 구현했다는 뜻이 아니며, 실제 실행 전에 작업 계획과 모델 배정을 사람이 검토합니다.

## 오류 수정과 성능·메모리 최적화

유지보수(Track M)는 특정 엔진 하나에만 속하지 않는 반복 작업입니다. 매주 오류와 사람 피드백을 재현해 원인이 있는 엔진·모듈을 좁히고, 2주마다 고정 workload로 wall time, CPU, peak RSS, Python allocation과 요청량을 측정합니다. 코드 효율화는 측정으로 확인한 병목이 있을 때만 대상 모듈에 적용합니다. 같은 workload를 수정 전후로 실행하고 정확성·provenance·결측/0·저장/복구 결과를 비교합니다. 개선을 구분할 수 없으면 코드를 바꾸지 않습니다.

모듈 내부 변경으로 기존 계약이 유지되면 해당 모듈의 fixture와 회귀 검사를 수행합니다. 엔진 간 입출력 계약이나 workflow 단계가 바뀌면 영향 모듈의 검증 뒤 오케스트레이터 통합 task를 별도로 만듭니다. 반복 횟수·측정 항목·승인 순서는 [운영 계획](../operator/OPERATING_PLAN.md)과 [성능 최적화 계획](performance/PERFORMANCE_OPTIMIZATION_PLAN.md)을 따릅니다.

## 사용자 Python 확장 — 설계 제안, 미구현

세부 hook·폴더·오류 계약은 [사용자 Python 확장 설계](extensions/USER_PYTHON_EXTENSIONS.md)를 따른다.

사용자 코드가 필요하면 core 모듈을 직접 덮어쓰는 patch가 아니라 버전이 있는 package를 명시된 extension hook에 연결합니다. 초기 hook 후보는 후보 선택/필터, metadata 보강, 수집 이후 승인된 가공, 출력 layout입니다. Connector transport, credentials, raw writer, SQLite 직접 변경, 임의 network call은 기본 extension 권한에 포함하지 않습니다.

제안 경로는 `MACROATLAS_DATA_DIR/extensions/<user_id>/<extension_id>/`입니다. 실행은 `.py` module, hook/schema/capability/version을 선언하는 JSON/YAML manifest, 사람이 읽는 README/Markdown 설명으로 나눕니다. Markdown과 YAML/JSON은 executable source가 아닙니다. 매 run은 extension version/hash와 입력·출력 fingerprint를 고정합니다. 현재 Python runner, sandbox, dependency isolation, per-user extension registry는 아직 구현되지 않았습니다.

코드 처리 전 syntax/import/contract/fixture 검사를 수행합니다. 실행은 main workflow process와 분리하고 timeout·memory·capability 제한을 둬야 합니다. 격리 수준과 Windows 지원을 검증할 수 없으면 기능을 활성화하지 않습니다. 문법·contract·runtime 오류는 해당 extension stage를 실패시키고 raw·이전 단계 산출물을 보존합니다. 승인된 safe fallback이 사전에 선택되지 않았다면 기본 엔진으로 자동 대체하지 않습니다. 오류 표시는 사용자가 고칠 수 있도록 extension ID/version, 오류 ID, 파일/행 및 sanitised cause를 제공하되 비밀값은 제외합니다.

Markdown의 문법·링크·표시 문제는 lint와 agent가 수정 제안을 만들 수 있습니다. Markdown에 적힌 방법론·단위·source 계약의 의미를 변경하는 것은 단순 formatting fix로 취급하지 않고 사람 검토를 거칩니다.

## 변경 기록

코드 수정은 변경한 동작의 fixture와 영향을 받는 regression 확인을 포함해야 합니다. 측정 없는 성능 개선을 주장하지 않습니다. 보고서와 decision log에 사실, 미검증 범위, 다음 gate를 남깁니다. 사용자 작업이 들어 있는 dirty worktree를 정리하거나 되돌리지 않습니다.
