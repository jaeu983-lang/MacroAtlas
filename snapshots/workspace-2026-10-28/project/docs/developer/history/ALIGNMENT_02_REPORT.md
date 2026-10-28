# 보완 02 구현 보고서

기준일: 2026-10-24. 범위: 최신 PROJECT_PLAN/IMPLEMENTATION_PLAN/WORKFLOW_ALIGNMENT_PLAN의
**보완 02만**. 브랜치: `codex/workflow-alignment-02`. 보완 03·04회차 미착수.

## 구현 결과

제공된 후보/근거·요청 조건·전달 설정을 WorkflowService에 연결했다. 누락된 항목만
구조화 질문으로 반환하며 부족한 메타데이터는 review로 표시한다. file/link/both 선택지,
링크 4상태/현재 유효성·수동 필터·제약·불확실성, 후보 그룹/변형을 보존한다.
과거 출력 선호를 적용하거나 후보를 자동 선택하지 않는다.

완전한 명시 지시는 바로 확인 기록을 만든다. 내용만 충분한 READY는 확인이 아니며,
explicit_request/followup 근거가 있어야 확정된다. 서비스 입력의 확인 방식은 호출자가
실제 사용자 지시에서 전달해야 한다. UI나 사용자 동의를 자동 추론하는 기능은 없다.

확정 기록에서 별도 CREATED 작업을 원자 생성하고 출처 요청/탐색 task_id·개정과 연결한다.
원래 탐색 계획/결과는 보존한다. 새 작업의 plan은 None이며 file/both는 파일 작업 의도,
link는 링크 전달 의도다. link 전용 수집 계획은 금지한다. 기관별 계획 생성과 실제
링크 반환은 구현하지 않았다. 테스트의 실행은 주입한 mock 엔진만 사용했다.

변경·재시작·동시 호출·실패에도 확인/작업 연결을 유지한다. 같은 확인은 같은 작업을
반환하며 다른 context에 같은 키를 재사용하면 거부한다. 처음 지정한 키와 다른 키를
뒤늦게 추가하는 것도 거부한다. 조건/정의/변형이 바뀌면 기존 확인과 작업을 무효화하고
resume 승인으로 우회할 수 없다. 완료된 과거 결과와 실행 중 단계 결과는 보존한다.
링크 만료는 재검토하며 파일로 자동 변경하지 않는다.

## 변경 파일 및 이유

| 파일 | 이유 |
|---|---|
| src/macro_data_platform/orchestration/workflow.py | 구조화 질문·확인·개정·멱등 새 작업 연결 및 context 재검증 |
| src/macro_data_platform/storage/history.py | 트랜잭션 내부의 작업 문서 생성/삽입·멱등 키 조회 공통 함수 |
| src/macro_data_platform/orchestration/runner.py | 새 context의 계획/실행/재개/단계 검증, 조건별 fingerprint, 키 충돌 방지 |
| src/macro_data_platform/orchestration/__init__.py | WorkflowService 공개 |
| tests/test_workflow.py | 신규 offline 서비스/실제 SQLite 통합 테스트 46개 |
| PROJECT_PLAN.md | 현재 구현 수준 표시 갱신 |
| docs/developer/IMPLEMENTATION_PLAN.md | 보완 02 완료/검증, 보완 03·04 미착수 표시 |
| docs/developer/planning/WORKFLOW_ALIGNMENT_PLAN.md | 상세 보완 명세의 구현 상태 갱신 |
| docs/developer/ARCHITECTURE.md | 호출·저장·개정·멱등성·만료·자원 상한 설명 |
| docs/developer/history/DECISION_LOG.md | D-044~047 구현 결정과 남은 범위 |
| docs/developer/history/ALIGNMENT_02_REPORT.md | 이번 결과·한계·검증 보고 |

기존 workflow_contracts.py/workflow_extensions.py, contracts.py의 enum/오류,
golden JSON, World Bank connector/engine와 기존 테스트는 수정하지 않았다.

## 사용 흐름 (Python API)

```python
from macro_data_platform.orchestration import WorkflowService

service = WorkflowService(store)
# request/proposal/links는 출처 근거를 포함해 호출자가 준비한 값 계약이다.
pending = service.begin(request, proposal, candidate_id="c1", links=links)
state = pending["workflow_request"]
questions = state["questions"]

# 실제 사용자의 답을 구조화해 전달한다. 누락 사항은 다시 questions로 반환된다.
confirmed = service.revise(
    pending["task_id"], expected_revision=state["revision"],
    request=answered_request, delivery=answered_delivery,
    confirmation_method="followup",
)
if confirmed["workflow_request"]["state"] == "CONFIRMED":
    child = service.create_work(
        confirmed["task_id"],
        expected_revision=confirmed["workflow_request"]["revision"],
    )
    # 여기까지가 보완 02. 기관별 계획/전달 handler는 보완 03의 범위다.
```

get은 저장 당시 스냅샷이다. 현재 시점의 질문/링크 사용 가능 상태는
revise(id, expected_revision=n)로 재평가한다. 실행 직전에도 runner가 재검사한다.
역사적 개정은 store.events(id)로 명시 조회한다. 원본 관측치를 context에 넣지 않는다.

## 검증 결과

| 검증 | 정확한 결과 |
|---|---|
| 변경 전 전체 pytest | 318 passed in 5.93s |
| 변경 전 Ruff | All checks passed! |
| 신규 테스트 최종 개별 실행 | 46 passed in 4.30s |
| 최종 전체 pytest | **364 passed in 11.00s**, 실패/skip 없음 |
| 최종 Ruff | **All checks passed!**, exit 0 |

```powershell
.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_alignment02_final
.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py
```

모든 검증은 로컬/offline이다. 새 테스트는 HTTP 요청을 실패 처리하도록 차단하고
실제 SQLite 재개방·동시 호출·이벤트 삽입 실패를 사용했다. 질문 대기/명시 확인,
3모드/4링크 상태/만료, stale 링크, 조건/정의/변형 변경, 원본 탐색 결과 불변,
동시 중복 방지, 원자 롤백·고아 작업 방지, mock 재개·오류 코드, 옛 작업/새 작업
fingerprint 격리를 검증했다. 기존 318개 테스트와 v1 golden/hash 검증도 포함한다.
개발 중 첫 신규 실행은 테스트의 Settings 경로 속성 오기로 1 failed/34 passed였고,
실제 project_root를 사용하도록 수정한 뒤 위 최종 검증을 통과했다.

기본 계약 파일 SHA-256은 이전 기준과 같은
`c32035793b586f10f743e912a6198f9deba7d5a7235d3baae3a9cf61225fbb9a`다.
옛 ConfirmedSelection fingerprint
`92b82d2b99402fba6a7704aed19e10db20dceb4345c1146f8a3d54d2cd8b7d96`도 golden 테스트로 유지했다.
SQLite user_version=2 및 선택 필드 없는 작업의 기존 실행 테스트도 통과했다.

공식 문서 신규 조사: 없음. 실제 API/수집 호출: 없음. 링크 fixture의 example.org는
실제 유효성 검증 증거가 아니다. 이전 World Bank 실측을 이번 검증으로 소급하지 않는다.
Python 실행 파일을 직접 사용했으며 PowerShell 실행 정책을 변경하지 않았다.
저장소는 기존부터 전체가 untracked 상태라 Git diff를 이번 파일 변경의 검증 근거로
삼을 수 없다. 위 목록은 이번에 실제 수정/추가한 파일이다. 커밋/병합은 하지 않았다.

## 남은 문제 및 보안·데이터 완전성

- 보완 03의 실제 World Bank 기간/지원 범위 검증과 file/link/both 실행 handler는 없다.
  생성한 작업은 준비된 의도이며 수집/링크 전달 완료가 아니다. 04회차 Gate A도 미통과다.
- 실제 대화 UI/자연어 해석·자동 탐색/그룹 생성·공식 링크 조사·Excel/CSV 생성·기관별 키
  접근·지식 엔진은 미구현이다. 지원 선언과 실제 exporter 지원의 연결은 후속 검증 대상이다.
- 링크 status는 제공된 근거 선언이고 서비스가 사이트에 접속해 확인하지 않는다.
  미지원/미확인/만료를 가용으로 바꾸지 않으며 수동 필터 조건도 보존한다.
- 신규 조회는 현재 작업 행/색인 키만 읽는다. 과거 전체 이벤트를 자동 검색하지 않는다.
  초안 후보 50·링크 100·JSON 256 KiB·개정 100회 제한은 초기 서비스 상한이며
  대량 데이터/지식 엔진의 성능 검수는 아니다. 보관 이력은 자동 삭제하지 않는다.
- API 키 접근·출력·네트워크·원본 관측치 변경·스키마 이관은 없다. 자유문장 입력의 모든
  비밀을 탐지하는 도구는 아니며 호출자는 키를 입력하지 않아야 한다. hash는 전자서명이 아니다.
- 이번 범위의 미해결 실패는 없다. 인간 검토/다음 작업 범위 결정은 필요하며,
  별도 요청 전까지 보완 03과 04회차를 진행하지 않는다.
