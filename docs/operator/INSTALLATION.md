> **Legacy template:** 이 문서는 초기 기획안 배치 예시이며 현재 설치 절차나 Git 승인 지침이 아닙니다. 현재 개발환경은 [DEVELOPMENT_GUIDE.md](../developer/DEVELOPMENT_GUIDE.md), credential/live 운영은 [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md)를 따르세요.

# START HERE — 기획안 설치 및 첫 Codex High 작업

## 1. 어디에 저장하나?

기존 Windows 프로젝트의 **루트 폴더**(예: `C:\Projects\macro_data_platform`)에 다음 파일을 배치한다.

```text
macro_data_platform/
├─ PROJECT_PLAN.md                  # 제품 정의 및 최상위 설계
├─ AGENTS.md                        # 기존 파일 유지, 아래 3항의 지침만 추가
├─ GUIDELINES.md                    # 기존 데이터 보존·보안 원칙 유지
├─ README.md                        # 기존 설치 안내 유지
├─ docs/
│  ├─ INSTALLATION.md               # 이 문서
│  ├─ INSTITUTION_CATALOG.md        # 기관 21개 조사대장
│  ├─ REFERENCE_SCENARIOS.md        # 표준 사례 A~H 및 오류 시나리오
│  ├─ IMPLEMENTATION_PLAN.md        # 14회 High 회차별 구현 범위
│  └─ DECISION_LOG.md               # 설계 변경 기록
├─ src/
└─ tests/
```

**권장:** 제공된 `macro_platform_final_plan_only.zip`을 기존 프로젝트 폴더에 푼다. `AGENTS.md`와 `GUIDELINES.md`는 포함되지 않으므로 기존 파일을 덮어쓰지 않는다. 대신 아래 항목만 `AGENTS.md` 상단에 추가한다.

## 2. 처음 실행 전 확인

PowerShell:

```powershell
cd C:\Projects\macro_data_platform
git status
# 파일을 배치한 뒤
git add PROJECT_PLAN.md docs
# 실제 변경 사항과 비밀정보 미포함 확인 후
git commit -m "Add project plan and 14-step implementation roadmap"
```

Git 저장소가 없다면 기존 `README.md`의 초기화 절차를 따른다. 파일 배치는 코드 구현이 아니다.

## 3. `AGENTS.md`에 추가할 내용

```markdown
## Project plan precedence
- Before implementing a feature, read `PROJECT_PLAN.md`, the matching section of `docs/developer/IMPLEMENTATION_PLAN.md`, and the relevant institution/scenario documentation.
- Treat `PROJECT_PLAN.md` as the authoritative product scope and acceptance criteria. Follow stricter security and data-integrity constraints in `AGENTS.md` and `GUIDELINES.md`.
- Implement exactly one numbered High iteration at a time. Do not advance unless its acceptance gate passes.
- Do not claim that an institution API, data series, or ingestion scenario worked without actual evidence; distinguish live tests from fixtures.
- Preserve source provenance and original statistical meaning. Record conflicts and unresolved decisions in `docs/developer/history/DECISION_LOG.md`.
```

## 4. Codex 실행

```powershell
cd C:\Projects\macro_data_platform
codex
```

첫 요청 프롬프트:

> `PROJECT_PLAN.md`를 최상위 기획서로 읽고 `AGENTS.md`, `GUIDELINES.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/operator/reference/INSTITUTION_CATALOG.md`, `docs/developer/testing/REFERENCE_SCENARIOS.md`를 확인해. 현재 코드와 테스트를 먼저 조사한 뒤 **01회차만** 구현해. 구현 범위를 넘어서는 기능을 미리 작성하지 마. 실제 테스트 결과, 검증하지 못한 가정, 변경 파일, 다음 회차 선행조건을 보고해.

한 회차 종료 후 보고를 확인하고 변경 파일/테스트를 Git에 기록한 다음 02회차를 별도 요청한다.

## 5. 주간 자동 개선 스크립트 주의

기존 시작 템플릿의 `scripts/install_tasks.ps1`은 주간 Codex 개선 작업 등록 기능을 포함한다. **Phase 5가 완성되기 전에는 자동 개선 스케줄을 새로 설치하지 말 것.** 이미 예약 작업이 설치돼 있다면 실행 상태를 확인하고, 기획 범위 밖의 자동 코드 수정을 방지하도록 조직 정책 및 사용자 의사에 따라 비활성화한다. 수동 `Codex High` 회차 작업과 주간 자동 개선은 다른 절차다.

## 6. 경로가 다른 경우

프로젝트를 다른 드라이브나 폴더에 설치했다면 `C:\Projects\macro_data_platform`만 실제 경로로 바꾼다. 파일명과 상대 경로는 유지한다.
