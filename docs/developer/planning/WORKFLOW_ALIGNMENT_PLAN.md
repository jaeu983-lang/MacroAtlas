# 사용자 흐름에 맞춘 01~03회차 최소 보완 명세

기준일: 2026-10-25. 이 문서 범위의 상태: **보완 01 기본·확장, 보완 02 서비스, 보완 03 제한 실행 연결 완료**.
현재 전체 현황에서는 04회차 Gate A도 통과했다. 별도 보고서 `docs/developer/history/ITERATION_04_REPORT.md`를 참조한다.
기준은 PROJECT_PLAN.md §4.0/7.3/8.3 및 docs/developer/IMPLEMENTATION_PLAN.md다.
docs/developer/planning/USER_WORKFLOW_REVIEW.md의 제안을 제품 요구사항으로 반영하고 최소 보완을 정리했다.
04회차를 시작하거나 기존 회차를 다시 구현 완료 처리하는 문서가 아니다.

실행 순서/우선순위의 최신 기준은 IMPLEMENTATION_PLAN.md 상단의 ‘현재 기준과 실행 재정렬’이다.
이 문서는 그 아래의 보완 상세 명세다. 보완 01 확장을 다시 시작하는 별도 개발 경로로 사용하지 않는다.

## 1. 최소 목표와 제외 범위

목표는 “후보 탐색 → 선택/조건 확정 → 연결된 실제 수집”의 **계약과 실행 연결**을 마련하는 것이다.
후보와 메타데이터는 우선 수동으로 제공한 근거 또는 테스트 fixture를 사용한다.
자동 기관 추천·자연어 의미 해석·메타데이터 검색 엔진은 05~08회차에서 구현한다.

이번 보완안에는 신규 기관/국가/지표, CSV/XLSX 내보내기, 변환·리샘플링,
대규모 다운로드, 인증 키 로더, 04회차의 정규화/품질/피드백 저장을 포함하지 않는다.
최종 사용 설명서/PPT 제작도 이번 대상이 아니다.

추가 출력/변형 정책은 기본 계약과 분리된 workflow_extensions.py의 값 모델로 반영했다.
파일/링크/둘 다·링크 상태·후보 그룹/변형을 표현하고 검증하지만 탐색·질문·출력 실행은 없다.
표현 선호의 저장/자동 적용도 미구현이다. 아래 통합 순서로 기존 계획을 갱신하며
과거 JSON/fingerprint 및 Task/Stage 오류 계약을 유지한다.

## 2. 보완 01 — 공통 요청·선택·출력 계약

기존 contracts.py의 Task/StageResult/상태 enum/ValueError 계약을 바꾸지 않고,
별도 workflow_contracts.py에 다음의 최소 값 모델을 추가하는 안이다. 이름은 제안이다.

| 계약 | 최소 내용/검증 |
|---|---|
| DataRequest | 원요청, 선택적 기관 힌트, 통계 개념, 국가/차원, 기간, 주기·단위/변환 정책, 개정판 요구. 미확정 값은 명시적 unknown |
| CandidateProposal | 제안 ID·개정, 후보 목록, 후보별 기관·식별자/series key·정의·근거·추천 이유·불확실성·가용성·인증/지원 상태 |
| OutputSpec | 요청 형식·저장소 상대 출력 위치. 원본 보존과 출력물을 구분. 잘못된 경로·미지원 형식을 조용히 대체하지 않음 |
| ConfirmedSelection | 요청·제안 개정·선택 후보와 확정 조건/출력의 스냅샷, UTC 확인 시각·확인 방식·내용 fingerprint |

후보 식별자 미확인을 허용하는 초안과 수집 가능한 확정 요청을 구분한다.
확정에는 필요한 선택·조건·근거가 있어야 하며 true 하나로 미확정 값을 승인하지 않는다.
가용성·인증이 unknown이면 known으로 조용히 바꾸지 않는다.
fingerprint는 선택/조건의 동일성 표식이며 04회차 원본 파일 hash 카탈로그가 아니다.

**예상 변경 파일**

- 신규 src/macro_data_platform/workflow_contracts.py
- 신규 tests/test_workflow_contracts.py
- docs/developer/ARCHITECTURE.md, docs/developer/history/DECISION_LOG.md, 해당 보완 보고서

**추가 테스트 기준**

- 기관 미지정/지정 요청, 후보 1개/여러 개/없음, 미확인 메타데이터 표현.
- 존재하지 않는 후보 선택, 제안 개정 불일치, 필수 기간/대상 누락은 확정 불가.
- 동일 후보라도 기간·출력·정의/근거 개정 변경 시 확인 fingerprint가 달라짐.
- UTC·JSON 왕복·변경 가능한 입력 복사와 unknown/null 보존.
- 절대 경로/저장소 이탈 거부, 테스트용 비밀값을 모델 설명·예외에 노출하지 않음.
- 기존 contracts 및 테스트 기준 유지. 새 계약을 만드는 것만으로 수집을 실행하지 않음.

### 2.1 보완 01 확장 통합 명세 (값 계약 구현, 실행 미구현)

| 확장 모델 | 역할 |
|---|---|
| DeliverySpec | mode=None/file/link/both, 선택적인 기존 OutputSpec과 링크 ID. None은 질문 필요로 유지 |
| VariantAttributes / CandidateVariant | 계절조정·가격/기준년·stock/flow·수준/변화율·단위/배율·개정/방법론/대상 및 원코드·근거 |
| CandidateGroup / GroupedProposal | 기존 제안을 감싸고 명시적 concept·멤버·그룹 근거를 연결. 자동 분류/병합 없음 |
| DataLink | 후보/제안/조건 fingerprint에 연결된 링크 상태·유형·확인/만료·공개/공유 조건·수동 필터·제약·근거 |
| DeliveryOffer | 선언된 파일 형식과 특정 시각에 유효한 데이터 링크로 가능한 전달 모드를 계산 |
| ConfirmedDelivery | 명시적인 전달 방식·선택 후보/조건·변형·유효 링크의 일관성 및 새 내용 fingerprint |

기존 workflow_contracts.py/schema_version=1 JSON/ConfirmedSelection fingerprint는 그대로 둔다.
확장은 별도 wrapper 형식과 domain을 갖는 fingerprint를 쓰며 기존 객체를 자동 승격하지 않는다.
변경 전 JSON 5종과 hash를 golden fixture로 고정해 byte 왕복과 해시를 검사한다.
mode를 파일 형식 문자열로 대체하거나 link 선택에 가짜 OutputSpec을 채우지 않는다.

확장 변경 파일: 신규 workflow_extensions.py, tests/test_workflow_extensions.py 및
tests/fixtures/workflow_v1_golden.json. 기존 실행기·DB·수집기는 변경하지 않는다.
검수는 3모드/미지정, 4링크 상태와 만료/참조 페이지/권한/비밀 URL, 그룹 참조·stock/flow 충돌,
요구 변형의 일치/미상, 조건·그룹·링크 변경에 따른 확인 무효화, JSON/불변성과 무부작용을 포함한다.

## 3. 보완 02 — 확인 상태와 새 수집/전달 작업 연결

구현 완료: WorkflowService(Python API), 전체 364개 테스트/Ruff 통과.
기존 SQLite version 2의 선택적 JSON 필드/이벤트로 저장하며 기관별 실행은 연결하지 않았다.
사용 예·멱등성/만료 정책·남은 문제는 ALIGNMENT_02_REPORT.md와 ARCHITECTURE.md 참조.

Orchestrator 앞에 WorkflowService를 두어 후보/조건/전달 방식의 초안·부족한 항목·확정을 관리한다.
워크플로 확인 상태는 기존 TaskStatus/StageStatus와 별개다.
이미 명시한 데이터 선택·조건·수집 지시는 확인 근거로 기록해 재질문하지 않는다.
누락/모호한 부분만 한 번에 반환한다. 실제 질문 UI·자연어 추출기는 이 보완의 대상이 아니다.

새 요청 경로는 DeliverySpec/DeliveryOffer/ConfirmedDelivery를 사용한다. 전달 방식이 없으면
requires_choice에 따라 가능한 방식만 담은 구조화 질문 항목을 반환하며 과거 선호로 채우지 않는다.
available/unavailable/unknown/blocked와 수동 필터 제약을 질문 데이터에 남긴다.
링크만 선택하면 수집 엔진을 계획하지 않고 링크 전달 의도로, file/both는 필요한 파일 작업으로
분기한다. 자동 링크 조사·자동 그룹 생성 대신 제공된 근거/fixture만 연결한다.
기존 v1 확인 기록은 legacy로 보존하고 새 확인은 wrapper 종류/버전을 context에 명시한다.
실제 링크 전달과 수집/파싱 성공의 작업 의도·결과를 구분한다.

탐색 작업의 계획/성공 결과는 유지하고 새 수집 task_id를 만든다. 원요청 연결에는
기존 탐색 task_id를 활용하며, 알려진 후보로 시작하는 경우도 출처 있는 요청/제안 기록을
먼저 만든다. 수집 작업은 선택 스냅샷과 출처 요청/제안 개정으로 연결한다.
조건 변경은 새 확인 기록·수집 작업이며, 실패 재개는 기존 수집 task_id의 새 시도다.

저장은 기존 작업 JSON의 선택적인 workflow context와 추가 이벤트를 사용하는 안을 우선한다.
기존 문서에 그 필드가 없으면 legacy로 해석하고, schema version 2와 과거 행을 임의로
변환하지 않는다. 새 context/이벤트/수집 작업 생성은 원자적으로 처리해야 한다.
구현 중 별도 테이블·스키마 이관이 필요해지면 최소안에서 확장하지 말고 결정 로그에 기록한다.

같은 확인 스냅샷으로 반복 요청하면 같은 수집 작업을 반환하고, 같은 키에 다른 스냅샷이
오면 충돌로 거부한다. runner의 기존 요청 기반 멱등성은 context 없는 호출에서 유지한다.
재사용 fingerprint에도 확인 스냅샷을 연결해 서로 다른 선택·조건을 재사용하지 않는다.
resume(approved=True)만으로 미확정 후보/변경된 조건을 확정하지 않는다.

**예상 변경 파일**

- 신규 src/macro_data_platform/orchestration/workflow.py: 구조화된 후보/조건 확인 서비스
- src/macro_data_platform/storage/history.py: 선택적 context·연결 이력·원자적 생성 지원
- src/macro_data_platform/orchestration/runner.py: 기존 호출과 호환되는 선택적 context 및 fingerprint 연결
- src/macro_data_platform/orchestration/__init__.py: 새 서비스 공개
- 신규 tests/test_workflow.py, tests/test_orchestration.py: 보완·회귀 검증
- docs/developer/ARCHITECTURE.md, docs/developer/history/DECISION_LOG.md, 해당 보완 보고서

**추가 테스트 기준**

- 미확정/필수 정보 누락 상태에서는 엔진 호출·raw 쓰기가 0회.
- 모든 조건이 명시된 수집 지시는 중복 확인 없이 기록·실행 준비 가능.
- 확정 후보/기간/출력과 생성한 수집 작업이 정확히 일치하며 원래 계획은 불변.
- 같은 확인 반복은 중복 작업/실행을 만들지 않고, 다른 확인에 같은 키를 쓰면 충돌.
- 선택·근거/조건 변경 후 옛 확인으로 실행·재사용 불가. resume 승인으로 우회 불가.
- 프로세스 재시작 후 확인 대기·확정·작업 연결을 동일하게 조회.
- 기록/이벤트/수집 작업 생성 중 장애 시 모두 롤백, 고아 연결 없음.
- 기존 version 2/선택 필드 없는 작업의 조회·계획·실행·재개·취소 결과 불변.
- 출력 미지시 시 구조화 질문, 명시 지시 중복 질문 없음, 링크 전용 계획의 수집 엔진 0개,
  미지원/만료 링크의 자동 파일 대체 금지, 새/legacy wrapper 구별·context hash 연결을 추가 검증.

기존 Python 저수준 API의 호환성은 유지한다. 이 확인 서비스는 제품 요청 경로의 계약이며
임의 Python 호출을 차단하는 보안 권한 장치를 뜻하지 않는다. 네트워크·접근권한은 별도로 검사한다.

## 4. 보완 03 — 확정 요청을 기존 World Bank 경로에 연결

구현 완료: worldbank_request.py의 명시적 legacy 계획 builder와 새 wrapper dispatcher.
file 실제 API HTTP 200/3행, link/both fixture, 전체 406개 테스트/Ruff를 검증했다.
범위·고정 URL/변형 필터 제한·실제 근거는 ALIGNMENT_03_REPORT.md와 connectors/WORLDBANK.md 참조.

연결 어댑터가 ConfirmedSelection을 검사해 기존 StageSpec의 start_year/end_year로 변환한다.
WorldBankGDPEngine의 기존 입력 형태와 기관별 Python 분리 구조는 유지한다.

통합 후 새 요청은 ConfirmedDelivery를 받되 legacy 진입은 호환 경로로 분리한다.
file/both의 파일 부분만 기존 기간 입력으로 변환한다. link는 이미 근거가 제공된 해당 경로의
링크 결과를 반환하는 분기로 두며 GET/다운로드/파일 생성을 하지 않는다.
이 연결이 링크를 새로 발견하거나 검증하는 모듈을 구현하는 것은 아니다.

허용 범위는 USA / source 2 / NY.GDP.MKTP.CD / 기존 연도 제한·1~10년·1페이지·1 MiB다.
단위·주기는 원본 보존 정책만 허용하고 변환하지 않는다. API가 제공하지 않은 단위·주기를
후보 이름에서 만들어 확정하지 않는다. 파일 전달의 초기 지원 출력은 기존 원본 JSON과 요청 manifest의
경로 반환뿐이다. CSV/XLSX·다른 출력 위치/레이아웃이 미지원이면 전송 전에 명확히 알린다.
원본은 기존 data/raw 정책 안에 저장한다. 다른 형식이나 목적지를 raw로 몰래 대체하지 않는다.

**예상 변경 파일**

- 신규 src/macro_data_platform/ingestion/worldbank_request.py: 확정 요청→제한된 계획 연결
- scripts/verify_worldbank.py: 같은 고정 경로·명시적 --live 조건에 구조화 확인 예시 연결
- tests/test_worldbank.py 또는 신규 tests/test_worldbank_request.py: 실제 전송 없는 통합 검증
- docs/developer/connectors/WORLDBANK.md, docs/developer/ARCHITECTURE.md, 해당 보완 보고서

기존 connectors/worldbank.py, ingestion/worldbank.py, storage/raw_downloads.py의 전송·
파싱·raw 정책은 변경하지 않는 것을 최소안으로 한다. 변경이 필요하면 이유·영향을 별도로 보고한다.

**추가 테스트 기준**

- 올바른 확정 후보와 기간만 기존 엔진의 정확한 입력으로 연결.
- 미확정/후보 개정 불일치·다른 나라/지표/source·기간 초과는 전송/파일 쓰기 0회.
- 미지원 CSV/XLSX/변환/출력 목적지는 수집 전에 보고하며 raw_json으로 자동 대체하지 않음.
- 알려진 필수 조건이 모두 주어진 경우 추가 질문 없이 모의 수집까지 완료.
- 숫자/null/0·빈 단위·관측 상태·lastupdated 보존, 기존 raw 비덮어쓰기와 실패 이력 유지.
- 네트워크 기본 거부·TLS 검증·리다이렉트 거부·키 미접근·요청 예산 유지.
- 확정/미확정 분기는 fixture로 검증. live 재검증은 별도 허용·필요성이 있을 때만 수행하고
  기존 실측 원본 재해석과 새 API 호출을 구분해 기록.

## 5. 후속 회차에 남기는 기능

05~08회차는 자동 기관/후보 탐색과 내부 메타데이터 확인, 실제 사용자 질문·선택을 이 계약에
연결한다. 04/09회차는 해당 회차 범위에서 검증·정규화·지원 출력 형식을 확대한다.
09~10회차는 샘플→예산·분할 계획→본 수집→부분 성공 목록→재개를 구현·검증한다.
대규모 작업의 숫자 상한은 아직 결정하지 않았으며 현재 03회차 상한은 그대로 유지한다.

## 6. 구현 순서·검증 명령·현재 변경

보완 01 기본·확장과 보완 02·03은 완료했다. 04회차 Gate A의 현재 상태는 별도 보고서에 기록했다.
기존 전체 테스트(01~03회차 118개, 기본 보완 후 241개, 확장 후 318개)를 유지하고
매 작업의 새 정상/실패 테스트와 Ruff를 통과해야 한다.
테스트 개수만 맞추기 위해 기준을 낮추지 않으며 이전 보고서의 실측 결과는 소급 변경하지 않는다.

```powershell
.venv/Scripts/python.exe -m pytest -ra --basetemp reports/<해당_보완의_새_임시폴더>
.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py
```

최초 기획 반영은 문서만 변경했고 코드를 적용하지 않았다. 이후 사용자의 보완 01 구현
요청으로 workflow_contracts.py와 해당 테스트를 추가했다. 이후 확장 요청으로 별도 wrapper
모듈/테스트와 v1 golden JSON을 추가했다. 기존 계약/실행기/DB/원본/키/실행 정책은
변경하지 않았다. 확장 최종 전체 318개 테스트와 Ruff 통과. 기본 결과는 ALIGNMENT_01_REPORT.md,
확장 결과는 ALIGNMENT_01_EXTENSION_REPORT.md를 따른다.
위 318개 검증은 보완 01 확장 당시 기록이다. 이후 보완 02만 구현해 전체 364개/Ruff를
검증했다(ALIGNMENT_02_REPORT.md). 이후 별도 보완 03 요청에 따라 제한 실행 연결을 구현했고
전체 406개/Ruff와 file 실제 API를 검증했다(ALIGNMENT_03_REPORT.md). 이후 04회차 Gate A는
별도 실행으로 완료했으며 `docs/developer/history/ITERATION_04_REPORT.md`를 따른다. 보완 01~03 범위 및
그 시점의 결과를 기록한 이 문서의 나머지 내용은 소급 변경하지 않는다.
