# 21개 기관 공식 API 상태 조사

**현재:** [Iteration 32 결과 overlay](#iteration-32-결과-overlay), metadata 5곳 통과/INSEE 404 실패를 별도로 기록한다. 아래 초기 감사와 Iteration 31 기록은 소급 변경하지 않는다.

Iteration 31 현재 overlay: 사용자 지시로 Census·BLS는 active rollout에서 보류한다. 공식 API 문서 집계 15/6/0은 그대로이며, BEA GetDataSetList 13개 및 e-Stat getStatsList(E, limit=1) metadata의 실제 요청·source 계약·archive/read-back은 [Iteration 31](../../developer/history/ITERATION_31_REPORT.md)에서 확인했다. 아래 원래 조사 범위와 후속 live 증거를 구분한다.

Iteration 29 구현 보충: API 문서 집계는 15 documented / 6 unconfirmed / 0 not_offered 그대로입니다. TIC·BoE에는 검토된 공식 CSV 3개 다운로드 경로와 dataset별 합성 검증을 추가했습니다. 일반 API 미제공·live 성공으로 바꾸지 않습니다. [데이터셋 계약](../../developer/connectors/DATASET_CONTRACTS.md) 참조.

**조사일:** 2026-10-25\
**범위:** `docs/operator/reference/INSTITUTION_CATALOG.md`의 21개 기관·서비스와 `source_registry.py`의 실행 레지스트리 정합화.\
**근거 경계:** 공식 문서·공식 통계 포털을 읽어 API 명세 존재 여부와 명시된 이용조건을 기록했다. HTTP endpoint를 호출하지 않았고, API 인증·가용성·데이터셋 커버리지·adapter 동작의 live 검증은 하지 않았다.

`documented`는 공식 API 사양을 확인했다는 뜻이지 모든 통계표가 API로 제공되거나 MacroAtlas가 수집할 수 있다는 뜻이 아니다. `unconfirmed`는 검토한 공식 문서에서 일반 공개 API 사양을 찾지 못한 상태다. API 부재를 공식 문서가 명시하지 않았으므로 이번 조사에서 `not_offered`로 확정한 기관은 없다.

| ID | 기관·API 제공 주체 | API 상태 | 공식 근거와 확인 사항 | 인증/제한 메모 |
|---|---|---|---|---|
| INT-01 | IMF | documented | [IMF Data API](https://data.imf.org/en/Resource-Pages/IMF-API) 및 [공식 MATLAB/R public 안내 조사](../../developer/connectors/IMF.md). | Iteration 34 공개 CPI metadata는 무키 1회 HTTP 200·계약·archive/hash 통과. Swagger/private auth와 별개이며 관측치 미검증. |
| INT-02 | BIS | documented | [BIS SDMX API v2](https://stats.bis.org/api-doc/v2/)는 공개 통계·메타데이터용 REST API와 SDMX 하위집합을 문서화한다. [Iteration 22 BIS 프로필](../../developer/connectors/BIS.md)은 `WS_TC` 2.0 후보의 공식 정의·coverage를 정리한다. | 기존 감사 근거는 키 불필요로 안내; 이번 회차에서 인증·쿼터·접근성 live 미검증. |
| INT-03 | OECD | documented | [OECD SDMX REST Swagger](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1)는 REST API 사양을 제공한다. | 인증과 외부 endpoint 접근성은 live 미검증. |
| INT-04 | World Bank | documented | [Indicators API v2](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)는 version 2 및 데이터 호출을 문서화한다. | API 키 불필요. MacroAtlas live 범위는 USA/WDI/GDP 한 경로만 해당. |
| US-01 | Federal Reserve Board → **FRED가 API 제공** | documented | [Board DDP/FRED 전환 안내](https://www.federalreserve.gov/data/data-download-fred-information.htm)는 FRED API로 DDP series를 조회할 수 있다고 설명한다. [FRED API 사양](https://fred.stlouisfed.org/docs/api/fred/)은 실제 API 제공 주체를 확인한다. | `FRED_API_KEY` 필요. DDP 전환과 series crosswalk 때문에 Board 데이터 전체 커버리지는 표별로 확인해야 한다. |
| US-02 | St. Louis Fed FRED/ALFRED | documented | [FRED API](https://fred.stlouisfed.org/docs/api/fred/)는 FRED 및 ALFRED 자료 접근을 설명한다. | [API Key 안내](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html)에 따라 `FRED_API_KEY` 필요. 제3자 series의 별도 이용권리는 유지된다. |
| US-03 | Treasury TIC | unconfirmed | [TIC 사용 안내](https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic)는 TXT/CSV/HTML/PDF 등 공식 배포 형식을 설명한다. 검색 범위에서 TIC 공개 API 명세를 찾지 못했다. | API 부재 증거는 아니다. 파일/표 경로는 통계별로 검토한다. |
| US-04 | BEA | documented | [BEA API 문서](https://apps.bea.gov/API/docs/index.htm)는 데이터와 메타데이터 API 및 등록 UserID를 설명한다. | `BEA_API_KEY` 필요. 공식 안내서는 제한 초과 시 HTTP 429와 `Retry-After`를 설명한다. |
| US-05 | BLS | documented | [BLS Public Data API 시작 안내](https://www.bls.gov/developers/home.htm) 및 [FAQ](https://www.bls.gov/developers/api_faqs.htm)는 API v1/v2와 요청·시리즈 제한을 설명한다. | v1은 등록 없이 이용 가능, v2는 등록 시 확대 기능을 제공. 선택 키 변수는 `BLS_API_KEY`. |
| US-06 | U.S. Census Bureau | documented | [Census Data API 가이드](https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html)는 2026년 개정판에서 모든 데이터 요청의 API key와 요청당 최대 50개 변수를 명시한다. | `CENSUS_API_KEY` 필요. 이용 가능한 데이터셋과 필드는 프로그램별로 다르다. |
| EU-01 | ECB | documented | [ECB Data Portal API 개요](https://data.ecb.europa.eu/help/api/overview)는 SDMX 2.1 REST 기반 조회·발견을 설명한다. | 공개 API 문서는 확인했으며 실제 접근·rate limit은 미검증. |
| EU-02 | Eurostat | documented | [Eurostat API 소개](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction)는 Statistics, Catalogue, SDMX 2.1·3.0 서비스를 구분한다. | 키 불필요. 대량 응답은 비동기 처리/공정 사용 조건을 따라야 한다. |
| EU-03 | Deutsche Bundesbank | documented | [Bundesbank SDMX API 도움말](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448)는 데이터·메타데이터 REST 경로와 SDMX/XML/JSON/CSV/ZIP 형식을 설명한다. | 문서에서 인증을 확정하지 않아 auth는 unknown. CSV 요청은 최대 200 series, 큰 요청은 413/비동기 처리 가능. |
| EU-04 | Bank of England | unconfirmed | [Bankstats 데이터베이스](https://www.bankofengland.co.uk/boeapps/database/) 및 [통계 FAQ](https://www.bankofengland.co.uk/statistics/faqs)는 데이터와 HTML/Excel/XML/CSV 다운로드를 안내한다. 일반 공개 통계 API 사양은 찾지 못했다. | API 부재로 확정하지 않는다. 다운로드 파일 조건·사용권한은 자료별로 확인한다. |
| EU-05 | INSEE | documented | [INSEE SDMX 서비스](https://www.insee.fr/en/information/2868055)는 무료 SDMX 2.1 REST web service와 BDM/idbank 조회를 문서화한다. | 무료라는 사실만으로 인증 없음으로 간주하지 않아 auth는 unknown. |
| JP-01 | Bank of Japan | documented | [BOJ Time-Series API 안내](https://www.stat-search.boj.or.jp/info/nme_aphelp_en.html)는 JSON·CSV API와 공개 이용을 설명한다. | 누구나 이용 가능하다고 안내; 호출 제한·실행은 별도 확인. |
| JP-02 | Japan Ministry of Finance | unconfirmed | [MOF 통계 포털](https://www.mof.go.jp/english/statistics/index.html)과 [공식 reserve 데이터](https://www.mof.go.jp/english/policy/international_policy/reference/official_reserve_assets/data/index.htm)는 일부 CSV·SDMX 자료를 제공한다. MOF 일반 API 명세는 찾지 못했다. | e-Stat 같은 타 기관 API에서 특정 MOF 통계표를 제공하는지 표별 확인 전에는 MOF API로 간주하지 않는다. |
| JP-03 | e-Stat | documented | [e-Stat API 사양](https://www.e-stat.go.jp/api/en/api-info/api-spec)은 표 목록·메타데이터·통계값 API를 문서화한다. | 등록 `ESTAT_APP_ID` 필요. FAQ는 현재 요청 빈도 제한이 없다고 안내하지만 약관은 서버 부하에 따른 접근 제한을 허용한다. |
| CN-01 | PBOC | unconfirmed | [PBOC 공식 사이트](https://www.pbc.gov.cn/en/)와 [통계 규정](https://www.pbc.gov.cn/en/3688253/3689009/3788456/2025092319414130565/index.html)에서 통계 공표를 확인했다. 공개 API 명세는 찾지 못했다. | 기관별 통계 공표 경로와 접근 방식 추가 조사 필요; API 부재로 확정하지 않는다. |
| CN-02 | SAFE | unconfirmed | [SAFE 공식 통계 포털](https://www.safe.gov.cn/en/)에서 BOP·IIP·외환 통계 공표 경로를 확인했다. 공개 API 명세는 찾지 못했다. | 표별 파일/페이지 형식과 재사용 조건 확인 필요. |
| CN-03 | NBS China | unconfirmed | [National Data 포털](https://data.stats.gov.cn/)과 [NBS 이용 약관](https://www.stats.gov.cn/english/nbs/200701/t20070104_59236.html)은 데이터 포털·다운로드 사용을 설명하지만 공개 API 사양은 확인되지 않았다. | portal upgrade 후 테이블별 안정성·접근 방법을 확인한다. API 부재로 확정하지 않는다. |

## 집계와 후속 조사

**Iteration 27 키 발급 재조사:** 실제로 준비할 추가 이름은 `FRED_API_KEY`, `CENSUS_API_KEY`, `BLS_API_KEY`입니다. BEA/e-Stat과 합쳐 Settings는 5개 이름을 허용합니다. [키 발급·입력 안내](../API_KEYS.md)에 공식 링크와 21개 source별 판단을 기록했습니다. Census 데이터 요청에는 키가 필요하지만 2026년 6월 공식 안내상 metadata 요청은 예외입니다. BLS는 v2 등록 키와 무등록 v1을 구별하고 매년 갱신합니다. IMF Swagger 로그인과 데이터 API 인증은 별도이며, INSEE Sirene의 키 방식을 직접 BDM 경로에 전용하지 않습니다. 추가 Settings 지원은 source client 구현·인증 성공 증거가 아닙니다. 기존 auth unknown은 근거 없이 변경하지 않았습니다.

- API 문서 확인: **15개**. API 문서 미확인: **6개** (TIC, Bank of England, Japan MOF, PBOC, SAFE, NBS). 공식 API 미제공을 명시한 문서 확인: **0개**.
- 인증 `unknown`은 의도된 미확인 상태다. API 문서가 있다고 인증을 추정하지 않는다. API가 중개 플랫폼을 거치는 경우 원 기관과 API 제공자를 별도 표기한다.
- API 명세를 확인한 것은 fixture, 기관 adapter, live endpoint, 인증 성공을 검증한 것이 아니다. 이번 회차는 공식 문서 조사와 registry/catalog 정합화만 수행한다.
- 다음 adapter 회차에서 선택한 구체 dataset/table의 availability, version, terms, request budget, language, revisions, expected response schema를 다시 확인한다.

## Iteration 25 이후 현재 코드 상태

**Iteration 28 현재:** FRED v1·Census·BLS v1 clients와 기관별 synthetic 응답 검사·파일 저장/read-back을 추가해 공통 archive 대상은 12개 source다. BLS는 무키 v1 POST만 사용하며 v2·등록 키 전송은 제외한다. FRED/Census의 실제 키 인증과 세 기관 live 요청·일반 workflow는 미검증이다. [회차 보고서](../../developer/history/ITERATION_28_REPORT.md), [FRED](../../developer/connectors/FRED.md), [Census](../../developer/connectors/CENSUS.md), [BLS v1](../../developer/connectors/BLS.md) 참조. 아래 Iteration 24/25 내용은 해당 시점 증거를 보존한다.

Iteration 24에서 BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE에 공식 문서 경로 기반 SDMX raw-response clients와 기관별 mocked route tests를 추가했다. Iteration 25는 현재 client가 있는 9개 source의 response object를 파일로 저장하고 hash/manifest를 검증해 다시 읽는 공통 helper를 추가했으며, 전체 offline suite 666 passed, 1 skipped였다. BEA/e-Stat 저장물은 exact HTTP bytes가 아닌 sanitized JSON payload serialization이다. World Bank 외 8개 helper 호출은 기관 discovery/ingestion workflow에 아직 연결되지 않았으며, source response parsing·인증 성공·실제 endpoint 도달성은 검증되지 않았다. 기관별 route 및 제한은 [SDMX connector batch](../../developer/connectors/SDMX_FAMILY.md)와 [API response file archive](../../developer/connectors/API_RESPONSE_STORAGE.md)를 참고한다.

IMF 역시 SDMX API 문서가 있지만, 공식 API 페이지는 Swagger 상세 탐색에 beta portal 계정 로그인을 안내한다. 해당 route/auth 자료를 확인하기 전에는 요청 경로를 만들지 않았다. Iteration 25는 기존 client의 저장 경로만 추가했으며, 신규 API route는 만들지 않았다. 나머지 documented API의 현황은 [전기관 검증 프로그램](../../developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)을 따른다.
# Iteration 32 결과 overlay

공식 API 문서 집계 15/6/0은 유지한다. BIS·OECD·Eurostat·Bundesbank 선택 metadata는 최초 HTTP 200·계약·archive/hash 통과, ECB는 최초 파서 실패 후 같은 저장 응답의 수정 후 오프라인 재검증 통과, INSEE는 공식 예제 DSD의 HTTP 404로 실패다. 요청은 각 1회, 총 6회, retry 0이다. [경로·ID·접근/이용/format 근거](../../developer/connectors/SDMX_METADATA_CANARY.md), [Iteration 32 report](../../developer/history/ITERATION_32_REPORT.md)를 따른다. Census·BLS 보류와 Gate U NOT PASSED 이력은 유지한다. IMF도 SDMX 기관이며 상세 route/auth·adapter 준비는 별도다.
