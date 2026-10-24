# Institution Catalog — 국제금융 통계기관 사전 조사대장

> 확인 기준일 2026-10-24. **상태 구분:** `공식 문서 확인` = 공식 제공 방식 확인 / `기관 확인·경로 추가 조사` = 공식 기관 존재 및 통계 주제 확인, 접근 방법·구체 엔드포인트 미검증. 어느 상태도 Python 수집 성공을 뜻하지 않는다. 링크·접근 조건은 구현 시 재검증한다.

## 초기 기관·서비스 21개

| ID | 지역 | 기관/서비스 | 대표 주제 | 관찰된 접근 유형·특징 | 조사 상태 | 공식 출처 |
|---|---|---|---|---|---|---|
| INT-01 | 국제 | IMF | BOP/IIP, IFS·외환·거시 | SDMX 2.1/3.0 API, Data Portal 문서 | 공식 문서 확인 | https://data.imf.org/en/Resource-Pages/IMF-API |
| INT-02 | 국제 | BIS | 국제은행·글로벌 유동성·파생상품 | SDMX REST, CSV/SDMX ZIP bulk, Excel 수동 export | 공식 문서 확인 | https://stats.bis.org/api-doc/v1/ ; https://data.bis.org/bulkdownload |
| INT-03 | 국제 | OECD | GDP·고용·산업·국가비교 | Data Explorer SDMX API·쿼리 빌더, rate limit | 공식 문서 확인 | https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html |
| INT-04 | 국제 | World Bank | WDI 등 국가별 지표 | Indicators API v2, 국가·지표 기반 | 공식 문서 확인 | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 |
| US-01 | 미국 | Federal Reserve Board | 금리·금융계정·통화·대출 | DDP·공표통계·FRED 매핑, 2026~27 전환 예고 | 공식 문서 확인 | https://www.federalreserve.gov/data/data-download-fred-information.htm |
| US-02 | 미국 | St. Louis Fed FRED/ALFRED | 다양한 미 거시시계열·vintage | REST API, release/source/series 검색, 인증 | 공식 문서 확인 | https://fred.stlouisfed.org/docs/api/fred/overview.html |
| US-03 | 미국 | Treasury TIC | 미국 증권의 외국인 보유·거래 | 공식 웹표·CSV/TXT/HTML/PDF·아카이브; TIC 사용안내 | 공식 문서 확인 | https://home.treasury.gov/data/treasury-international-capital-tic-system ; https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic |
| US-04 | 미국 | BEA | GDP, BOP, IIP, 직접·증권투자 | API 키·dataset/parameter 목록 선탐색·JSON/XML | 공식 문서 확인 | https://apps.bea.gov/API/swagger/index.htm |
| US-05 | 미국 | BLS | CPI, PPI, 고용 | 시계열 API, 코드 식별, JSON | 공식 문서 확인 | https://www.bls.gov/audience/developers.htm |
| US-06 | 미국 | Census Bureau | 무역·산업·인구 | 공식 통계·API 계열 확인 필요 | 기관 확인·경로 추가 조사 | https://www.census.gov/data.html |
| EU-01 | 유로존 | ECB | 금리·환율·은행·신용 | SDMX REST, metadata-driven data discovery | 공식 문서 확인 | https://data.ecb.europa.eu/help/api/overview |
| EU-02 | EU | Eurostat | GDP·HICP·무역·국가별 통계 | CATALOGUE API 별도, SDMX 2.1/3.0·JSON-stat | 공식 문서 확인 | https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction |
| EU-03 | 독일 | Bundesbank | 독일·유로 금융/경제 시계열 | 새 통계포털·SDMX REST, 구 시계열 키 매핑 | 공식 문서 확인 | https://www.bundesbank.de/en/statistics/time-series-and-real-time-data |
| EU-04 | 영국 | Bank of England | 통화·금융·금리 | Bankstats IADB 검색, 다운로드·코드 기반 탐색 | 공식 문서 확인 | https://www.bankofengland.co.uk/boeapps/database/help.asp |
| EU-05 | 프랑스 | INSEE | 생산·물가·거시시계열 | SDMX 2.1 웹서비스, idbank 단위 시계열 | 공식 문서 확인 | https://www.insee.fr/en/information/2868055 |
| JP-01 | 일본 | Bank of Japan | 금융·금리·국제수지 | 2026-02-18 JSON/CSV API 도입, flat files 병행 | 공식 문서 확인 | https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm |
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

## 05회차 fixture 기반 기관·사이트 탐색 — 2026-10-25

- 기존 문서 조사에서 기록한 INT-02의 data.bis.org / stats.bis.org 및 US-03의 home.treasury.gov를 입력 후보 도메인으로 사용했다. 이 회차에서 기관대장의 도메인 근거, endpoint_live_tested 또는 ingestion_tested 상태를 새로 검증하거나 변경하지 않았다.
- BIS HTML 메뉴 fixture에서 통계 포털과 SDMX 문서 링크를 분류했고, Treasury TIC XML sitemap fixture에서 공식 호스트 URL을 추출했다. 두 fixture 본문은 합성 데이터이며 실제 사이트에서 가져오지 않았다.
- 생성 프로필의 verified_at은 기존 공식 문서 확인일을 가리킨다. discovery_run_at과 fixture 근거는 별도 필드로 남고, site_live_tested=false / links_live_tested=false다.
- 외부 호스트는 공식 링크로 승격하지 않는다. 외부 URL 경로와 query는 저장하지 않고 호스트, 출처 문서, 탐색 전략만 external_candidate 근거로 기록한다.
- 프로필 저장 구현은 테스트용 SQLite DB에서 재시작 후 조회·중복 저장·append-only 이력을 검증했다. 실제 프로젝트 DB에는 프로필을 쓰지 않았다.
- 상세 범위와 한계: docs/ITERATION_05_REPORT.md.
