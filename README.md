> **최종 기획안 통합본:** 이 저장소는 `PROJECT_PLAN.md`와 `docs/`의 14회 개발 계획이 추가된 버전입니다. 먼저 `START_HERE.md` / `docs/INSTALLATION.md`를 읽으세요. 기존 주간 자동 개선 작업은 Phase 5 검증 전에 설치·실행하지 않는 것을 권장합니다.

# 국제금융 데이터 탐색·수집 플랫폼 — Windows 시작 템플릿

이 템플릿은 **로컬 Windows PC + Python + Git + Codex CLI**를 전제로 합니다.

- 데이터 탐색(discovery)과 실제 데이터 수집(ingestion)을 분리합니다.
- 일일 점검은 Python 테스트를 실행합니다.
- 주간 개선 작업은 별도 Git 브랜치에서 Codex가 코드를 수정하고 테스트합니다.
- 개선 결과는 자동으로 main에 반영하거나 배포하지 않습니다. 사용자가 diff와 테스트 결과를 검토한 뒤 병합합니다.

> **현재 상태:** World Bank USA GDP의 제한 경로에서 04회차 Gate A를 통과했습니다.
> 실제 HTTP 수집, 원본·manifest 해시, SQLite 관측치·검증·피드백 이력을 확인했습니다.
> 범위와 한계는 `docs/ITERATION_04_REPORT.md`, 지원 경로는 `docs/connectors/WORLDBANK.md`를
> 참조하세요. 일반 기관 검색, 타 기관 어댑터, Excel/CSV 내보내기와 폭넓은 통계 품질 검증은
> 지원하지 않습니다.

사용자 관점의 “후보 탐색 → 조건 확인 → 실제 수집” 흐름과 프롬프트 예시,
현재 기획 대비 보완 검토는 [사용 흐름 검토](docs/USER_WORKFLOW_REVIEW.md)를 참조하세요.
이 문서는 목표 흐름과 현재 구현의 차이를 설명하며 신규 기능 구현 완료를 뜻하지 않습니다.

## 1. 설치

PowerShell에서 프로젝트를 저장할 위치로 이동한 뒤 압축을 풉니다. 예시 경로는 `C:\Projects\macro_data_platform`입니다.

다음 프로그램을 설치합니다.

1. Python 3.11 이상
2. Git for Windows
3. Node.js LTS (Codex CLI 설치용)
4. Codex CLI: `npm install -g @openai/codex`

설치 확인:

```powershell
python --version
git --version
node --version
npm --version
codex --version
```

Codex에 로그인하고, 터미널에서 `codex`를 실행해 인증 절차를 완료합니다. 조직에서 제공하는 계정·정책을 사용하는 경우 조직의 지침을 따르세요.

## 2. 프로젝트 초기화

프로젝트 루트에서 실행:

```powershell
Set-Location C:\Projects\macro_data_platform
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
git init
git add .
git commit -m "Initial project scaffold"
```

이미 Git 저장소가 있다면 `git init`을 다시 할 필요가 없습니다. 첫 커밋을 만들기 전에 `.env` 파일이나 API 키가 들어 있지 않은지 확인하세요.

## 3. 먼저 수동 테스트

```powershell
.\scripts\run_checks.ps1
```

테스트가 통과하면 `reports\health_check_*.txt`에 결과가 저장됩니다.

## 4. 자동 개선 실행

자동 개선 스크립트는 아래 조건을 확인합니다.

- Git 저장소인지 확인
- 현재 작업 트리가 깨끗한지 확인
- `agent/improvement-날짜시간` 브랜치 생성
- Codex를 프로젝트 폴더 안에서만 쓰기 가능한 모드로 실행
- Codex에 기존 테스트 실행 및 결과 기록을 지시
- main 브랜치에 자동 병합하거나 커밋하지 않음

수동 실행:

```powershell
.\scripts\run_improvement.ps1
```

중요: Codex의 실제 CLI 옵션은 설치 버전에 따라 달라질 수 있습니다. 실행 전 `codex exec --help`로 옵션을 확인하세요. 템플릿은 `--sandbox workspace-write --ask-for-approval never`를 사용해 **프로젝트 작업 폴더 안의 수정·테스트만 자동화**하도록 구성합니다. 외부 네트워크 접근이나 작업 폴더 밖 권한을 요청하는 작업은 자동으로 허용하지 않습니다.

자동 개선을 처음 실행하기 전에는 `AGENTS.md`와 `GUIDELINES.md`를 읽고, Git 백업/초기 커밋을 확인하세요.

## 5. Windows 작업 스케줄러

`install_tasks.ps1`를 일반 사용자 PowerShell에서 실행합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_tasks.ps1
```

이 스크립트는 현재 사용자 기준으로 다음 작업을 등록합니다.

- `MacroData-HealthCheck`: 매일 오전 07:30에 점검
- `MacroData-AgentImprovement`: 매주 토요일 오전 09:00에 개선 브랜치 생성 및 Codex 실행

기본값은 **사용자가 로그인해 있을 때만 실행**입니다. 노트북이 꺼져 있거나 절전 상태면 실행되지 않을 수 있습니다. 업무용 PC에서는 기관 보안정책과 IT 규칙을 먼저 확인하세요.

작업 확인:

```powershell
Get-ScheduledTask -TaskName "MacroData-*"
Get-ScheduledTaskInfo -TaskName "MacroData-HealthCheck"
```

수동 실행:

```powershell
Start-ScheduledTask -TaskName "MacroData-HealthCheck"
Start-ScheduledTask -TaskName "MacroData-AgentImprovement"
```

삭제:

```powershell
Unregister-ScheduledTask -TaskName "MacroData-HealthCheck" -Confirm:$false
Unregister-ScheduledTask -TaskName "MacroData-AgentImprovement" -Confirm:$false
```

## 6. 검토 및 승인 절차

주간 실행 후:

1. `git status`로 생성된 브랜치 확인
2. `git diff main...agent/improvement-YYYYMMDD-HHMMSS`로 변경사항 검토
3. `reports`에서 Codex 작업 결과 및 테스트 결과 확인
4. 테스트를 직접 다시 실행
5. 변경이 타당할 때만 병합

```powershell
git diff --check
.\scripts\run_checks.ps1
```

검토 전에는 브랜치를 main에 병합하지 마세요. 필요하면 브랜치를 버릴 수 있습니다.

## 7. 보안 기본값

- API 키·비밀번호를 코드, Git, 로그, 프롬프트에 넣지 않습니다.
- `.env`는 로컬 전용이며 Git에 올리지 않습니다.
- API 수집과 코드 개선 작업의 권한을 분리합니다.
- 자동 개선은 프로젝트 작업 폴더에서만 수행합니다.
- 외부 네트워크가 필요한 작업은 별도로 검토하고 필요한 도메인만 허용합니다.
- 실제 데이터 파일이나 개인·기관 내부 파일을 개발 에이전트의 작업 폴더에 무분별하게 넣지 않습니다.
- 금융기관의 업무용 PC에서는 사내 보안정책, API 이용조건, 데이터 라이선스를 우선합니다.

## 8. 다음 개발 단계

1. `discovery/`: 기관별 카탈로그와 SDMX 구조 검색
2. `metadata/`: 원본 메타데이터 모델 및 저장
3. `mapping/`: 공통 개념 ID와 기관 간 crosswalk
4. `connectors/`: IMF/BIS/한국은행 등 실제 API 어댑터
5. `ingestion/`: 다운로드·재시도·검증·갱신
6. `storage/`: SQLite로 시작하고 필요 시 PostgreSQL로 확장
7. `analysis/`: 시계열 결합·변환·분석

먼저 카탈로그와 메타데이터를 구현하고, 그 다음 실제 수치 수집기를 추가하는 순서를 권장합니다.
