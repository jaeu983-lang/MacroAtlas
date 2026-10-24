# 사용자 흐름 보완 01 결과 — 2026-10-24

범위: WORKFLOW_ALIGNMENT_PLAN.md의 보완 01 값 계약만 구현했다.
보완 02·03, 04회차, 자동 탐색·실제 수집·질문 UI·내보내기는 진행하지 않았다.
브랜치: codex/workflow-alignment-01. 커밋·병합·배포 없음.

## 시작 상태

AGENTS/GUIDELINES, PROJECT_PLAN의 관련 요구, 구현·보완 계획과 기존 공통 모델/경로 정책,
관련 기관 문서 및 기존 테스트를 확인했다. 기존 전체 **118 passed in 6.33s**, Ruff 통과.
모든 시작 파일은 여전히 untracked이며 기존 작업물을 삭제하거나 초기화하지 않았다.

## 변경 파일과 이유

| 파일 | 변경 이유 |
|---|---|
| src/macro_data_platform/workflow_contracts.py (신규) | 요청·후보·제안·출력·확인 값 모델, 불변 스냅샷/JSON/내용 fingerprint 검증 |
| tests/test_workflow_contracts.py (신규) | 신규 123개 결정적 정상·실패·무부작용 테스트 |
| docs/ARCHITECTURE.md | 실제 모델 API, unknown/JSON/확인·보안 경계 설명 |
| docs/DECISION_LOG.md | D-027~030 구현 선택·남은 경계 기록 |
| docs/ALIGNMENT_01_REPORT.md (신규) | 이 보고서 |
| docs/WORKFLOW_ALIGNMENT_PLAN.md | 보완 01 완료와 02/03 미착수 구분 |
| docs/IMPLEMENTATION_PLAN.md | 보완 01 값 계약 완료 상태만 갱신 |
| docs/USER_WORKFLOW_REVIEW.md | 최초 검토와 현재 구현 상태 구분 |
| PROJECT_PLAN.md | 값 계약 완료·실행 연결 미구현 상태 명시 |

기존 contracts.py/Orchestrator/SQLite/World Bank/검증 스크립트·테스트 기준·의존성·
PowerShell 정책은 변경하지 않았다. 생산 코드 추가는 신규 계약 모듈 하나다.

## 제공하는 계약과 검증

- DataRequest: 기관 미지정/지정 원요청, 개념·대상·차원·기간·주기/단위 정책·개정판 요구.
  초안의 미확정 값은 None/명시된 빈 목록으로 유지하고 기간으로 주기를 추정하지 않는다.
- Candidate/CandidateProposal: 없거나 1개/여러 개의 후보, 출처 식별·정의·근거·범위·
  불확실성·인증 정책·지원 상태를 보존한다. 실제 키 값 필드는 없고 환경변수 이름만 표현한다.
- OutputSpec: 요청 형식을 표현하며 지원되지 않은 형식을 자동 변경하지 않는다.
  안전한 상대 경로를 검증하고 실제 포함 경로를 조회할 수 있지만 파일은 생성하지 않는다.
- ConfirmedSelection: request_id·제안 개정·선택 후보가 맞고 필수 조건·근거·알려진
  가용 범위가 충족돼야 생성된다. 다른 대상/기간/주기/미지원 출력은 거부한다.
  단위 변환 요구는 알려진 원단위/목표 단위만 기록하고 실제 변환은 하지 않는다.
- fingerprint는 전체 요청·제안/근거·선택·출력의 동일성을 표현한다. 조건/정의/근거 개정이
  달라지면 matches가 False다. 확인 시각/방법은 기록하되 내용 fingerprint에는 넣지 않는다.
- to_dict/to_json 및 각 클래스의 from_dict/from_json 제공. 불변 내부 매핑은 명시적
  변환 메서드로 직렬화한다. 기존 dataclasses.asdict/실행기에 자동 통합하지 않았다.

## 실제 검사 결과

Python 3.12.14/pytest 8.4.2의 기존 .venv를 사용했다. 네트워크·기관 API 호출 없음.

| 검사 | 최종 실제 결과 |
|---|---|
| `.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_alignment01_final` | **241 passed in 6.37s**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py` | **All checks passed!**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m macro_data_platform.health` | 종료 코드 0 |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| `git diff --check` | 종료 코드 0. untracked 신규 파일의 검증을 대신하지 않음 |

기존 118개 + 신규 123개이며 실패/건너뜀 없음.
로그: reports/alignment_01_pytest.txt 및 reports/alignment_01_ruff.txt (Git 제외).

검증한 사례: 기관 힌트/후보 수, unknown 보존, 모든 모델 JSON 왕복, 후보/요청/개정
불일치·필수 조건 누락, 조건/근거 개정 fingerprint 변경, 매핑 순서 안정성,
확인 시각/방법 기록, JSON 변조·중복 키·NaN/버전/미지 필드 거부, 복사/불변성,
유효/잘못된 연·월·분기·일과 UTC, 가용 국가/차원/기간·출력·개정판 불일치,
Windows/POSIX 위험 경로 및 모의 resolver 이탈 거부, 자격증명 필드/표현 비노출,
fixture/문서/API/수집 근거 유형의 비승격, HTTP/DB/파일 생성 부작용 없음.

최초 전체 231개/Ruff는 통과했다. 추가 검사 편집 중 테스트 변수 범위 오류 2건이
발생해 수정했고 테스트 기준을 낮추거나 삭제하지 않았다. 위 표는 수정 후 전체 결과다.
경로 이탈 resolver 테스트는 모의 테스트이며 Windows 실제 junction 생성 검증은 아니다.

## 보안·데이터 완전성

기존 관측치·원본·DB를 변경하지 않았다. 인증정보·환경변수·키 TXT를 읽거나 실제 키를
사용하지 않았다. 생성/복원/비교는 값 검증만 하며 확인 서비스나 수집을 실행하지 않는다.
모델 repr/str 및 검증 오류에는 사용자 입력값을 넣지 않는다. credential URL query와
민감 키 형태의 차원/series key도 거부한다. SourceEvidence/EvidenceKind는 기존 계약을 사용한다.
None/원본 메타데이터 부재와 범위를 임의 보정하지 않으며 근거 유형을 바꿔 표시하지 않는다.

## 남은 문제와 사람 검토

- 상태·지원·가용성은 호출자가 제공한 기록이며 모델이 공식 출처를 조사해 검증하지 않는다.
  확인 객체는 사용자 선택 진위·자격증명 유효성·실제 최신성·실행 권한을 증명하지 않는다.
- CSV/XLSX 등 출력 요청은 표현할 수 있어도 exporter가 생기지 않는다. 실제 지원
  형식·목적지·변환·네트워크/키 설정은 보완 02·03의 실행 전 검증이 필요하다.
- 자유문장의 모든 비밀값을 자동 검출하지 않는다. 명시적 JSON에는 원문이 있으므로
  통째로 로그에 넣지 말아야 한다. 실제 키를 요청/메타데이터 값에 넣어서는 안 된다.
- resolve_under 이후 실제 쓰기 전 경로 재검증/원본 비덮어쓰기는 후속 실행의 책임이다.
- 기간은 해석된 달력 구간만 받는다. 최신/상대 기간 해석, 다른 기간 체계, 임의 단위
  변환과 통계적 동등성 판정은 구현하지 않았다.
- 기존 키 로더·대규모 처리·dependency lockfile·PowerShell 서명 정책·Git 체크포인트
  제한은 유지된다. 모든 파일이 untracked이므로 사람의 변경 검토가 필요하다.

보완 01의 값 계약·정상/실패·JSON·기존 회귀·Ruff 기준은 통과했다.
사람은 명시적 unknown/확정 정책과 JSON·fingerprint·경로 정책을 검토해야 한다.
현재 보완 01을 마치는 데 추가로 필요한 차단 결정은 없다. 보완 02·03과 04회차는 미착수다.
