# Institution Catalog — 국제금융 통계기관 사전 조사대장

Iteration 29: TIC MFH 역사·January 2023 Table 3D, BoE IUDBEDR의 공식 CSV 경로가 제한 구현됐습니다. API 상태는 미확인으로 유지하고 API 4개·파일 3개 데이터셋 계약의 synthetic 저장 검증을 [별도 명세](../../developer/connectors/DATASET_CONTRACTS.md)에서 구분합니다.

> 기관 카탈로그 조사 기준일 2026-10-24; 전체 21개 API 상태 재검토일 2026-10-25. **상태 구분:** `documented` = 공식 API 명세 확인 / `unconfirmed` = 이번 검토에서 공식 API 명세를 찾지 못함 / `not_offered` = 공식 문서가 API 미제공을 명시. 어느 상태도 Python 수집 성공을 뜻하지 않는다. 링크·접근 조건은 구현 시 재검증한다.

> MacroAtlas 자체의 기관별 실행 구현은 [구축 상태표](INSTITUTION_IMPLEMENTATION_STATUS.md)에 별도로 분류했다. API 문서 보유와 MacroAtlas connector 구현은 서로 다른 상태다.

## 초기 기관·서비스 21개

| ID | 지역 | 기관/서비스 | 대표 주제 | 관찰된 접근 유형·특징 | 조사 상태 | 공식 출처 |
|---|---|---|---|---|---|---|
| INT-01 | 국제 | IMF | BOP/IIP, IFS·외환·거시 | SDMX 2.1/3.0 API, Data Portal 문서 | 공식 문서 확인 | https://data.imf.org/en/Resource-Pages/IMF-API |
| INT-02 | 국제 | BIS | 국제은행·글로벌 유동성·파생상품 | SDMX REST 2.1, CSV/SDMX ZIP bulk, Excel 수동 export | 공식 문서 확인 | https://stats.bis.org/api-doc/v2/ ; https://data.bis.org/bulkdownload |
| INT-03 | 국제 | OECD | GDP·고용·산업·국가비교 | Data Explorer SDMX API·쿼리 빌더, rate limit | 공식 문서 확인 | https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html |
| INT-04 | 국제 | World Bank | WDI 등 국가별 지표 | Indicators API v2, 국가·지표 기반 | 공식 문서 확인 | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 |
| US-01 | 미국 | Federal Reserve Board | 금리·금융계정·통화·대출 | DDP 자료 일부를 FRED API로 제공; DDP 2026~27 전환 안내 | API documented via FRED; provider 분리 | https://www.federalreserve.gov/data/data-download-fred-information.htm |
| US-02 | 미국 | St. Louis Fed FRED/ALFRED | 다양한 미 거시시계열·vintage | REST API v1/v2, release/source/series 검색, 인증 | 공식 API 문서 확인 | https://fred.stlouisfed.org/docs/api/fred/overview.html |
| US-03 | 미국 | Treasury TIC | 미국 증권의 외국인 보유·거래 | 공식 웹표·CSV/TXT/HTML/PDF·ZIP 아카이브; API 명세 미확인 | 공식 파일 경로 확인; API unconfirmed | https://home.treasury.gov/data/treasury-international-capital-tic-system ; https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic |
| US-04 | 미국 | BEA | GDP, BOP, IIP, 직접·증권투자 | API 키·dataset/parameter 목록 선탐색·JSON/XML | 공식 문서 확인 | https://apps.bea.gov/API/swagger/index.htm |
| US-05 | 미국 | BLS | CPI, PPI, 고용 | Public Data API v1/v2, JSON/XLSX; 등록·호출 제한 차이 | 공식 API 문서 확인 | https://www.bls.gov/developers/home.htm |
| US-06 | 미국 | Census Bureau | 무역·산업·인구 | Census Data API; 2026 가이드에서 data query API key 필수 | 공식 API 문서 확인 | https://www.census.gov/data/developers.html |
| EU-01 | 유로존 | ECB | 금리·환율·은행·신용 | SDMX REST, metadata-driven data discovery | 공식 문서 확인 | https://data.ecb.europa.eu/help/api/overview |
| EU-02 | EU | Eurostat | GDP·HICP·무역·국가별 통계 | CATALOGUE API 별도, SDMX 2.1/3.0·JSON-stat | 공식 문서 확인 | https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction |
| EU-03 | 독일 | Bundesbank | 독일·유로 금융/경제 시계열 | SDMX REST API; SDMX-ML/CSV/JSON 및 metadata | 공식 API 문서 확인; 인증 미확인 | https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448 |
| EU-04 | 영국 | Bank of England | 통화·금융·금리 | Bankstats database와 HTML/Excel/XML/CSV; 일반 API 사양 미확인 | API unconfirmed; 공식 download 문서 확인 | https://www.bankofengland.co.uk/boeapps/database/ |
| EU-05 | 프랑스 | INSEE | 생산·물가·거시시계열 | SDMX 2.1 REST 웹서비스, BDM/idbank 단위 시계열 | 공식 API 문서 확인; 인증 미확인 | https://www.insee.fr/en/information/2868055 |
| JP-01 | 일본 | Bank of Japan | 금융·금리·국제수지 | 2026-02-18 JSON/CSV API 도입, flat files 병행 | 공식 문서 확인 | https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm |
| JP-02 | 일본 | Ministry of Finance | 국제수지·직접·증권투자 | 통계 포털·일부 CSV/SDMX; MOF 일반 API 명세 미확인 | API unconfirmed; 표별 파일/배포 경로 확인 | https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/index.htm |
| JP-03 | 일본 | e-Stat | 정부 통계표·코드북 | 표 목록→메타→통계값 API, 등록/Application ID | 공식 문서 확인 | https://www.e-stat.go.jp/api/en/api-info |
| CN-01 | 중국 | PBOC | 통화량·대출·사회융자 | 공식 통계 공표 경로 확인; 일반 공개 API 명세 미발견 | API unconfirmed; 표별 조사 필요 | https://www.pbc.gov.cn/en/ |
| CN-02 | 중국 | SAFE | BOP·IIP·외환보유액·외채 | 공식 통계 포털·통계 게시물 확인; 공개 API 명세 미발견 | API unconfirmed; 표별 조사 필요 | https://www.safe.gov.cn/en/ |
| CN-03 | 중국 | NBS | 생산·GDP·물가 | 국가데이터 포털·이용 약관 확인; 공개 API 명세 미발견 | API unconfirmed; 테이블별 접근 조사 | https://data.stats.gov.cn/ |

## 21개 기관 API 우선 상태 스냅샷 — 2026-10-25

`documented`는 공식 API 문서가 확인됐다는 뜻이고 실제 호출 성공을 뜻하지 않는다. `unconfirmed`는 이번 공식 문서 검토 범위에서 API 명세를 찾지 못한 상태며 API 부재를 뜻하지 않는다. 기관/통계의 API 제공 여부와 API 운용 주체, 구현·fixture·live 상태를 구분한다. 실행 가능한 레지스트리의 원본은 `src/macro_data_platform/discovery/source_registry.py`다.

| 기관 ID | A–H 시나리오 | 기관 / 제공 서비스 | API 상태·우선순위 | API 계열 / 제공 주체 | 인증 안내 | 구현·fixture | live |
|---|---|---|---|---|---|---|---|
| INT-01 | A | IMF | `documented` / API 우선 | SDMX 2.1·3.0; [공식 API 안내](https://data.imf.org/en/Resource-Pages/IMF-API) | 선택 public metadata 무키; private/Swagger auth 별도 | partial 2.1 metadata client·synthetic/recorded fixture | CPI dataflow 5.0.0 단건 HTTP 200·계약·archive/hash 통과 |
| INT-02 | B | BIS | `documented` / API 우선 | SDMX REST 2.1; [공식 명세](https://stats.bis.org/api-doc/v2/) | 키 불필요로 안내 | partial raw-response client·mock route; 실제 payload fixture 없음 | 미실행 |
| INT-03 | H | OECD | `documented` / API 우선 | SDMX REST v1·v2; [공식 Swagger](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1) | 미확인; 외부 접근/인증 live 미검증 | partial raw-response client·mock route; 실제 payload fixture 없음 | 미실행 |
| INT-04 | H | World Bank | `documented` / API 우선 | Indicators API v2; [공식 안내](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392) | 키 불필요 | 미국 GDP 고정 경로 일부 | 제한 live: USA/WDI/GDP 한 경로 |
| US-01 | — | Federal Reserve Board | `documented` / API 우선 | Board DDP series는 FRED API 경유; [Board 전환 안내](https://www.federalreserve.gov/data/data-download-fred-information.htm) · 제공 주체: Federal Reserve Bank of St. Louis | `FRED_API_KEY` 필요 | 어댑터·fixture 없음; DDP 전환/ID crosswalk 확인 필요 | 미실행 |
| US-02 | — | St. Louis Fed FRED/ALFRED | `documented` / API 우선 | FRED API v1·v2; [공식 문서](https://fred.stlouisfed.org/docs/api/fred/) | `FRED_API_KEY` 필요; 시리즈별 이용 조건도 확인 | partial v1 metadata·명시적 page client, synthetic fixture/file round-trip; 원기관 자동 추정 없음 | 미실행 |
| US-03 | C | Treasury TIC | `unconfirmed` / API 조사 우선 | API 명세 미확인; [공식 TIC 이용 안내](https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic) | 미확인 | CSV/코드북 파싱 fixture; 공식 TXT·CSV·HTML·PDF·ZIP 자료 경로 확인 | 미실행 |
| US-04 | D | BEA | `documented` / API 우선 | BEA REST JSON/XML; [공식 API](https://apps.bea.gov/API/docs/index.htm) | `BEA_API_KEY` 필요 | JSON GET·synthetic/recorded metadata fixture; 일반 workflow 미연결 | GetDataSetList 13개 metadata·archive/read-back 부분 통과 |
| US-05 | — | Bureau of Labor Statistics | `documented` / API 우선 | Public Data API v1·v2; [개발자 안내](https://www.bls.gov/developers/home.htm) | 현재 client는 무키 v1만 사용, v2 미구현 | partial v1 POST client (25 series·10년), synthetic fixture/file round-trip | 미실행 |
| US-06 | — | U.S. Census Bureau | `documented` / API 우선 | Census Data API; [공식 가이드](https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html) | 데이터에 `CENSUS_API_KEY` 필요, metadata는 무키 | partial metadata·header/row client, synthetic fixture/file round-trip | 미실행 |
| EU-01 | E | ECB | `documented` / API 우선 | SDMX REST 2.1; [공식 API 안내](https://data.ecb.europa.eu/help/api/overview) | 공개 API, 키 불필요 | partial raw-response client·mock route; 실제 payload fixture 없음 | 미실행 |
| EU-02 | E | Eurostat | `documented` / API 우선 | Catalogue, SDMX 2.1·3.0, Statistics JSON-stat; [공식 API 안내](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction) | 키 불필요 | partial raw-response client·mock route; 실제 payload fixture 없음 | 미실행 |
| EU-03 | — | Deutsche Bundesbank | `documented` / API 우선 | SDMX REST; [공식 API 가이드](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448) | 미확인; 명세에 근거한 정책 미등록 | partial raw-response client·mock route; 실제 payload fixture 없음 | 미실행 |
| EU-04 | — | Bank of England | `unconfirmed` / API 조사 우선 | 일반 API 명세 미발견; [공식 통계 FAQ](https://www.bankofengland.co.uk/statistics/faqs) | 미확인 | 공식 DB HTML·Excel·XML·CSV 다운로드 안내; API 부재로 확정하지 않음 | 미실행 |
| EU-05 | — | INSEE | `documented` / API 우선 | SDMX 2.1 REST·BDM/idbank; [공식 서비스 안내](https://www.insee.fr/en/information/2868055) | 직접 BDM metadata 단발 무키 확인; portal auth 별도 | partial client·synthetic/recorded metadata fixture | CL_NATURE 1.0 codelist HTTP 200·계약·archive/hash 통과; 옛 DSD 404 보존 |
| JP-01 | F | Bank of Japan | `documented` / API 우선 | Time-Series Data Search REST JSON/CSV; [공식 안내](https://www.stat-search.boj.or.jp/info/nme_aphelp_en.html) | 누구나 사용할 수 있다고 안내 | 기관 어댑터 없음 | 미실행 |
| JP-02 | F | Japan Ministry of Finance | `unconfirmed` / API 조사 우선 | MOF 고유 API 명세 미발견; [공식 통계](https://www.mof.go.jp/english/statistics/index.html) | 미확인 | 일부 CSV·SDMX 파일; e-Stat 등 배포 경로는 표별 확인 필요 | 미실행 |
| JP-03 | F | e-Stat | `documented` / API 우선 | REST API v3.0; [공식 사양](https://www.e-stat.go.jp/api/en/api-info/api-spec) | `ESTAT_APP_ID` 필요 | JSON GET·synthetic/recorded metadata fixture; 일반 workflow 미연결 | getStatsList(lang=E, limit=1) metadata·archive/read-back 부분 통과 |
| CN-01 | G | PBOC | `unconfirmed` / API 조사 우선 | 공개 API 명세 미발견; [공식 사이트](https://www.pbc.gov.cn/en/) | 미확인 | 사이트 탐색 fixture만; 수집 어댑터 없음 | 미실행 |
| CN-02 | G | SAFE | `unconfirmed` / API 조사 우선 | 공개 API 명세 미발견; [공식 통계 포털](https://www.safe.gov.cn/en/) | 미확인 | 기관별 통계 공표 페이지; 수집 어댑터 없음 | 미실행 |
| CN-03 | G | NBS China | `unconfirmed` / API 조사 우선 | 공개 API 명세 미발견; [National Data 포털](https://data.stats.gov.cn/) | 미확인 | 국가 데이터 포털; 테이블별 접근 형식·이용 조건 확인 필요 | 미실행 |

집계: 공식 API 문서 확인 **15**, API 여부 미확인 **6**, 공식 문서가 API 미제공을 확인한 기관 **0**. 특히 `unconfirmed`를 `not_offered`로 바꾸지 않았다. 문서화된 API도 특정 dataset 전체를 제공한다거나 어댑터가 구현됐다는 뜻은 아니다.

Iteration 24 기준 구현 상태: limited API clients **9/21** (World Bank·BEA·e-Stat 및 SDMX 6곳), fixture-only **5/21**, API client 미구현 **7/21**. 6개 SDMX clients의 정확한 raw request scope와 인증·payload·live 한계는 [SDMX connector 명세](../../developer/connectors/SDMX_FAMILY.md)를 참고한다. 여기서 client 구현은 전기관 수집 준비나 live 통과를 의미하지 않는다.

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
- 상세 근거/한계: docs/developer/connectors/WORLDBANK.md 및 docs/developer/history/ITERATION_03_REPORT.md.
  다른 기관의 기존 검증 상태는 갱신하지 않았다.

## 04회차 Gate A 추가 검증 — INT-04 / 2026-10-25

- 기존과 같은 USA / source 2 / `NY.GDP.MKTP.CD` / 2020:2022 file 경로를 대상으로 실제 수집에서 원본·manifest hash, 정규화 관측치, 품질 결과, feedback 기록까지 연결했다.
- 저장 보고서 `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`에서 `live_path_passed=true`, HTTP 200, 724 bytes, 검증 통과와 관측치 3개를 확인했다. 저장 파일들의 원본 및 manifest SHA256도 보고서 값과 일치한다.
- 전체 433개 pytest와 Ruff가 통과했다. 이 테스트는 결정적 로컬 검증이며 Gate A fixture가 실제 HTTP를 사용하지 않는다.
- Gate A는 World Bank의 이 고정 경로에 한정한다. 기관대장의 다른 프로필은 이전 조사 상태를 유지한다. 단위/주기는 미상으로 남았고, 데이터셋별 이용 조건·재배포 가능성은 별도 확인 대상이다.
- 상세 기록: `docs/developer/history/ITERATION_04_REPORT.md`.

## 05회차 fixture 기반 기관·사이트 탐색 — 2026-10-25

- 기존 문서 조사에서 기록한 INT-02의 data.bis.org / stats.bis.org 및 US-03의 home.treasury.gov를 입력 후보 도메인으로 사용했다. 이 회차에서 기관대장의 도메인 근거, endpoint_live_tested 또는 ingestion_tested 상태를 새로 검증하거나 변경하지 않았다.
- BIS HTML 메뉴 fixture에서 통계 포털과 SDMX 문서 링크를 분류했고, Treasury TIC XML sitemap fixture에서 공식 호스트 URL을 추출했다. 두 fixture 본문은 합성 데이터이며 실제 사이트에서 가져오지 않았다.
- 생성 프로필의 verified_at은 기존 공식 문서 확인일을 가리킨다. discovery_run_at과 fixture 근거는 별도 필드로 남고, site_live_tested=false / links_live_tested=false다.
- 외부 호스트는 공식 링크로 승격하지 않는다. 외부 URL 경로와 query는 저장하지 않고 호스트, 출처 문서, 탐색 전략만 external_candidate 근거로 기록한다.
- 프로필 저장 구현은 테스트용 SQLite DB에서 재시작 후 조회·중복 저장·append-only 이력을 검증했다. 실제 프로젝트 DB에는 프로필을 쓰지 않았다.
- 상세 범위와 한계: docs/developer/history/ITERATION_05_REPORT.md.

## 06회차 fixture 기반 이용 가이드·기관별 전략 — 2026-10-25

- 기존 카탈로그에 기록된 IMF data.imf.org API 안내 URL과 Treasury TIC home.treasury.gov 이용 안내 URL을 기관 후보 도메인 검증 근거로 연결했다. 해당 페이지의 현재 내용·접근성·약관은 이 회차에서 다시 확인하지 않았다.
- IMF SDMX 문서는 API_GUIDE, TIC 합성 문서는 USAGE_POLICY로 명시 분류했다. 파일 본문은 합성 fixture이며 공식 페이지에서 복사하거나 내려받지 않았다.
- 가이드 저장은 원문 bytes와 SHA256, 출처 URL, 문서 유형, 수동 전달된 추출 텍스트·경로, evidence kind/reference, retrieval/expiry/version metadata를 append-only SQLite 스냅샷으로 보존한다. 프로젝트 저장소의 실제 데이터베이스에는 쓰지 않았다.
- site_live_tested, links_live_tested 및 기관별 ingestion 검증 상태를 갱신하지 않았다. 실제 이용 조건 승인이나 Gate B 검증을 뜻하지 않는다.
- 상세 범위와 한계: docs/developer/history/ITERATION_06_REPORT.md.

## 07~08회차 metadata/search fixture 근거 — 2026-10-25

- IMF형 SDMX 구조와 합성 제공 series key, TIC형 추출 코드북·CSV/접근 경로, World Bank형 catalogue를 메타데이터/검색/확인/수집 연결 테스트에 사용했다. IMF/TIC 식별자·본문·파일 URL은 합성 fixture이며 실제 경로가 아니다.
- 메타데이터 원문과 언어·코드·단위·정의·필드/셀 경로를 보존하고 이름 일치만으로 개념을 등가 처리하지 않았다. INT-04를 기존 World Bank 고정 수집 어댑터에 연결하는 fixture도 통과했다.
- 기존 endpoint_live_tested/ingestion_tested와 공식 문서 조사 날짜는 갱신하지 않았다. 새 네트워크 요청·현재 약관 확인·실제 IMF/TIC 수집은 수행하지 않았다.
- 보고서: docs/developer/history/ITERATION_07_REPORT.md, docs/developer/history/ITERATION_08_REPORT.md.
