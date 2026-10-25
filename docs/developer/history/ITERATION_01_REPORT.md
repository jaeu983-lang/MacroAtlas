# 01회차 결과 — 2026-10-24

구현 범위: 공통 데이터 모델 및 엔진 경계만 구현. 02회차 미착수.

## 시작 상태

- AGENTS, GUIDELINES, PROJECT_PLAN, IMPLEMENTATION_PLAN, INSTITUTION_CATALOG,
  REFERENCE_SCENARIOS 및 기존 코드·테스트를 읽었다.
- 기존 코드는 health.py와 테스트 함수 2개인 템플릿이었다.
- 초기 브랜치는 master, 모든 시작 파일이 untracked 상태였다.
- 별도 codex/iteration-01 브랜치로 전환했다. 커밋·병합·배포는 하지 않았다.
- 기본 PATH에는 Git/Python이 없었다. 앱의 번들 Git과 Python 3.12.14를 사용했다.

## 변경 파일 및 이유

- src/macro_data_platform/contracts.py: Task/SourceEvidence/StageResult,
  상태·오류·근거 유형과 독립 Engine Protocol. 필수 값/UTC/실패 오류 검증.
- src/macro_data_platform/config.py: 명시적 환경 입력, 오프라인 기본값,
  SQLite/원본/정규화 경로 구분과 저장소 밖 경로 거부.
- src/macro_data_platform/{discovery,metadata,mapping,connectors,ingestion,
  analysis,storage,orchestration}/__init__.py (8개): 구현 없는 책임 경계.
- tests/test_foundations.py: 정상·실패 계약 및 설정 테스트 11개.
- .env.example: 비밀정보 없는 환경변수 예시.
- .gitignore: SQLite journal/WAL 등 부속 파일 제외.
- docs/developer/ARCHITECTURE.md: 엔진 계약, 경로·설정 정책 및 회차 범위 문서화.
- docs/developer/history/DECISION_LOG.md: 설계 선택과 미해결 사항 D-005~009.
- docs/developer/history/ITERATION_01_REPORT.md: 이 보고서.

## 최초 테스트 결과 (보완 전 이력)

PYTHONPATH=src, 번들 Python 사용. 네트워크 호출 없음.

| 검사 | 실제 결과 |
|---|---|
| python -m pytest (변경 전) | 실행 실패: No module named pytest |
| python -m unittest discover -s tests -v | 11개 실행, 모두 통과 |
| 기존 test_health.py 함수 2개를 별도 임시 디렉터리로 직접 호출 | 2개 모두 통과 |
| python -m macro_data_platform.health | cp949 출력 UnicodeEncodeError |
| python -X utf8 -m macro_data_platform.health | 종료 코드 0, 레이아웃 확인 통과 |
| git diff --check | 종료 코드 0; 모든 파일이 untracked이므로 신규 파일 검사 근거로는 불충분 |

unittest는 기존 pytest 함수를 수집하지 않으므로 직접 호출 결과를 별도로 기록했다.
pytest 러너의 수집·fixture 동작까지 확인한 것은 아니다.

## 최초 한계 (아래 보완 결과로 대체)

- 전체 pytest 검증은 보류. 통제된 개발 환경에 venv/dev 의존성을 준비한 후 재실행 필요.
- 기존 health CLI의 Windows 출력 인코딩 문제는 남아 있다. UTF-8 실행으로 우회 검증했다.
- 공식 문서 링크는 저장소 사전 조사만 읽었으며 새 외부 문서/API 검증은 하지 않았다.
  기관 시나리오 A~H와 실제 수집은 NOT_RUN이다.
- 실제 DB/원본 저장, 정규화, 상태 전이·재개는 미구현이다.
- unknown을 None으로 보존하고 근거 유형을 구별한다. 원본 관측치 변경 없음.
- 인증정보를 읽거나 기록하지 않았다. 네트워크·스케줄러·자동 개선은 실행하지 않았다.
- 경로 검증은 파일 접근 권한을 대체하지 않는다. 향후 실제 쓰기 시 재검증 필요.

## 최초 검토 상태 (아래 보완 결과로 대체)

01 구현 범위는 작성했고 로컬 계약 검증은 통과했다. 전체 pytest 및 사용자 검토가
남아 있으므로 01회차 검수는 조건부다. 02회차는 진행하지 않았다.
사용자는 경로/계약 선택과 미해결 결정, 전체 untracked 시작 파일을 검토해야 한다.
다음 회차 전에 전체 pytest 실행과 01 변경 검토·Git 체크포인트가 필요하다.

## 01회차 검증 보완 완료 — 2026-10-24

02회차는 진행하지 않았다. 기존 codex/iteration-01 브랜치를 유지했다.

### 이번 보완 변경 파일

- src/macro_data_platform/health.py: stdout 인코딩은 유지하고 backslashreplace 오류
  처리로 미지원 경로 문자 출력 시 중단 방지. UTF-8에서는 원문 그대로 출력.
- tests/test_health.py: cp949/UTF-8/ASCII strict 출력 subprocess 회귀 테스트 3개 추가.
  경로 구분자의 OS 차이도 고려한다.
- .gitignore: editable 설치의 *.egg-info 및 Ruff 캐시 제외.
- docs/developer/ARCHITECTURE.md: venv 실행 방법과 출력 정책 추가.
- docs/developer/history/DECISION_LOG.md: D-007/008 해결, 스크립트 정책·Ruff 잔여 사항 기록.
- docs/developer/history/ITERATION_01_REPORT.md: 현재 검증 결과로 갱신.
- 로컬 환경 .venv 및 reports/iteration_01_{pytest,health,environment,ruff}.txt 생성.
  이 파일들은 Git 제외 대상이다. scripts/run_checks.ps1의 내용은 변경하지 않았다.

### 환경 준비 및 최종 검증

번들 Python 3.12.14로 저장소 내부 .venv 생성 후 프로젝트/dev editable 설치 완료.
최초 설치는 샌드박스 네트워크 차단으로 실패했고, 승인된 네트워크 설치로 완료했다.
pytest 8.4.2, 설치 의존성 버전은 reports/iteration_01_environment.txt에 기록했다.
버전 기록은 `python -X utf8 -m pip list --format=freeze`로 생성했다.
초기 pip freeze는 editable 경로 출력 인코딩과 PATH의 Git 부재로 실패해 사용하지 않았다.

| 명령/검사 | 최종 결과 |
|---|---|
| .venv/Scripts/python.exe -m pytest -ra | 16 passed, 실패·건너뜀 없음 |
| 포함 테스트 | 기존 레이아웃 2개 + 공통 계약 11개 + 출력 인코딩 3개 |
| .venv/Scripts/python.exe -m macro_data_platform.health | 종료 코드 0, -X utf8 없이 통과 |
| .venv/Scripts/python.exe -m pip check | No broken requirements found, 종료 코드 0 |
| .venv/Scripts/python.exe -m ruff check src tests | 종료 코드 1, 17건 잔여 |
| scripts/run_checks.ps1 | 미실행: 서명되지 않은 스크립트를 금지하는 실행 정책으로 차단 |

회귀 테스트 작성 중 첫 전체 실행은 OS 경로 구분자에 대한 테스트 단정 때문에
15 passed/1 failed였다. Windows 구분자를 고려하도록 수정 후 최종 전체 16개 통과.
설치 완료 전 임시 확인은 pytest/프로젝트 모듈 부재로 실패했으며 최종 결과와 구분한다.

### 현재 남은 문제 및 검수 결론

- pytest 환경 부재와 health 출력 예외는 해결했다. 01회차의 전체 테스트 기준은 통과했다.
- cp949/ASCII에서 지원하지 않는 문자는 이스케이프로 표시된다. 원문 표시가 필요하면
  UTF-8 출력 환경을 사용한다. 파일 경로나 원자료 자체를 바꾸지는 않는다.
- Ruff 17건은 config.py, contracts.py, test_foundations.py의 import/스타일 및 타입
  예외 권고다. 테스트를 약화하거나 ValueError 계약을 임의 변경하지 않았다.
- PowerShell 스크립트 자체의 실행 검증은 서명 정책 때문에 남아 있다. 정책 우회나
  자동 스케줄러 실행 없이 구성 명령들을 직접 검증했다.
- 설치 버전 스냅샷은 남겼으나 완전한 의존성 lockfile은 아직 없다.
- 전체 시작 파일은 여전히 untracked다. 커밋·병합 전 사람의 전체 변경 검토가 필요하다.
- 실제 DB·수집·상태 전이·재개는 후속 회차 범위이며 이번에 구현하지 않았다.
  공식 문서 재조사/API 호출/기관 시나리오 A~H는 NOT_RUN이다.
- 네트워크는 승인된 패키지 설치에만 사용했다. 인증정보 접근, 원본 관측치 수정,
  배포·병합·예약 작업 등록은 하지 않았다.

01회차 테스트 검증은 완료. 사람의 변경 검토와 Git 체크포인트는 남아 있다.
추가 사용자 결정이 필요한 구현 차단 사항은 없다. 스크립트 서명 및 Ruff 정리는
별도 검토 항목이며 02회차는 사용자 요청 전까지 시작하지 않는다.

## Ruff 정리 최종 결과 — 2026-10-24

위 검증 보완 당시의 Ruff 17건은 해결했다. 최신 상태는 다음과 같다.

- 변경 파일: config.py(Mapping import), contracts.py(조건문·반공변 타입 변수명),
  test_foundations.py(import·UTC 별칭·동일 의미의 dict/with 표현), 이 보고서와 DECISION_LOG.md.
- 기존 ValueError 오류 유형과 메시지를 유지했다. TypeError를 권하는 TRY004 세 곳은
  공개 오류 계약 보존 사유를 적은 줄 단위 noqa로 처리했다. 전역 Ruff 규칙은 변경하지 않았다.
- 테스트 삭제·기준 완화·동작 변경 없음. `python -m pytest -ra`: **16 passed in 0.46s**.
- `python -m ruff check src tests`: **All checks passed!**, 종료 코드 0.
- 최신 로그: reports/iteration_01_pytest.txt 및 reports/iteration_01_ruff.txt.
- PowerShell 실행 정책과 스크립트는 변경하지 않았다. 스크립트 서명 정책에 따른
  실행 검증 한계, 의존성 lockfile 부재, Git 체크포인트·사람 검토는 남아 있다.
- 네트워크 호출·원본 데이터 변경·병합·배포 없음. 추가 사람 결정이 필요한 코드
  차단 사항은 없다. 02회차는 진행하지 않았다.

## 기획 보완 — 기관별 API 키 선택 등록

사용자 요청에 따라 PROJECT_PLAN.md §2.1 및 DECISION_LOG.md D-012를 추가했다.
필요한 기관만 키를 등록하고 키가 필요 없는 경로는 익명 이용한다. 미설정 기관은
그대로 두되 필수 키가 필요한 경로만 설정 필요 상태로 처리하는 향후 정책이다.
실제 키는 기획안에 넣지 않고 로컬 .env/환경변수로 보관한다.
문서 3개만 변경했으며 실제 키 접근·등록, 네트워크 호출, 코드·테스트 기준 변경은 없다.
이번 문서 변경에서는 테스트를 재실행하지 않았다. 직전 코드 검증은 pytest 16개 및
Ruff 통과이며 실제 인증·.env 로딩·기관별 키 요구 조건은 검증하지 않았다.
02회차와 PowerShell 실행 정책은 변경하지 않았다.
