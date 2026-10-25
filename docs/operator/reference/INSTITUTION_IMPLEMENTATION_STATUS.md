# 기관별 MacroAtlas 구축 상태

**기준일:** 2026-10-25\
**원본 상태:** `src/macro_data_platform/discovery/source_registry.py`의 21개 기관 프로필과 Iteration 30까지의 보고서.
**목적:** 공식 API 문서 보유 여부와 MacroAtlas 안에 실제 기관별 실행 경로가 있는지를 분리해 보여준다. 21개 전체의 offline/live 검증 기준과 실행 순서는 [전기관 검증 프로그램](../../developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)을 따른다.

## 현재 요약

아래의 구현 유형 집계는 live 상태와 별도 축이다. Iteration 30의 후속 canary는 등록된 7개 profile을 각 1회 실행해 4/7 source contract 및 hash read-back을 통과했다. Census는 HTTP 302 redirect 차단, BLS 두 profile은 HTTP 503으로 Gate U는 미통과다. [상세 실행 기록](../../developer/testing/LIVE_CANARY_REPORT.md).

| MacroAtlas 구현 상태 | 기관 수 | 의미 |
|---|---:|---|
| 제한 경로 구현·실 API 검증 일부 | 1 | World Bank의 미국 WDI GDP 고정 경로. Iteration 30에서는 FRED GDP·BoE Bank Rate의 bounded live 응답과 TIC 파일 2개도 별도 범위에서 확인했다. |
| API 클라이언트 일부 구현 | 11 | BEA, e-Stat, SDMX 6기관과 FRED·Census·BLS v1. FRED·Census·BLS는 고정 collector profile 일부가 있으며 일반 자연어 workflow와 정규화 DB는 미구현. live overlay는 아래 기관별 표에 기록. |
| 공식 파일 클라이언트 일부 구현 | 2 | TIC 2개·BoE 1개 CSV의 다운로드·계약 검사·raw/receipt 저장·hash read-back. 합성 fixture 검증. |
| fixture 구성요소만 있음 | 4 | IMF synthetic SDMX, 중국 3개 기관 탐색 fixture. 전용 API 요청 경로는 없다. |
| 기관 전용 클라이언트 없음 | 3 | Board 전용 crosswalk, BOJ, 일본 MOF. 공통 FRED client를 Board 전용 검증으로 일반화하지 않음. |
| **전체** | **21** | 자연어 UI 및 전 기관용 자동 검색 기능은 구축되어 있지 않다. |

## 기관을 MacroAtlas에서 실제로 조회할 수 있는 정도

### 제한된 실행 경로가 있음

| 기관 | 현재 가능한 범위 | 검증·한계 |
|---|---|---|
| World Bank | Indicators API의 특정 GDP 수집 경로 | 미국 / WDI source 2 / `NY.GDP.MKTP.CD` 고정 범위만 제한 live 검증. 범용 국가·지표 discovery는 아님. |

### API 호출 클라이언트 일부만 있음

아래 11개 source는 limited Python API clients가 있습니다. 그중 FRED·Census·BLS에는 고정 dataset profile collector 연결과 synthetic contract 검사도 있으며, FRED의 한 page는 live contract/hash 확인, Census 한 경로와 BLS 두 경로는 canary 실패가 기록됐습니다. 나머지 source의 일반 discovery/ingestion workflow와 live 호출은 미검증입니다. 공통 archive helper로 저장·hash 확인 read-back 할 수 있습니다. SDMX raw clients의 provider payload parsing은 이 검사 범위와 구별합니다.

| 기관 | 구현된 부분 | 아직 없는 부분 |
|---|---|---|
| BEA | JSON GET 클라이언트, 요청 parameter 목록, redacted JSON archive/read-back helper | workflow 연결, source payload semantics/정규화·검증, live API 확인 |
| e-Stat | JSON GET 클라이언트, 요청 parameter 목록, redacted JSON archive/read-back helper | workflow 연결, source payload semantics/정규화·검증, live API 확인 |
| FRED/ALFRED | v1 metadata·검색·명시적 관측치 page·release/source, synthetic archive/read-back | 2026-10-25 FRED GDP 1개 고정 page live contract/hash 검증; v2, Board crosswalk, 전체 자동 pagination·workflow·범용 인증/coverage |
| BLS | 무키 v1 POST, 25 series·10년 한도, warning/선택 검증과 synthetic archive/read-back | 후속 canary의 두 경로 모두 HTTP 503 `http_transient_status`; 구체 서버 측 원인 미확정. v2, key 사용, 일일 budget scheduler, workflow·live 성공 |
| Census | catalogue/variables/geographies, keyed header/row table과 synthetic archive/read-back | 후속 ACS query는 HTTP 302 `redirect_refused`로 안전 중단; redirect 목적지는 기록되지 않아 원인 미확정. 큰 응답 자동 분할, 통계 의미 정규화, workflow·live 성공 |
| BIS | SDMX v2 raw-response routes와 mocked routes, 공통 file archive/read-back helper | provider payload fixture·parse, metadata/ingestion workflow, live |
| OECD | SDMX v1 raw-response routes와 mocked routes, 공통 file archive/read-back helper | 인증/외부 접근 조건, provider payload fixture·parse, workflow, live |
| ECB | SDMX 2.1 dataflow/structure/data routes, 공통 file archive/read-back helper | provider payload fixture·parse, metadata/ingestion workflow, live |
| Eurostat | SDMX 2.1 dataflow/structure/data routes, 공통 file archive/read-back helper | DS-prefixed Comext/Prodcom 경로, async, provider payload fixture·parse, workflow, live |
| Deutsche Bundesbank | SDMX data/metadata routes, 공통 file archive/read-back helper | 인증, 413/async 경로, provider payload fixture·parse, workflow, live |
| INSEE | BDM/idbank와 dataflow data routes, 공통 file archive/read-back helper | API portal auth, provider payload fixture·parse, workflow, live |

### 공식 파일 경로 일부 구현

| 기관 | 데이터셋별 범위 | 미검증·제외 |
|---|---|---|
| Treasury TIC | MFH 역사 CSV 반복 연도/월 블록·Series break 기록, Table 3D January 2023 snapshot 별도 profile/validator. 원 bytes·결측·집계·각주 보존. 후속 canary에서 두 live 응답 모두 HTTP 200, source contract 및 hash read-back 통과. | 전체 raw 최신성 보장, 국가 코드 정규화, 전체 국가·총부채 의미 검증 없음 |
| Bank of England | IUDBEDR CSVF=TN, 최대 366일 요청, 원 보고 날짜·결측 검증, 원본/receipt 저장. | 2026-10-25 고정 10일 요청 live contract/hash 검증; 일반 시리즈 discovery, 월말 정렬·보간 없음 |

일반 API 명세는 계속 unconfirmed이며 파일 다운로드를 API 구현으로 집계하지 않습니다. [데이터셋 계약](../../developer/connectors/DATASET_CONTRACTS.md)은 API 4개·파일 3개 선택 경로를 Python collector로 실행합니다. 최신 후속 run은 7개 중 4개 live source-contract pass이며, Census 302 및 BLS 503 두 건으로 Gate U는 NOT PASSED입니다. 일반 대화 workflow·정규화 관측치 DB는 별도입니다.

### fixture 수준만 있음

실제 기관 API를 호출하는 구현이 아닙니다. 아래 fixture는 기관 형태의 합성 입력 또는 탐색/파서 조각을 확인하는 용도입니다.

| 기관 | fixture가 다루는 범위 | 실제 API/자료 조회 |
|---|---|---|
| IMF | IMF 형태의 합성 SDMX 구조·series metadata | 없음. API 문서는 있지만 상세 Swagger는 beta portal login을 안내해 route/auth 근거가 확보되지 않음 |
| PBOC | 사이트 탐색 fixture | 없음 |
| SAFE | 사이트 탐색 fixture | 없음 |
| 중국 NBS | 사이트 탐색 fixture | 없음 |

### 기관별 어댑터가 없음

공식 문서 또는 자료 포털 조사는 되어 있을 수 있지만, MacroAtlas에서 해당 기관을 질의하는 전용 데이터 경로는 없습니다.

| 기관 | 조사된 접근 방식 | MacroAtlas 상태 |
|---|---|---|
| Federal Reserve Board | 일부 DDP 계열의 FRED 경유 API 문서 | Board 자료용 connector·series crosswalk·live 호출 없음 |
| Japan Ministry of Finance | 공식 통계·CSV/SDMX 파일 경로; 일반 API 명세 미확인 | 전용 탐색·다운로드 어댑터 없음 |
| Bank of Japan | JSON/CSV REST API 문서 | connector·기관 fixture·live 호출 없음 |

## API 문서 상태는 별도 집계

| API 문서 상태 | 기관 수 | 기관 |
|---|---:|---|
| 공식 API 문서 확인 | 15 | IMF, BIS, OECD, World Bank, Federal Reserve Board(FRED 경유), FRED/ALFRED, BEA, BLS, Census, ECB, Eurostat, Bundesbank, INSEE, BOJ, e-Stat |
| 검토 범위에서 일반 API 문서 미확인 | 6 | Treasury TIC, Bank of England, Japan MOF, PBOC, SAFE, 중국 NBS |
| 공식 문서가 API 미제공을 명시 | 0 | 확인된 기관 없음 |

`문서 확인`은 API 호출 성공·기관별 데이터셋 제공·MacroAtlas 연결을 뜻하지 않습니다. `미확인`도 API가 없다는 뜻이 아닙니다. 자료별로 API 제공 및 이용 조건을 더 조사해야 합니다.

## 용어 해석과 범위

- **구축됨:** 표의 범위에 한해 MacroAtlas 코드 경로가 존재한다는 뜻입니다. 전 기관 또는 전 데이터셋 지원을 뜻하지 않습니다.
- **기관 클라이언트:** 기관별 HTTP 요청 메서드가 일부 구현됐지만 orchestration/discovery/ingestion과 연결되지 않은 상태입니다.
- **SDMX raw client:** 기관별 고정 route를 호출해 원 response entity bytes를 반환합니다. source payload parsing, metadata와 observation 검증, workflow 수집을 뜻하지 않습니다. 구현 범위는 [SDMX connector 명세](../../developer/connectors/SDMX_FAMILY.md)에 있습니다.
- **Response archive helper:** API client 12곳과 공식 파일 client 2곳의 response object를 source별 파일·manifest로 보존하고 hash/경로를 검증해 읽습니다. 등록 dataset collector는 별도 profile receipt를 추가하며 일반 workflow 자동 연결과 구별합니다. [저장 명세](../../developer/connectors/API_RESPONSE_STORAGE.md)를 참고하세요.
- **fixture:** 테스트 입력에 대한 로컬 동작 검증이며, 실제 기관 사이트/API 확인 증거가 아닙니다.
- **live 검증:** 실제 기관에 제한 요청을 보낸 증거입니다. World Bank의 고정 경로와 Iteration 30의 FRED GDP·BoE Bank Rate bounded paths는 live contract validation이 기록됐습니다. TIC 2개는 live 파일 저장/hash read-back 후 validator를 사후 offline 재실행해 통과했습니다. Iteration 30 Gate U는 Census와 BLS 두 경로가 미통과라 실패 상태입니다. 자세한 경계는 [canary 보고서](../../developer/testing/LIVE_CANARY_REPORT.md)를 봅니다.
- **자연어 요청 처리:** 사용자 대화형 제품 UI는 목표 구조이며 현재 제공 기능이 아닙니다.

이 상태표는 기관 카탈로그와 레지스트리의 현황을 사용자 관점으로 분리해 보여줍니다. 세부 API 문서 근거는 [기관 API 감사표](INSTITUTION_API_AUDIT.md), source 상태 원본은 [기관 카탈로그](INSTITUTION_CATALOG.md), 전체 경계는 [아키텍처](../../developer/ARCHITECTURE.md)를 참조하세요.
