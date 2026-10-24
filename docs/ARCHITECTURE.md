# 01회차: 공통 모델과 경계

기준: PROJECT_PLAN.md §5–8, docs/IMPLEMENTATION_PLAN.md 01.

기존 구현은 health.py의 레이아웃 점검과 pytest 테스트 2개뿐이었다.
이번 회차는 표준 라이브러리 기반 계약과 경로 계산만 추가한다.

| 패키지 | 책임 |
|---|---|
| contracts | Task, SourceEvidence, StageResult, 상태·오류 분류, Engine Protocol |
| discovery | 기관·가이드·데이터셋 후보 탐색 |
| metadata | 원문 보존 및 근거 기반 정규화 |
| mapping | 개념 연결 및 근거·신뢰도 |
| connectors | 기관별 API/파일 접근 어댑터 |
| ingestion | 선택된 출처의 관측치 수집·검증 |
| storage | SQLite 카탈로그 및 파일 저장 |
| analysis | 저장 데이터 분석 |
| orchestration | 02회차에서 순차 실행·재개·취소·이력 구현(아래 참조) |

엔진은 `Engine[Input, Payload].run(input) -> StageResult[Payload]` 계약을 사용한다.
반환 필드는 status, payload, evidence_refs, warnings, error_code, retry_hint다.
01회차에는 패키지 경계와 상태 어휘만 준비했다. 02회차의 실행·재개 구현은 아래와 같다.
02회차 종료까지 동작하는 기관 탐색·실제 수집 엔진은 없었다. 03회차의 제한 수집은 아래 참조.

SourceEvidence는 원본 참조·기관·URL·UTC 시각과 선택적인 데이터셋/시계열/버전을 보존한다.
공식 문서, fixture, live API, live ingestion은 별도 유형이다. 유형 값 자체가 검증을
수행하거나 공식성을 보증하지 않는다. 미확인 식별자는 None이며 추정하지 않는다.
실제 원본의 해시·저장 및 정규화 메타데이터 전체는 후속 회차 범위다.

Settings.from_env(project_root, env)는 명시적으로 받은 환경만 읽는다.
`.env` 자동 로드, 키 수집·로그, 네트워크 호출, 디렉터리 생성은 하지 않는다.
MACROATLAS_DATA_DIR 기본값은 data, NETWORK_ENABLED 기본값은 false다.
true는 설정 의사만 표현하며 네트워크 권한을 부여하지 않는다.
환경변수 전체 이름은 MACROATLAS_NETWORK_ENABLED이며 true/false만 허용한다.

SQLite 위치는 data/catalog.sqlite, 원본은 data/raw, 정규화는 data/processed다.
경로는 저장소 상대 경로여야 하며 resolve 후 저장소 밖이면 거부한다.
이 정책은 보안 격리 장치가 아니다. 향후 파일 쓰기 시 경로 재검증과 원본 비덮어쓰기,
해시·버전 관리가 필요하다. 01회차에는 DB 연결·스키마·관측치 쓰기를 구현하지 않았다.
실제 데이터·DB·비밀정보는 Git에 포함하지 않는다.

검증 명령(Python 3.11+, PYTHONPATH=src):
`python -m pytest` 또는 신규 계약 테스트만 `python -m unittest discover -s tests -v`.
후자는 기존 pytest 함수 테스트를 수집하지 않으므로 전체 pytest 통과로 보고하지 않는다.

01회차 검증 보완: 저장소 `.venv`에 `pip install -e ".[dev]"`로 설치했다.
PowerShell에서 `.venv/Scripts/python.exe -m pytest`로 전체 테스트를 실행한다.
editable 설치 후에는 PYTHONPATH 설정이 필요 없다. 설치 버전 기록은
reports/iteration_01_environment.txt에 있다(로컬 검증 산출물, Git 제외).
health CLI는 stdout의 인코딩을 유지하고 표현 불가능한 문자를 이스케이프한다.
따라서 cp949 출력에서도 UnicodeEncodeError 없이 종료하며 UTF-8에서는 원문을 유지한다.

README의 기존 개발 순서보다 PROJECT_PLAN/IMPLEMENTATION_PLAN의 회차 순서가 우선한다.
주간 자동 개선 및 스케줄러는 Phase 5 전 실행하지 않는다.

## 02회차: 순차 Orchestrator와 SQLite 작업 이력

`orchestration.models`는 StageSpec/TaskPlan/StageInput, `orchestration.runner`는
Orchestrator, `storage.history`는 HistoryStore를 제공한다. 새 의존성은 없다.
현재 실행 인터페이스는 Python API이며 자연어 계획 생성·CLI 제품 명령·네트워크
커넥터는 02회차에 없었다. 03회차 원본 수집은 아래, 정규화 관측치 저장은 04회차 범위다.

```python
from macro_data_platform.config import Settings
from macro_data_platform.orchestration import Orchestrator, StageSpec, TaskPlan
from macro_data_platform.storage import HistoryStore

# project_root는 명시적으로 지정한 저장소 Path, engines는 호출자가 주입한 엔진 목록.
store = HistoryStore(Settings(project_root))
runner = Orchestrator(store, engines)  # 키: (엔진 이름, 버전 문자열)
task = runner.create("구조화된 작업 요청", idempotency_key="사용자가 정한 요청 키")
runner.plan(task.task_id, TaskPlan((StageSpec("discovery", "mock", engine_version="1"),)))
result = runner.run(task.task_id)
history = store.get(task.task_id)
events = store.events(task.task_id)
```

계획은 순서가 있는 선형 의존성이다. 각 단계는 바로 앞 단계의 payload와
evidence_refs를 StageInput.upstream/input_refs로 받으며 원본은 변경하지 않는다.
계획 입력과 저장·조회 결과는 JSON 스냅샷이다. NaN/비 JSON 결과는 성공 저장을 거부한다.
각 단계 시도에는 입력 fingerprint, engine/version, 입력 근거와 이전 stage_run_id,
결과의 payload/출력 근거/warnings/error_code/retry_hint, UTC 시작·종료 시각을 남긴다.

저장소는 설정의 database_path(기본 data/catalog.sqlite)에 tasks와 task_events를
생성한다. tasks의 JSON에 고정 계획·작업 시도·단계 시도를 보존하고 이벤트는 추가만 한다.
스냅샷 갱신과 이벤트 추가는 BEGIN IMMEDIATE 트랜잭션 하나로 커밋한다. schema version은
2이며 0(초기)/2 이외 버전은 거부한다. 이는 메타데이터 전체 카탈로그 스키마가 아니다.
JSON 전체 갱신 방식은 대규모 이력에 최적화하지 않았으며 스키마 마이그레이션은 미구현이다.

### 상태와 재시도

- create → CREATED, plan → PLANNED, run → RUNNING → COMPLETED.
- 재시도/종료 실패: 성공한 앞 단계가 있으면 PARTIAL, 없으면 FAILED.
  NEEDS_REVIEW 결과는 작업도 NEEDS_REVIEW로 중단한다. 후속 단계는 실행하지 않는다.
- run은 PLANNED에서만 시작하고 완료된 작업의 재호출은 기존 결과를 반환한다.
  이전 시도는 resume으로만 재실행하며 동일 task_id 아래 새 작업 시도와 단계 시도를 추가한다.
- NEEDS_REVIEW의 resume은 approved=True라는 호출자의 명시적인 검토 확인이 필요하다.
  인증/이용권한 오류가 재시도 가능으로 잘못 반환되면 NEEDS_REVIEW로 제한한다.
  FAILED_TERMINAL은 취소나 승인으로도 재시도하지 않는다. 조건 수정은 새 작업으로 기록한다.
- max_attempts는 단계당 전체 엔진 호출 상한(기본 3, 허용 1~10)이다. 재사용은 호출로
  세지 않는다. 상한 초과 시 NEEDS_REVIEW, approved=True로도 상한을 초기화하지 않는다.
  이번 회차는 수동 resume이며 자동 sleep/backoff·HTTP 재시도는 후속 회차 범위다.

### 재사용·취소·복구

동일 idempotency_key와 정확히 동일한 요청은 같은 task_id를 반환한다. 다른 요청과
충돌하면 거부한다. 키 생략 시 새 작업이다. 저장 계획은 변경 불가하며 동일 계획 저장만
멱등이다. 계획·엔진 버전·의존 입력은 fingerprint로 연결한다.

resume 시 재사용은 성공한 연속된 앞 단계만 가능하다. 동일 fingerprint, 원래 성공
시점부터의 TTL(기본 3600초, 0이면 재사용 금지), 호출자가 주입한 reuse_validator의
True를 모두 요구한다. 검증기는 원자료/파일/근거의 동일성과 최신성을 확인할 책임이 있다.
없거나 실패·예외·만료·시계 역행이면 재실행한다. 재사용이 원래 TTL을 연장하지 않는다.
앞 단계 하나라도 재실행하면 후속 저장 결과도 재사용하지 않는다. 검증기에는 복사본을
주므로 검증 중 수정이 저장 이력이나 실행 입력을 바꾸지 않는다.

cancel은 실행 중인 엔진을 강제로 끊지 않고 다음 단계 경계에서 중단한다. 이미 얻은
결과는 보존하며 나머지는 실행하지 않는다. 실행 중 DB 락을 잡고 있지 않아 다른 연결로
취소 요청이 가능하다. 완료/취소 상태에 반복 취소해도 결과·이력을 중복 생성하지 않는다.

작업 실행 토큰으로 중복 실행을 거부한다. KeyboardInterrupt/프로세스 중단/저장 실패는
RUNNING 기록을 남길 수 있다. **이전 작업자가 종료됐고 외부 부작용을 확인한 뒤에만**
recover_interrupted(task_id)를 호출한다. 그 후 resume은 새 시도로 진행한다.
복구된 예전 토큰은 결과를 커밋할 수 없다. 자동 장애 감지·분산 lease·강제 종료는 없다.
DB와 외부 다운로드를 하나의 트랜잭션으로 묶지 않으므로 외부 부작용의 exactly-once를
보장하지 않는다. 향후 수집 어댑터는 별도의 멱등성과 원본 비덮어쓰기 정책이 필요하다.

오류 예외의 메시지/traceback은 저장하지 않고 INTERNAL_BUG로만 기록한다. 자격증명은
실행 설정으로 엔진에 별도 주입해야 하며 요청·계획·payload·근거 URL에는 넣지 않는다.
이 API는 임의 문자열의 모든 비밀값을 탐지하는 필터가 아니다. 실제 인증·.env 로딩은
미구현이며 키를 읽지 않는다. 기관별 인증 유무는 구현했다고 주장하지 않는다.

## 03회차: World Bank 한 경로의 실제 수집

connectors/worldbank.py는 고정 GDPQuery·네트워크 기본 거부 전송·독립 최소 파서를,
ingestion/worldbank.py는 WorldBankGDPEngine을, storage/raw_downloads.py는 해당 경로의
원본/요청 manifest 배타 저장을 제공한다. 기존 Orchestrator는 수정하지 않고 주입한다.
실제 API 인증이 없는 이 경로만 구현했으며 .env 로딩이나 다른 기관 키 처리는 없다.

네트워크 opt-in·원본 보존·1페이지/1 MiB/짧은 기간 제한과 모의 HTTP 테스트를 추가했다.
공식 문서 확인, fixture 검증, 실제 API 응답 및 그 원본의 로컬 재해석을 구분한다.
범위·오류·이용 조건·검증 보조 명령은 docs/connectors/WORLDBANK.md에 기록했다.
04회차의 해시/정규화 저장·종합 품질·피드백 기능은 추가하지 않았다.

## 사용자 흐름 보완 01: 값 계약 (실행 연결 없음)

workflow_contracts.py에 DataRequest, Candidate, CandidateProposal, OutputSpec,
ConfirmedSelection을 추가했다. 기존 contracts.py와 Orchestrator/SQLite/World Bank
코드는 변경하지 않았다. 보완 02 서비스·보완 03 연결·04회차 기능은 미구현이다.

DataRequest는 기관 힌트 없는 요청과 지정 요청을 모두 표현한다. concept/기간/주기/
단위 정책/개정판 요구 등의 None은 unknown이며, countries 빈 목록은 대상 미확정,
dimensions=None은 차원 미확정, dimensions={}는 추가 차원 없음이다.
기간은 해석된 YYYY/YYYY-MM/YYYY-Qn/YYYY-MM-DD만 받는다. latest 같은 자연어 기간은
요청 원문에 보존하고 해석되기 전에는 확정하지 않는다. 기간 모양으로 주기를 추정하지 않는다.

Candidate는 출처별 정의·식별자/series_key·차원·가용 범위·근거·불확실성·인증/지원 상태를
보존한다. CandidateProposal은 후보가 없거나 1개/여러 개인 경우를 모두 지원한다.
근거는 기존 SourceEvidence/EvidenceKind를 사용한다. 검증 상태는 호출자의 명시적
기록이며 evidence kind만으로 검증/가용성을 승격하지 않는다. 자동 탐색/공식성 검증은 없다.
credential_env_var는 변수 이름만 받으며 실제 키·환경변수·파일은 읽지 않는다.

ConfirmedSelection은 존재하는 후보, 동일 request_id/제안 개정, 필요한 요청 조건,
출처 식별·정의·근거, 알려진 가용성/인증 정책/지원 상태와 범위를 검사한다.
국가·차원·기간·명시한 주기가 맞아야 하며 미지원 출력은 거부한다. 원본 주기/단위를
보존하겠다는 정책은 메타데이터를 만들어내지 않는다. 변환 요구는 알려진 단위가 필요하지만
모델 자체는 변환하지 않는다. 실제 변환/출력 지원·키 설정·최신성은 후속 실행 경로에서
다시 확인해야 한다. 이 객체는 사람의 조건 확인 기록이며 실행 권한이나 의미 동등성의 증명이 아니다.

모델은 frozen dataclass와 읽기 전용 매핑/tuple로 입력을 분리한다. dataclasses.asdict
대신 제공된 to_dict()/to_json()으로 직렬화하고 각 클래스의 from_dict()/from_json()으로 복원한다.
JSON schema_version=1은 이 값 계약의 버전이며 기존 SQLite version 2와 무관하다.
UTC만 허용하고 JSON 중복 키·NaN·알 수 없는 필드/버전·변조 fingerprint를 거부한다.

확인 fingerprint는 원요청·전체 제안/근거·선택·개정·출력을 canonical JSON으로 묶은
SHA-256이다. 매핑 삽입 순서에는 무관하고 재확인 시각/방법에는 영향받지 않는다.
확인 기록에는 시각/방법도 별도로 남긴다. matches()로 현재 입력과 일치하는지 확인할 수 있다.
이는 비밀 서명·사람 승인 증명·원본 파일 hash 카탈로그가 아니다. 아무 서비스도 자동 실행하지 않는다.

OutputSpec은 요청 형식과 출력 상대 경로를 표현할 뿐 파일을 내보내지 않는다.
Windows/POSIX 절대 경로·드라이브/UNC·..·예약 파일명 등을 거부하고 구분자를 정규화한다.
resolve_under(project_root)는 실제 경로의 저장소 포함 여부만 검사하며 디렉터리를 만들지 않는다.
실제 쓰기 직전 경로 재검증은 후속 구현의 책임이다.

모델 repr/str과 검증 예외에는 사용자 값을 넣지 않는다. 잘 알려진 자격증명 query/차원
키도 거부한다. 명시적 to_dict/to_json은 원문을 보존하므로 무조건 로그에 남기면 안 된다.
임의 자유문장의 모든 비밀값을 검출하는 도구는 아니며 호출자는 키를 입력하지 않아야 한다.
세부 테스트와 미구현 범위는 docs/ALIGNMENT_01_REPORT.md 참조.

## 보완 01 확장: 전달·링크·그룹/변형 wrapper

workflow_extensions.py는 기본 v1 파일 계약을 수정하지 않고 새로운 값 모델을 제공한다.
기존 JSON 5종/ConfirmedSelection fingerprint는 그대로이고, 새 모델도 명시적인
to_dict/to_json/from_dict/from_json으로 직렬화한다. SQLite나 실행기 버전을 바꾸지 않는다.

- DeliverySpec: None/file/link/both. mode=None의 requires_choice는 True이고 확정 불가다.
  file에는 기존 OutputSpec을, link에는 링크 ID를 쓴다. link-only에 가짜 파일 경로를 넣지 않는다.
- DataLink: 4상태, 유형, 후보/제안/조건 fingerprint, 공개 접근·공식성/공유 가능 선언,
  확인/만료 시각, 근거, 수동 필터/제약을 보존한다. reference는 available 데이터 링크가 될 수 없다.
  unavailable/blocked는 이유·확인 시각·조사 근거가 필요하다. unknown을 없음으로 바꾸지 않는다.
- VariantAttributes/CandidateVariant: 계절조정·가격/기준년·stock/flow·수준/변화율·
  단위/배율·개정/방법론/대상·원코드를 근거와 연결한다. None은 미상이다.
- CandidateGroup/GroupedProposal: 기존 후보를 바꾸지 않고 명시적 개념·그룹 근거로 연결한다.
  후보/그룹 중복·없는 참조·다른 개념·알려진 stock/flow 또는 수준/rate 충돌을 거부한다.
  묶음은 자동 동일성 판정·숫자 합산·복수 선택이 아니다. 기본 후보와 주기/단위 모순도 거부한다.
- DeliveryOffer: 특정 후보/조건에 연결된 결과만 묶는다. available_modes(at)는 선언된
  파일 지원과 그 시각에 유효한 링크로 가능한 방식을 계산하며 실행 준비 전체를 증명하지 않는다.
- ConfirmedDelivery: 명시적 모드·지원 출력·선택 링크·후보 조건·요구 변형을 확인한다.
  파일 부분은 기존 ConfirmedSelection 검증을 그대로 사용한다. 링크 전용은 파일/로컬
  수집기 지원·API 키 설정을 요구하지 않지만 메타데이터 범위와 공개 링크 근거는 필요하다.
  단위 변환을 링크로 수행했다고 주장하지 않는다. 그룹/변형/링크/조건 변경은 새 hash를 만든다.

새 target/confirmation hash는 domain을 분리해 기존 확인 hash와 혼동하지 않는다.
확인 시각/방법은 기록하되 내용 hash에서는 제외한다. 옛 모델을 새 의미로 자동 업그레이드하지 않는다.
legacy 값은 기존 API로 읽고, 새 입력 경로는 wrapper 종류를 명시해 처리해야 한다.

모든 메서드는 값 검증/계산이다. available/official/public은 호출자가 제공한 검증 기록이며
이 모듈이 URL을 열거나 공식성을 판단하지 않는다. usable_at/available_modes의 시각도 명시적으로
받는다. 저장된 확인을 읽는 것이 현재 시점의 링크 재검증을 뜻하지 않는다.
공유 데이터 URL의 자격증명/signed query/opaque fragment를 보수적으로 거부한다. 정상 문서
근거의 section anchor는 허용한다. 모든 비밀값을 탐지하는 보안 장치는 아니며 자유문장 JSON을
통째로 로그에 남기면 안 된다. 해시도 서명/승인 증명/원본 hash 카탈로그가 아니다.

실제 질문·선호 저장·링크 탐색/병행 실행·출력 생성은 없다. 이후 보완 02는 wrapper로
확인과 작업 의도를 연결하고, 보완 03은 고정 경로의 file/link/both 실행 연결만 다룬다.
기관 링크 자동 발견·검증은 05~08회차에 남긴다. 통합 계획은 WORKFLOW_ALIGNMENT_PLAN.md 참조.

## 보완 02: 구조화 질문·확인·새 작업 연결

orchestration.WorkflowService는 수동/fixture로 제공한 DataRequest, GroupedProposal,
DataLink, VariantAttributes, DeliverySpec을 받아 기존 값 계약으로 확인한다.
begin은 요청 컨테이너를 만들고, revise는 expected_revision과 제공된 변경만 적용한다.
누락 항목은 questions의 field/kind(input 또는 review)/choices로 한 번에 반환한다.
기존 지시·후보·출력을 추측하지 않는다. 메타데이터 부족은 review로 분리한다.
링크 4상태와 현재 usable, 수동 필터·이유·제약을 link_statuses에 남긴다.
같은 초안을 다시 평가할 때는 revise(id, expected_revision=n)를 사용할 수 있다.

workflow_request는 기존 tasks.document의 선택적 필드다. NEEDS_INPUT/NEEDS_REVIEW/
READY/CONFIRMED/WORK_CREATED는 워크플로 상태이며 기존 Task/Stage enum을 바꾸지 않는다.
컨테이너의 TaskStatus.CREATED는 실행 준비 완료를 뜻하지 않으며 runner는 컨테이너 실행을 거부한다.
READY는 내용이 충족되었지만 명시 확인이 없는 상태다. explicit_request 또는 followup을
받은 경우에만 ConfirmedDelivery를 저장한다. 완전한 명시 지시는 추가 질문 없이 확정된다.

create_work는 확정 스냅샷과 출처 task_id를 workflow_context로 가진 별도 CREATED 작업을
생성한다. 계획은 None이다. file/both는 collect/collect_and_link 의도, link는 deliver_link
의도이며 link 전용 작업에는 runner가 수집 계획을 허용하지 않는다. 실제 handler/기관별
계획 생성은 보완 03의 책임이다. 기존 저수준 Python 실행 API는 유지되며 인증 장치는 아니다.

요청 저장·이벤트, 자식 생성·연결·이벤트, 개정·기존 작업 무효화는 각각 BEGIN IMMEDIATE로
원자 처리한다. source_task_id는 완료된 기존 작업에 대한 호출자의 명시 연결이며 자동 탐색
증명이 아니다. 그 작업의 계획·성공 결과·이벤트는 수정하지 않는다. 현재 초안은 한 행으로
읽고 과거 개정은 append-only 이벤트에서 명시적으로 조회한다. SQLite 버전 2는 그대로다.
초안당 후보 50개/링크 100개/UTF-8 JSON 256 KiB, 개정 100회로 제한하며 자동 정리는 없다.

begin의 키는 최초 입력/출처/명시 확인 방식에 연결된다. 같은 확인의 create_work는 기본
결정적 키 또는 처음 지정한 키로 같은 작업을 반환한다. 다른 내용에 같은 키를 쓰거나
이미 연결된 작업에 다른 키를 추가하면 ValueError다. 조건/근거/그룹/변형 변경은 개정을
증가시키고 확인을 무효화한다. 명시 확인 방식이 함께 주어진 새 지시는 새 확인을 기록한다.
미완료 자식은 취소 요청하며 실행 중 단계의 결과는 보존하고 다음 단계로 넘어가지 않는다.
완료된 과거 결과는 보존하되 현재 조건의 결과로 실행·재사용할 수 없다.

runner는 계획·실행/재개·단계 시작 시 현재 개정/확인/연결/선택 링크 유효성을 확인한다.
resume(approved=True)로 이를 우회할 수 없다. 단계 사이 링크 만료는 NEEDS_REVIEW로
종료한다. 실행 전 만료는 ValueError이며 revise로 질문 상태를 갱신할 수 있다.
읽기만 하는 get은 시각이 저장 당시인 스냅샷이며 링크 최신성 재검증이 아니다.
파일 전용 작업에서 선택하지 않은 링크의 만료는 파일 확인/작업을 무효화하지 않는다.
서비스는 URL에 접속하지 않으며 available은 제공된 근거의 선언 상태다.

단계 fingerprint는 새 작업에만 workflow_context를 포함한다. 선택 필드 없는 legacy
작업의 JSON/멱등성/hash/오류와 기존 값 계약은 유지한다. API 키 값·원본 관측치를 이
context에 추가하지 않는다. 모델의 일반 자유문장은 비밀 자동 탐지 대상이 아니므로
호출자는 키를 입력하지 않고 snapshot 전체를 일반 로그로 출력하지 않아야 한다.

## 보완 03: 기관별 제한 실행 어댑터

ingestion/worldbank_request.py는 확인 context를 World Bank의 기존 연도 입력으로 연결한다.
WorldBankRequestDispatcher.prepare/run/resume은 현재 확인과 source 2/USA/GDP·추가 필터 없음,
원본 주기/단위·latest 정책·1~10년·raw_json/설정된 raw 경로를 먼저 검증한다.
저장된 계획이 확인에서 생성한 계획과 다르면 실행하지 않는다. 미지원 요구를 축소하지 않는다.
신규 wrapper와 v1 ConfirmedSelection의 명시적 build_worldbank_plan 진입은 분리한다.
기본 JSON/확인 hash/StageInput과 기존 source-specific 전송·파싱·raw writer는 수정하지 않았다.

file은 기존 worldbank_gdp 단계를, both는 그 다음 worldbank_delivery 단계를 계획한다.
전달 단계는 upstream 수집 결과·원본 참조를 보존하며 제공된 링크 근거만 반환한다.
추가 GET이나 exporter는 없다. link 전용은 collector plan을 만들지 않고 별도 트랜잭션으로
delivery_result와 LINK_DELIVERED 이벤트·완료 시도를 저장한다. 결과/이벤트 저장 실패는
롤백되고 반복 완료 호출은 추가 전달을 만들지 않는다. collector용 runner는 계속 link 계획을 거부한다.
공유 workflow 검증 함수의 allow_link=True는 이 전용 handler에서만 명시 사용한다.

링크는 GDPQuery의 정확한 URL만 지원한다. 다른 뷰어/쿼리·변형 필터는 후속 정책 사항이다.
DataLink 유효성/근거·수동 필터·제약과 전달/수집 증거 구분을 보존한다. 단계 사이의 확인 변경이나
링크 만료는 다음 단계를 막는다. 전달 직전 확인 변경도 기존 SEMANTIC_AMBIGUITY/NEEDS_REVIEW로
보고하며 이미 수집한 raw를 지우지 않는다. 네트워크 정책·TLS·요청 상한은 기존 transport가 검사한다.

verify_worldbank.py --live는 기존 문서화 프로필에 대한 명시 file 확인을 생성해 새 경로로
실제 수집한다. --legacy는 예전 저수준 검증을 선택한다. live 수집 성공은 자동 발견·정규화·
품질/피드백 완료가 아니며 04회차 Gate A와 구분한다. 검증 결과는 ALIGNMENT_03_REPORT.md 참조.
