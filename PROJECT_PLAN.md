# MacroAtlas 제품 기획

**기준일:** 2026-10-25
**문서 역할:** 제품의 목적, 현재 범위, 성공 조건을 정의합니다. 실제 실행 순서와 반복 주기는 [운영 계획](docs/operator/OPERATING_PLAN.md), 현재 개발 큐는 [구현 계획](docs/developer/IMPLEMENTATION_PLAN.md)을 따릅니다.

## 1. 만들려는 것

MacroAtlas는 사용자의 자연어 요청을 받아 국제금융·거시경제 통계를 공식 기관에서 찾고, 통계의 의미를 확인하며, API를 우선해 수집하고, 원자료·출처·검증·실패 이력을 보존하는 로컬 우선 데이터 에이전트 플랫폼입니다.

사용자는 “원하는 통계가 무엇인지” 설명합니다. 시스템은 모호한 조건을 질문으로 좁히고, 공식 출처의 후보를 비교해 단위·주기·지역·정의·개정 정보를 보여줍니다. 조건이 확인된 뒤에만 준비된 경로로 수집합니다. 결과가 달라지거나 실패하면 원인을 숨기지 않고 이전 실행과 연결해 설명합니다.

## 2. 사용자가 받는 결과

1. **출처가 분명한 후보:** 기관, 표/시계열 식별자, 공식 링크, 정의와 적용 범위.
2. **검토 가능한 수집 결과:** 원본 응답, 수집 시각, 요청 조건, 단위·주기·차원, 검증 결과.
3. **다시 이어갈 수 있는 실행:** 작업 단계와 오류를 기록하고 안전한 조건에서 재개.
4. **경험의 재사용:** 과거의 교정과 기관별 주의점을 범위·근거와 함께 저장하고, 검증 전에는 공통 사실로 승격하지 않음.

발견된 후보는 다운로드 가능성이나 통계적 동등성을 자동으로 보증하지 않습니다. 이용 조건, 불확실한 분류, 국가·기간·자료 유형은 필요하면 사람이 결정합니다.

## 3. 현재 구현과 목표를 구분

Iteration 33은 INSEE의 공식 CL_NATURE 1.0 codelist metadata를 단발 HTTP 200·source 계약·archive/hash read-back 범위로 검증했다. 과거 IPC DSD 404를 성공으로 바꾸지 않는다. 사용자 D-103에 따라 다음 Iteration 34 IMF는 공식 route/auth 준비 상태부터 독립 검증하며 35는 시작하지 않는다. [Iteration 33 report](docs/developer/history/ITERATION_33_REPORT.md).

2026-10-25 사용자 지시(D-101)로 Census·BLS는 active API rollout에서 보류한다. 기존 Gate U 실패 이력과 코드는 보존하며, 다른 기관은 독립 source gate에서 진행한다. Iteration 32는 기존 SDMX 6곳의 metadata 계약과 archive/read-back 검증이다. BIS·OECD·ECB·Eurostat·Bundesbank 5곳은 선택 metadata만 통과했고 INSEE는 공식 예제 DSD 요청의 HTTP 404로 실패했다. ECB 최초 파서 실패는 보존하고 같은 저장 bytes의 수정 후 오프라인 재검증으로 구분한다. [회차 보고서](docs/developer/history/ITERATION_32_REPORT.md)를 따른다. 보류 source는 사용자의 재개 지시 전까지 live 호출하지 않는다.

Iteration 31 결과는 BEA dataset metadata 13개와 e-Stat 영어 요청 목록 1건의 HTTP 200·source 계약·archive/hash read-back 통과다. Engineering Gate V와 두 source의 metadata sub-gate를 통과했으며 전체 offline 884 passed, 1 skipped다. source registry는 metadata-only PARTIAL 근거를 기록하고 관측치 수집 전체로 확대하지 않는다. [회차 보고서](docs/developer/history/ITERATION_31_REPORT.md)를 따른다.

### 현재 확인된 범위

- 공통 Python 계약, 순차 orchestration, SQLite 작업·감사 기록, 기관 프로필, 메타데이터·지식 조회, 파일/응답 파서와 검증 구성요소가 있습니다.
- 21개 출처 중 공식 API 문서가 확인된 곳은 15개, 조사한 문서에서 API 명세를 찾지 못한 곳은 6개입니다. 공식 문서가 API 미제공을 명시한 곳은 현재 0개입니다.
- API 문서가 있다는 사실은 MacroAtlas 어댑터나 데이터셋 지원을 뜻하지 않습니다. API 문서 상태, 인증, 코드 구현, fixture, live 상태는 각각 구분합니다.
- 제한 live 경로 근거는 World Bank USA/WDI/GDP 고정 수집과 Iteration 30의 두 차례 bounded canary입니다. 최신 run에서 FRED GDP·TIC MFH·TIC Table 3D·BoE Bank Rate 4개 profile이 source contract 및 hash read-back을 통과했습니다. Census는 302 redirect 차단, BLS v1 두 profile은 HTTP 503으로 실패해 Gate U는 NOT PASSED입니다. 이 결과는 일반 discovery, 전 데이터셋, 정규화 observation 승인이나 Gate U 전체 통과를 뜻하지 않습니다. 세부는 [Iteration 30 live 보고서](docs/developer/testing/LIVE_CANARY_REPORT.md)를 참조합니다.
- BEA·e-Stat의 제한 JSON 클라이언트와 BIS·OECD·ECB·Eurostat·Bundesbank·INSEE의 SDMX raw-response client는 공통 파일 보존 모듈을 통해 저장·manifest·hash-checked read-back 할 수 있습니다. BEA·e-Stat 저장물은 redacted payload 재직렬화이며 byte-exact 원 HTTP 응답이 아닙니다. Iteration 29에는 FRED·Census·BLS v1 API profile 4개와 Treasury TIC·BoE 공식 CSV profile 3개를 고정 선택 데이터셋 collector에 연결했습니다. Iteration 30 후속 live run은 7개 중 4개 source contract를 검증했고, Census redirect 차단과 BLS 503 두 건 때문에 Gate U는 계속 실패입니다. 이 7개는 고정 요청 흐름이지 자연어 대화 전체를 처리하는 workflow가 아닙니다. 나머지 8개 API archive helper의 일반 수집·기관별 workflow와 payload 의미 검증은 미완료입니다. IMF Data API는 공식 SDMX API 문서가 있으나 Swagger 상세 탐색에 beta portal 계정이 필요하다고 안내되어 route/auth 자료 확보 전까지 미구현입니다. 세부는 [API response 저장 명세](docs/developer/connectors/API_RESPONSE_STORAGE.md), [Iteration 30 보고서](docs/developer/history/ITERATION_30_REPORT.md), [구현 계획](docs/developer/IMPLEMENTATION_PLAN.md)을 따릅니다.
- 자연어 요청을 실제 제품 UI에서 처리하는 에이전트는 목표 구조입니다. 현재의 로컬 서비스와 Python API를 자연어 제품 기능으로 설명하지 않습니다.
- Iteration 28 시점에는 FRED·Census·BLS v1 clients를 synthetic fixture→파일→hash read-back 범위로 추가했으며 BLS는 무키 v1만 사용합니다. Iteration 29에서 일부 경로를 고정 dataset collector에 연결했습니다. Iteration 30 최신 후속 canary에서 FRED는 통과했고, Census는 HTTP 302 redirect 거부, BLS 두 경로는 HTTP 503으로 실패했습니다. 전체 API client archive 범위와 기관별 상태는 각각 [Iteration 28 보고서](docs/developer/history/ITERATION_28_REPORT.md), [기관 상태표](docs/operator/reference/INSTITUTION_IMPLEMENTATION_STATUS.md)를 따릅니다.

정확한 구현 경계는 [현재 구조](docs/developer/ARCHITECTURE.md), 기관별 근거는 [기관 목록](docs/operator/reference/INSTITUTION_CATALOG.md)과 [API 조사](docs/operator/reference/INSTITUTION_API_AUDIT.md), 회차별 증거는 회차 보고서를 봅니다.

현재 Gate U 실패를 좁힌 추가 근거는 [Census·BLS 진단](docs/developer/testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md)을 따릅니다. Census 302는 공식 invalid-key 안내이며 사용자 활성화 완료 응답과 별개로 현재 키가 서버에서 거부됩니다. BLS GET·POST 비교는 모두 503 HTML로 끝났고 앞단 오류/접근 페이지 가능성만 확인했습니다. 코드에는 안전한 인증 실패 분류와 등록 profile별 단발 실행을 보강했으며 전체 offline suite는 846 passed, 1 skipped입니다. live 자료 성공이나 Gate U 통과로 승격하지 않습니다.

### 제품 범위

Iteration 29는 API 4개 dataset binding과 TIC·BoE 공식 CSV 3개 binding을 version/hash profile 아래 연결합니다. 12개 API client와 별도 공식 파일 client 2곳의 raw 보존이 가능하며, 새 dataset 경로는 합성 fixture·원본/검증 receipt·hash read-back 범위입니다. API 문서 상태와 기존 live 범위는 바뀌지 않습니다. [데이터셋 계약](docs/developer/connectors/DATASET_CONTRACTS.md)을 따릅니다.

- 공식 출처·카탈로그·API 문서·메타데이터 발견.
- 기관 원문을 보존하는 정규화 및 근거 기반 개념 연결.
- 준비된 API 어댑터를 이용한 관측치 수집, 검증, 저장, 재조회, 오류 복구.
- 사용자 피드백과 오류 기록의 제한된 재사용.
- 필요에 따른 기관별 어댑터와 공통 엔진의 개선.
- 요청된 계산만 실행하는 별도 변환 엔진과, 원자료·공식·coverage를 추적하는 파생 산출물. 이는 현재 목표 범위이며 구현된 기능으로 보지 않습니다.
- 방법론·비교가능성 엔진(작업명)은 공식 방법론 근거로 정의·측정 시점·기간 정렬 가능성을 먼저 평가하며, 실제 값 변경은 별도의 deterministic 변환 엔진이 사용자 승인 후 수행합니다. 이름은 추후 확정합니다.

자동 로그인/CAPTCHA 우회, 권한 없는 자료 수집, 의미가 불확실한 수치 보정, 키의 로그/소스 기록, 무인 병합·배포는 범위에 포함하지 않습니다.

## 4. 공통 엔진과 기관별 연결

기관마다 다른 API 경로·인증·식별자·페이지 처리·언어·개정 정보는 기관 어댑터와 기관별 문서/fixture에 둡니다. 공통 엔진은 요청 확인, 실행 상태, raw 보존, 메타데이터 계약, 검증, 재시도·복구와 이력을 담당합니다.

공통 엔진을 안정적으로 유지하면서 기관별 연결을 늘립니다. 한 기관의 특수 처리를 공통 코드의 기관명 조건문으로 퍼뜨리지 않습니다. 공통 계약을 바꿀 때는 영향을 받는 모든 어댑터를 회귀 확인합니다. 에이전트가 계획을 작성하거나 코드 변경을 제안하더라도 적용·live 실행·공통 규칙 승격에는 정해진 검토 단계를 둡니다.

구조도는 [docs/developer/ARCHITECTURE.md](docs/developer/ARCHITECTURE.md)를, 실제 유지·확장 방식은 [docs/operator/OPERATING_PLAN.md](docs/operator/OPERATING_PLAN.md)를 참고합니다. 다기관 후보 탐색부터 승인된 변환·XLSX 산출까지의 제안 흐름은 [다기관 실행 기획](docs/developer/planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md)에 정리합니다.

## 5. API와 언어 원칙

- 모든 기관에서 먼저 공식 API가 있는지 확인하고, 공식 문서가 확인된 API를 우선 접근 경로로 둡니다.
- API 상태(문서 확인/미확인/공식 미제공), 인증, 코드 구현, fixture, live 범위는 독립적으로 기록합니다.
- API 미확인 기관은 endpoint를 추정해 호출하지 않습니다. 문서 조사 후 API가 자료별로 없거나 부적합하다고 확인되면 그때 공식 파일/표 경로를 별도 검토합니다.
- 가능하면 API·메타데이터·코드 목록의 영어 응답을 먼저 사용합니다. 영어판이 없으면 일본어/중국어 원문을 보존하고 영어 중간 번역을 만든 뒤 한국어로 전달합니다. 식별자·숫자·원 단위는 번역으로 바꾸지 않습니다. 번역 언어와 출처를 기록합니다.

## 6. 품질과 데이터 보호

- 기관·dataset/series ID·원URL·요청 조건·UTC 수집 시각·원본 hash를 가능한 범위에서 보존합니다.
- 단위, 주기, 차원, 개정/vintage와 이용 조건을 추적합니다. 원천이 제공하지 않는 값은 임의로 채우지 않습니다.
- 결측·비공개·해당 없음·0을 구별합니다. 결측을 0으로 변환하지 않습니다.
- 새로운 수집 결과는 이전 raw를 조용히 덮어쓰지 않습니다.
- 네트워크와 인증은 명시적으로 준비된 경로에서만 사용하고, 키는 로컬 비밀 설정에만 둡니다.
- 외부 응답이 바뀐 것과 파서 오류를 구분합니다. 재시도는 시간·횟수·호출량 상한이 있어야 합니다.

## 7. 완료 기준

한 변경은 요청된 동작과 현재 범위를 먼저 고정하고, fixture/mock 검사 및 영향을 받는 회귀 검사를 통과하며, 결과·한계·미검증 범위를 기록해야 완료입니다. 실기관 문서 조사, fixture 검증, live API 호출, live ingestion은 각각 별도 증거로 표시합니다. 측정되지 않은 성능 향상이나 확인되지 않은 API 지원을 주장하지 않습니다.

## 8. 기준 문서

- 운영 주기와 Track M/C: [docs/operator/OPERATING_PLAN.md](docs/operator/OPERATING_PLAN.md)
- 지금의 개발 큐: [docs/developer/IMPLEMENTATION_PLAN.md](docs/developer/IMPLEMENTATION_PLAN.md)
- 아키텍처: [docs/developer/ARCHITECTURE.md](docs/developer/ARCHITECTURE.md)
- 사람용 절차: [docs/user/USER_GUIDE.md](docs/user/USER_GUIDE.md)
- 성능 측정: [docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md](docs/developer/performance/PERFORMANCE_OPTIMIZATION_PLAN.md)
- 기존 운영·개발 PPT(참고용; 엔진별 개정은 기획 안정화 후): [docs/operator/reference/MacroAtlas_운영_개발_개정.pptx](docs/operator/reference/MacroAtlas_운영_개발_개정.pptx)
- 실제 독자별 안내: [docs/README.md](docs/README.md), [사용자](docs/user/USER_GUIDE.md), [운영자](docs/operator/OPERATOR_RUNBOOK.md), [개발자](docs/developer/DEVELOPMENT_GUIDE.md) 문서를 구분합니다.
- API 출처 상태: [docs/operator/reference/INSTITUTION_API_AUDIT.md](docs/operator/reference/INSTITUTION_API_AUDIT.md)
- 전기관별 API·fixture·offline E2E·live 검증 기준: [docs/developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md](docs/developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)
- 보존할 실행 증거: 회차 보고서, [docs/developer/history/DECISION_LOG.md](docs/developer/history/DECISION_LOG.md), [docs/developer/performance/OPTIMIZATION_LOG.md](docs/developer/performance/OPTIMIZATION_LOG.md), 기준선·비교·회귀 보고서.
