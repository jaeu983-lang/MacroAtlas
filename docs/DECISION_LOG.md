# Decision Log — 설계 변경·미해결 판단

> 이 문서는 날짜가 붙은 결정 이력이다. 현재 범위와 우선순위는 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md), 구현·Gate 증거는 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), 짧은 순서 요약은 [`ROADMAP_2026_10_26.md`](ROADMAP_2026_10_26.md)를 따른다. 오래된 회차 기록은 당시 상태를 보존하며 최신 코드 상태로 자동 갱신된 것으로 보지 않는다.

## 05회차 제한 구현 (2026-10-26)

- BLS·Census 기관 어댑터의 catalogue seed/HTML fixture 탐색과 프로필 저장을 추가했다.
  정확한 공식 호스트만 허용하며 인증·live 가용성·수집 가능성은 추정하지 않는다.
- 대화 속 후속 구현 보고서와 현재 체크아웃이 달라 현재 파일 기준으로 진행했다.
  query 기반 공식 링크 허용, live 문서/원문 보존은 후속 판단으로 남긴다.
- 신규 unittest 6개 통과. pytest 미설치로 전체 회귀 검증 미실행이며 다음 회차는 보류한다.
  상세: docs/ITERATION_05_REPORT.md.

## BLS·Census 수집 연결 및 live 확인 (2026-10-26)

- BLS API v2와 Census ACS API에 전용 connector/ingestion을 연결했다. 키는
  실행환경 변수에서 읽고, 원본 응답은 write-once raw 경로에, 키 없는 요청 메타데이터는
  manifest에 저장한다. Orchestrator 등록 이름은 `bls/1`, `census/1`이다.
- 실행 중인 새 게시 환경의 두 key binding을 확인했다. BLS CUUR0000SA0 2024년 요청은
  API `REQUEST_SUCCEEDED`와 관측치 12개를, Census 2022 ACS1 California 요청은 HTTP 200,
  주 코드 열을 포함한 한 행을 반환했다. 저장 원본/manifest의 키 비노출을 검사했다.
- parser는 Census의 응답 지역코드 열을 원본 dimension으로 보존한다. 변수 정의·단위,
  BLS series metadata 및 전체 회귀는 미검증이다. 신규 unittest 10개 통과, 기존 탐색
  unittest 6개는 앞선 05회차 실행 결과이며 pytest/Ruff가 없어 전체 회귀는 수행하지 않았다.
- 코드 branch만 갱신했다. 환경 설정이나 게시 동작은 수행하지 않았다.

## 06회차 기관별 가이드와 전략 (2026-10-26)

- `discovery/institution_guides.py`는 고정된 공식 HTTPS URL만 불러오고 redirect를 거부한다.
  원본·HTML visible-text 추출·동일 호스트의 query 없는 link 후보·SHA256 manifest를
  새 경로에 보존한다. 실패 상태도 manifest로 기록하며 원본 가이드는 덮어쓰지 않는다.
- 동일 guide를 다시 받으면 직전 무결성 검증 성공본과 hash를 비교해 changed/unchanged를
  남긴다. 전략별 재사용 함수는 archive hash를 검증하고 호출자가 지정한 TTL로 신선도를
  표시한다. 자동 refresh·고정 TTL은 두지 않는다.
- live HTTP 200: BLS API v2, Census API 안내 5종, IMF API, TIC portal/usage 2종.
  IMF는 페이지의 식별 가능한 User-Agent 요청에서 성공했다. TIC 안내가 Excel 파일을
  일반 지원하지 않고 MHT 예외를 둔다는 점을 전략에 반영했다. IMF/TIC 수집기는 미구현이다.
- 현행 이용 조건 원문은 보존했으나 법적 이용/재배포 판단을 자동 승인하지 않는다.
  PDF 추출·자동 갱신 예약도 미구현이다. 상세: `docs/ITERATION_06_REPORT.md`.

| ID | 날짜 | 내용 | 결정/보류 이유 | 영향 범위 | 승인 | 상태 |
|---|---|---|---|---|---|---|
| D-001 | 2026-10-24 | Windows + Python + Git + Codex, SQLite+파일 기본 | 초기에 운영 복잡도 최소화 | Phase 1~5 | 사용자 검토 예정 | PROPOSED |
| D-002 | 2026-10-24 | 14회 High, Gate A~E 순차 개발 | 전 단계 검증 후 확장 | 전체 | 사용자 검토 예정 | PROPOSED |
| D-003 | 2026-10-24 | 기관 조사와 live API 검증 결과 구분 | 거짓 검증 방지 | 전 기관 | 사용자 검토 예정 | PROPOSED |
| D-004 | 2026-10-24 | 사용자 대화→로컬 피드백 자동 동기화는 별도 통합 | 실제 연결 기능 부재 | Phase 4 | 사용자 검토 예정 | PROPOSED |

## 신규 결정 기록 템플릿

## 01회차 구현 기록 (2026-10-24)

- **D-005 / IMPLEMENTED, 검토 대기:** 표준 라이브러리 dataclass/enum/Protocol로
  공통 계약을 정의. 상태 어휘만 제공하고 전이·실행·저장은 02회차로 유보한다.
  근거 유형은 official_docs/fixture/live_api/live_ingestion으로 구분한다.
- **D-006 / IMPLEMENTED, 검토 대기:** SQLite는 data/catalog.sqlite, 원본/정규화는
  data/raw와 data/processed. 상대 경로와 저장소 내부 경로만 허용한다.
  설정 생성은 파일을 쓰지 않으며 네트워크 기본값은 false다.
- **D-007 / RESOLVED (01회차 검증 보완):** 저장소 .venv에 프로젝트와 dev 의존성을
  설치했다(Python 3.12.14, pytest 8.4.2). 샌드박스 네트워크 차단 후 승인된 설치로
  완료했으며 전체 pytest 16개 통과. 설치 버전은 reports/iteration_01_environment.txt에 기록.
- **D-008 / RESOLVED (01회차 검증 보완):** health CLI에서 stdout 인코딩을 유지하고
  오류 처리를 backslashreplace로 설정한다. 표현 불가능한 문자만 이스케이프한다.
  cp949/UTF-8/ASCII subprocess 회귀 테스트 통과. UTF-8 출력은 원문을 보존한다.
- **D-009 / PARTIALLY RESOLVED (02회차):** 단계별 전체 엔진 호출 상한과 작업 상태
  정책은 D-014에서 구현했다. retry_hint는 선택적 설명 문자열을 유지한다.
  전체 메타데이터 카탈로그 스키마/마이그레이션 및 HTTP backoff는 후속 회차로 남는다.
  기관별 인증·엔드포인트·통계 의미는 새로 검증하지 않았다.
- **D-010 / OPEN:** run_checks.ps1은 현재 시스템 서명 정책으로 실행 차단됐다.
  정책 변경 없이 Python 명령으로 전체 pytest/health/pip check를 직접 검증했다.
  스크립트 실행 검증은 조직 정책에 맞는 서명 또는 허용 환경이 필요하다.
- **D-011 / RESOLVED:** Ruff 17건 정리 후 전체 pytest 16개 및 Ruff 통과.
  import/UTC 별칭/조건문/타입 변수명/테스트 표현을 정리했다. 기존 ValueError 계약을
  유지하기 위해 TRY004 세 곳만 사유를 명시한 줄 단위 noqa를 사용했다.
  전역 규칙 설정과 오류 메시지·테스트 기준은 변경하지 않았다.

## 기획 정책 추가 (2026-10-24)

- **D-012 / ACCEPTED (사용자 요청 반영):** 필요한 기관의 API 키만 선택 등록하며
  전체 기관 키를 요구하지 않는다. 실제 값은 로컬 .env/환경변수, 기획서에는 환경변수
  이름만 기록한다. 경로별 인증 none/optional/required/unknown과 키 설정·유효성은
  분리한다. 필수 키 누락은 해당 경로만 중단한다. PROJECT_PLAN_ORIGINAL_2026_10_24.md §2.1에 정책과
  후속 검수 기준을 추가했다. 이번에는 설정 로더·커넥터·02회차 기능을 구현하지 않았다.
  기관별 실제 인증 조건은 커넥터 구현 시 공식 문서로 확인해야 한다.

- **D-013 / ACCEPTED (사용자 요청 반영):** 14회차 최종 통합·검증 단계에 사용자
  설명서(Markdown)와 안내 PPT(PPTX)를 제작한다. 실행 방법·기관별 선택적 키 설정·
  수집 결과 확인을 실제 구현 기준으로 설명하고 대표 절차 재현 및 PPT 표시를 검수한다.
  PROJECT_PLAN_ORIGINAL_2026_10_24.md §10.3/14.2와 IMPLEMENTATION_PLAN.md 14회차에 반영했다.
  이번 작업은 기획 문서 3개만 변경했으며 설명서/PPT 제작과 02회차는 진행하지 않았다.
  실행 코드 변경이 없어 테스트는 재실행하지 않았다. 실제 키 접근·네트워크 호출 없음.

위 구현 기록은 사용자 승인 완료를 뜻하지 않는다. D-012/013은 사용자가 명시한 기획 정책이다.

## 02회차 구현 선택 (2026-10-24, 검토 대기)

- **D-014 / IMPLEMENTED:** 고정된 선형 TaskPlan을 주입된 엔진으로 동기 실행한다.
  idempotency_key는 정확히 동일한 요청에만 재사용, 다른 요청은 충돌 오류다.
  계획 변경은 새 작업으로 기록한다. 성공한 앞 단계가 있는 실패는 PARTIAL,
  없으면 FAILED, 검토 필요는 NEEDS_REVIEW다. 재개는 동일 task_id에 새 시도를 추가한다.
  단계별 기본 호출 상한 3(1~10), 승인/취소로 초기화하지 않는다. 자동 재시도는 없다.
- **D-015 / IMPLEMENTED:** 재사용은 성공한 연속 앞 단계에 한정한다. 입력 fingerprint,
  원래 성공 시각 기반 TTL(기본 3600초), 호출자가 제공하는 근거 검증기의 True가
  모두 필요하다. 검증기가 없거나 실패하면 재실행하며 이후 단계의 재사용도 막는다.
  NEEDS_REVIEW 재개는 approved=True가 필요하고 종료 실패는 새 작업을 요구한다.
  인증/라이선스 오류는 엔진이 재시도 가능으로 반환해도 검토 필요로 제한한다.
- **D-016 / IMPLEMENTED:** SQLite schema version 2에 작업 JSON 스냅샷과 추가 전용
  이벤트를 저장한다. 단계별 결과/이벤트와 작업 완료/이벤트는 각각 원자적 저장이다.
  전체 계획·시도·실패 근거를 보존한다. 큰 이력 최적화와 DB 버전 이관은 미구현이다.
- **D-017 / IMPLEMENTED, 운영 제한:** 실행 토큰과 SQLite 트랜잭션으로 중복 실행과
  오래된 작업자의 저장을 차단한다. cancel은 단계 경계에서 처리한다.
  중단된 RUNNING은 이전 작업자 종료·외부 부작용 확인 후 명시적으로 복구해야 한다.
  자동 장애 판단·강제 중단·외부 부작용 exactly-once는 보장하지 않는다.
- **D-018 / OPEN:** 실제 커넥터는 자격증명을 저장되는 요청/계획/결과와 분리하고
  비밀값을 제거한 근거만 반환해야 한다. 이번 엔진 예외 메시지는 저장하지 않지만
  임의 사용자 문자열의 비밀값 자동 탐지·.env 로더·실제 인증은 구현하지 않았다.

이 선택은 02회차 모의 엔진/로컬 SQLite 테스트로 검증했다. 실제 기관 수집을 뜻하지
않으며 03회차는 진행하지 않았다. 기본 TTL/상한 및 복구 운영 방식은 사람 검토 대상이다.

## 03회차 구현 선택 (2026-10-24, 검토 대기)

- **D-019 / IMPLEMENTED:** 첫 기관은 World Bank Indicators API로 선정했다.
  공식 문서의 GDP 예시와 키 불필요 정책을 확인했고 USA/source 2/NY.GDP.MKTP.CD
  한 경로만 지원한다. 1960..2100 중 1~10년, 1페이지·1 MiB로 제한한다.
- **D-020 / IMPLEMENTED:** 네트워크는 명시적 True opt-in만 허용한다. 고정 HTTPS
  호스트·TLS 검증·리다이렉트 거부·trust_env=False로 암묵적 자격증명 접근을 막는다.
  1회 GET/연결 5초·읽기 20초/청크별 30초 예산 검사, 자동 재시도 없음.
  전송 예외 상세는 저장하지 않는다. 조직 프록시/사설 CA 지원은 미구현이다.
- **D-021 / IMPLEMENTED:** 원본 엔터티 바이트와 요청 manifest를 새 UUID 폴더에
  배타 저장한다. HTTP/파싱 실패의 완전 응답도 보존하며 과대/불완전 응답은 성공 raw로
  저장하지 않는다. 파일 장애 시 부분 파일이 남을 수 있다. 해시·격리/종합 품질은 04회차다.
- **D-022 / IMPLEMENTED:** 관측 행을 그대로 반환하고 null/0/빈 unit/obs_status를
  유지한다. lastupdated는 source_last_updated이지 불변 vintage가 아니다.
  source_version/명시적 주기·단위·series_id 부재는 None, 식별 조합은 series_key로 남긴다.
  최종 파서는 저장된 live 원본 로컬 재해석으로 검증했다. 초기 성공 이력은 덮어쓰지 않았다.
- **D-023 / OPEN:** 일반 이용 조건 URL이 새 Terms & Conditions로 리다이렉트된다.
  개별 지표의 재배포 조건을 전면 확인했다고 주장하지 않는다. 링크·출처를 보존했고
  로컬 소량 검증만 수행했다. 다른 지표 확대/배포 전 개별 이용 조건 재확인이 필요하다.

실제 GET 성공과 모의 테스트는 03회차 보고서에서 분리했다. 04회차는 진행하지 않았다.

## 사용자 흐름 검토 (2026-10-24)

- **D-024 / ACCEPTED (기획 반영, 코드 미구현):** 기관 미지정/지정 요청 모두에 대해 후보 제안·내부 메타데이터
  확인 → 선택 데이터/기간/출력 조건 확정 → 실제 수집·결과 제공의 두 사용자 작업으로
  설명한다. 기존 기획과의 대응, 확인 절차·대규모 분할 계획의 부족한 부분 및 프롬프트
  예시는 docs/USER_WORKFLOW_REVIEW.md에 정리했다. 후속 사용자 요청으로 PROJECT_PLAN
  §4.0/7.3/8.3/10.1과 IMPLEMENTATION_PLAN의 관련 보완·검수 항목에 반영했다.
- **D-025 / PLANNED, 코드 적용 보류:** 01~03회차의 최소 계약·확인 이력·World Bank
  연결 보완과 예상 변경 파일/테스트 기준은 docs/WORKFLOW_ALIGNMENT_PLAN.md에 정리했다.
  보완 01→02→03을 각각 별도 구현 작업으로 수행한다. 기존 고정 계획·오류 계약·118개
  회귀 테스트와 03회차 수집 제한은 유지한다. 자동 탐색은 05~08, 대규모 계획/분할/예산/
  부분 성공은 09~10회차 범위다. 숫자 상한은 후속 결정 사항이다.
- **D-026 / ACCEPTED (기획만):** 조건 확정은 후보·조건 스냅샷에 연결하고 탐색 계획을
  덮어쓰지 않은 새 수집 작업을 생성한다. resume 승인으로 선택 확인을 대체하지 않는다.
  기존 저장소의 선택적 JSON context를 활용하는 최소안을 제안하며 스키마 이관이 필요해지면
  별도 설계 판단을 기록한다. 이번 변경은 문서 5개뿐으로 테스트/Ruff 미재실행,
  실제 API·키 접근·원본 수정·04회차 착수는 없다.

## 사용자 흐름 보완 01 (2026-10-24)

- **D-027 / IMPLEMENTED, 검토 대기:** workflow_contracts.py에 요청·후보·제안·출력·
  확정 스냅샷 값 계약을 분리했다. 기존 Task/Stage/ValueError 및 실행 코드는 유지한다.
  None은 unknown, 빈 후보 목록은 발견 없음, 빈 대상 목록은 대상 미확정으로 구분한다.
  확정에는 필요한 선택·조건·식별·정의·근거와 가용성/지원/인증 정책이 알려져 있어야 한다.
- **D-028 / IMPLEMENTED:** frozen 모델/읽기 전용 복사와 명시적 schema_version=1 JSON
  직렬화를 사용한다. 확인 내용 fingerprint는 요청·전체 제안/근거·선택·출력을 포함하고
  확인 시각/방법은 제외해 동일 조건의 재확인을 멱등하게 표현한다. 서명/실행 권한은 아니다.
- **D-029 / IMPLEMENTED, 경계 명시:** 상대 출력 경로·resolved 포함 검사만 제공하고
  파일을 쓰지 않는다. 모델 표현/검증 예외는 값을 숨기며 알려진 credential query/차원
  키를 거부한다. 명시적 JSON에는 원문이 보존되므로 자유문장의 비밀값 필터라고 보지 않는다.
- **D-030 / OPEN:** 실제 확인 서비스·이력/새 작업 연결·지원 형식/변환/인증·최신성의
  실행 전 재검증은 보완 02·03 범위다. 이 값 계약을 만들었다고 수집 가능한 전체 흐름이나
  인간의 선택 진위를 검증했다고 주장하지 않는다. 조직별 추가 민감 파라미터 정책도 후속 검토 대상이다.

보완 01 최종 전체 241개 테스트/Ruff 통과. 실제 API 호출은 하지 않았다.
보완 02·03과 04회차는 진행하지 않았다. 상세는 docs/ALIGNMENT_01_REPORT.md에 기록했다.

## 출력·링크·변형 제안 정책 추가 (2026-10-24)

- **D-031 / ACCEPTED, 미구현:** 전달 방식은 파일/링크/둘 다로 구분하고 현재 요청에
  지시가 없으면 가능한 선택지만 보여주고 묻는다. 링크 unavailable/unknown/blocked를
  구별하고 없음/차단은 선택 제외한다. 홈페이지 링크로 대체하거나 파일을 자동 생성하지 않는다.
- **D-032 / ACCEPTED, 미구현:** 공식 데이터 링크 발견·검증을 후보/메타데이터 조사와
  병행 가능한 모듈로 분리한다. 동일 후보·조건·개정에 결과를 연결하고 권한/호출 예산을 지킨다.
  링크 전달 완료와 실제 다운로드/품질 검증 완료는 구분한다. 현재 Orchestrator 병렬 실행 구현은 없다.
- **D-033 / ACCEPTED, 미구현:** 같은 개념의 변형은 근거 기반 그룹과 차이로 표시한다.
  계절조정·가격/주기·단위·개정 차이를 숨기지 않고, 중요한 모호함은 먼저 질문한다.
  표현 선호는 작업/기관/개념 범위에서만 재사용하고 현재 지시가 우선한다. 출력 미지시 질문은 생략하지 않는다.
- **D-034 / PARTIALLY RESOLVED:** delivery mode/링크·그룹 계약 확장은 D-035~037에 반영했다.
  복수 변형 선택/선호 저장은 미구현이다. 최초 정책 추가 당시에는 별도 확장 명세와
  JSON·fingerprint 호환 테스트가 필요하다. 현재 보완 01 모델을 소급 변경하거나 보완 02·03에
  자동 포함하지 않는다. PROJECT_PLAN/IMPLEMENTATION_PLAN/OUTPUT_AND_VARIANT_POLICY/
  WORKFLOW_ALIGNMENT_PLAN/USER_WORKFLOW_REVIEW/이 로그 6개 문서만 변경했다.
  실제 코드·키·원본·외부 API·PowerShell 정책 변경 없음. 테스트/Ruff는 재실행하지 않았다.

## 보완 01 계약 확장 (2026-10-24)

- **D-035 / IMPLEMENTED:** v1 workflow_contracts.py는 수정하지 않고 workflow_extensions.py의
  wrapper로 전달·링크·그룹/변형을 추가했다. 변경 전 JSON 5종을 golden fixture로 고정하고
  byte 왕복·기존 fingerprint를 검증했다. 새 hash는 link_target_v1/confirmed_delivery_v1
  domain을 사용한다. 기본 schema_version=1 및 SQLite 버전/기존 오류 계약은 바꾸지 않는다.
- **D-036 / IMPLEMENTED, 값 검증 한정:** DeliverySpec은 미지정/file/link/both를 구분한다.
  미지정은 질문 필요로 남기고 확정하지 않는다. DataLink의 4상태·공개/공유 선언·확인/만료·근거를
  저장하고 후보/조건/개정이 다르거나 만료/미확인/차단된 링크는 선택하지 않는다.
  링크만 선택할 때 파일 경로나 로컬 exporter를 요구하지 않고 단위 변환도 약속하지 않는다.
  실제 링크를 열거나 질문·파일 생성을 수행하는 서비스는 없다.
- **D-037 / IMPLEMENTED, 값 검증 한정:** 그룹은 명시적 concept/후보 참조/근거와 변형 속성을
  보존한다. 잘못된 참조와 알려진 stock/flow·level/rate 모순을 거부하며 원래 후보를 변경/합산하지 않는다.
  요구 변형과 실제 선언이 다르거나 미상이면 확정하지 않는다. 통계적 동등성 자동 판정은 아니다.
- **D-038 / OPEN:** 실제 링크 발견·권한/최신성 검증·질문/실행 연결, 출력 생성·병행 실행,
  표현 선호 저장·복수 후보 확정은 후속 범위다. 공유 URL 검사는 보수적이며 정상 viewer fragment
  지원은 검증된 기관 어댑터 정책이 필요하다. 임의 비밀값 자동 탐지나 사람 승인 증명으로 보지 않는다.

통합 보완 계획을 갱신했고 확장 최종 318개 테스트와 Ruff 통과. 실제 API 호출·키 접근 없음.
보완 02·03과 04회차는 진행하지 않았다. 상세는 docs/ALIGNMENT_01_EXTENSION_REPORT.md 참조.

## 기관·개념 지식 엔진 기획 (2026-10-24)

- **D-039 / ACCEPTED, 미구현:** 저장 크기보다 요청당 지연·메모리·연산량 통제를 우선하는
  기관·개념 지식 엔진을 추가한다. 공유 저장소/기존 탐색·매핑·개선 엔진과 역할을 분리하며
  사용자 설명·공식 근거·추론 후보의 상태/범위/버전을 보존한다.
- **D-040 / ACCEPTED, 미구현:** 요청은 색인된 제한 조회·근거 지연 로딩·짧은 교정 기록만
  수행한다. 필요한 범위만 확장하고 갱신/추론/재색인은 별도 예산의 명시적 작업으로 둔다.
  원본/이력 보존과 조회용 현재 기록을 분리한다. 캐시 상한·무효화·상충 근거·시점 격리를 검수한다.
- **D-041 / PLANNED:** 11~13회차에 입력/검증, 조회/갱신과 성능, 추론 후보를 배치한다.
  성능 예산은 기준 환경/자료/부하를 정해 수치화하고 Gate D에서 지연/메모리/조회량과
  정합성을 함께 검증한다. 현재 성능 통과나 자동 백그라운드 실행을 주장하지 않는다.
  최종 스키마·예산·실행기는 후속 결정 사항이다. PROJECT_PLAN/IMPLEMENTATION_PLAN/
  KNOWLEDGE_ENGINE_PLAN/이 로그만 변경했으며 코드·API·키·DB·테스트 실행·04회차 착수는 없다.

## 실행 계획 재정렬 (2026-10-24)

- **D-042 / PLANNED, 실행 미착수:** IMPLEMENTATION_PLAN 상단에 실제 자산/미구현 구분,
  사용자 결과별 순서와 수용 기준을 통합했다. 기존 14회·Gate A~E를 유지하며 보완 02→03→04를
  먼저 연결한다. 범위 없는 미래 모델 확장을 반복하지 않고 실제 통합 결함/입출력에 필요한
  최소 변경만 해당 회차에서 검토한다. 기존 코드·역사적 검증 기록은 폐기하거나 소급 변경하지 않는다.
- **D-043 / PLANNED:** 분류/포괄범위 의미와 미해결 모호함은 07/08의 실제 후보 해석/질문에,
  지식 축적·제한 조회/갱신·추론은 11~13에 배치한다. 그 전에는 확인된 좁은 경로/명시적 근거를
  사용하며 자동 탐색·완전한 개념 온톨로지·지식 백그라운드 실행을 이미 있는 것으로 가정하지 않는다.
  이번에는 PROJECT_PLAN/IMPLEMENTATION_PLAN/WORKFLOW_ALIGNMENT_PLAN/이 로그만 갱신했다.
  코드·DB·원본·키·실행 정책 변경과 실제 API·테스트/Ruff 실행은 없다. 직전 318개 통과는 기존 보고다.

## 보완 02 확인 서비스 (2026-10-24)

- **D-044 / IMPLEMENTED:** WorkflowService의 구조화 입력/질문/명시 확인/새 작업 연결을
  기존 SQLite version 2 JSON과 이벤트에 저장한다. 값 계약 파일과 기존 JSON/hash/오류
  enum은 변경하지 않는다. 워크플로 컨테이너와 실행 작업의 상태·ID를 분리한다.
- **D-045 / IMPLEMENTED:** 변경에는 expected_revision을 요구한다. 같은 확인은 한 작업으로
  연결하고 다른 context에 같은 멱등 키를 재사용하거나 이미 연결된 작업에 별도 키를 추가하면
  거부한다. 최초 확인 시각을 보존한다. 개정/연결/이벤트·취소는 원자 처리한다.
  현재 행은 제한된 스냅샷이며 과거 개정은 이벤트에서만 조회한다. 초기 상한은 후보 50,
  링크 100, 초안 JSON 256 KiB, 개정 100회다. 대량 데이터/지식 엔진 예산을 대신하지 않는다.
- **D-046 / IMPLEMENTED:** 계획/실행/재개/단계 시작에서 새 context를 재검증한다.
  변경된 조건은 새 확인·새 작업이고 기존 성공 결과는 보존한다. 이미 실행 중인 단계는
  결과를 남기고 취소 경계에서 중단한다. 링크 전용 collector 계획은 금지한다.
  선택 링크의 만료는 거부/검토 상태로 처리하며 파일로 자동 대체하지 않는다.
  파일 전용에서 선택하지 않은 링크 만료는 확인 무효화 사유로 삼지 않는다.
- **D-047 / OPEN, 후속 범위:** 실제 질문 UI/자연어 추출, 공식 링크 발견/재검증,
  기관별 file/link/both handler, 실제 파일 exporter·분류 의미 해석은 미구현이다.
  보완 03은 별도 요청 전까지 미착수이고 04회차 Gate A도 미착수다. source_task_id 연결은
  호출자가 지정하며 근거의 실제 공식성이나 사용자 동의의 진실성을 서명으로 증명하지 않는다.
  보완 02의 증거는 전체 364개 offline 테스트와 Ruff이며 실제 API/수집 재검증은 없다.

## 보완 03 제한 실행 연결 (2026-10-24)

- **D-048 / IMPLEMENTED:** 기관 특수 로직은 ingestion/worldbank_request.py에 둔다.
  새 연결된 ConfirmedDelivery 작업과 명시적인 legacy ConfirmedSelection 계획 builder를
  분리한다. canonical institution_id=worldbank/dataset_id=2/USA/지표 키를 검사하고
  alias·이름 추론을 하지 않는다. 기존 전송/파싱/raw writer와 JSON/hash/오류 enum은 유지한다.
- **D-049 / IMPLEMENTED:** file은 기존 raw_json/설정 raw 경로만, link는 제공된 유효 근거의
  정확한 GDPQuery URL만, both는 collect→deliver로 처리한다. link 전용은 collector plan 없이
  원자적으로 delivery_result/LINK_DELIVERED를 저장한다. 전달 결과와 수집 결과를 구별한다.
  반복 완료는 중복 호출하지 않으며 변경된 확인/만료/잘못된 계획은 전송 전에 거부한다.
- **D-050 / IMPLEMENTED:** source 주기/preserve 단위/latest_available/추가 차원 없음만
  지원한다. 후보 metadata를 보존하되 비어 있지 않은 변형 requirements를 필터로 실행하지 않는다.
  CSV/XLSX/다른 위치·국가·지표·source/기간 초과는 사전 ValueError로 알리고 자동 대체하지 않는다.
- **D-051 / OPEN, 후속 범위:** 일반 viewer/URL query 동등성·자동 링크 발견/공식성 재검증,
  실제 exporter/주기·단위/변형 변환·기관 확대는 미구현이다. 이 보완은 전체 H 시나리오나
  04회차 Gate A가 아니다. 실제 검증은 새 file 요청 1건의 HTTP 200/724 bytes/3행이며
  최초 기본 환경 TRANSIENT도 별도 보존했다. link/both는 fixture 증거다.
  전체 406개/Ruff 통과. 04회차는 요청 전까지 미착수다.

## 04회차 Gate A 완료 (2026-10-25)

- **D-052 / IMPLEMENTED, 사람 검토 대기:** Gate A를 기존의 제한된 World Bank USA GDP file 경로에 연결했다. live 보고서에서 HTTP 200, raw 724 bytes, 원본·manifest 해시 일치, SQLite 검증 상태 `passed`와 관측치 3개, feedback 및 이벤트 이력을 확인했다. 보고서의 `live_path_passed=true`와 pytest 433개/Ruff 통과를 기준으로 Gate A를 통과 처리한다.
- 검증 보고서는 단위·주기를 알 수 없다고 남겼고 경제적 이상치, revision history, cross-source equivalence는 검사하지 않았다. 데이터셋별 이용·재배포 조건도 전면 승인되지 않았다. 다른 기관/지표 지원이나 자동 탐색을 의미하지 않는다.
- 근거: `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`, `docs/ITERATION_04_REPORT.md`, `tests/test_gate_a.py`. 현재 저장소는 첫 기준 커밋 전이며 파일이 untracked다. 프로젝트 전체 Git 체크포인트는 사람이 포함 범위와 민감하지 않은 로컬 산출물을 확인한 뒤 수행한다. 이번 문서 정리에서는 커밋하지 않는다.

- **ID/일시:**
- **문제/선택지:**
- **채택안 및 근거:**
- **영향 받는 모듈·회차:**
- **보안·데이터 정확성 영향:**
- **승인자/검증 방법:**
- **상태:** Proposed / Approved / Rejected / Superseded

## 07회차 메타데이터 탐색·정규화 (2026-10-26)

- **D-053 / IMPLEMENTED, 범위 제한:** BLS catalogue, Census ACS variable metadata,
  supplied codebook rows, SDMX-ML 2.1 structures를 공통 `known`/`unknown`/`conflict`
  필드로 표현한다. 원본 응답은 `data/raw/metadata`, 표준 결과는 `data/processed/metadata`
  에 분리하고 hash와 source pointer를 남긴다. 키는 BLS POST 본문 또는 Census 요청 중의
  쿼리에만 사용하며 저장 URL·manifest·normalized records에는 넣지 않는다. 원문에 없는
  정의·단위·주기·기간을 보충하지 않는다.
- **D-054 / OPEN:** IMF/BIS 등 SDMX network discovery, 기관 전체 API 목록 순회, XLS/XLSX
  reader, 계절/가격/비율 변형의 완전한 개념 모델, 분류 포괄/중첩 관계 해석 및 사용자
  후보 검색은 구현되지 않았다. SDMX 근거는 fixture parser coverage이며 live endpoint
  검증으로 간주하지 않는다. 제한 live 근거는 BLS `CUUR0000SA0` catalogue 1건과 Census
  `B01001_001E` variable metadata 1건이다. 상세와 경계는 `docs/ITERATION_07_REPORT.md`.
- 검증: 전체 pytest 470개, Ruff와 `git diff --check` 통과. Live raw/normalized SHA256 일치,
  키 문자열 부재를 로컬 artifacts에서 확인했다. 환경 설정을 변경/게시하거나 코드를 커밋하지 않았다.

## 08회차 후보 검색·수집 연결 (2026-10-26)

- **D-055 / IMPLEMENTED, fixture E2E 범위:** `series_search/1`은 hash-verified 로컬 BLS/Census
  metadata archive와 보고서 근거가 있는 단일 World Bank USA GDP 경로를 검색한다. 토큰 score는
  후보 순위로만 사용하고 알려진 조건 모순은 제외한다. 누락된 정의/지역/기간/주기/차원은
  `review_required`로 남긴다. 검색 엔진은 네트워크를 호출하지 않는다.
- 명시된 `ConfirmedSelection`만 collector plan으로 바꾼다. 정확한 선택/증거/확인 시각을
  `record_selection/1` stage에서 먼저 저장하고 raw_json 경로만 허용한다. World Bank, BLS,
  Census의 기존 수집 engine으로 mapping하되 미상 메타데이터는 기존 확인 계약에서 차단한다.
- fixture 검증은 candidate search→explicit selection→Orchestrator receipt→World Bank fixture
  수집·raw 보존까지 확인했다. 실제 BLS/Census 선택 후 API 수집은 환경 readiness가 unknown이라
  실행하지 않았다. 자연어 의미 분석, cross-source equivalence와 기관 전체 카탈로그는 OPEN.
- 검증: 전체 pytest 477개, Ruff 및 `git diff --check` 통과. 환경 설정 변경/게시와 commit은 없다.

## 09회차 로컬 표/파일 parser 확장 (2026-10-26)

- **D-056 / IMPLEMENTED, bounded local input:** explicit format parser는 UTF-8/UTF-16 CSV/TSV/
  delimited TXT, HTML table, ZIP tabular member, XLS, XLSX를 지원한다. 요청 파일은 repository-local
  `data/inbox/` 아래에서만 읽고 16 MiB input, ZIP 1000 entries/64 MiB uncompressed/200x ratio,
  100,000 rows/1,000 columns/500,000 cells 한도를 적용한다. XLSX/XLS readers는 `openpyxl`/`xlrd`
  runtime dependency로 선언했다.
- ZIP은 추출하지 않고 선택한 member만 메모리에서 읽는다. traversal, symbolic link, encrypted,
  duplicate member names, expansion bomb를 거부한다. HTML span/중첩 표와 모호한 workbook/sheet/table
  선택은 수동 review로 돌린다. Formula는 계산하지 않고 문자열/캐시값으로 남긴다.
- raw source와 parsed table을 `data/raw/tabular` 및 `data/processed/tabular`에 별도 보존한다.
  동일 raw hash+옵션+parser revision은 기존 결과를 재사용하고, 중복 data row는 지우지 않고
  1-based row index로 기록한다. 파서 오류에도 안전 크기 안의 원본 raw는 보존한다.
- fixture에는 synthetic TIC형 TSV/HTML과 BIS형 zipped CSV 구조가 있다. 별도 planning utility는
  World Bank GDP/BLS/Census의 sample/full 요청을 bounded chunk로 분할하며 chunk 1000개 상한,
  raw_json 외 format 거부, 미입력 예상 크기 unknown을 검증한다. 계획기는 Orchestrator queue,
  chunk 실행/재개와 연결되지 않는다. PDF/fixed-width parser, formula evaluation/recovery,
  external URL fetch, 범용 API 계획과 파일 exporter는 미구현.
- 검증: 전체 pytest 499개, Ruff 및 `git diff --check` 통과; 외부 네트워크 사용 없음.

## 10회차 품질 진단·오류 분류·복구 (2026-10-26)

- **D-057 / IMPLEMENTED, 제한 API 범위:** BLS/Census 원본 저장 manifest에 raw SHA256,
  source-payload comparison SHA256과 canonical request fingerprint를 기록하고 같은 URL·요청
  범위의 최근 원본과 비교한다. BLS comparison은 top-level `responseTime`만 제외한 canonical
  JSON이며 Census는 canonical JSON이다. 원본 raw bytes와 hash는 그대로 보존한다.
  변경 응답은 덮어쓰지 않고 새 raw package로 남기며 `NEEDS_REVIEW/QUALITY_FAILURE`를 반환한다.
  기존 비교 이력의 무결성이 깨졌거나 1,000 package/64 MiB scan budget을 넘으면
  `unknown_history_*` 상태와 warning으로 남긴다. JSON 의미 정규화 비교는 하지 않는다.
- BLS는 series-period 중복, 빈 value를 세고, Census는 중복/불일치 geography와 null/빈 셀을
  진단한다. 누락·중복 값을 자동 제거/대체하지 않는다. 정의·단위·주기·revision이 불명확하면
  unknown 상태를 유지한다. 통계적 이상치, 완전한 기간 간격, MOE·조정 방법, 기관 간 동등성은
  판정하지 않는다.
- HTTP 401/403은 AUTH_ACCESS, 429/5xx 및 timeout은 TRANSIENT, redirect는 LICENSE_SECURITY,
  예기치 않은 HTTP status는 SITE_CHANGED로 분류한다. BLS/Census 수집기가 실패 error code와
  sanitized status code를 Orchestrator에 보존한다. 자동 network retry는 없고 명시적 resume와
  기존 max_attempts 상한을 따른다. HTTP error response body는 원본 저장하지 않는다.
- 검증: mocked 403/429/503/404 및 timeout, 재시작 후 429 resume, schema drift 원본 보존,
  unknown metadata, duplicate/mismatched rows, 같은 요청의 changed/unchanged raw, tampered
  history, 다른 query scope, BLS `responseTime` volatility, 전체 pytest 518개/Ruff/diff check 통과. 환경 network/key 상태가
  unknown이어서 구현 당시에는 live 호출을 하지 않았다. 후속 사용자 요청에서 BLS/Census 각각
  한 건을 현재 workspace 엔진으로 직접 Orchestrator 실행해 HTTP 200/COMPLETED를 받았다.
  BLS 12행/1,181 bytes, Census 1행/64 bytes, 두 manifest의 SHA와 byte_count 일치 및 키 필드
  비노출을 확인했다. 이전 manifest에 저장 hash가 없어 두 응답 모두 source change는
  `unknown_history_integrity`; 세 BLS capture의 post-hoc 차이는 top-level `responseTime`뿐이고
  관측 row는 같았다. 네 Census capture는 raw가 byte-identical이다.
  설정 draft repository ref는 `codex/iteration-04-gate-a`; 현재 `codex/institution-discovery-05`
  작업 트리의 이후 코드는 미커밋이다. fresh checkout의 코드 상태는 확인되지 않았다.
  환경 telemetry는 observed spec revision 5이나 network/key readiness는 계속 `unknown`이다.
  환경 draft/게시를 변경하지 않았다. Gate C는 여전히 미통과.

## 계획 구현 정합성 보완 (2026-10-26)

- **D-058 / IMPLEMENTED, retry contract:** 제품 계획의 TRANSIENT/X01이 자동 backoff를 요구하던
  반면 BLS/Census 구현은 호출당 1회 후 명시적 resume를 사용했다. 호출 예산과 Orchestrator의
  동기 실행 모델에 맞춰 자동 재시도 대신 수동 resume를 기준 정책으로 확정했다. `Retry-After`
  초/HTTP-date를 파싱해 실패 결과에 저장하며, 지연시간 전 resume는 차단한다. X01, PROJECT_PLAN,
  GUIDELINES와 구현 상태 문서를 같은 정책으로 수정했다. 자동 지수 backoff와 공용 rate limiter는
  미구현으로 남긴다.
- 사용자가 요청한 08→09 순차 진행은 일반적인 단일 회차 규칙의 명시적 예외로 기록한다. 08은
  fixture World Bank E2E만 통과했고 자연어 해석·공식 검색 범위·live BLS/Census 연결은 미검증이라
  Gate B를 통과하지 않았다. 10의 두 live smoke도 기관 전반 검증을 대체하지 않으므로 Gate C는
  미통과, 11회차는 보류다.
- 구성·배포 추적성: live smoke는 현재 `codex/institution-discovery-05` 작업 트리에서 실행됐으며
  05~10 변경 중 일부가 미커밋/untracked다. 관측된 환경 repository ref는 `codex/iteration-04-gate-a`로,
  이 작업 트리와 일치하지 않는다. 현재 변경을 게시하거나 환경 draft를 바꾸지 않았으며, fresh
  checkout에 05~10 소스가 포함됨을 확인하기 전까지 배포 검증으로 간주하지 않는다.
- 검증: Retry-After 초/HTTP-date 파싱, BLS/Census 결과 전달, 조기 resume 차단을 포함해 전체
  pytest 523개, Ruff, `git diff --check` 통과. 외부 요청을 하지 않았다.

## API별 인증 정책과 후보 상태 보정 (2026-10-26)

- **D-059 / IMPLEMENTED:** 공식 BLS API 가이드상 ordinary series-data request는 등록 키 없이
  가능하지만 `catalog=true`와 선택 parameter는 등록 키가 필요하다. BLS observation transport는
  키가 있을 때만 보내고, 없어도 ordinary series-data 요청을 수행한다. BLS 후보는 auth `optional`,
  Census 후보는 보존된 공식 안내에 따라 auth `required`로 표시한다. Census 수집과 BLS metadata
  catalogue 요청은 필요한 키가 없으면 안전하게 중단한다.
- 검증: BLS 키 포함/미포함 mocked transport, 후보 인증 상태 단위 테스트 통과. Census live calls는
  등록 키를 사용했던 과거 근거이며, Census 키 없는 호출을 시험하지 않았다.

## Gate B 입력 계약과 통과 범위 명확화 (2026-10-26)

- **D-060 / ACCEPTED:** `PROJECT_PLAN.md`가 MVP를 구조화된 요청으로 정의하고 자연어 UI를 별도
  통합 단계로 두는 한편 Gate B 문구는 자연어 해석까지 요구해 서로 달랐다. Gate B는 Python engine/API
  수준에서 구조화 `DataRequest`를 근거 후보 순위·사용자 명시 선택·지원 collector에 연결하는
  최소 기능 게이트로 한정한다. 자연어 parser, CLI/UI, 일반 기관 전체 탐색은 별도 사용자 인터페이스/
  기관 확대 작업으로 둔다.
- 현재 테스트의 known-mismatch exclusion, explicit confirmation 및 World Bank fixture E2E가 위
  제한 criteria를 충족하므로 Gate B를 제한 범위에서 통과 처리한다. 이는 BLS/Census candidate-to-live
  collection 또는 전체 제품 출시를 승인하지 않는다. Gate C는 기존 범위의 부족한 기관/변경/복구
  매트릭스를 채울 때까지 미통과다.
- 이는 기존 `ITERATION_08_REPORT.md`의 당시 판정을 삭제하지 않고 후속 재판정으로 추가한다.
  상세 적용은 PROJECT_PLAN의 현행 요구사항과 IMPLEMENTATION_PLAN의 상태 표를 따른다.

## 로컬 source checkpoint와 clean checkout 검증 (2026-10-26)

- **D-061 / IMPLEMENTED, remote publication pending:** 05~10회차 코드·테스트·계획을 local branch
  `codex/institution-discovery-05`의 commit
  `7a2bb031d61061abc894ac206c45a95d8e45f5fd`로 고정했다. detached clean checkout에서 pytest 524개,
  Ruff 및 `git diff --check`가 통과했다. API 키와 `data/raw` 원본은 커밋하지 않았다.
- 읽기 전용 `git ls-remote`에서 `origin/codex/iteration-04-gate-a`는 기존 기준 commit
  `2c4e11fa0534bae6458154abfa14a03d3617a15b`이며, 새 local branch/commit은 origin에 없다.
  기존의 게시 금지 지시에 따라 push, 환경 draft 변경 또는 publish를 수행하지 않았다. 따라서 clean
  remote checkout과 실행 환경 배포 추적성은 아직 미해결이다.

## 게시된 기준선 검증 및 World Bank 변경 감지 보완 (2026-10-26)

- **D-062 / IMPLEMENTED LOCALLY, not published:** 게시 후 fresh environment의 `HEAD`가
  `781827593924e35dadbc1188f09c7ea40a7b7c76`, branch가 `codex/institution-discovery-05`,
  working tree가 clean임을 확인했다. Runtime은 observed spec revision 4에서 running/connected다.
  이로써 해당 게시 기준선의 repository-reference mismatch를 닫았다. BLS/Census secret readiness와
  network policy는 `unknown`; 이 후속 task에서는 실제 API 호출을 하지 않았다.
- Gate C의 X08 보완으로 World Bank Gate A 감사 수집에서 동일 공식 URL·요청 범위·evidence mode의
  최신 성공 capture와 현재 payload를 비교한다. JSON은 key order/formatting을 정규화하고, JSON이
  아니면 raw bytes hash를 쓴다. 이전 raw와 manifest 무결성을 확인하기 전에는 과거 해시를 신뢰하지 않는다.
  payload 변경은 두 원본을 보존하고 `NEEDS_REVIEW`와 함께 정규화 게시를 차단한다. 실패한 HTTP/
  수집 capture는 비교 기준선이 되지 않는다. 최대 1,000개 artifact 조회 후 이력을 못 찾거나
  이력 무결성·비교 방식이 확인되지 않으면 `unknown`으로 보고한다.
- fixture 회귀는 changed/unchanged response, formatting-only difference, 다른 요청 범위,
  손상된 prior raw, 비교 metadata가 없는 legacy artifact, evidence mode 분리, 재시도 중 바뀐
  payload를 검증한다. TIC TSV/HTML과 BIS ZIP/CSV-shaped fixture는 raw archive·manifest·normalized
  table까지 ingestion engine으로 통과한다. 전체 pytest 534개, Ruff와 `git diff --check`를 통과했다.
  official provider/change workflow와 Japan 및 기관별 recovery 표본이 부족하므로 Gate C는 계속
  미통과다. 이번 변경은 local-only이며 게시본에는 포함되지 않는다.

## Tabular source provenance and changed-file guard (2026-10-26)

- **D-063 / IMPLEMENTED LOCALLY:** For local tabular imports with a safe HTTPS `source_url`, store
  source agency/table and bounded capture metadata in the request and final manifests. Compare
  verified prior raw bytes only within the same source URL and parser scope; capture timestamp,
  HTTP status, and content type are excluded from scope so repeated unchanged downloads compare
  correctly. When source bytes changed or prior history integrity is unknown, preserve the raw file
  and stop with `NEEDS_REVIEW` before normalized data is written.
- Verified with a live Treasury TIC Table 5 file imported from the already-fetched official response,
  plus deterministic tests for changed/unchanged and tampered-history cases. The live TIC source has
  only one capture, so this does not establish live revision detection, an automatic TIC downloader,
  or Gate C completion. These code changes remain local and unpublished.

## Gate C follow-up: BIS/BOJ live evidence and parser policy (2026-10-26)

- **D-064 / IMPLEMENTED LOCALLY:** BIS official guide inspection and one official Global Liquidity
  column ZIP intake are limited live evidence. Keep the strategy as manual file intake; do not imply
  SDMX/series-level support. Preserve exact-case distinct headers such as `DECIMALS` and `Decimals`
  because they are separate source columns; reject only exact normalized duplicates.
- **D-065 / BLOCKED:** BOJ's official API notice is reachable, but the linked official API manual
  returned HTTP 403. Without verified request parameters and series IDs, do not guess or issue a data
  API request; expose BOJ collection as `blocked_manual_access`.
- Live BIS flat ZIP HTTP 503 is recorded without retry. For retryable guide-fetch failures,
  `Retry-After` is parsed and persisted as a manual retry hint; automatic retry is not performed.
- Full verification after these changes: **556 pytest passed**, Ruff and `git diff --check` passed.
  Live source-change comparison and provider recovery evidence remain incomplete, so Gate C is not
  passed. These code/document changes are local, uncommitted and unpushed; no environment publish was
  performed.

## Iteration 12 bounded knowledge lookup (2026-10-26)

- **D-066 / IMPLEMENTED, Gate D not passed:** Following the user's explicit next-stage instruction,
  continue with the bounded portion of iteration 12 while Gate C was still failed. Keep the feature in
  SQLite as a current projection over the append-only feedback store. Feedback writes enqueue changes;
  only an explicit refresh applies at most 500 queue entries. Requests never rebuild the projection or
  load task histories. Institution and supplied scope dimensions are indexed; unspecified request
  dimensions only match null-scope records, while requested dimensions may also match broader null scope.
- Return only accepted instructions/evidence by default. Inference remains opt-in and review-required;
  official evidence is reference-only. Prior output preferences always require user confirmation,
  conflicts require review, and a current explicit instruction takes precedence. Bound candidate reads,
  result count, and cache bytes/entries; incomplete candidate scans cannot supply reuse decisions.
- Gate D remains **not passed** because no Orchestrator repeat-task/retry path consumes the lookup and
  same-institution end-to-end efficiency has not been measured. Synthetic microbenchmark measurements
  cover only the SQLite lookup layer. See `docs/ITERATION_12_REPORT.md`.

## Gate C limited-scope acceptance (2026-10-26)

- **D-067 / ACCEPTED AND IMPLEMENTED:** At the user's direction to change the way Gate C can proceed,
  allow a limited pass for only the verified paths: selected live capture and manifest integrity,
  deterministic changed-source handling using a controlled copy of an actual captured TIC raw file,
  and Orchestrator persistence/resume through a simulated retryable provider response.
- The TIC raw capture remains unchanged. Its temporary copy was altered from Japan `1068.3` to
  `1068.4`; the ingestion engine returned `changed`/`NEEDS_REVIEW`, retained both raw copies, and
  emitted no normalized table for the changed copy. The test suite separately includes an Orchestrator
  integration test that persists HTTP 503 with `Retry-After: 2`, reopens the task store, blocks an early
  resume, then succeeds on the same task after the delay using a fixture response.
- This decision does **not** assert a natural live source revision or natural provider outage/recovery.
  Both remain `NOT_RUN`; BOJ remains `BLOCKED`, semantic dimension checks remain partial, and untested
  institutions and paths remain outside the passed scope. Detailed evidence and hashes are in
  `docs/GATE_C_REVIEW_2026_10_26.md`. At that point Gate D was not passed; D-068 records the later
  Orchestrator integration and current result.
- This is a formal narrowing of the Gate C acceptance scope, not a backdated claim that the original
  full-live evidence requirements were observed. No environment publish was performed.

## Gate D knowledge-to-Orchestrator integration (2026-10-26)

- **D-068 / IMPLEMENTED, Gate D passed:** Connect the existing bounded institution-scoped knowledge
  projection to task planning through explicit feedback selection. Only an accepted `user_instruction`
  returned by a ready, complete, matching-scope lookup can be attached to a task. The caller selects one
  feedback ID; current instructions take precedence, and changed/pending index state blocks planning.
- A stage opts in to conditional omission by declaring its `knowledge_reuse_category`. When the caller
  selects matching knowledge, only that tagged planning stage is omitted and the task records the
  selected scope, feedback revision, source evidence, skipped stage and index revision. Remaining stages
  receive the context. Stage fingerprints include it so changed knowledge cannot reuse stale results.
- A 30-repeat BLS/CPI fixture E2E measured stage runs decreasing from 2 to 1 per repeated task (60 to 30
  total). One run measured p50/p95 latency 4.207/4.582 ms without reuse and 3.444/4.537 ms with reuse. A different
  institution, broad scope, conflict, inference, unreviewed feedback, and stale index are blocked; current
  instruction wins. Maximum Python allocation increased by about 7 KB in this tiny fixture.
- This proves the supported explicit planning path only. It does not provide UI consent collection,
  automatic knowledge selection, live-provider efficiency claims, or cross-institution common-rule
  promotion. See `docs/ITERATION_12_REPORT.md`; no 13th iteration or environment publish was performed.

## Iteration 13 planning criteria (2026-10-26)

- **D-069 / PLANNED, not implemented:** After Gate D passed, make iteration 13 measurable before
  starting it. Treat a pattern as recurring only when the same bounded fingerprint appears in at least
  three distinct task IDs; retries inside one task do not count as independent cases. Keep institution,
  engine/version, stage, error/category, and known dataset/concept scope in the fingerprint. Unknown or
  different dimensions do not merge.
- Bound one analysis to 500 tasks / 2,500 stage or feedback records, at most 20 proposals and 10 evidence
  references per proposal. Report truncation as incomplete. Use only persisted outcome metadata and
  accepted explicit feedback; exclude raw provider payloads, secrets, unreviewed feedback, and inference
  from evidence. Every result remains a `draft` with evidence IDs, impact, risk, counterexamples, and a
  regression-test proposal. No feedback status changes, fact promotion, or code edits occur in iteration 13.
- X09 and the 100/1,000/5,000-record benchmark are the planned verification. These are initial planning
  caps to measure and refine during iteration 13. Gate E / iteration 14 remains unstarted.

## Iteration 13 bounded pattern analyzer (2026-10-26)

- **D-070 / IMPLEMENTED:** Added a read-only SQLite analyzer and `macro-patterns` CLI. It selects only
  terminal task/stage metadata and accepted `user_instruction` feedback. Stage and accepted-feedback
  patterns use separate fingerprints; feedback is compared by normalized exact text hash, without
  returning its text. At least three distinct tasks and a complete matching scope are required. Unknown
  dimensions are task-local and do not merge. Conflicting accepted instructions are separated for human
  review. Every proposal stays `draft`/`not_promoted`.
- Enforced caps are 500 terminal tasks, 2,500 outcome/feedback records, 20 proposals, and 10 evidence IDs
  each. Read-only SQLite mode does not initialize a missing database. Raw provider payloads and task request
  text are not selected into Python; common secret-shaped feedback is excluded.
- X09 synthetic tests pass; full suite **591 passed**, Ruff and `git diff --check` pass. Warm local synthetic
  benchmark p95 was 5.448/51.023/134.287 ms for 100/1,000/5,000 stage records; the 5,000 input correctly
  returns partial at the 2,500-record cap. The 5,000-case maximum traced Python allocation was 5,484,768 bytes.
  The observed environment's reference budgets are p95 150 ms and 8 MiB Python allocation for bounded runs.
- This is local synthetic evidence only. It does not establish live recurring errors or root cause, does not
  change Gate C, and does not start iteration 14 / Gate E. See `docs/ITERATION_13_REPORT.md`.

## BOJ official API manual recheck (2026-10-26)

- **D-071 / DOCUMENTATION VERIFIED, COLLECTOR NOT IMPLEMENTED:** Re-fetched the official BOJ notice and
  its linked API manual once each using the configured proxy and explicit network permission. The notice
  returned HTTP 200, 36,614 bytes, SHA256
  `1c48b9491cbfc43d7b8100278ef6a432a9fcb4996a34795c06e2f396d7d0db68`. The manual returned HTTP 200,
  `application/pdf`, 857,117 bytes, SHA256
  `8e289fb77b9e3f80569206d27059eeb3f35e824facff1c339670179aad5ba9cd`; it is dated 2026-02-18 and has
  27 pages. Both original responses and manifests are preserved under gitignored `data/raw/guides/`.
- The manual documents `/api/v1/getMetadata`, `/getDataLayer`, `/getDataCode`, request parameters and
  250-series / 60,000-point per-request limits. One limit paragraph says `/getLayerCode`, unlike the
  `/getDataLayer` endpoint elsewhere; verify that path before constructing a data request. No BOJ
  metadata/data API request was sent, so series mapping and observation schema remain unverified.
- The previous HTTP 403 attempt saved no body/hash and current archive comparison is `baseline_unavailable`;
  whether the manual itself changed cannot be established. It is now accessible. Update institution support
  state from `blocked_manual_access` to `collection_not_implemented`, since documentation exists but the
  BOJ observation adapter is absent. Gate C's D-067 limited pass and its scope are unchanged.

## BOJ live endpoint re-evaluation (2026-10-26)

- **D-072 / LIMITED LIVE VERIFIED:** The manual naming discrepancy does not block independent,
  explicitly documented metadata and code endpoints. One FM08 metadata GET and one confirmed FXERD01
  September 2026 data GET both returned HTTP/JSON STATUS 200. Arrays contain 30 dates, 19 numeric
  values and 11 nulls. No reusable collector or orchestration integration was implemented.
  Details and hashes: `docs/BOJ_LIVE_RECHECK_2026_10_26.md`. This supersedes D-071
  only regarding the later live requests, without expanding Gate C acceptance.

## BOJ same-scope live retest (2026-10-26)

- **D-073 / REPEAT VERIFIED, SCOPE UNCHANGED:** Repeated the official FM08 metadata request and the
  fixed FXERD01/202609 `getDataCode` request once each. Both returned HTTP/JSON STATUS 200. Metadata
  body hash matched the first request. The data response was 995 bytes, SHA256
  `9633b5794015ffa16494228f84746152fdf02c7dc08f044d5bdb9f115a4264b2`; the documented nested
  `RESULTSET[0].VALUES` schema contains 30 dates, 19 numeric values, and 11 nulls. The canonical
  requested-scope data hash matched the first capture; only the response `DATE` envelope field
  differed. A local validator initially assumed arrays were at the wrong JSON path; the already
  archived body was revalidated against its actual nested schema without another network request.
  This is repeat API-access/response-shape evidence only. It does not demonstrate a source revision,
  provider durable resume, collector integration, or a broader Gate C pass. See
  `docs/BOJ_LIVE_RECHECK_2026_10_26.md`.

## Iteration 14 Gate E and explicit proxy support (2026-10-26)

- **D-074 / IMPLEMENTED, GATE E PASSED FOR RESTRICTED LOCAL V1:** Reproducing the documented World Bank
  live path exposed a transport issue: `trust_env=False` prevented use of the configured sidecar proxy.
  Keep implicit `.netrc`/credential lookup disabled, but pass the configured HTTP(S) proxy and Requests/Curl
  CA bundle explicitly to the request. TLS verification, redirect refusal, bounds, timeout, and no automatic
  retry remain in force. Mocked tests verify both the default and configured-proxy cases without network use.
- The first live task ended as `TRANSIENT` before a complete response; the same fixed request succeeded after
  the change (`HTTP 200`, three validated observations, `live_path_passed=true`). Raw SHA256
  `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1` matches the prior Gate A capture,
  so this is not a source revision. `592` tests and Ruff passed. The A–H/X01–X09 status matrix, supported-scope
  user guide, and 10-slide PPTX were produced and checked.
- Gate E is a restricted local-v1 review only. Blocked/partial institutions, Windows installation not run in
  this Linux environment, natural TIC/BIS revision, natural provider durable resume, and absent BOJ collector
  remain explicit. No environment publish or main merge occurred. See `docs/ITERATION_14_REPORT.md`.

## Four-track post-merge follow-up (2026-10-26)

- **D-075 / IMPLEMENTED WITH NATURAL GATE C EVIDENCE STILL OPEN:** After PR #1 merged at
  `9986472f983a70aacc86209ee54883cca558c5e9`, the user asked to complete the four remaining tracks in order.
- Added fixed FM08/FXERD01 monthly BOJ metadata/data stages, a persisted TIC/BIS exact-scope watch, and the
  bounded `macroatlas` CLI for World Bank, BOJ, status/resume, and the two file watches. These paths do not
  generalize to arbitrary series, URLs, natural language, or institutions.
- TIC and BIS live source checks returned HTTP 200 and `unchanged` against the validated baseline. No natural
  provider failure occurred; same-task resume evidence remains fixture-only. Gate C D-067's limited pass is
  unchanged.
- Added a Linux/Windows Python 3.11/3.12 CI workflow. Live World Bank and BOJ commands completed on the
  managed Linux environment. The initial PR run caught a Windows case-insensitive environment-variable
  assumption in one proxy test; after correcting the test, CI run `40336575209` passed all four OS/Python
  combinations, including tests, Ruff, and installed CLI help. Details are in `docs/ITERATION_15_REPORT.md`.
- No environment publish/deploy was performed. Current code, exact scopes, test evidence and remaining natural
  events are in `docs/ITERATION_15_REPORT.md`, `docs/GATE_C_SOURCE_WATCH.md`, and `docs/connectors/BOJ.md`.

## D-076 — 16회차 이후 현행 Gate 재검증

과거 BLOCKED/PARTIAL 표기를 그대로 사용하지 않고 현재 코드·회귀·지원 경로 live 응답으로 재검증했다.
BIS flat 보존 원본의 cells=500010 인계 성공은 정책에 따른 정상 중단이다. 정상화 지원 완료로 확대하지 않는다.
현재 관측에서 발생하지 않은 자연 revision/자연 transient resume는 미관측으로 유지한다.
재검증 중 ZIP 선택·read-only 조회·HTTP 용량 타입·CLI 사유 누락·workbook 예외 처리를 수정했다.
근거는 GATE_REAUDIT_AFTER_ITERATION_16.md에 있다.

## D-077 — 경험적 대용량 qualification과 미실행 응답

사용자 지시에 따라 DuckDB/Arrow/Polars 공식 streaming·메모리 제한 사례를 조사했다.
추가 외부 엔진 의존성 대신 제한된 표준 CSV worker로 qualification 경로를 먼저 구현했다.
명시 large-check가 불변 인계 event·원본 stat·코드/예산에 결합한 child task를 저장하고
Linux resource limit·timeout·출력 예산·동시 실행 제한으로 시험한다. 실패는 미실행, 애매한 구분자 추정은
불확실성을 남기며 자동 승인하지 않는다. 합성 19개 사례와 BIS 보존 원본을 실측했다.
정식 대용량 normalized·원격 download·Windows resource worker는 이 구현에 포함되지 않는다.

## D-078 — 대용량 시험 process 중단 복구

시험 worker가 parent process 종료 뒤에도 살아 있을 수 있으므로, workspace lock을 task claim 전에 잡고
child process에 상속한다. 새 `resume`은 같은 lock을 얻어 실제 worker 종료를 확인한 뒤 표시된 scratch만 정리한다.
저장된 결과가 없으면 `trial_state=UNKNOWN`, `execution_state=NOT_EXECUTED`, `NEEDS_REVIEW`로 기록하고
같은 task의 qualification을 자동 재실행하지 않는다. 원본과 부모 task는 그대로 둔다.

## D-079 — BIS flat 제한 production handoff

19회차에서 기존 16회차 deferral event·origin task·보존 raw/request manifest와 같은 hash의 성공 trial을
검증하는 별도 child task를 연결한다. 명시 `--approve-production` 전에는 실행하지 않으며 같은 immutable event와
artifact 조합은 같은 child를 반환한다. child 생성과 `handed_off` event, 완료 시 `resolved` event는 각각
task history와 같은 SQLite transaction에서 기록한다.

현재 지원은 BIS GLI flat ZIP 내부 단일 UTF-8 CSV 한 건이다. Linux worker는 10,000행 chunk,
hash-verified checkpoint, 128 MiB input/192 MiB output/384 MiB memory/30초 CPU/60초 wall 예산을 사용한다.
다른 OS·파일은 제한 없는 fallback 없이 미실행 처리한다. output은 문자열 JSONL이며 구조·출처 검증만 포함한다.
단위·빈도·경제 의미를 채우지 않고, Gate C natural source change/recovery와도 분리한다.
구현·실측 결과와 알려진 제한은 `docs/ITERATION_19_REPORT.md`에 기록한다.

PR #6은 CI 네 조합 통과 후 merge commit `dfdfa307`로 통합됐다. 보존된 event seq `1`은 child task
`c244a486-17e5-4b60-a82b-287f8a37bbe7`에서 한 번 처리되어 24,378×21 구조 보존 JSONL을 만들었다.
원본·manifest·chunk hash와 `handed_off/resolved` 이력을 확인했다. 이번 로컬 처리 결과는 Gate C 자연 revision이나
자연 장애 후 재개 증거가 아니다. 후속 순서는 [제품 로드맵](ROADMAP_2026_10_26.md)을 따른다.

## D-080 — 검증된 World Bank/BOJ task의 제한 CSV 전달

20회차에서 완료·quality-passed인 고정 World Bank USA GDP와 BOJ FM08/FXERD01 task만 읽는 CSV CLI를 추가했다.
exporter는 SQLite 이력을 read-only로 열고 stage, provider scope, quality, normalized observations, raw 및
request manifest를 task와 대조한다. UTF-8 CSV와 provenance sidecar를 `data/exports/`에 no-overwrite로 만들며,
null과 0을 구분하고 unknown unit/frequency는 빈 값으로 남긴다. BOJ는 수집 시 manifest digest를 task에
기록하지 않아 export에서 manifest field/raw hash를 다시 검증하고 이 한계를 sidecar에 공개한다.

`NEEDS_REVIEW`, changed/unknown source status, 미완료 task, 변조 원본, 경로 traversal/symlink와 기존 출력은
거부한다. BIS flat JSONL, XLSX, 임의 provider는 미지원이다. 로컬 증거는 [20회차 보고서](ITERATION_20_REPORT.md)에
있으며 자연 Gate C revision/recovery 증거와 무관하다.

## D-081 — CSV 전달 사용자 흐름 내부 dry run

저장된 World Bank·BOJ 성공 task를 다시 조회하고 각각 새 파일명으로 CSV export했다. CLI help, task 상태,
품질 경고, row/null 수와 CSV hash가 사용자 문서의 제한 범위와 일치했다. 요청은 모두 로컬 SQLite/raw에서
읽었고 외부 네트워크는 사용하지 않았다. task 산출물은 기존 경로를 덮지 않고 Git-ignored `data/exports/`에
기록했다.

이는 작성자의 desk review라 독립 사용성 evidence가 아니다. Gate C와 제품 지원 범위는 바꾸지 않는다.
실제 분석가 1–2명의 관찰 세션에서 CLI JSON과 경고 이해도를 확인하기 전 UI/provider/natural-language 작업을
선정하지 않는다. 상세 기록은 `docs/USER_WORKFLOW_DRY_RUN_2026_10_26.md`다.

## D-082 — 비API 대용량 실행 전 예상과 실측 보정

사용자는 qualification과 대용량 production을 시작하기 전에 예상 소요 시간을 알아야 한다. 두 실행 경로에 bounded
read-only profile, stage wall-time forecast, 실행 직전 요약과 무실행 `large-estimate` 명령을 둔다. 최근 성공 task를
qualification/production별로 나누어 baseline 및 workload 유사 후보의 shadow forecast를 실제 시간과 비교한다. paired
forecast가 3건 쌓이기 전에도 유사 successful run 3건 이상이면 경험 후보를 쓰며, 이후에는 paired 결과의 중앙 APE가
낮은 모델을 택한다. 무작위 production A/B 분할은 하지 않는다.

입력에서 최대 256 KiB만 읽고 샘플 값은 저장하지 않는다. 예측은 추정이며 자원 예산, worker 실행 여부, 원본·승인·
qualification guard를 바꾸지 않는다. 실측 표본 수·신뢰도·범위를 사용자에게 보여주며, Gate C와 API 경로에는 적용하지
않는다. 구현/검증 결과는 `docs/ITERATION_22_REPORT.md`와 `docs/LARGE_FILE_ENGINE.md`에 남긴다.

## D-083 — 제품 엔진과 개발자 유지보수 workflow의 경계

2026-10-26 기준 코드 대조에서 제품 데이터 실행은 `Orchestrator`와 `(engine, version)` registry를 이미 공유한다.
API connector, 작은 파일 engine, 대용량 worker, exporter는 source·parser·resource 경계가 다르므로 전문 adapter/worker로
유지하고 공통 실행 계약만 공유한다. 이를 하나의 data super-engine으로 합치지 않는다.

개발자 코드 업데이트는 제품 task path와 별도 control plane으로 둔다. `pattern_cli` 분석, `run_improvement.ps1`,
`run_maintenance_qa.py`, `run_checks.ps1`의 중복/연결 공백은 [엔진 통합·분리 개선안](ENGINE_CONSOLIDATION_PLAN.md)의
24–27회차 순서로 다룬다. 자동 수정은 격리 branch/worktree에서 실행하고, 동일 candidate SHA에 QA evidence를 붙인 뒤
성공한 branch만 commit/push/PR로 제출할 수 있다. merge와 publish는 사람 검토로 남긴다.

현재는 설계 선택만 기록했으며 코드를 바꾸거나 scheduler를 수정하지 않았다. analyzer scope adapter의 허용 source
field와 updater의 경로 allowlist는 후속 구현 시작 전에 실제 workflow model에 맞춰 확인한다. 미상 concept은 계속 unknown으로 둔다.

## D-084 — 유지보수 health와 QA 진입점 통합

24회차에서 `scripts/run_maintenance_qa.py`를 공통 offline check entrypoint로 확장했다. clean commit의 detached worktree에서
pytest, Ruff, commit whitespace, CLI module/entrypoint help, project health를 check별 timeout/log/report로 수행한다.
`scripts/run_checks.ps1`은 이 Python runner의 thin wrapper이며 GitHub Actions matrix도 동일 runner를 호출한다.
실행 파일이 없거나 한 check가 실패해도 나머지 check를 실행해 원인을 구조화 결과에 남긴다.

이 결정은 `run_improvement.ps1`의 코드 수정 경로, PatternAnalyzer의 근거 부족, candidate SHA 검증·PR 생성, Windows
예약 설정을 연결 완료 처리하지 않는다. 이 잔여 범위는 D-083에서 정한 25–27회차 순서를 따른다.

## D-085 — immutable candidate SHA 기반 유지보수 QA

2026-10-27 후속 구현에서 공통 QA runner에 `--base <full-sha> --candidate <full-sha>` 입력을 추가한다. runner는 두 commit이
현재 repository object store에서 전체 SHA로 resolve되는지, base가 candidate의 조상인지 확인한 다음 candidate SHA를 detached
worktree에 checkout한다. 원 checkout이 dirty여도 검사 대상은 candidate commit으로 고정되며 report에는 source checkout 상태,
두 SHA와 변경 파일을 기록한다. CI의 Ubuntu/Windows × Python 3.11/3.12 matrix는 PR base와 candidate SHA를 넘겨 이 모드와
PowerShell wrapper를 함께 검증한다.

QA runner는 변경을 commit/push하거나 PR을 만들지 않는다. `run_improvement.ps1`의 별도 updater worktree·수정 범위 allowlist·
candidate commit·QA·성공 조건부 push/PR handoff와 scheduler pilot은 아직 후속 단계이며, merge/publish는 사람 검토로 남긴다.

## D-086 — updater와 candidate QA handoff 연결

2026-10-27 `scripts/run_improvement.ps1`을 Python workflow의 얇은 Windows wrapper로 바꾸고, `scripts/run_improvement.py`에서
source checkout을 전환하지 않는 흐름을 구현한다. 기본 base는 `origin/HEAD`이며, 없으면 명시 `--base-ref`를 요구한다.
Codex는 git worktree에서 실행되고, 변경은 `src/`, `tests/`, `docs/`, 제한된 문서/스크립트 경로에만 허용한다. database·credential·
symlink·`.github` 등 보호 경로 변경은 거부한다. 실행 결과와 단계별 log를 구조화 report로 남긴다.

변경이 없으면 생성 worktree/branch를 정리한다. 변경이 있으면 candidate commit을 만든 뒤 D-085 runner가 같은 SHA를 검사한다.
QA 실패나 timeout이면 push/PR을 하지 않으며, 통과한 경우에만 원격 branch를 push하고 review PR을 생성한다. 자동 merge와 publish는
없다. Unit tests는 no-op 정리, allowlist, QA 실패 시 무push, 성공 시 QA→push→PR 순서를 검증하고 CI dry-run은 Linux/Windows wrapper를
확인한다. 상세 구현 근거는 `docs/ITERATION_26_REPORT.md`에 둔다. 실제 Windows Codex pilot, scheduler 운영 및 동시성은 아직 검증하지 않았다.

## D-087 — Codex CLI 인증 실패의 사용자 조치 상태

2026-10-27 감독 updater run에서 설치된 CLI 인자 문법 오류를 바로잡은 뒤 service `401 Unauthorized`와 token refresh 실패를
확인했다. Codex prompt는 실행되지 않았고 worktree는 clean/base HEAD로 확인했다. 사용자 credentials를 읽거나 갱신하지 않고, 해당
응답은 `CODEX_AUTH_REQUIRED` 및 “Codex CLI에 다시 로그인한 뒤 재실행” action으로 보고한다. 이 상태는 QA 실패, GitHub push 실패,
provider/API 연결 실패와 구분한다. 상세 실행 증거는 `docs/ITERATION_26_PILOT_BLOCKER_REPORT.md`에 보존한다.

## D-088 — 증거 기반 기관·dataset scope projection 확장

2026-10-27. Full-catalog 감사에서 오류 3건은 모두 institution/dataset이 있었지만, 성공 stage 5건(BLS 2, Census 2,
large-file production 1)은 projection에 scope가 비어 있었다. BLS/Census는 기관의 exact HTTPS API URL, 보존 request manifest,
UTC retrieval time, HTTP 200, request/plan 일치, raw path·byte count·SHA 및 JSON 응답을 확인한 경우에만 기관·dataset scope를
분석 결과에 연결한다. BLS manifest는 기관을 증명하지만 dataset은 명시적으로 null이므로 두 건 모두 dataset unknown으로 남긴다.
Census는 응답·plan·manifest의 `acs/acs1`이 일치해 dataset을 복구했다. 대용량 BIS production은 plan의 raw/manifest SHA를
기존 BIS verifier 결과와 대조한다. 어느 adapter도 concept을 유추하거나 task·raw·manifest를 수정하지 않는다.

회귀 검증 후 49 terminal tasks / 57 stages snapshot에서 operational 37 stage, verified scope resolution 7건, 오류 3건,
institution unknown 0건, dataset unknown 2건을 확인했다. 후속으로 확인한 [BLS API FAQ](https://www.bls.gov/developers/api_FAQs.htm)는 전체
series catalogue가 없으며 registered API v2의 description/catalog 지원은 한정적이라고 명시한다. [CPI code 문서](https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm)의
`CU`는 CPI-U series type을 구분하지만 MacroAtlas dataset ID를 단독으로 증명하지는 않는다. 등록 metadata가 보존된 정상 수집 응답이
생기기 전까지 BLS `dataset_id=null`을 유지하고 series ID를 dataset으로 승격하지 않는다. Full-catalog error audit는 [별도 보고서](ENGINE_INSTITUTION_ERROR_AUDIT_2026_10_27.md),
회귀 범위는 [scope recovery 기록](SCOPE_EVIDENCE_RECOVERY_PLAN.md)에 있다.

## D-089 — Updater scheduler 가드와 보수적 report retention

2026-10-27. Windows installer는 PR handoff가 가능한 명시 local/remote branch, 선택된 Python executable, 현재 로그인 사용자의
`Interactive`/`Limited` principal을 task action에 고정한다. `-DryRun`은 action·trigger·settings·principal 계획을 출력하고
Task Scheduler에 등록하지 않는다. Updater manual/scheduled 실행은 reports 디렉터리의 OS advisory lock을 공유하며 lock 점유 시
수정·네트워크 작업 없이 `ALREADY_RUNNING` report만 남긴다.

90일이 지난 정상 `NO_ACTIONABLE_CHANGE` updater report는 cleanup 성공, checkout 미존재, git worktree/branch 부재, 허용 파일만 존재할
때만 정리한다. 정상 non-candidate maintenance check report도 같은 기간 뒤 정리할 수 있지만 candidate QA, 실패, cleanup 미완료,
손상·예상 밖 내용을 포함한 report는 자동 삭제하지 않는다. 이 정책은 Windows changed/failure 사용자 pilot을 대신하지 않으며
예약 task는 해당 pilot 전까지 설치·활성화하지 않는다.

## D-090 — Windows stale-checkout installer 실행 복구

2026-10-27. 사용자가 `git fetch`만 한 checkout `8fc22c8`에서 아직 `-DryRun`을 지원하지 않는 이전 installer를 실행해,
`MacroData-HealthCheck`와 `MacroData-AgentImprovement`가 실제 등록됐다. 읽기 전용 action 조회에서 두 task가 사용자 저장소를
가리키는 것을 확인한 뒤 unregister했고, 후속 task 조회에서 둘 다 없음을 확인했다. 최신 base `a7f7a1f`로 fast-forward한 다음
installer dry-run은 base SHA, Anaconda Python 경로, 현재 user principal, `Interactive`/`Limited` 및 두 action을 출력하면서
`registered=false`를 반환했다. 이 실측은 installer 계획 검증에 한정하며 actual scheduled execution을 의미하지 않는다.

## D-091 — 최신 Windows updater no-op 경로 실측

2026-10-27. 사용자가 updater 운영 가드가 포함된 Windows checkout에서 `run_improvement.ps1`을 실행했다. Run
`20261027T062202Z-a897a292`는 base `689cd1b14dd15c50987893ac9cd25dbe9c6aab62`, `NO_ACTIONABLE_CHANGE`,
`cleanup=PASSED`, `network_requested=false`로 끝났고 candidate/QA/push/PR은 없었다. Retention 요약은 90일, scanned 3,
removed 0, preserved 3이었다. 이는 단일 정상 no-op 경로만 확인하며 concurrent lock contention, candidate handoff, failure resume,
또는 scheduler 실행의 증거로 확대하지 않는다. 예약 task는 계속 비활성이다.

## D-092 — Windows updater 교차 프로세스 lock 경합 실측

2026-10-27. 사용자가 temporary Python holder로 OS lock을 점유한 동안 별도 PowerShell process에서 updater를 실행했다. Run
`20261027T063105Z-60a54edf`는 `ALREADY_RUNNING`, `network_requested=false`, `changed_paths=[]`, `push_status=NOT_RUN`,
`pull_request=null`을 반환했으며 저장소 수정이나 provider 요청은 없었다. 이는 Windows OS-level lock 경합 차단을 확인한 증거다.
실제 Windows candidate QA/handoff, failure 복구 및 Task Scheduler invocation은 아직 검증하지 않았다. 예약 task는 계속 비활성이다.

## D-093 — 최신 base의 Windows updater no-op 재실측

2026-10-27. 사용자가 PR #38 merge commit `aefd320a67d0abb5779393b90d32f6d149efa77e`를 checkout한 뒤 updater를 실행했다.
Run `20261027T063907Z-d01e9247`은 `NO_ACTIONABLE_CHANGE`, `cleanup=PASSED`, `network_requested=false`로 끝났고 candidate, QA,
push, PR handoff는 없었다. Worktree와 branch가 정리됐으며 90일 retention report는 `scanned=5`, `removed=0`, `preserved=5`를
기록했다. 이는 최신 base의 no-op 정리 경로를 확인하며 Windows changed-candidate/failure 복구나 실제 scheduler 실행의 증거는 아니다.
예약 task는 계속 비활성이다.

## D-094 — World Bank GDP 공식 metadata 보존 및 unknown 유지

2026-10-27. Official World Bank indicator metadata endpoint를 한 번 조회해 HTTP 200 응답과 manifest를
[metadata response](evidence/worldbank_gdp_indicator_metadata_20261027.json) 및
[request manifest](evidence/worldbank_gdp_indicator_metadata_20261027.manifest.json)에 보존했다. Exact indicator
`NY.GDP.MKTP.CD`의 공식 name은 `GDP (current US$)`이며 source note는 현재 가격의 미국 달러라고 설명한다.
그러나 response의 structured `unit` 값은 빈 문자열이고 frequency/periodicity field가 없다. 따라서 이 결과는
indicator의 표시 의미를 확인하지만 정규화 unit/frequency 값을 증명하지 않는다. 저장된 2020–2022 observation,
원본 manifest, 과거 quality report는 변경하지 않고 unit/frequency unknown을 유지한다.

## D-095 — 시계열 주기 기반 최신성 판정

2026-10-27. 사용자의 요청에 따라 최신성은 다운로드 시각이나 metadata refresh 시각이 아니라
관측기간 끝을 기준으로 평가한다. 기본 최대 허용 일수는 일간 7, 주간 21, 월간 120, 분기 240,
반기 183, 연간 730이며, 정책 ID·SHA256 fingerprint와 시계열 단위 override를 기록한다.
이는 발표 달력을 공식 검증한 값이 아니라 명시적 운영 기본값이다. 주기가 없거나, 기간을
해석할 수 없거나, 관측이 미래인 경우 `FRESHNESS_UNVERIFIED`; 허용치를 초과하면 `STALE`로
분류하고 정규화 관측값과 지원 CSV 출력을 보류한다. 원본·manifest는 보존한다. World Bank,
BLS, Census, BOJ 경로 및 World Bank/BOJ CSV 재검증에 연결했다. fixture 기반 테스트는
실행했으나 이 변경의 live freshness 동작은 검증하지 않았다. Gate C는 통과 처리하지 않는다.
세부 정책과 현재 범위는 [`SERIES_FRESHNESS.md`](SERIES_FRESHNESS.md).

## D-096 — TIC/BIS 자료 변경상태 반복 확인 제외

2026-10-27. 사용자가 TIC/BIS 원자료 변경상태를 확인하는 작업은 현재 필요하지 않다고 지정했다.
이에 `Gate C 자연 증거 감시`와 `Gate C Source Watch` 두 반복 자동화를 중지했고, 로드맵의 활성 작업에서
정기 TIC/BIS 변경 확인을 제외했다. 기존 live `unchanged` 결과, 미관측 natural revision/recovery 기록,
raw baseline, Gate C D-067 제한 범위 판정은 수정하지 않는다. 변경 감지 CLI와 기준본은 보존하며,
사용자가 나중에 다시 요청할 때만 단발 범위·목적을 새로 확인한다. 이는 TIC/BIS 서버 오류나 데이터 손상이
없음을 새로 검증한 결정이 아니며 Gate C 통과 범위를 확대하지 않는다.

## D-097 — 통합 제품 기획을 현재 요구사항·우선순위 기준으로 지정

2026-10-27. 사용자가 원초 기획과 이후 수정 기획을 하나의 유기적 기준으로 통합해 달라고 요청했다.
현재 `PROJECT_PLAN.md`를 제품 목표·지원/제외 범위·엔진 책임과 상태·데이터 품질 정책·통합 실행 순서의 단일 기준으로 정리하고,
원초 문서는 `PROJECT_PLAN_ORIGINAL_2026_10_24.md`에 보존한다. 세부 기능 계약과 과거 회차 보고서는 근거·설계 이력으로 남기며,
구현 상태와 검증 결과는 `IMPLEMENTATION_PLAN.md` 및 회차 evidence가 담당한다. `ROADMAP_2026_10_26.md`는 통합 기획의 요약이고,
이전 상세 로드맵은 snapshot으로 보존한다. 이 문서 통합 자체는 코드 기능의 구현 또는 Gate 통과를 뜻하지 않는다.

## D-098 — 공통 runtime engine 성능 계측을 composition 정리보다 앞에 둠

2026-10-27. 통합 구조 검토에서 일반 stage는 UTC 시작·종료 시각만 기록하고, 대용량 외 engine별 elapsed/phase timing과
성능 기준선은 없음을 확인했다. 고정 작업의 병목을 먼저 측정하고, network·raw/write·parse·quality·SQLite/export 등
가능한 하위시간과 입력 규모를 개인정보 없이 기록한다. 표본 수와 fixture/synthetic/live 구분을 함께 보고하며, p50/p95는
최소 20개 표본이 있을 때만 정식 표시한다. live 요청을 성능 표본 확보 목적으로 반복하지 않는다. 측정 결과가 나온 뒤에만
engine composition이나 저장·파싱 경로 최적화를 선택한다. 대용량 추정기는 이 범용 기준선을 대체하지 않는다.

## D-101 — 계측 후 provider 실행 조립을 공통 registry로 연결

2026-10-27. 성능 계측 PR #56에서 161개의 fixture/stored 표본과 privacy-safe 보고 경로를 먼저 구현했다.
이 표본은 live network나 production 저장 병목을 증명하지 않아 catalog cache, task 저장, raw write의 성능 최적화는 보류한다.
이후 사용자의 명시적 효율화 지시에 따라 통합 기획 §11 순서 8의 구조 정리를 진행한다. `EngineRegistry`가 saved
`(engine, version)` plan으로 공통 Orchestrator를 조립하고 재개하며 World Bank·BOJ·BLS·Census/Gate C의 transport와
response/parser/quality adapter는 유지한다. World Bank confirmation은 dispatcher가 실행 전 재검사하며 대용량 trial/production은
worker lock·checkpoint recovery 때문에 전용 runner로 남긴다. Registry 변경 자체를 성능 개선 측정으로 표현하지 않는다.

## D-099 — synthetic 평가 scaffold와 user-evidence gate를 분리

2026-10-27. 실제 사용 피드백 사례가 아직 없으므로, A/B corpus plumbing을 검증하기 위해 각 split에
두 건씩 synthetic 계약 사례를 추가한다. 사례는 author self-review이며 private user data나 live provider 결과를
포함한다고 주장하지 않는다. Validator는 provenance별 case count와 선언된 `reviewed_feedback_split_coverage`를
별도로 보고한다. 이 coverage는 feedback ID를 SQLite 로그와 대조 검증하지 않는다. `READY`는 구조·분리·hash
준비만 뜻하며 user-evidence 일반화 평가 완료를 뜻하지 않는다. validation/holdout은 set version 2와 계산된
SHA-256을 같이 갱신한다. 공개 저장소의 holdout hash는 secrecy나 anti-overfitting 보증이 아니다.

## D-100 — 성능 표본을 task history와 분리하고 측정 후에만 최적화

2026-10-27. 통합 기획 §11 순서 7을 구현하면서 UTC 시각을 elapsed 계산에 쓰지 않고 `perf_counter_ns()`를 사용한다.
공통 stage wall과 가능한 network/raw/parse/quality/SQLite/export 경계는 engine/version·상태·attempt·숫자 크기·evidence class·workload·code/environment와 함께 별도 `performance.sqlite`에 쓴다. 요청, 원본 값, task ID, credential, URL은 제외한다. 이 DB 분리는 export의 catalog read-only 계약을 유지하고 측정 기록을 task history와 분리한다. knowledge는 latency를 반환하고 cache hit/miss를 표본화한다. 보고기는 read-only이고 그룹당 표본이 20개 미만이면 p95를 미확정으로 표시한다. live API 요청은 측정용으로 만들지 않는다. 대용량 worker 기준은 그대로 별도 유지한다. 실제 병목이 드러날 때까지 EngineRegistry/composition 및 저장 경로 최적화를 다음 순서로 미룬다.

## D-103 — evidence-backed 평가 corpus와 assistant 초안을 별도 보관

2026-10-27. Iteration 28은 기존 JSON-per-split synthetic scaffold를 유지하면서 별도의 immutable `EvaluationCase` v1 JSONL corpus,
고정 candidate snapshot, evidence/file SHA-256 manifest와 split leakage audit을 추가한다. 고정 corpus는 목표 36개 중 9개이며
초기 target 유형의 `near_match`가 0개라 gate는 `blocked`로 둔다. 별도 27개 assistant-simulated draft는 모두
`independent_review_pending`이고 평가 corpus나 candidate catalog에 들어가지 않는다. hash 검증과 날짜 정규화 text audit은
독립 의미 검토를 대신하지 않는다. `validate-corpus`는 evidence integrity와 gate 상태만 보고하고 검색 엔진을 실행하거나 draft를
승격하지 않는다. 이 변경은 A의 일부 계약/fixture 준비이며 36-case gate, C/D 평가·승격 또는 사용자 관찰 통과를 뜻하지 않는다.
