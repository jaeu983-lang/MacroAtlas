# 개발 환경 설치와 검사

이 문서는 현재 MacroAtlas 소스 체크아웃을 설치하고 로컬 테스트하는 절차다. 제품 상태와 다음
구현 회차는 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), 제품 요구사항은
[`../PROJECT_PLAN.md`](../PROJECT_PLAN.md)를 기준으로 한다.

## 필요한 도구

- Python 3.11 이상
- Git
- 선택: Codex CLI

## 설치

프로젝트 루트에서 실행합니다.

PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

## 검사

```text
python -m pytest
python -m ruff check src tests
git diff --check
```

가상환경을 사용한다면 `python` 대신 해당 가상환경의 Python 경로를 사용합니다. 전체 제품 기능의
검증을 주장하려면 테스트 결과 외에도 실제 서비스 호출 여부와 대상 경로를 따로 기록합니다.

## API 비밀값

`.env.example`은 환경 변수 이름 예시만 포함하며 프로젝트는 `.env`를 자동으로 읽지 않습니다.
실제 키는 승인된 실행 환경의 secret 설정이나 프로세스 환경변수로 공급합니다.

- `BLS_API_KEY`: BLS 일반 series-data 조회에서는 선택 사항이고, 등록 키가 필요하다고 명시된
  catalogue/선택 parameter 요청에는 필요합니다.
- `CENSUS_API_KEY`: 저장소가 확인한 Census API 안내에 따라 데이터 조회에 필요합니다.

키를 소스, Git, 테스트 fixture, 채팅, URL이 포함된 로그에 넣지 않습니다. 실제 인증 성공은 키가
저장돼 있다는 설정 상태와 구분해 live 요청 결과로만 기록합니다.

## 원격 코드와 배포 추적

`git status -sb`, `git rev-parse HEAD`, `git ls-remote --heads origin`으로 작업 트리와 원격
branch가 같은 commit을 가리키는지 확인합니다. local commit만으로 원격 checkout이나 실행 환경에
코드가 전달되지는 않습니다. 원격 push, 환경 draft 변경, 환경 publish는 별도 승인 절차입니다.

API 키와 실제 수집 원본은 저장소에 올리지 않습니다. 이 저장소는 현재 Python API 중심이며,
자연어 채팅 UI와 무인 예약 개선 실행은 완료된 제품 기능이 아닙니다.
