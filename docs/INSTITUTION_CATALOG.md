# Institution Catalog — 국제금융 통계기관 사전 조사대장

> 조사대장 기준일 2026-10-24, 이후의 제한 live 근거는 날짜가 붙은 추가 섹션에 기록한다.
> **상태 구분:** `공식 문서 확인`은 안내 문서 검토, `제한 live 확인`은 이름이 붙은 API/요청의
> 한정 실측, `기관 확인·경로 추가 조사`는 기관·주제만 확인한 상태다. 어느 상태도 기관 전체
> 지원이나 Gate 통과를 뜻하지 않는다.
> 사용자가 실제 실행할 수 있는 현행 경로는 [사용자 안내서](USER_GUIDE.md), 구현 범위·우선순위는
> [통합 제품 기획](../PROJECT_PLAN.md)에서 확인한다.

## 초기 기관·서비스 21개

| ID | 지역 | 기관/서비스 | 대표 주제 | 관찰된 접근 유형·특징 | 조사 상태 | 공식 출처 |
|---|---|---|---|---|---|---|
| INT-01 | 국제 | IMF | BOP/IIP, IFS·외환·거시 | SDMX 2.1/3.0 API, Data Portal 문서 | 공식 문서 확인 | https://data.imf.org/en/Resource-Pages/IMF-API |
| INT-02 | 국제 | BIS | 국제은행·글로벌 유동성·파생상품 | SDMX REST, CSV/SDMX ZIP bulk, Excel 수동 export | 공식 문서 확인 + Global Liquidity CSV bulk 제한 live intake | https://stats.bis.org/api-doc/v1/ ; https://data.bis.org/bulkdownload |
| INT-03 | 국제 | OECD | GDP·고용·산업·국가비교 | Data Explorer SDMX API·쿼리 빌더, rate limit | 공식 문서 확인 | https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html |
| INT-04 | 국제 | World Bank | WDI 등 국가별 지표 | Indicators API v2, 국가·지표 기반 | 공식 문서 확인 | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 |
| US-01 | 미국 | Federal Reserve Board | 금리·금융계정·통화·대출 | DDP·공표통계·FRED 매핑, 2026~27 전환 예고 | 공식 문서 확인 | https://www.federalreserve.gov/data/data-download-fred-information.htm |
| US-02 | 미국 | St. Louis Fed FRED/ALFRED | 다양한 미 거시시계열·vintage | REST API, release/source/series 검색, 인증 | 공식 문서 확인 | https://fred.stlouisfed.org/docs/api/fred/overview.html |
| US-03 | 미국 | Treasury TIC | 미국 증권의 외국인 보유·거래 | 공식 웹표·CSV/TXT/HTML/PDF·아카이브; TIC 사용안내 | 공식 문서 확인 | https://home.treasury.gov/data/treasury-international-capital-tic-system ; https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic |
| US-04 | 미국 | BEA | GDP, BOP, IIP, 직접·증권투자 | API 키·dataset/parameter 목록 선탐색·JSON/XML | 공식 문서 확인 | https://apps.bea.gov/API/swagger/index.htm |
| US-05 | 미국 | BLS | CPI, PPI, 고용 | Public Data API v2, JSON; 일반 시계열은 등록 키 선택, `catalog=true` 등 선택 parameter는 등록 키 필요 | 공식 문서 확인 + 제한 live 확인 | https://www.bls.gov/audience/developers.htm |
| US-06 | 미국 | Census Bureau | 무역·산업·인구 | Data API; 확인된 안내에 data query 키 필수, ACS variable endpoint 일부 실측 | 공식 문서 확인 + 제한 live 확인 | https://www.census.gov/data/developers/guidance/api-user-guide.html |
| EU-01 | 유로존 | ECB | 금리·환율·은행·신용 | SDMX REST, metadata-driven data discovery | 공식 문서 확인 | https://data.ecb.europa.eu/help/api/overview |
| EU-02 | EU | Eurostat | GDP·HICP·무역·국가별 통계 | CATALOGUE API 별도, SDMX 2.1/3.0·JSON-stat | 공식 문서 확인 | https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction |
| EU-03 | 독일 | Bundesbank | 독일·유로 금융/경제 시계열 | 새 통계포털·SDMX REST, 구 시계열 키 매핑 | 공식 문서 확인 | https://www.bundesbank.de/en/statistics/time-series-and-real-time-data |
| EU-04 | 영국 | Bank of England | 통화·금융·금리 | Bankstats IADB 검색, 다운로드·코드 기반 탐색 | 공식 문서 확인 | https://www.bankofengland.co.uk/boeapps/database/help.asp |
| EU-05 | 프랑스 | INSEE | 생산·물가·거시시계열 | SDMX 2.1 웹서비스, idbank 단위 시계열 | 공식 문서 확인 | https://www.insee.fr/en/information/2868055 |
| JP-01 | 일본 | Bank of Japan | 금융·금리·국제수지 | 2026-02-18 JSON/CSV API 도입, flat files 병행 | FM08/FXERD01 한 달 collector live 200, 30 observations; 그 밖의 series 미지원 | https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm |
| JP-02 | 일본 | Ministry of Finance | 국제수지·직접·증권투자 | 공개 통계표 및 BOJ Time-Series Data Search 연계 | 공식 문서 확인 | https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/index.htm |
| JP-03 | 일본 | e-Stat | 정부 통계표·코드북 | 표 목록→메타→통계값 API, 등록/Application ID | 공식 문서 확인 | https://www.e-stat.go.jp/api/en/api-info |
| CN-01 | 중국 | PBOC | 통화량·대출·사회융자 | 공식 홈페이지 통계 섹션의 접근·재사용 경로 추가 실사 | 기관 확인·경로 추가 조사 | https://www.pbc.gov.cn/en/ |
| CN-02 | 중국 | SAFE | BOP·IIP·외환보유액·외채 | 공식 Data and Statistics 공개 페이지·자료 탐색 | 공식 문서 확인(포털); 구체 자동수집 미검증 | https://www.safe.gov.cn/en/ |
| CN-03 | 중국 | NBS | 생산·GDP·물가 | 국가통계 포털 탐색; 인증·API 여부 추가 실사 | 기관 확인·경로 추가 조사 | https://data.stats.gov.cn/ |

## 대표 유형 및 테스트 연결

| 제공 방식 | 대표 기관 | 필요한 어댑터/전략 | 대표 사례 |
|---|---|---|---|
| SDMX 메타데이터 탐색 | IMF, BIS, ECB, OECD, Eurostat | dataflow·DSD·codes·series key | A/B/E/H |
| 카탈로그+파라미터 API | BEA, e-Stat | dataset list·param discovery·auth | D/F |
| 시계열 REST·매핑 | FRED, BOJ, Bundesbank | source→series ID·변경 감지·vintage | E/F |
| 웹 통계표/파일 | Treasury TIC, MOF, SAFE, BoE | HTML/CSV/TSV/TXT/ZIP, 헤더·자료해석 | C/F/G |
| 다국어 사이트·불확실 접근 | SAFE, PBOC, NBS | 기관 분리·중국어 검색·미확인 표기 | G |

## 중요한 사전 조사 사실과 설계 함의

1. IMF는 SDMX 2.1 및 3.0 API를 제공. 첫 API 질의에 앞서 dataflow/structure 조사 필요.
2. BIS는 SDMX REST와 ZIP bulk(CSV·SDMX) 제공. 소규모 요청과 대용량 일괄 수집을 별도 전략으로 설계.
3. 미국 Treasury TIC 공식 가이드는 주로 TXT·CSV·HTML·PDF 등 형태를 설명하고, 악성코드 우려로 공식 Excel 파일 사용을 피한다고 명시. **TIC=Excel/XLSX로 가정 금지**. 다만 범용 파서는 Excel 지원.
4. Federal Reserve Board DDP는 FRED 연계와 DDP 단계적 종료 관련 공지를 포함. 기존 series ID→FRED series ID 변환을 별도 관리.
5. Eurostat는 CATALOGUE API와 데이터 질의용 SDMX·Statistics API가 구분됨. 검색 API와 수집 API 분리를 입증하는 사례.
6. BOJ는 2026년 2월 18일 JSON·CSV API 제공 시작. MOF의 국제수지 페이지에서 BOJ의 더 상세한 시계열로 연결됨.
7. e-Stat은 표 목록→메타 정보→값 조회로 나뉘며 Application ID를 요구.
8. Bundesbank는 통계 포털 개편과 시계열 키 변경 이력이 있어 version/crosswalk 검증 필요.
9. 중국 3개 기관은 통계별 담당 주체를 구분하고, 공식 제공 경로를 하나로 단정하지 않는다.
10. **사이트 안내를 읽은 상태와 실제 호출에 성공한 상태는 다른 필드**로 기록한다.

## 기관 프로필 권장 항목(구현 목표)

```yaml
institution_id: INT-02
name: Bank for International Settlements
jurisdiction: international
verified_official_domains:
  - bis.org
  - data.bis.org
  - stats.bis.org
discovery_channels: [official_portal, docs, sdmx, bulk_download]
retrieval_formats: [sdmx, csv, zip, excel_manual_export]
user_guides:
  - https://data.bis.org/help/export
metadata_capabilities: [dataflow, datastructure, codes]
verification:
  docs_checked_on: '2026-10-24'
  endpoint_live_tested: false
  ingestion_tested: false
  status: docs_verified
known_issues: []
```

## 재검증 트리거

공식 문서 갱신, 404/403, 구조/단위/ID 변화, 기존 메타데이터 오래됨, 사용자 피드백, 수집 결과 급변, 관련 API 서비스 종료 공지. 기관별 프로필 `verified_at`와 변경 내역을 보존.

## 03회차 제한 경로 검증 추가 — INT-04 / 2026-10-24

- 경로: World Bank Indicators API v2, USA / WDI source 2 / NY.GDP.MKTP.CD / 2020:2022.
- 공식 인증 안내 재확인: API 키 불필요. `auth_requirement=none`, `credential_env_var=null`.
- endpoint_live_tested=true, raw_download_tested=true, minimal_parse_tested=true.
  전체 기관/지표 지원, 정규화·종합 품질 검증 또는 Gate A 통과를 의미하지 않는다.
- 실제 성공 시각: 2026-10-24T02:12:07.442440+00:00. HTTP 200, 원본 724 bytes, 관측 행 3개.
- 상세 근거/한계: docs/connectors/WORLDBANK.md 및 docs/ITERATION_03_REPORT.md.
  다른 기관의 기존 검증 상태는 갱신하지 않았다.

## 04회차 Gate A 추가 검증 — INT-04 / 2026-10-25

- 기존과 같은 USA / source 2 / `NY.GDP.MKTP.CD` / 2020:2022 file 경로를 대상으로 실제 수집에서 원본·manifest hash, 정규화 관측치, 품질 결과, feedback 기록까지 연결했다.
- 저장 보고서 `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`에서 `live_path_passed=true`, HTTP 200, 724 bytes, 검증 통과와 관측치 3개를 확인했다. 저장 파일들의 원본 및 manifest SHA256도 보고서 값과 일치한다.
- 전체 433개 pytest와 Ruff가 통과했다. 이 테스트는 결정적 로컬 검증이며 Gate A fixture가 실제 HTTP를 사용하지 않는다.
- Gate A는 World Bank의 이 고정 경로에 한정한다. 기관대장의 다른 프로필은 이전 조사 상태를 유지한다. 단위/주기는 미상으로 남았고, 데이터셋별 이용 조건·재배포 가능성은 별도 확인 대상이다.
- 상세 기록: `docs/ITERATION_04_REPORT.md`.

## 2026-10-26 BLS·Census 제한 live 수집 추가 확인

- BLS: `https://api.bls.gov/publicAPI/v2/timeseries/data/`, CPI series `CUUR0000SA0`,
  2024년. 등록 키를 포함한 API v2 요청에서 `REQUEST_SUCCEEDED`, 12개 월 관측치 수신.
- Census: `https://api.census.gov/data/2022/acs/acs1`, 변수 `NAME`, `B01001_001E`,
  geography `state:06`. 등록 키를 포함한 요청에서 HTTP 200과 한 행 수신. API 응답이
  덧붙이는 `state` 열을 원본 observation dimension에 보존한다.
- 근거: `docs/ITERATION_05_REPORT.md`와 `data/raw/{bls,census}/...` manifest/response.
  이 실측은 선택한 각 API 호출의 연결·응답 파싱을 확인한다. 시리즈/변수 정의와 단위,
  전체 카탈로그·호출한도·재배포 조건을 검증하지 않았으며 기관 전체 준비 완료를 뜻하지 않는다.

## 2026-10-26 기관별 안내와 전략 근거 추가

- BLS API v2 공식 안내(HTTP 200)에서 단일 series의 3년 요청, 등록된 multi-series 3년 요청의
  최대 50개 ID, 20년 확장 요청과 optional fields의 key 조건을 확인했다. 현재 커넥터는
  최대 20개 ID로 더 보수적으로 제한한다.
- Census Data API User Guide·API key·Query Limits·Core Concepts·Terms 페이지(HTTP 200)를
  보존했다. 2026 가이드는 data query마다 API key가 필요하고 query당 최대 50개 변수를
  허용한다고 적는다. dataset별 필수 변수와 지리 코드는 별도 확인한다.
- IMF API 페이지(HTTP 200)는 SDMX 2.1 및 3.0 API를 안내하고 Swagger 사용에 beta portal
  로그인을 요구한다. 이 저장소에는 IMF 수집기가 없다.
- Treasury TIC 포털과 사용 안내(HTTP 200)는 대부분 TXT/tab-delimited TXT/CSV/HTML/PDF를
  안내하고 Excel은 제공하지 않는다고 설명하며, 연간 securities 일부 MHT 예외를 명시한다.
  TIC 수집기는 아직 없다.
- 원본 HTML·추출 텍스트·manifest는 `data/raw/guides/<guide_id>/...`에 쓰고 덮어쓰지 않는다.
  근거와 한계는 `docs/ITERATION_06_REPORT.md`에 정리했다.

## 2026-10-26 BLS·Census variable metadata live 확인

- BLS Public Data API v2 `catalog=true`: series `CUUR0000SA0`, 2024 요청 범위, HTTP 200,
  1 catalogue record. API 응답에서 이름, 지리 범위, 계절조정, 항목 및 조사 식별정보를
  받았다. 정의·단위·주기·시간 범위는 미상으로 유지했다.
- Census ACS 2022 1-year `B01001_001E` variable endpoint: HTTP 200, 1 metadata record.
  label, concept, predicate type 등 원문 속성을 보존했다. 이 응답만으로 정의·단위·주기·
  지리 범위를 확정하지 않았다.
- raw JSON·credential-free request/manifest는 `data/raw/metadata/{bls,census}/<package>/`,
  별도 normalized JSON은 `data/processed/metadata/{bls,census}/<package>/`에 저장했다.
  저장된 raw·normalized SHA256은 각 manifest와 일치하고 API key 문자열은 해당 파일들에 없다.
- 이 확인은 선택한 두 metadata record의 live 경로다. 전체 API catalogue 검색, 다른 BLS/Census
  변수 정의나 license/reuse 조건 검증은 아니다. 보고서: `docs/ITERATION_07_REPORT.md`.

## 2026-10-26 Treasury TIC Table 5 live file intake

- 공식 TIC 포털의 "direct link to the MFH table"가 연결하는 `slt_table5.txt`를 한 번 요청해
  HTTP 200, `text/plain`, 3,804 bytes를 확인했다. 포털·사용 안내 페이지에서 확인한 링크와
  응답 내부의 출처 URL이 일치한다.
- 저장된 원본을 일반 tabular intake에 넣어 TSV 형태, 6행 헤더를 읽고 manifest와 normalized
  table을 만들었다. raw와 normalized SHA256이 각각 저장 파일과 일치한다. 36개국, 2025-08~
  2026-08 월별 13개 기간의 표이며 일본 2026-08 값은 1,068.3이다. 표 설명은 기간 말 보유잔액,
  십억 달러 단위를 명시한다.
- 이는 실제 파일 1건의 출처·파싱 실측이지 TIC 자동 다운로드 어댑터나 전체 TIC 지원이 아니다.
  보유잔액을 증권 거래액과 혼동하지 않도록 범위를 확인했으며, 변경된 실제 후속 파일은 아직
  요청하지 않았다. 상세·manifest 경로는 `docs/ITERATION_10_REPORT.md` 참조.

## 2026-10-26 BIS bulk 및 BOJ API 경로 실측

- BIS 공식 bulk 다운로드 페이지 `https://data.bis.org/bulkdownload`는 HTTP 200으로 저장했고,
  페이지에서 `WS_GLI_csv_col.zip`을 연결했다. 해당 ZIP은 HTTP 200, 104,833 bytes,
  SHA256 `aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d`였다.
  일반 ZIP/CSV intake 결과는 225행·220열이고 raw, manifest, normalized table 해시가 일치한다.
  여러 series와 단위가 섞여 있어 자동으로 단일 시계열로 해석하지 않는다. 평면형 대안 ZIP은
  HTTP 503을 반환해 재시도하지 않았다.
- BOJ의 공식 API 공지는 HTTP 200이며 JSON/CSV 시계열 API 제공을 설명한다. 공지에서 연결된
  API user manual은 HTTP 403을 반환해 본문 없이 응답 상태만 기록했다. 요청 규격과 series ID를
  확립하지 못해 BOJ observation API 요청은 만들지 않았고, 플랫폼 collector 지원 상태는
  `BLOCKED`다. 상세 응답 manifest와 한계는 `docs/ITERATION_10_REPORT.md`에 있다.
- 이 결과는 BIS 한 파일의 intake와 BOJ 공식 안내/접근 상태만 확인한다. BIS SDMX 전체 지원,
  BOJ 데이터 API 연결, source revision 감지 또는 Gate C 통과를 뜻하지 않는다.

## 2026-10-26 BOJ API manual 재확인

- 공식 BOJ 공지는 HTTP 200, 36,614 bytes, SHA256
  `1c48b9491cbfc43d7b8100278ef6a432a9fcb4996a34795c06e2f396d7d0db68`였다. 현재 notice는 같은 공식
  `api_manual_en.pdf`와 `api_notice_en.pdf`를 링크한다.
- 매뉴얼 PDF는 HTTP 200, `application/pdf`, 857,117 bytes, SHA256
  `8e289fb77b9e3f80569206d27059eeb3f35e824facff1c339670179aad5ba9cd`, 27 pages다. 표지 날짜는
  2026-02-18이다. 이전 시도는 HTTP 403만 기록하고 body/hash를 저장하지 않아 이 PDF가 그때보다
  수정됐는지는 판정할 수 없다.
- 매뉴얼은 `/api/v1/getMetadata`, `/getDataLayer`, `/getDataCode`, `db`, `code`, `layer`,
  `frequency`, 기간, 출력 형식 및 `STARTPOSITION`을 설명한다. `/getDataCode`는 요청당 series
  code 250개·자료점 60,000개 상한, `/getDataLayer`의 탐색 상한은 1,250개로 기재한다.
- limit 절 일부는 endpoint를 `/getLayerCode`로 부르지만 구조·예제 절은 `/getDataLayer`로 기재한다.
  이 표기 차이는 실제 endpoint 호출 전에 공식 API로 확인해야 한다. 이번 재검토에서는 observation
  API 요청을 보내지 않았다. 수집 지원 상태는 매뉴얼 접근 차단에서 `collection_not_implemented`로
  바뀌었고, series 매핑·collector·실제 데이터 응답은 미검증이다.
- 원본 PDF와 manifest는 gitignored `data/raw/guides/boj_api_manual/be0d3f61ef264b1cb715bfd8b2ef9336/`
  아래에 보존했다. 자세한 기록은 `docs/GATE_C_REVIEW_2026_10_26.md`와 D-071에 있다.

## 2026-10-26 BOJ metadata/data endpoint smoke — D-072/D-073

이 항목은 위 manual 재확인 뒤 수행한 제한 API 실측이며, collector 지원 상태를 바꾸지 않는다.

- 공식 `getMetadata`의 FM08 응답과 `getDataCode`의 FXERD01/202609 응답은 각각 두 번 요청해 모두
  HTTP/JSON STATUS 200이었다. FXERD01은 Tokyo Market 09:00 JST 달러/엔 현물 시계열이며 unit은
  Yen per U.S. Dollar, frequency는 DAILY로 metadata에서 확인했다.
- 요청 범위 응답은 30일, 숫자 19개와 null 11개다. 반복 실행에서 관측 날짜/값은 같았고 동적 응답
  `DATE`만 달랐다. 결측은 원본 null로 유지했다.
- 이 smoke 당시에는 BOJ 재사용 adapter, source mapping catalog, Orchestrator task,
  natural failure recovery가 미구현/미검증이었다. 상세와 hashes는
  `docs/BOJ_LIVE_RECHECK_2026_10_26.md`에 있다.

## 2026-10-26 BOJ limited collector follow-up

- `macroatlas collect boj-fxer --month 202609 --live`가 공식 metadata와 data를 각각 한 번 요청해
  동일 Orchestrator task로 저장했다. HTTP/JSON STATUS 200, 30 daily observations, 11 null 값이
  보존됐고 제한된 structural quality 검사에 통과했다.
- 이 구현은 FM08/FXERD01 한 달에만 적용된다. 다른 BOJ series나 기관 전반 지원으로 확대하지 않으며,
  자연 provider failure/resume 증거도 새로 생기지 않았다. 구현 상세는 `docs/connectors/BOJ.md`다.
