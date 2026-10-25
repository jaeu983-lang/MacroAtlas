# Decision Log — 설계 변경·미해결 판단

## D-097 — 7개 live canary 실행 한도 (2026-10-25)

- **상태: LIVE ATTEMPTED; GATE U NOT PASSED.** 사용자가 요청한 1회 canary를 실행했다. FRED·Census·BLS v1·TIC·BoE의 7개 선택을 각각 한 번 시도했고 재시도는 0회였다.
- **근거와 설정:** FRED key/rate/third-party terms, Census API 일일 query budget, 무키 BLS v1, Treasury TIC file scope, BoE Database 재사용 조건은 [dataset contract](../connectors/DATASET_CONTRACTS.md)에 있다. 실행 시 process-only `MACROATLAS_NETWORK_ENABLED=true`를 사용했고 `.env`의 `false`는 유지했다. credential 값은 출력·기록하지 않았다.
- **결과:** FRED와 BoE contract validation 및 raw hash read-back 통과. TIC 두 경로는 HTTP 200 및 raw hash read-back 후 `dataset_contract_changed`. Census는 `LICENSE_SECURITY/NEEDS_REVIEW`, BLS 두 경로는 `TRANSIENT/FAILED_RETRYABLE`. 따라서 7/7 통과 조건을 만족하지 못했다. [live report](../testing/LIVE_CANARY_REPORT.md), [Iteration 30 report](ITERATION_30_REPORT.md), local-only [run JSON](../../../reports/iteration_30_live_canary_ffc0fe15c3b440a28c65b64aa9b5bb81.json) 참조.
- **다음 단계:** 이번 실행의 요청 예산은 소진됐고 retry는 금지됐다. Census 보안 분류·TIC schema 변화·BLS transient 원인을 먼저 검토한다. Gate U를 통과하기 전 Iteration 31로 넘어가지 않는다.

## D-096 — API·공식 파일 데이터셋 실행 계약 (2026-10-25)

- **상태: IMPLEMENTED; ITERATION 29 GATE T PASSED.** API와 비API를 모두 준비하라는 사용자 요청에 따라 API 4개/FRED·Census·BLS v1, 공식 CSV 3개/TIC·BoE의 명시적 dataset profile을 공통 실행·검증·보존 계약으로 연결했다. 기관별 규칙은 binding/validator에 둔다.
- **보존과 안전:** immutable profile version/hash와 전체 snapshot, raw/manifest/validation receipt를 배타 생성·hash read-back한다. CSV 변경은 원본을 남기고 needs_review, API 오류의 파일 자동 fallback은 없다. 결측/0·집계·각주와 원 날짜를 유지하고 변환/정규화 관측치를 발행하지 않는다. BLS2·실제 `.env`/키·repository live 요청은 제외했다.
- **검증:** 전체 offline 815 passed, 1 skipped, 0 failed (76.67초), 변경 Python Ruff 통과. 프로젝트 합성 artifact 7개 저장·read-back, 실제 HTTP는 차단했다. 일반 sandbox의 raw 하위폴더 생성 WinError 5는 같은 합성 스크립트에 한정된 승인 실행으로 완료했다. 전역 권한을 바꾸지 않았다.
- **미검증:** TIC·BoE API 상태는 여전히 unconfirmed, 인증 unknown, live 미검증. Table 3D는 확인된 January 2023 snapshot이지 최신 자료 보장이 아니다. 전체 기관 workflow·장시간 live·통계적 비교/가공·XLSX는 별도다. 다음 후보는 Iteration 30 IMF 상세 route/auth이며 시작하지 않았다. stage·commit·merge·publish하지 않았고 사람의 통합 검토가 남는다.
- [실행 계약](../connectors/DATASET_CONTRACTS.md), [회차 보고서](ITERATION_29_REPORT.md), [원시 결과](../../../reports/iteration_29_offline_777d9f70f81c4d58b501201deeabdb0f.json).

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
  분리한다. 필수 키 누락은 해당 경로만 중단한다. PROJECT_PLAN.md §2.1에 정책과
  후속 검수 기준을 추가했다. 이번에는 설정 로더·커넥터·02회차 기능을 구현하지 않았다.
  기관별 실제 인증 조건은 커넥터 구현 시 공식 문서로 확인해야 한다.

- **D-013 / ACCEPTED (사용자 요청 반영):** 14회차 최종 통합·검증 단계에 사용자
  설명서(Markdown)와 안내 PPT(PPTX)를 제작한다. 실행 방법·기관별 선택적 키 설정·
  수집 결과 확인을 실제 구현 기준으로 설명하고 대표 절차 재현 및 PPT 표시를 검수한다.
  PROJECT_PLAN.md §10.3/14.2와 IMPLEMENTATION_PLAN.md 14회차에 반영했다.
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
  예시는 docs/developer/planning/USER_WORKFLOW_REVIEW.md에 정리했다. 후속 사용자 요청으로 PROJECT_PLAN
  §4.0/7.3/8.3/10.1과 IMPLEMENTATION_PLAN의 관련 보완·검수 항목에 반영했다.
- **D-025 / PLANNED, 코드 적용 보류:** 01~03회차의 최소 계약·확인 이력·World Bank
  연결 보완과 예상 변경 파일/테스트 기준은 docs/developer/planning/WORKFLOW_ALIGNMENT_PLAN.md에 정리했다.
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
보완 02·03과 04회차는 진행하지 않았다. 상세는 docs/developer/history/ALIGNMENT_01_REPORT.md에 기록했다.

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
보완 02·03과 04회차는 진행하지 않았다. 상세는 docs/developer/history/ALIGNMENT_01_EXTENSION_REPORT.md 참조.

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
- 근거: `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`, `docs/developer/history/ITERATION_04_REPORT.md`, `tests/test_gate_a.py`. 초기 프로젝트 체크포인트는 root commit `2c4e11f`(70개 파일)로 기록했다. `.gitignore`가 SQLite DB, raw 자료, 생성된 live JSON을 제외한다. Product Owner 검토 후 병합한다.

## 05회차 기관·사이트 탐색 (2026-10-25)

- **D-053 / IMPLEMENTED:** 후보의 공식 도메인은 기존 기관 카탈로그의 문서 근거로 입력받고, 허용된 HTTPS URL의 hostname이 해당 도메인과 일치하거나 DNS label 경계가 있는 하위 도메인일 때만 공식 링크 후보로 기록한다. HTTP, 사용자정보, 비표준 포트와 query가 있는 URL은 저장 대상에서 제외한다. 충돌하는 전략 분류는 official_other로 낮춰 근거별 분류를 보존한다. 이 정책은 live 소유권/DNS/TLS 검증이 아니며 profile의 site_live_tested와 links_live_tested는 false로 둔다.
- **D-054 / IMPLEMENTED:** HTML navigation 및 XML sitemap을 독립 strategy로 구현하고 입력 문서의 fixture/official_docs evidence, 참조 URL, retrieval 시각, 전략 ID를 보존한다. 외부 링크는 raw URL 없이 hostname과 출처를 기록한다. 기관 프로필은 SQLite의 별도 append-only 테이블과 UPDATE/DELETE 방지 trigger에 저장하고 기존 user_version=2를 바꾸지 않는다. HTML/XML 원문은 보관하지 않는다.
- **검증:** BIS HTML 및 Treasury TIC XML의 합성 fixture, 외부 링크/도메인 경계/분류 충돌, 문서 크기·XML DTD 차단, 프로필 재열기·중복 저장·append-only 저장을 테스트했다. 전체 pytest 445개와 Ruff가 통과했다. 실제 기관 사이트 요청이나 저장소 DB 변경은 없었다.
- **후속 범위(당시 계획):** 이용 가이드의 수집·재사용은 06회차, 메타데이터 해석은 07회차, 후보 검색과 수집 연결/Gate B는 08회차에서 각각 별도 지시와 검토 후 진행한다.

## 06회차 이용 가이드·기관별 전략 — 2026-10-25

- **D-055 / IMPLEMENTED, 사람 검토 대기:** API 가이드·이용 정책·코드북·통계 해설을 명시 유형으로 구분하고, 출처 URL과 원문 bytes/hash, 추출 텍스트·경로, retrieval/expiry/version, fixture/official-docs 근거를 가이드 스냅샷으로 저장한다. 기관 후보의 공식 도메인 근거와 일치하는 URL만 허용한다. 기존 SQLite user_version=2를 유지하고 스냅샷은 append-only로 보존한다. 저장된 본문을 현재 공식 문서라고 추정하거나 이용 가능성을 승인하지 않는다.
- **D-056 / IMPLEMENTED, 사람 검토 대기:** 기관 전략은 명시 태그·우선순위와 정확한 가이드 snapshot ID에 고정한다. 동률 전략은 NEEDS_REVIEW, 만료 문서는 GUIDE_EXPIRED, 최신 원문이 참조 snapshot과 다른 경우 GUIDE_CHANGED, 만료 정보 없음은 경고를 반환한다. 변경 문서로의 재연결은 새 명시 규칙 기록으로만 수행하며 자동 대체하지 않는다.
- **검증:** IMF API_GUIDE 및 TIC USAGE_POLICY의 합성 문서 fixture, 공식 후보 도메인 경계, append-only 저장, 스냅샷 변경, 전략 재사용·기관 격리·만료·변경·모호성·만료 미상 검사를 추가했다. 전체 검증 결과는 docs/developer/history/ITERATION_06_REPORT.md에 기록한다. 라이브 페이지/API 확인은 하지 않았다.
- **후속 범위(06 완료 당시):** 메타데이터 탐색·정규화 07회차 및 데이터셋/시계열 검색·수집 연동 08회차는 이 회차와 별도 승인·검토 대상으로 남겼다. 이후 실행의 한정 예외와 결과는 D-057~D-060을 따른다.

## 07→08 연속 실행 한정 예외 — 2026-10-25

- **D-057 / APPROVED, 이번 작업에 적용 완료:** 사용자가 작업당 한 회차 규칙의 예외를 7회차 완료 전에 처리하도록 요청했다. 예외를 먼저 기록한 뒤 사용자가 07→08 순차 구현을 선택했다. 07 검증·보고를 먼저 마치고 08을 구현·검증·보고했으며 이 한 건의 예외는 사용 완료했다. 이후 작업에는 기본 한 회차 규칙을 적용한다.
- **순서·실패 조건:** 07회차 구현, 필수 검사 및 완료 보고를 마친 뒤에만 08회차를 시작한다. 완료 기준 미충족 또는 필수 검사 실패 시 08회차를 시작하지 않는다. 각 회차의 보고·검증 근거를 별도로 보존하며 Gate B를 생략하지 않는다.
- **범위·안전 조건:** 09회차 이후 또는 다른 회차 묶음에 자동 적용하지 않는다. 네트워크 설정, 데이터 무결성 및 기존 미커밋 유지·사람 검토 후 체크포인트/커밋 조건을 변경하지 않는다.

## 07회차 메타데이터 계약 — 2026-10-25

- **D-058 / IMPLEMENTED:** 온라인 발견과 입력 문서 파싱을 구분한다. 제공된 SDMX 구조, API 목록, 추출 코드북을 어댑터로 읽고 원문 bytes/hash·언어·추출 위치와 정규화 값을 분리 보존한다. 매핑 없는 코드와 충돌 값은 미상/경고로 남기며 분류 관계는 명시된 축·버전·근거만 사용한다. SQLite 원문/정규화 이력은 append-only로 저장하고 현재 문서 버전만 제한 조회한다.
- **07→08 선행조건(07 완료 시점):** 07 전용 테스트 10개, 전체 pytest 468개와 Ruff 통과 및 docs/developer/history/ITERATION_07_REPORT.md 작성을 마친 뒤 D-057에 따라 08회차를 순차 시작했다. 커밋·병합은 하지 않았으며 네트워크 설정은 변경하지 않았다.

## 08회차 검색·수집 연결 — 2026-10-25

- **D-059 / IMPLEMENTED:** 명시된 source concept/ID·국가·차원·기간·변형과 범위 관계로 후보를 검색하고 이름만으로 매핑하지 않는다. 제한된 자연어 어휘는 미상 조건을 질문으로 남긴다. 더 넓은 source scope 수용은 별도 확인 개정과 discovery_context로 보존하고 원정의·분류 불확실성을 덮어쓰지 않는다.
- **D-060 / IMPLEMENTED:** metadata/structure 스냅샷과 사용자의 확인을 연결하며 기존 WorkflowService/Orchestrator 직접 실행에도 discovery 근거 검사를 적용한다. 수집은 기존 World Bank 고정 경로 및 기관별 명시 스키마의 작은 CSV 경로에 한정한다. SourceAccess와 transport evidence kind를 보존하고 새 raw/manifest·원문 값·해시를 남긴다. CSV는 1 MiB/120기간/10국가로 제한하고 변환·범용 파일 파서는 구현하지 않는다.
- **검증:** 07은 전체 pytest 468개/Ruff 및 별도 보고 후 08을 시작했다. 08 최종 전체 pytest 499개/Ruff 통과. Gate B는 A형 구조/후보 및 C형 검색→확인→CSV 수집의 로컬 fixture 범위이며 live/전체 시나리오는 미검증이다. docs/developer/history/ITERATION_07_REPORT.md, docs/developer/history/ITERATION_08_REPORT.md 참조.
- **남은 확인:** 실제 기관의 메타데이터/파일 스키마·접근성·약관·이용 조건과 live transport 검증은 별도 확인 대상이다. 미커밋 유지 및 사람의 diff 검토 후 체크포인트/커밋 조건을 유지한다. 09회차는 시작하지 않았다.

## 08회차 검색 개념군 보완 — 2026-10-25

- **D-061 / IMPLEMENTED:** 사용자가 “미국 GDP” 질의에 명목·실질 GDP를 모두 포함하도록 요구했다. Concept ID 동일 필터를 주요 후보의 개념군/하위 유형 포함과 관련 지표 구분으로 수정했다. 검색 관계는 명시 근거·버전으로 관리하며 통계적 등가성이나 원통계 사실로 승격하지 않는다. 넓은 질의는 후보를 먼저 보여주고 수집 전 유형/후보를 확인한다. 상세 정책과 수용 기준은 docs/developer/planning/CONCEPT_SEARCH_REVISION_PLAN.md를 따른다.
- **이전 기록 해석:** D-059의 명시 Concept ID 사용은 이름만으로 매핑하지 않기 위한 안전장치였지만 상하위 ID까지 배제하는 구현은 넓은 질의의 재현율을 충족하지 못했다. 기존 499개 테스트 통과와 08 최초 보고를 이 보완의 검증으로 간주하지 않는다.
- **보완 검증:** 전체 pytest 515 passed in 45.20s, Ruff 통과. 주요/관련 후보 구분, 명목·실질 동일/상이 ID, 유형 미상·충돌, 정책 변경과 선택/요청 변경의 실행 차단을 fixture로 검증했다. 새 live 호출이나 실제 실질 GDP 수집은 하지 않았다. 결과·파일·한계는 docs/developer/history/CONCEPT_SEARCH_REVISION_REPORT.md에 기록한다. 미커밋 유지와 사람의 diff 검토 조건을 유지한다.
- **D-063 / IMPLEMENTED:** 후속 diff 리뷰에서 개념 미상 질의가 family_variant 주요 매치로 오인되어 관계 없는 후보까지 노출되는 것과, 다른 요청 조건으로 탈락한 관련 후보가 참고 결과에 남는 것을 확인했다. 개념 미상은 명확화 입력을 요구하고 주요 매치에서 제외한다. 관련 후보는 개념 이외의 명시 검색 조건도 통과해야 반환한다.
- **Gate B 재검증:** 회귀 사례를 추가/확장한 뒤 pytest 516 passed in 32.08s, Ruff 및 diff check가 통과했다. fixture/로컬 범위이며 live 호출은 없다. 사람의 diff 검토 및 미커밋 조건은 유지한다.

## 09→12 연속 실행 한정 예외 — 2026-10-25

- **D-062 / APPROVED·사용 완료, 09~12 완료:** 사용자가 12회차까지 완료하도록 지시해 이번 작업에서만 09→10→11→12를 순차 구현했다. 각 회차의 검사와 보고를 남기고 12회차 Gate D에서 멈췄다. 이번 예외는 소진되었고 13회차는 시작하지 않았다.
- **게이트:** Gate C(10회차) 실패 시 11·12회차를 시작하지 않는다. Gate D(12회차)가 최종 완료 기준이며, 실패 시 13회차를 시작하지 않는다.
- **범위·안전 조건:** 이번 예외는 09~12 범위에 한정한다. 네트워크 설정·원자료·데이터 무결성·사람의 diff 검토 후 체크포인트/커밋 조건을 변경하지 않으며 커밋·병합을 승인하지 않는다. 완료 후 미래 작업은 기본 한 회차 규칙으로 돌아간다.

## 09회차 파서·분할 계획 — 2026-10-25

- **D-064 / IMPLEMENTED, 사람 검토 대기:** CSV/TSV/TXT/ZIP/HTML/XLS/XLSX 입력은 명시된 SourceAccess 경로·열 이름·시트/멤버 선택에 한정한다. 파일 크기, ZIP 구성원·확장량·압축 비율, 표 행·열·셀 수를 제한하고 ZIP을 디스크에 풀지 않는다. XLSX 수식은 계산하지 않으며 외부 링크·매크로·오류 셀·중복 행 좌표·잘못된 공유문자열을 거부한다. 병합 셀이나 모호한 HTML 표도 거부한다. 원본과 parse selection을 manifest에 보존한다.
- **대량 요청:** `build_collection_plan`은 샘플/전체를 명시적으로 선택하게 하고 시리즈·국가·기간 단위로 요청을 나누며 요청·관측치·예상 byte/시간 예산을 적용한다. 모드 미선택이면 단위를 만들지 않는다. 실행은 하지 않으며 모든 계획은 명시 확인이 필요하다. 비용 추정치가 없는 경우 `None` 및 경고를 보존한다.
- **검증:** 전체 pytest 559 passed in 33.24s, Ruff 및 `git diff --check` 통과. 전부 로컬 fixture/mock 범위이며 live API/공식 문서 확인은 없다. `xlrd`는 의존성으로 선언했으나 오프라인 venv에 설치되지 않아 실제 XLS 파일 검증은 미수행이고 route는 unsupported로 fail-closed 한다. 결과·상세 한계는 `docs/developer/history/ITERATION_09_REPORT.md`.
- **진행:** Gate C 검증을 위한 10회차를 시작할 수 있다. Gate C 통과 전에는 11회차를 시작하지 않는다.

## 10회차 Gate C — 오류 복구·품질·대량 단위 이력 — 2026-10-25

- **D-065 / IMPLEMENTED:** 429·408·5xx와 시간 초과/연결 끊김은 `TRANSIENT`로 분류하고 즉시 반복 요청하지 않는다. 실행 이력에 bounded exponential backoff와 Retry-After를 저장하고 due 전 재개를 거부한다. 시도 한도는 workflow stage의 고정 상한을 사용한다. 401/403은 `AUTH_ACCESS` 검토로, redirect는 보안 검토로, 404/410은 경로 변경 terminal 실패로 멈춘다. Retry-After가 지원 대기 상한을 넘으면 자동 재시도를 예약하지 않고 검토로 보낸다.
- **D-066 / IMPLEMENTED:** bulk 계획은 확인된 workflow fingerprint와 기관/시리즈/국가/주기/기간 범위가 일치할 때만 durable per-unit ledger로 초기화한다. 요청·byte·관측치·시간 사용량, artifact 경로, attempt와 retry-not-before를 기록한다. 성공한 단위는 재개 시 건너뛰고 retryable 또는 미실행 단위만 대기열에 남긴다. 검토/terminal 오류 또는 자원 초과는 남은 단위를 중지한다. Callback만 단위 수집을 수행하며 저장소는 외부 요청을 만들지 않는다.
- **Gate C 검증:** 429·Retry-After 상한/재개 대기, 403, content type/schema drift, conceptual ambiguity, 현재 metadata revision 변경, raw 보존, link expiry/access/condition mismatch, 대량 단위 성공·재시도·미실행·resource cap을 fixture/mock으로 검증했다. 전체 pytest 568 passed in 34.83s, Ruff 및 `git diff --check` 통과. 상세는 `docs/developer/history/ITERATION_10_REPORT.md`와 `docs/developer/testing/REFERENCE_SCENARIOS.md`.
- **범위 한계:** 외부 live API/사이트/링크는 호출하지 않았다. metadata 개정 중단은 metadata snapshot 변경을 재현했으며 source 값의 실제 revised vintage를 확인한 것은 아니다. callback의 transport 구현은 callback이 전달받은 남은 time/byte budget을 지켜야 한다.
- **진행:** Gate C 통과로 11회차를 시작할 수 있다. Gate D 전에는 13회차를 시작하지 않는다.

## 11회차 사용자 피드백·지식 입력 — 2026-10-25

- **D-067 / IMPLEMENTED:** feedback의 원문은 immutable `gate_a_records`에 두고 edit/review/cancel은 별도 append-only event로 남긴다. revision 충돌을 거부하고 task/stage/incident error와 기관·개념 범위 인덱스로 조회한다. 기존 task JSON, observations와 DB schema version을 변경하지 않는다.
- **D-068 / IMPLEMENTED:** `KnowledgeStore`는 `user_statement`, `official_evidence`, `inference`를 분리하고 기관/dataset/concept/classification-axis, source/record version, UTC 유효 범위, validation state, evidence refs, supersedes/cancel 관계를 보존한다. 짧은 등록은 추가 입력과 해당 scope/version 조회만 수행한다. inference를 verified/accepted source fact로 표시하지 않는다.
- **검증:** 신규 feedback/knowledge 및 Gate A 집중 회귀와 전체 573개 pytest, Ruff, `git diff --check` 통과. legacy feedback idempotency/read path, task/error 격리, 편집/취소 및 대체 이력을 로컬 SQLite로 검증했다. 네트워크/실제 기관 문서 검증은 없다.
- **제한:** 제품 일반 CLI 및 ChatGPT 자동 동기화는 없다. 공식 근거 참조의 실시간 검증, bounded 지식 현재 색인·검색·캐시 및 규모별 성능은 12회차에서 다룬다. 상세는 `docs/developer/history/ITERATION_11_REPORT.md`.
- **진행 당시 기록:** 11회차 완료 후 Gate D 검증을 위해 12회차를 시작할 수 있었다. 이후 결과는 아래 12회차 결정을 따른다.

## 12회차 Gate D — 제한 지식 재사용·색인·개념 검색 (2026-10-25)

- **D-069 / IMPLEMENTED:** append-only 원문/이벤트와 별도인 `knowledge_current` 범위 투영, 세대 번호, 페이지 단위 명시 색인 갱신, 예산 내 조회와 제한 캐시를 구현했다. 쿼리는 색인/근거를 하나의 SQLite read snapshot에서 읽고, 캐시 키는 범위·시점·source version·override·concept policy fingerprint·세대를 포함한다. 외부 저장소 인스턴스의 변경도 세대 검사로 stale cache hit를 막는다. refresh/예산 초과/상충 미검토에서는 결과 완전성을 낮추고 재사용을 보류한다.
- **D-070 / IMPLEMENTED:** 명시적으로 전달된 versioned `ConceptSearchPolicy`의 `subtype` 관계만 최대 깊이 4·총 후보 개념 ID 16개 이내로 탐색한다. `related` 링크는 제외하고 자식 concept 질의는 형제/상위 확장하지 않는다. subtype 검색 후보는 경로·근거·깊이를 보존하되 항상 자동 재사용 불가로 반환한다. 이 관계는 통계적 동등성이나 대체 가능성 근거가 아니다. 정책 fingerprint는 캐시 키에 포함된다.
- **검증:** 전체 pytest 578개, Ruff, `git diff --check` 통과. 100/1,000/10,000 합성 SQLite 레코드의 application-cache-cleared/warm 조회 p50·p95, Python allocation peak, 읽은 행·근거 byte, 범위/개념 검색 정합성 및 broad budget 종료를 측정했다. snapshot을 유지하는 read transaction 도중 별도 writer가 시작하는 결정적 동시성 회귀도 통과했다. GDP 명목·실질 subtype 검색 결과는 두 후보 모두 반환하되 자동 재사용하지 않았다. 세부 결과는 `docs/developer/history/ITERATION_12_REPORT.md`와 `reports/iteration_12_benchmark.json`에 있다.
- **D-071 / OPEN:** synthetic single-host benchmark는 SQLite native memory/process RSS, 현실 기관 데이터 분포, 다중 reader/writer 경합과 운영 SLA를 검증하지 않는다. 운영 환경 목표를 주장하기 전에 대표 workload의 동시성·RSS 측정과 product integration 검수가 필요하다.
- **제한/무결성:** 실제 기관 URL/API나 원문 근거를 조회하지 않았다. 사용자 지침은 해당 기관에서 확인이 필요한 제안이고 inference는 verified/accepted 사실로 승격할 수 없다. 공통 규칙 자동 생성·기관 간 배포·제품 CLI/ChatGPT 동기화는 구현하지 않았다. 커밋·스테이징·병합은 하지 않았으며 사람 diff 검토를 기다린다.

### 새 결정 기록 템플릿

- **ID/일시:**
- **문제/선택지:**
- **채택안 및 근거:**
- **영향 받는 모듈·회차:**
- **보안·데이터 정확성 영향:**
- **승인자/검증 방법:**
- **상태:** Proposed / Approved / Rejected / Superseded

## 13→14 연속 실행 한정 예외 — D-072 (2026-10-25)

- **상태: APPROVED·사용 완료.** 사용자가 13회차와 14회차 시작을 명시 지시했다. 13회차 구현과 Gate 13 검사·보고를 완료한 뒤 14회차 Gate E를 순차 완료했다.
- **결과:** `docs/developer/history/ITERATION_13_REPORT.md`와 `docs/developer/history/ITERATION_14_REPORT.md` 참조. 예외는 소진됐으며 향후 작업은 한 회차 규칙으로 돌아간다.
- **안전 조건:** 해당 작업에서 커밋·스테이징·체크포인트·main 병합·배포는 수행하지 않았다.

## API 우선 출처 상태와 검증 범위 — D-073 (2026-10-25)

- **상태: APPROVED, IMPLEMENTED.** 사용자는 모든 출처의 API 경로를 우선 검토하고, 공식 API 문서가 확인된 기관과 API 여부가 확인되지 않은 기관을 분리하도록 요청했다.
- **채택:** API 문서 존재 여부(`documented`/`unconfirmed`/`not_offered`), 우선 경로, 인증, 어댑터 상태, fixture 범위, 실 API 검증 범위를 별도 필드로 둔다. 공식 API 문서를 찾지 못했으면 `unconfirmed`로 두며 부재로 단정하지 않는다. API가 문서화된 출처는 API 우선, 미확인 출처는 API 문서 추가 조사 우선이다.
- **영향:** A–H의 14개 기관을 실행 가능한 `discovery.source_registry`와 `docs/operator/reference/INSTITUTION_CATALOG.md`에 등록한다. 기관별 HTTP 어댑터 추가는 이후 한 회차씩 진행한다.
- **근거·검증:** 2026-10-25 공식 API/통계 문서 조사와 `docs/developer/history/ITERATION_15_REPORT.md`. 로컬 fixture/mock 검증과 실 API 호출 결과를 분리한다.
- **데이터·보안:** 실제 키는 레지스트리에 넣지 않고 환경변수 이름만 기록한다. 공식 출처 HTTPS 링크만 허용한다. 미확인 endpoint를 자동 호출하지 않는다.

## 로컬 비밀 설정 및 BEA·e-Stat 어댑터 — D-074 (2026-10-25)

- **상태: APPROVED, IMPLEMENTED, Gate G 통과.** 사용자는 BEA와 e-Stat API 키를 직접 입력할 수 있도록 설정 로더와 두 API 클라이언트 구현을 요청했다.
- **채택:** 저장소 루트의 무시 대상 `.env`와 프로세스 환경변수에서 지원 설정만 읽는다. 프로세스 환경변수가 파일 값보다 우선한다. `Settings` repr 및 예외/응답/요청 이력에서 키 값을 노출하지 않는다. BEA와 e-Stat은 각각 공식 문서의 고정 HTTPS API 경로로 GET JSON을 호출하는 독립 클라이언트로 추가한다.
- **제약:** 네트워크 기본값은 off로 유지한다. 실제 키는 사용자만 `.env`에 입력한다. live 연결·인증 검증과 workflow/UI 통합은 이 회차 범위가 아니다. mocked 응답 결과를 live 근거로 표시하지 않는다.
- **공식 근거:** BEA API URI, UserID, method/ResultFormat은 [BEA 공식 문서](https://apps.bea.gov/API/docs/index.htm)와 [API 안내서](https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf)를 따른다. e-Stat v3.0 경로와 JSON 메서드, Application ID는 [API 사양](https://www.e-stat.go.jp/api/en/api-info/api-spec) 및 [이용 가이드](https://www.e-stat.go.jp/api/api/api/index.php/en/api-info/api-guide)를 따른다.
- **검증:** `.env` parsing/precedence, 제한·권한 안전, mock HTTP 경로와 에러, 비밀값 비노출을 deterministic 테스트로 검사한다. 기관 실 호출은 하지 않는다.
- **결과:** 전체 pytest 625 passed/1 skipped, Ruff 및 `git diff --check` 통과. symlink 생성이 제한된 Windows 환경에서만 해당 보호 테스트를 skip했다. 상세는 `docs/developer/history/ITERATION_16_REPORT.md`.

## 성능 기준선, 기관별 보정 및 다국어 API 정책 — D-075 (2026-10-25)

- **상태: APPROVED FOR PLAN; 구현 항목은 후속 회차.** 사용자는 모든 기관을 API 우선으로 분류하고, 가능한 한 공통 코드 간소화 후 기관별로 실제 데이터를 무작위 선택·수집·저장·재조회하며 장기간 오류를 확인하도록 요청했다.
- **채택:** 사용자가 말한 fine-tune은 모델 가중치 학습이 아니라 기관별 source adapter와 공통 파이프라인의 실데이터 보정/장기 검증으로 정의한다. 자연어 agent prompt 평가·LLM 비용 계측은 저장소 Python 수집/처리 엔진과 구분한다.
- **문서 구조:** 공통 운영/conformance/benchmark 정책은 `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`에 둔다. 각 기관 문서는 실제 endpoint, 인증, 식별자, paging, revision, 언어, 이용 제한과 검증된 예외만 기록한다. 기관별 문서에 공통 정책을 중복 복사하지 않는다.
- **기관 상태:** 최초 카탈로그 21개와 A–H 실행 레지스트리 14개를 구분한다. 현재 상태는 API 문서 확인 9, 미확인 5, 공식적 API 부재 확인 0이며 7개는 레지스트리 미포함이다. 공식 근거 없이 `unconfirmed`를 API 부재로 바꾸지 않는다.
- **언어:** 영어 API/metadata 우선. 영어 dataset/metadata 필드가 실제로 없을 때 source original Japanese/Chinese를 보완하며, 원문 → English canonical metadata → 한국어 presentation 순서로 유지한다. API/network 오류 또는 조건상 empty observations를 언어판 부재로 오해하지 않는다. IDs, code, numeric observations, unit, dates와 vintage는 번역하지 않는다.
- **테스트:** 완전 무작위와 coverage-stratified sampling을 분리하고 seed/모집단 hash/dataset lineage/sample IDs를 저장한다. 같은 seed replay는 전후 비교용이고 새 seed는 탐색용이다. Live test는 adapter+official docs+request budget 준비 이후에만 기관별 canary→2h→6h+로 확대한다. Offline mock soak는 별도 실행하며 실제 API 오류를 발생시키지 않는다.
- **데이터·보안:** 원응답/hash, source ID/URL, retrieved-at, 언어, unit/frequency/dimensions/revision을 보존한다. `.env` 비밀값은 출력/결과에 넣지 않는다. 요청량·concurrency·bytes·time budget 및 safe stop을 기관별 공식 제한에 맞춘다.
- **근거/검증:** `docs/developer/performance/BASELINE_REPORT.md`, `docs/developer/performance/BOTTLENECK_ANALYSIS.md`, `docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md`, `docs/developer/history/ITERATION_17_REPORT.md`. 로컬 suite 반복과 mock만 수행했으며 live API와 end-to-end 기관별 장기 수집은 미실행이다.

## 사람 관점 다중 질문·답변 테스트 산출물 — D-076 (2026-10-25)

- **상태: APPROVED, IMPLEMENTED AS MANUAL SCRIPT.** 사용자는 테스트 파일이 단순 checklist가 아니라 여러 사례의 실제 자연어 질문→에이전트 응답→사용자 답변→후속 응답을 보여주는 것이라고 구체화했다.
- **채택:** `docs/user/examples/HUMAN_CONVERSATION_TESTS.md`에 여러 turn의 한국어 예시, 기대 동작, 사람 판정란을 둔다. 현재 저장소에는 실제 대화 UI/LLM이 없으므로 예시는 MacroAtlas가 이미 생성한 출력으로 표시하지 않고, 연결된 에이전트에서 사람이 재생할 목표 대화로 표시한다.
- **범위:** 누락 정보, 명목/실질 ambiguity, API 미확인 기관, BEA/e-Stat credential, 영어 우선/일본어·중국어 metadata, missing vs zero, 429 및 randomized soak 준비 사례를 포함한다.
- **보안/정확성:** 대화에 API 키 입력을 요청하지 않는다. fixture/mock 결과와 live 수집을 구분하며, 데이터 코드·관측값·단위를 번역하거나 결측을 0으로 바꾸지 않는다.

## 21개 출처 정합화와 기관별 API 제공자 구분 — D-077 (2026-10-25)

- **상태: APPROVED, ITERATION 19 SCOPE.** 사용자는 21개 카탈로그 항목과 14개 실행 레지스트리를 맞추고, API 상태를 공식 문서로 조사한 뒤 기관별 adapter와 seeded data validation을 순차 실행하도록 요청했다.
- **순서:** Iteration 19에서 전체 21개 공식 API 상태/인증/제공자 조사를 완료한다. 공통 코드 간소화는 Iteration 20에서 측정·복구 회귀 근거로 수행한다. 그 후 Iteration 21+에서 source adapter와 fixture를 한 기관씩 추가한다. 기관별 Gate 뒤 offline soak, 준비된 source만 승인된 live canary→2h→6h+로 진행한다.
- **상태 모델:** API `documented`, `unconfirmed`, `not_offered`는 공식 문서 근거로만 정한다. 이번 조사에서 API 미제공을 명시한 근거를 찾지 못한 항목은 `unconfirmed`에 둔다. API 제공자와 통계 원 기관이 다르면 `api_provider`에 따로 기록한다. 아직 A–H 수용 시나리오가 없는 7개 source는 잘못된 시나리오에 끼워 넣지 않고 `scenario_ids=()`로 catalog 전용 소속을 표시한다.
- **조사 결과:** 21개 profile 중 documented 15, unconfirmed 6, not_offered 0. 공식 문서 조사는 live endpoint·인증 성공·adapter 구현을 증명하지 않는다. 세부 표와 출처는 `docs/operator/reference/INSTITUTION_API_AUDIT.md`.
- **보안·데이터:** API 키 값은 저장하지 않고 필요 시 환경 변수 이름만 등록한다. 요청/원자료/live 테스트는 이 회차에서 수행하지 않는다. 현재 사용자가 입력한 실제 `.env` 값은 읽지 않는다.
- **후속 조정:** 기관 adapter를 모두 기다리는 순차 계획은 D-078에서 Track M/C 병렬 workstream 및 기관별 live 합류 게이트로 조정했다.

## 운영·유지보수와 기관 확장 병렬 workstream — D-078 (2026-10-25)

- **상태: APPROVED, ITERATION 20.** 사용자는 전 기관 live 시험에 앞서 기존 공통 코드의 효율을 다시 확인하고, 공통 엔진 유지보수와 기관별 API/adapter 추가를 하나의 순차 대기열 대신 구분된 작업 묶음으로 운영하기를 원했다.
- **채택:** Track M은 공통 엔진의 reliability, data integrity, security, telemetry, recovery, performance를 담당한다. Track C는 기관 문서, auth, source-specific adapter/fixture 및 coverage를 담당한다. 서로 독립된 offline 작업은 병렬 진행할 수 있다.
- **합류 조건:** live canary는 공통 platform gate와 기관별 source gate가 둘 다 통과한 기관에서만 실행한다. 준비된 기관은 독립적으로 시작할 수 있지만 같은 API provider/credential의 쿼터와 동시성 예산을 공유한다. API `unconfirmed`는 공식 경로 조사 전 추정 호출하지 않는다.
- **기존 개선 기능:** `ImprovementAnalyzer`는 read-only 개선 후보 분석기이며 코드를 자동 변경하거나 성능을 자동 최적화하지 않는다.
- **성능 근거:** World Bank 고정 fixture를 30회씩 두 번 재측정했다. 내부 반복은 서로 근접했으나 기존 Gate I와 값이 크게 달라 환경 차이를 배제할 수 없었다. transaction/connection 코드는 측정으로 개선 가능성이 분리될 때까지 수정하지 않는다. 결과는 `reports/iteration_20_baseline_recheck.json` 및 `docs/developer/history/ITERATION_20_REPORT.md`.
- **보안·데이터:** 이 회차 live API 요청과 사용자 `.env` 접근은 0회다. 원자료·누락/0·저장 경계는 기존 테스트로 유지한다.

## 다기관 통계 후보 비교와 기본 XLSX 산출물 — D-079 (2026-10-25)

- **상태: APPROVED FOR PLAN; IMPLEMENTATION NOT APPROVED.** 사용자는 broad indicator 요청을 여러 기관에서 탐색하고, 기관별 통계 특성을 비교해 원하는 계열을 찾으며, 기본 결과를 CSV가 아닌 plain XLSX로 제공하도록 기획을 요청했다.
- **요구 정책:** 후보 메타데이터/링크만 제공하는 결과도 유효하다. 데이터 수집은 선택·조건 확인 후 준비된 API/adapter 경로에서만 한다. 기관과 API provider를 분리하고 정의·단위·빈도·범위·개정·접근 상태 차이를 후보별로 보여준다.
- **기본 workbook 제안:** `Data`와 `Definitions` 두 sheet를 사용하며 Excel 기본 cell formatting을 유지한다. raw response/manifest는 별도 보존한다. 임의 unit/date/frequency transformation과 missing-to-zero 변환은 하지 않는다.
- **period mismatch 제안:** 서로 다른 time series를 자동으로 align/join/resample/interpolate하지 않는다. source-native period를 별도 보존하거나 side-by-side 비교가 필요하면 사용자에게 alignment 정책을 묻는다. `Definitions`는 정의와 차이를 기록하며 관측치 값을 대신하는 sheet가 아니다.
- **기획 문서:** `docs/developer/planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md`에 user flow, candidate comparison axes, XLSX contract, mismatch policy, staged gates, tests, implementation gaps를 기록했다.
- **현재 경계:** output contract와 XLSX input parser는 XLSX exporter 구현을 뜻하지 않는다. fixed World Bank workflow는 현재 raw JSON만 허용한다. 기관별 API docs/adapter/fixture/live는 독립 상태다.
- **데이터·보안:** `.env` 값은 읽지 않았다. 이 계획 작업에서 code/test/credential/live API를 바꾸거나 호출하지 않았다. 실제 구현은 이후 한 iteration씩 별도 지시와 검토를 받는다.


## 운영 기준·에이전트 구조 재정리 — D-080 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION; NO CODE/AUTOMATION CHANGE.** 사용자는 공통 데이터 엔진은 유지하되 주간 오류·사람 피드백 개선, 격주 메모리 최적화, 수요에 따른 기관 추가를 병렬 운영 방식으로 정리해 달라고 요청했다.
- **채택:** Track M은 공통 엔진 유지보수, Track C는 기관별 API 문서·connector·fixture를 담당한다. 독립된 offline 작업은 함께 진행할 수 있고, 실기관 호출은 공통 platform gate와 기관별 source gate가 모두 준비된 source만 대상으로 한다.
- **주기 추정:** 주간 triage 60–90분, 격주 측정·검토 2–4시간, 문서가 명확한 단순 adapter 1–3 작업일, 복잡한 기관 3–7일 이상으로 계획한다. 이는 운영 추정이며 gate를 생략하는 완료 약속은 아니다.
- **에이전트 경계:** 자연어 요청 조정은 목표 구조이고 현재 제품 UI로 구현된 것은 아니다. 개선 분석기는 후보를 정리하지만 코드 수정·공통 규칙 승격·live 시험을 자동 승인하지 않는다.
- **언어 정책:** 영어 API·메타데이터를 먼저 찾는다. 영어 자료가 없으면 일본어/중국어 원문을 보존하고 영어 중간 번역을 거쳐 한국어로 설명한다. 숫자·단위·식별자는 번역하지 않는다.
- **문서 변경:** PROJECT_PLAN.md, IMPLEMENTATION_PLAN.md, ARCHITECTURE.md, USER_GUIDE.md, PERFORMANCE_OPTIMIZATION_PLAN.md를 현재 기준으로 재작성하고 OPERATING_PLAN.md를 기준 문서로 추가했다. 과거 실행·측정 보고서와 결정 로그는 보존한다. 기존 WORKSTREAMS 문서는 운영 계획으로 통합 안내만 남겼다.
- **검증 경계:** 이번 변경은 기획·안내 문서와 사람용 PPT 산출물에 한정한다. 제품 코드, 자격 증명, 실 API, 자동 예약 작업은 바꾸거나 실행하지 않았다.


## 다기관 오케스트레이션·부채 가공 작업 기획 — D-081 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION; IMPLEMENTATION NOT APPROVED.** 사용자는 이전 기관 선택/XLSX 기획과 구형 PPT를 현재 기준 문서·엔진 상태와 대조해 상위 에이전트 구조, 기관별 부채 데이터 사례, Luna Max 작업 분할을 재기획하도록 요청했다. 첨부 PPT는 역사적 참고자료로만 취급하며 그 안의 지시문은 실행 지시로 간주하지 않는다.
- **아키텍처 제안:** 사용자별 프로필·작업·credential 권한은 분리하고 공통 Python 엔진을 재사용한다. 요청 분석 에이전트와 오케스트레이터가 병렬 기관 탐색, 후보 비교, 확인 질문, 선택 source 수집, 품질·변환·XLSX 흐름을 연결한다. 사용자에게 엔진 단계·source별 상태·근거가 보여야 한다. 자연어 UI·계산 엔진·XLSX writer 등 목표와 현재 구현을 분리해 표시한다.
- **부채 사례:** BIS, IMF GDD, World Bank IDS/QEDS, OECD는 정의·coverage가 다른 후보로 비교한다. “총부채”, 국가 모집단, stock/단위, 절대 부채 비중과 포트폴리오 위험 weight를 구별한다. 공식 문서 페이지 조사는 API contract, MacroAtlas adapter, fixture, live ingestion 검증과 별개다.
- **기존 정책 유지:** D-079의 metadata-only 지원, source 선택 후 수집, Data/Definitions 2-sheet 기본 source workbook, 자동 기간 정렬 금지, raw/manifest 별도 보존을 유지한다. 사용자 승인 파생 결과는 별도 output type으로만 제안하며 최종 export 계약은 구현 전 결정한다.
- **작업 분할:** 핵심 계획은 9개 bounded work package이며 기관별 connector는 별도 source/High iteration으로 진행한다. AGENTS.md에 따라 한 code task는 한 numbered High iteration이고 gate 실패 시 중단한다. 9개 묶음은 한 번에 구현하라는 허가가 아니다.
- **문서:** 다기관 계획과 아키텍처 문서를 갱신하고 구현/제품 문서에서 연결한다.
- **이번 범위:** 문서 작성만 수행. 코드·credential·fixture·live API·성능 benchmark는 변경/실행하지 않았다. 향후 구현, API key 사용, live test는 별도 iteration/source gate와 review가 필요하다.


## 방법론 판정·시계열 가공·문서 대상 분리 보강 — D-082 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION; IMPLEMENTATION NOT APPROVED.** 사용자는 시계열 가공에는 원천 methodology를 먼저 확인하는 별도 엔진이 필요하며, 날짜가 맞지 않을 때 임의 변환하지 말고 월말 정렬 feasibility를 검토해 불가 이유와 대체 XLSX layout을 제안하도록 요청했다.
- **엔진 분리:** 방법론·비교가능성 엔진은 공식 정의·측정 시점·stock/flow·주기·단위·coverage 근거와 정렬 가능/불가/미확인 판정을 내린다. 실제 key/date normalization, join/aggregation, weight 등 값 변환은 별도 deterministic transformation engine이 사용자 승인된 규칙만 실행한다. 방법론 엔진의 명칭은 작업명이며 최종 이름은 보류한다.
- **월말 규칙:** 월별 평균·유량·월말 stock·분기말 stock·일별 관측을 구분한다. 방법론과 관측 의미가 월말 정렬을 지지할 때만 제안한다. 일별 값의 월말/마지막 영업일/이전 가용치 및 missing fallback은 정책으로 고정한다. 분기/연간 자료를 월별로 복제·보간하거나 미확인 series를 합치지 않는다.
- **불일치 출력:** 정렬 불가/미확인은 source-native long output, 계열별 별도 sheet, 별도 workbook, 계산 보류를 reason/evidence와 함께 제안한다. 기존 D-079의 기본 Data/Definitions 두 시트는 유지하며 추가 sheet는 사용자 승인으로 output spec을 바꾼 경우에만 사용한다.
- **문서 독자:** 개발 문서, 운영자 문서, 실제 사용자 안내를 분리하는 후속 문서 전환을 계획에 추가했다. 역사 보고서와 결정/측정 로그는 보존하며 link-safe 전환을 전제로 한다.
- **PPT:** 모든 engine/gate·계약·명칭을 확정한 뒤 독자별 사용자/운영자 deck과 developer engine deck으로 재작성한다. 이번에는 PPT 파일을 수정하지 않는다.
- **작업 분할:** 방법론 gate를 별도 package로 두어 핵심 계획을 10개 bounded work package로 조정했다. 기관 connector는 source별 별도 iteration으로 진행하며 AGENTS.md의 단일 High iteration 규칙은 유지한다.
- **이번 범위:** 기획/구조 문서만 갱신. 변환 코드, documentation file moves, tests, API keys, live API, benchmark는 실행/변경하지 않았다. 이후 구현 및 구조 이동은 별도 task/gate와 review 대상이다.



## 방법론 엔진·문서 독자별 분리 반영 — D-083 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION; IMPLEMENTATION NOT APPROVED.** 사용자는 원천 methodology에 근거한 시계열 정렬 feasibility, 별도 변환 엔진, 개발/실사용 문서 구분, engine별 상세 PPT를 요청했다.
- **엔진 설계:** 방법론·비교가능성 엔진은 임시 명칭으로만 사용한다. 공식 methodology와 metadata를 근거로 stock/flow, period semantics, valuation, 주기·coverage와 정렬 가능/불가/미확인을 판정한다. 변환 엔진은 사용자가 승인한 날짜 정책·집계·join·가중치만 deterministic하게 실행한다. 월말 정렬 근거가 부족하면 값을 만들지 않고 이유와 원 주기/별도 sheet/별도 workbook/계산 보류 선택지를 제안한다.
- **문서 분리:** docs/README.md를 독자별 시작점으로 두고 DEVELOPMENT_GUIDE.md, OPERATOR_RUNBOOK.md, USER_GUIDE.md를 개발자·운영자·실제 사용자 대상으로 분리했다. README와 PROJECT_PLAN에서 안내하고 기존 INSTALLATION.md는 초기 템플릿임을 표시한다. 링크 호환성을 위해 flat 경로를 유지하며 물리적 폴더 이동은 별도 link audit 후 검토한다.
- **PPT:** 현재 deck은 수정하지 않는다. 계획·엔진 경계·명칭이 안정된 뒤 사용자/운영자용과 개발자용 deck을 각각 만들며, 개발자 deck은 engine별 입력·출력·계약·evidence·실패/복구·구현상태를 보여준다.
- **이번 범위:** 계획·문서 안내만 수정했다. 코드, raw data, credentials, API/live, tests, benchmark는 실행/변경하지 않았다. PPT는 사용자의 후속 순서에 따라 보류한다.

## 18개 기관 접근 경로 분류와 API 우선 구축 순서 — D-084 (2026-10-25)

- **상태: APPROVED FOR PLAN; IMPLEMENTATION AND LIVE TESTING NOT APPROVED.** 사용자는 공식 API가 있는 기관과 API 경로가 아직 확인되지 않은 기관, 공식 파일 경로를 구분하고, 18개 후보 모두에 기관별 구축 접근을 계획에 반영하도록 요청했다.
- **범위:** 21개 카탈로그 중 World Bank(INT-04), BEA(US-04), e-Stat(JP-03) 기준 프로필을 제외한 18개 프로필을 접근 경로표에 반영했다. Federal Reserve Board(US-01)와 St. Louis Fed FRED/ALFRED(US-02)는 원 기관과 API 제공자 관계를 보존하며, 중복 series를 독립 데이터원으로 세지 않는다.
- **경로 분류:** API 문서 확인 후보 12개(IMF, BIS, ECB, Eurostat, OECD, Board via FRED, FRED/ALFRED, BLS, Census, BOJ, Bundesbank, INSEE), 공식 파일 배포 경로 후보 3개(Treasury TIC, Bank of England, Japan MOF), 접근 방식 추가조사 gate 3개(PBOC, SAFE, China NBS)로 기획한다. 이 경로 분류는 API 감사 상태나 MacroAtlas 구현 완료를 대체하지 않는다.
- **상태 보존:** `docs/operator/reference/INSTITUTION_API_AUDIT.md`의 전체 21개 집계(문서 확인 15, 미확인 6, 공식 미제공 확인 0)와 각 profile의 adapter/fixture/live 상태를 바꾸지 않는다. API `unconfirmed`는 API 부재가 아니며, file fallback은 정확한 통계표의 API 경로가 없거나 부적합함을 확인한 뒤에 검토한다.
- **순서:** 사용자 부채 사례로 BIS를 첫 source task로 둔다. SDMX 기관(IMF, ECB, Eurostat, OECD, Bundesbank, INSEE)은 공통 전송 코드를 재사용하되 개별 profile·fixture·의미 검증을 유지한다. 그 다음 개별 REST, 표별 공식 파일 파서, 중국 기관 접근조사 gate를 진행한다. 독립 offline 조사는 병렬 가능하지만 단일 High iteration과 source gate, bounded live 승인 원칙은 유지한다.
- **기획 문서:** `docs/developer/planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md`의 6.1절에 18개 profile별 API/file/조사 경로, 현재 증거 경계 및 순서를 기록했다.
- **검증·보안:** 기존 공식 문서 조사를 정리하고 링크를 명시했다. 이 결정에서 API 키를 읽거나 live API 요청, adapter 구현, fixture 실행, benchmark, PPT 수정은 하지 않았다. 별도 코드 iteration과 검토가 필요하다.

## 엔진·모듈별 작업과 모델 할당 원칙 — D-085 (2026-10-25)

- **상태: APPROVED FOR FUTURE PLAN; IMPLEMENTATION NOT APPROVED.** 사용자는 향후 일반 변경은 엔진 또는 모듈별로 나누고 task마다 모델을 지정하되, 큰 변경은 본인이 좋은 모델을 선택해 사람 주도로 수정하고 오케스트레이터 통합은 필요한 범위에서 별도로 수행하는 운영 방식을 요청했다.
- **용어:** “엔진·모듈별 수정”을 사용한다. 엔진은 기능 책임과 입출력 계약, 모듈은 실제 코드·테스트·문서 수정 범위다. task마다 엔진, 변경 모듈, 계약, fixture, gate와 허용 파일을 명시한다.
- **5개 상위 계획:** 요청·탐색·metadata 기반, 방법론 판정과 BIS 세로 사례, 기관 connector·수집 품질, 가공·XLSX, 오케스트레이터 통합·회귀·무작위/장기시험으로 나눈다. 기존 10개 work package는 이 묶음의 세부 체크리스트로 보존한다. 이 5개는 5개의 거대 구현 task를 뜻하지 않는다.
- **모델 배정:** 모델은 엔진에 영구 고정하지 않고 task 시작 때 범위와 위험도에 맞게 지정한다. 안정된 단일 모듈 변경은 사용자가 정한 기본 모델(예: Luna Max), 기관 connector는 한 기관과 구체 dataset/table 단위, 방법론·계산 의미 변경은 강한 추론과 사람 검토, 다중 엔진/오케스트레이터나 큰 구조 변경은 사용자가 지정한 강한 모델과 사람 주도 계획을 권고한다. 모델 자동 라우팅은 구현 범위가 아니다.
- **오케스트레이터 gate:** 매 엔진 변경에 자동 포함하지 않는다. 입력/출력 계약, DAG 단계·병렬성, 사용자 확인, 상태·오류 전파, retry/cancel/resume, budget/credential 또는 provenance가 달라지는 경우에만 엔진별 gate 뒤 별도 통합 iteration에서 수정한다. 기존 계약을 보존하는 내부 모듈 수정이면 오케스트레이터를 건드리지 않는다.
- **문서:** `docs/developer/planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md`의 9절과 `docs/developer/DEVELOPMENT_GUIDE.md`에 상위 5개 묶음, 엔진·모듈 범위, 모델 배정과 오케스트레이터 조건을 기록하고 구현 계획에서 연결했다.
- **이번 범위:** 문서만 수정했다. 코드, 모델 설정/라우팅, agent 실행, credential, 테스트, live API, benchmark, PPT는 변경/실행하지 않았다. 향후 실제 구현은 단일 High iteration과 해당 gate를 별도 검토한다.

## 에이전트 구조 도식에 유지보수·측정·수정 흐름 통합 — D-086 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION; IMPLEMENTATION NOT APPROVED.** 사용자는 기존 구조도에 메모리 시험·성능 계산·코드 효율화·실제 수정 및 사람 검토 단계가 빠져 있고, 도식은 단순한 에이전트 구조처럼 모아야 한다고 지적했다.
- **도식:** `docs/developer/ARCHITECTURE.md`의 복잡한 요청 처리 그림을 요청 흐름과 지속 개선 흐름이 함께 보이는 하나의 고수준 도식으로 바꿨다. 탐색/metadata/mapping, 기관 connector/ingestion, 저장, 계획 단계의 방법론·변환·XLSX 구성요소를 묶어 표시하고, 현재 일부 구현과 미래 목표를 구별한다. `docs/operator/OPERATING_PLAN.md`의 중복 Mermaid 그림은 제거하고 공통 구조도로 연결한다.
- **유지보수 흐름:** 주간 오류·사람 피드백 재현, 격주 고정 workload의 CPU·peak RSS·시간·요청량 측정, 병목이 확인됐을 때만 엔진·모듈 코드 수정, fixture/회귀 및 재측정, 사람 diff 검토 순서를 추가했다. 근거가 없거나 개선이 재현되지 않으면 기준선을 유지하고 코드를 바꾸지 않는다.
- **병렬 트랙/통합:** Track M(유지보수·측정)과 Track C(기관 추가)는 독립 offline 작업을 병렬화할 수 있다. 오케스트레이터는 엔진 계약이나 workflow 상태·오류·재개 연결이 바뀌는 경우에만 엔진별 gate 후 통합 변경한다.
- **문서:** 아키텍처 구조도와 역할표, 운영 계획의 중복 그림 제거, 다기관 실행 계획 9.2절, 개발자 안내에 이 흐름을 반영했다.
- **이번 범위:** 문서만 수정했다. Python 코드, 테스트, 성능 측정, connector, 모델 자동 배정, live API, credentials, PPT는 실행/변경하지 않았다.

## 사용자 우선 문서 구조와 사용자별 Python 확장 제안 — D-087 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTATION AND DOCUMENT ORGANIZATION; IMPLEMENTATION NOT APPROVED.** 사용자는 문서 독자를 사용자·운영자·개발자로 분리하고, 사용자 관점 아키텍처를 개발자 구조보다 먼저 보여 달라고 요청했다. 사용자가 필요할 때 엔진의 일부만 안전하게 바꿀 수 있는 별도 Python 코드 확장 방식도 제안했다.
- **문서 구조:** `docs/user/`, `docs/operator/`, `docs/developer/`로 주 독자별 시작점을 분리했다. 개발자 아키텍처 자체도 사용자 흐름으로 시작한 뒤 엔진·모듈 구조를 설명한다. 구현·성능·결정·회차 이력은 개발자 이력 하위에 보존한다.
- **사용자 오류 개입:** 모호한 조건은 사용자에게 질문하고, 일부 기관 실패는 성공으로 숨기지 않으며, 무결성·보안·raw 손상·계산 신뢰성 문제는 영향을 받은 작업을 멈추고 사용자에게 상태를 알린 뒤 운영자·개발자 조사 후 재개한다.
- **확장 코드 방향:** Python package는 별도 extension 폴더에 두고 사전 정의된 hook만 호출한다. manifest는 JSON/YAML로 입출력 계약·권한·버전을 선언하고 Markdown은 설명에 쓴다. 실행 격리·자원 제한·권한 제한을 검증하기 전에는 runner를 구현하거나 확장을 활성화하지 않는다. 문법/링크 오류의 자동 수정과 방법론 의미 변경의 사람 검토를 구분한다.
- **세부 설계:** [사용자 Python 확장 제안](../extensions/USER_PYTHON_EXTENSIONS.md)에 package tree, 입력/출력 경계, 오류 분류, Windows 격리 gate를 기록했다.
- **결정 보류:** hook 목록과 안정된 API, package 설치 위치, dependency 격리, Windows에서의 신뢰 가능한 sandbox 방식, fallback 승인 절차는 추후 설계에서 결정한다. 사용자 확장 loader, 저장 위치, 실행 권한은 현재 구현되지 않았다.
- **PPT:** 잠금 파일이 있는 사용자 안내 PPT는 이동하지 않고 기존 위치를 유지했다. 운영·개발 참고 PPT는 운영자 reference로 옮겼다. PPT 내용 편집은 수행하지 않았다.
- **이번 범위:** 문서 파일과 내부 경로를 재구성·갱신했다. 코드 동작, API key, live 호출, 테스트 및 성능 측정은 변경·실행하지 않았다.

## Luna Extra High 작업 분량과 첫 실행 단위 — D-088 (2026-10-25)

- **상태: APPROVED FOR STAGED EXECUTION; DOWNSTREAM STATISTICAL AND LIVE DECISIONS PENDING.** 사용자는 기존 기획을 검토하고, Luna Extra High에서 다룰 적정 단위로 실행안을 나눈 다음 첫 작업을 실행하라고 요청했다.
- **분할 기준:** task는 토큰 수나 파일 수가 아니라 하나의 검토 가능한 결과, 하나의 엔진/모듈 동작, 하나의 gate로 자른다. source 작업은 기관 1곳과 구체 dataset/table 1개를 경계로 한다. 방법론 해석·전 세계 모집단·분모·위험 공식·live는 각각 승인 gate 전까지 멈춘다.
- **실행안:** `docs/developer/EXECUTION_PLAN.md`에 기존 5개 상위 묶음/10개 work package 연결, Track M/C 독립성, 단계별 gate, 향후 BIS→방법론→connector→변환→XLSX→통합·랜덤/soak 순서를 구체화했다. 실행 순서가 전체 직렬 고정이나 5개의 거대 task를 뜻하지 않음을 명시했다.
- **첫 작업 선택:** Iteration 20에서 같은 명명 E2E 측정이 이전 결과와 크게 달랐지만 과거 code fingerprint와 환경 근거가 부족했다. 따라서 제품 코드 효율화를 주장하거나 수정하기 전에 Iteration 21에서 benchmark provenance를 보강하고 고정 fixture를 두 번 재현했다.
- **Iteration 21 결과:** Gate L PASS. 두 독립 run 각각 30/30 완료, network/live HTTP 0, mock 1 call/sample, raw hash·missing·zero 보존. 같은 HEAD와 fingerprint에서 dispatcher p50/p95는 143.2193/183.3994 ms 및 150.7658/189.8372 ms였다. raw sample은 `reports/iteration_21_baseline_run_1.json`, `reports/iteration_21_baseline_run_2.json`이다.
- **해석 한계:** Iteration 18/20에는 code fingerprint가 없으므로 개선율·회귀율을 만들지 않는다. RSS/native SQLite memory도 미측정이다. 이 결과는 다음 작업을 재현 가능하게 만드는 baseline이지 제품 최적화가 아니다.
- **다음 gate:** 다음 후보는 BIS의 공식 API/dataflow 및 정확한 debt/credit 통계량 조사다. 이번 요청은 그 adapter 구현·통계 정의 선택·계산·XLSX·API key·live 실행까지 승인하지 않았다.
- **검토:** 전체 pytest는 실행하지 않았다. benchmark 자체가 두 run에서 계측·정확성 invariant를 검사했다. 구현 diff와 문서 변경은 stage/commit하지 않았고 사람 검토가 남아 있다.

## BIS 공식 API·통계 후보 조사 — D-089 (2026-10-25)

- **상태: OFFICIAL-DOCS RESEARCH COMPLETE; ADAPTER/LIVE NOT APPROVED.** Iteration 22는 BIS SDMX API v2 문서와 `Credit to the non-financial sector` 통계를 조사하는 Track C 작업으로 한정했다.
- **API 근거:** BIS는 공개 통계/메타데이터용 SDMX REST v2를 문서화하고 SDMX 2.1 데이터 응답 및 데이터·구조 질의 템플릿을 제공한다. 공식 BIS 통계 포털의 예시 계열은 `BIS,WS_TC,2.0`을 표시한다. 요청은 실행하지 않았다.
- **통계 해석:** BIS NFS 데이터는 정부 및 민간 비금융 부문의 gross debt/core debt 후보이며, 분기말 잔액·분기·SNA 2008 시장가치 원칙을 따른다. 정부 계열은 연결, 민간 부문은 비연결이다. lender 전체 범위를 뜻하는 “total credit”과 borrower sector aggregate를 문맥별로 구분한다.
- **범위 제한:** 공식 페이지는 40개 초과 경제와 상이한 국가별 이력을 설명한다. 전 세계 국가 완전성, 사용자 의도의 “총부채”, 국가별 위험 weight, 빈티지 재현 API는 확인/승인하지 않았다.
- **산출:** `docs/developer/connectors/BIS.md`와 `docs/developer/history/ITERATION_22_REPORT.md`를 만들고 실행·구현 계획과 기관 API 감사표에 gate 상태를 연결한다. 공식 문서 조사, API fixture, adapter, live는 각각 다른 상태로 기록한다.
- **Gate M:** PASS — 공식 API/dataflow 후보 근거 및 통계 정의/범위는 확인했고, 미확인 항목을 구현 앞의 질문으로 보존했다. 이번 회차 fixture·코드 테스트·live API 요청은 없다.
- **다음 task 후보:** Iteration 23 요청·metadata 계약 gap audit. BIS request scope와 workflow/series metadata 계약을 대조하고, 구현이 필요한 필드만 제안한다. 현재 회차에서 계약 코드 구현까지 시작하지 않는다.

## Luna Max 기준 전기관 검증 범위 — D-090 (2026-10-25)

- **상태: APPROVED FOR ALL-INSTITUTION TEST PLANNING; LIVE EXECUTION REMAINS SOURCE-GATED.** 사용자는 Max 기준 작업 분할을 요청하고, BIS는 예시일 뿐 21개 모든 기관·서비스의 live 동작을 확인해야 한다고 범위를 바로잡았다.
- **범위:** 검증 대상은 catalog/registry의 21개 기관 모두다. 현재 15곳은 공식 API 문서 확인, 6곳은 API 문서 미확인이며, 미확인은 API 부재가 아니다. 부분 구현 3곳, fixture-only 8곳, 미구현 10곳, 과거 partial live 근거는 World Bank 고정 경로 1개다.
- **Max batch:** 공통 API 계열(SDMX 7, 개별 REST 8)과 미확인 API 6곳의 조사 절차를 최대한 묶어 재사용한다. Batch를 묶더라도 기관/provider/dataset/table별 fixture·인증·coverage·live 판정은 독립한다. source-specific 증거 없는 성공 상속은 금지한다.
- **오프라인 근거:** 현재 checkout의 `.venv`와 `PYTHONPATH`를 사용한 전체 suite는 625 passed, 1 skipped, 0 failed, exit code 0이었다. 네트워크는 사용하지 않았다. Windows symlink를 만들 수 없어 1개 test가 skip됐다. 초기에 stale OneDrive editable install로 collection 오류가 났으나 current source를 지정한 최종 run에서 통과했다.
- **live 기준:** source-specific offline E2E, 공식 endpoint/table, auth/terms/quota, 최소 요청량과 raw/provenance 기록을 갖춘 기관만 bounded canary를 수행한다. API 미확인 표는 조사 전 live하지 않는다. 자격 증명 값은 확인하거나 기록하지 않는다. 각 source의 live 성공·실패·blocked 상태를 구분한다.
- **산출:** `docs/developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md`, `docs/developer/history/ITERATION_23_REPORT.md` 및 계획·기관 현황·테스트 결과 문서를 갱신했다. Iteration 23 Gate N은 readiness audit와 offline suite에만 PASS이며 live 통과를 뜻하지 않는다.
- **계획 변경:** D-089의 Iteration 23 request/metadata audit 제안은 버전 당시 순서를 기록한 것이다. 사용자 후속 지시에 따라 Iteration 23은 전체 source readiness audit가 되었고 request/metadata gap audit는 Iteration 24 후보로 이동했다. BIS는 대표 사례일 뿐 전체 테스트의 시작점이나 종료 조건이 아니다.
- **미실행:** 기관 adapter/fixture/코드 변경, credential 검사, live HTTP, 2h/6h soak는 수행하지 않았다. 전기관 live 프로그램은 source gate를 통과하는 기관부터 진행한다.

## 문서 확인 API 우선 구현 — D-091 (2026-10-25)

- **상태: APPROVED FOR DOCUMENTED-API ADAPTER IMPLEMENTATION; LIVE AND WORKFLOW GATES REMAIN SEPARATE.** 사용자는 API 문서 미확인 6곳을 우선 대상에서 제외하고 문서 확인된 API adapter 구현부터 하라고 요청했다. 기존 순서상 다음이던 all-source request/metadata gap audit를 먼저 수행하지 않고, 같은 SDMX API 계열의 첫 adapter batch로 Iteration 24를 진행했다.
- **Iteration 24 범위:** BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE 6개 기관의 고정 공식 route 및 bounded raw-response GET clients. 기관별 route tests를 따로 유지하고 공통 전송 안전성은 재사용한다.
- **IMF 처리:** IMF API 문서는 `documented`로 유지한다. 공식 상세 Swagger가 beta portal 로그인 후 제공된다고 안내되어 이 작업공간에서 상세 route/auth contract를 확보하지 못했으므로 endpoint를 추정하지 않고 후속 문서 gate로 둔다. 이는 API 부재 판정이 아니다.
- **구현 경계:** provider 원 응답 bytes의 transport까지만 포함한다. metadata/observation parsing, source payload fixtures, workflow/storage/recovery 연결, 인증·live access는 미구현/미실행이다. API 미확인 6개는 이번 batch에서 제외하고 표별 조사 후 별도 판단한다.
- **Gate O:** 전체 pytest 651 passed, 1 skipped, 0 failed; 변경 Python files Ruff passed. live HTTP는 0회. 결과/범위는 [Iteration 24 report](ITERATION_24_REPORT.md), provider별 route는 [SDMX connector 명세](../connectors/SDMX_FAMILY.md)에 보존했다.
- **후속:** IMF 문서 gate 뒤 남은 documented REST APIs를 기관별 auth/response contract를 유지하며 순차 구현한다. source payload fixtures와 workflow E2E를 통과한 기관만 bounded live canary 검토 대상으로 삼는다.
- **작업공간:** 기존 변경을 보존했고 이번 수정은 stage/commit/merge하지 않았다. 사람이 diff를 검토해야 한다.

## 9개 API 응답 파일 보존과 SDMX 검증 층 분리 — D-092 (2026-10-25)

- **상태: IMPLEMENTED; GATE P PASSED; LIVE VALIDATION REMAINS SEPARATE.** 사용자는 현재 client가 있는 전체 9개 source 결과를 파일로 보존하고 재검증한 뒤 전체 테스트를 다시 수행하라고 요청했다. SDMX는 공통 전송·기관별 route·기관별 응답 검증을 분리하라고 추가로 요청했다.
- **보존:** common archive helper는 World Bank, BEA, e-Stat, BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE response types를 source ID별 경로·manifest·hash로 저장하고 read-back한다. 기존 World Bank 저장 경로는 유지한다. BEA/e-Stat은 redacted JSON payload의 canonical serialization이지 byte-exact HTTP response가 아니다.
- **SDMX 경계:** `SdmxApiTransport`의 timeout/host-path/redirect/size/raw-byte safety, provider-specific adapter route/query, 그리고 각 source의 official payload fixture/auth limits/parser/live는 독립 gate로 기록한다. Iteration 25에서는 6개 SDMX의 mocked file round-trip만 통과했다. official payload fixture/parser는 없고 auth/access는 기관별 문서 상태, live는 `not_run`으로 유지한다.
- **검증:** 9개 source file round-trip과 관련 회귀 subset 122 passed, 1 skipped; 전체 offline pytest 666 passed, 1 skipped, 0 failed (37.93초); 변경 Python files Ruff passed. Live request 0회. skip은 현재 Windows 환경에서 symlink 생성이 불가능한 조건이다. 세부는 [Iteration 25 report](ITERATION_25_REPORT.md).
- **범위 한계:** 8개 non-World-Bank workflow는 archive helper를 아직 자동 호출하지 않는다. 데이터 parsing, 실제 기관 응답 fixture, auth/live 성공도 이 gate에서 주장하지 않는다. 다음 source 단계는 IMF 상세 route/auth 문서 조사이며, provider fixture/parser는 각 기관별로 뒤따른다.
- **승인:** file archive 구현과 offline 검증은 사용자가 지시했다. Stage/commit/merge/publish는 하지 않았고 사람의 diff 검토가 남아 있다.

## 공통 HTTP 전송층과 API 계열 adapter 분리 — D-093 (2026-10-25)

- **상태: IMPLEMENTED; ITERATION 26 GATE Q PASSED.** 사용자는 SDMX와 World Bank가 분리된 이유를 묻고 connector 구조 재설계를 요청했다.
- **설계 결정:** 하나의 `connectors/http_transport.py` bounded GET primitive가 network opt-in, HTTPS host/path policy, 세션 안전 설정, TLS 기본 검증, timeout/elapsed/byte bounds, redirect 거부와 raw entity-byte 수신을 맡는다. 기존 `WorldBankTransport`, `JsonApiTransport`, `SdmxApiTransport` wrappers와 각 provider client는 유지한다.
- **유지할 차이:** World Bank WDI route·JSON page envelope·all-status error body·Retry-After; BEA/e-Stat exact endpoint·credential parameter redaction·JSON parse/error mapping; SDMX provider data/structure paths·identifier/query constraints·8 MiB raw payload와 provider status mapping은 family/provider wrapper의 책임이다.
- **이유:** HTTP 실행은 재사용할 수 있지만 API 경로·auth·식별자·payload와 상태 의미는 같지 않다. 한 parser/client로 합치면 기관 차이를 공통 분기로 감추고 독립 검증을 약화시킨다.
- **범위 제한:** Iteration 26은 existing clients의 offline transport refactor와 문서/테스트만 다뤘다. endpoint/API 기능·workflow/storage behavior·live 호출은 바꾸지 않았다.
- **검증:** 관련 회귀 141 passed, 1 skipped; 전체 offline pytest 685 passed, 1 skipped, 0 failed (52.20초); 변경 Python Ruff passed; live HTTP 0회. Windows symlink 미지원으로 기존 e-Stat symlink test 하나가 skip됐다. 세부는 [Iteration 26 report](ITERATION_26_REPORT.md)에 기록한다.
- **작업 보호:** 기존 변경을 보존한다. stage/commit/merge/publish하지 않는다. 사람의 diff review는 남는다.

## 기관 API 키 발급 조사와 로컬 입력 준비 — D-094 (2026-10-25)

- **상태: IMPLEMENTED; ITERATION 27 GATE R PASSED.** 사용자는 추가 발급할 API 키를 조사하고 입력 이름을 `.env`에 준비해 달라고 요청했다. 이전의 Iteration 27 IMF 상세 route/auth 후보는 이 작업으로 대체했고 IMF 상세 문서는 Iteration 28 후보로 이동했다.
- **확인된 이름:** 기존 `BEA_API_KEY`, `ESTAT_APP_ID`에 `FRED_API_KEY`, `CENSUS_API_KEY`, `BLS_API_KEY`를 추가했다. FRED는 FRED/ALFRED와 FRED 경유 Board 자료의 공통 제공자 키다. Census는 데이터 조회에 필수이며 metadata 예외가 있다. BLS는 등록 없는 v1과 등록 키가 필요한 v2를 구별하고 최소 연 1회 갱신 안내를 남겼다.
- **문서 근거와 한계:** [API_KEYS.md](../../operator/API_KEYS.md)에 공식 발급·활성화·갱신 링크와 21개 source별 판단을 기록했다. IMF의 Swagger 로그인 안내를 데이터 API key 의무로 단정하지 않았고 INSEE의 별도 Sirene API key를 BDM에 전용하지 않았다. ECB help 페이지 재열람은 503이라 기존 근거를 유지했다. API 미확인 6곳의 기존 audit 상태와 authentication unknown은 유지했다.
- **로컬 보존:** 사용자가 지정한 `.env`는 기존 내용을 byte 단위로 보존하고 없던 3개 이름만 빈 값으로 append했다. 비밀값·값 유무는 보고하지 않고 네트워크 설정은 변경하지 않았다. strict loader는 5개 이름을 허용하고 빈 값은 None, 입력값은 repr 비노출로 처리한다. FRED/Census/BLS source client는 이 작업에서 구현하지 않았다.
- **검증:** 관련 설정/registry 36 passed, 1 skipped; 전체 offline 688 passed, 1 skipped, 0 failed (56.61초); 변경 Python Ruff 통과. skip은 Windows symlink 미지원이다. 공식 문서 조회 외에 통계 API 호출·키 발급·인증 검증은 0회다. 결과는 [Iteration 27 report](ITERATION_27_REPORT.md)에 보존한다. stage/commit/merge하지 않았다.

## FRED·Census와 BLS 1.0 전용 client·파일 검사 — D-095 (2026-10-25)

- **상태: IMPLEMENTED; ITERATION 28 GATE S PASSED.** 사용자는 본인이 키를 입력하는 동안 FRED/Census/BLS adapter와 파일 저장 테스트를 구현하라고 지시했고 BLS는 1.0만 사용하도록 범위를 확정했다. 이전 IMF 상세 문서 후보는 Iteration 29 후보로 이동했다.
- **API 계약:** FRED v1 metadata/search/관측치 page와 release/source, Census keyless metadata·keyed table, BLS 무키 v1 POST를 제공한다. BLS는 최대 25 series·10개 inclusive years를 허용하고 v2 route/registrationkey를 차단한다. `.env`의 기존 BLS key 항목은 수정하지 않으며 client는 쓰지 않는다.
- **공통 계층:** bounded HTTP에 16 KiB JSON POST를 추가하고 기존 GET 수신 안전 규칙을 공유한다. JSON family는 POST를 고정 BLS v1 endpoint에만 허용한다. Archive에 세 source와 HTTP method를 추가하고 query/body 조건은 credential 없이 남긴다. FRED API provider와 미확정 원 통계 기관은 분리한다.
- **출처·데이터 보존:** synthetic fixtures를 공식 live 응답으로 표시하지 않는다. FRED page/count/real-time, Census null·문자열·음수 sentinel·선행 0, BLS M13·footnotes·문자열을 보존하며 BLS warning/선택 누락을 성공으로 숨기지 않는다. JSON 보존물은 sanitized canonical serialization이지 정확한 HTTP 원 bytes가 아니다.
- **검증:** 기관별 source tests 71 passed; 전체 offline 763 passed, 1 skipped, 0 failed (70.76초); 수정 Python Ruff 통과. HTTP를 차단한 fixture 스크립트로 프로젝트 raw 파일 3개를 생성·read-back했고 [결과](../../../reports/iteration_28_offline_1ed43019cf344e5d86c64d5d79105a79.json)를 남겼다. Windows symlink 미지원으로 기존 test 한 개가 skip됐다.
- **한계:** `.env`/실제 키 읽기·변경, 실제 통계 API/인증 요청, 자동 pagination/일일 budget scheduler/재시도, 전체 기관 workflow·정규화 DB·가공·XLSX는 수행하지 않았다. Client 범위와 현재 미검증은 [FRED](../connectors/FRED.md), [Census](../connectors/CENSUS.md), [BLS v1](../connectors/BLS.md), [Iteration 28 report](ITERATION_28_REPORT.md)에 기록한다. stage/commit/merge/publish하지 않았다.
