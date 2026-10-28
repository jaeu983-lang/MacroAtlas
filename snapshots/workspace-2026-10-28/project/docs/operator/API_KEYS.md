# API 키 발급과 로컬 입력

**확인일:** 2026-10-25. 공식 문서·등록 페이지 조사 결과이며, 실제 키 발급·유효성 검사·통계 데이터 API 호출 결과는 아닙니다.

## 지금 준비할 키

기존 BEA·e-Stat 키는 Iteration 31의 metadata 요청에서 작동을 확인했고 기존 값을 사용합니다. **Census·BLS는 사용자 지시로 보류**했으므로 현재 키 입력·재발급을 요구하지 않습니다. 아래 발급 표는 참고 자료입니다. BLS client는 무키 v1 전용이며, 향후 다른 source의 추가 key가 필요하면 그 기관의 공식 auth 근거부터 확인합니다.

| 입력 이름 | 대상과 발급 이유 | 공식 발급 경로 | 받은 뒤 할 일 |
|---|---|---|---|
| `FRED_API_KEY` | FRED/ALFRED 및 FRED가 제공하는 연준 Board 계열. 두 profile에서 같은 FRED 자격 증명을 참조 | [키 발급·조회](https://fredaccount.stlouisfed.org/apikeys), [공식 설명](https://fred.stlouisfed.org/docs/api/api_key.html) | FRED 계정 가입·로그인 → API Keys에서 MacroAtlas용 키 신청 → 발급 키 입력 |
| `CENSUS_API_KEY` | Census **데이터 조회**에 필수 | [키 신청](https://api.census.gov/data/key_signup.html), [발급 절차](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html) | 실제 조직명·이메일과 약관 동의를 입력 → 받은 이메일의 활성화 링크 처리 → 키 입력 |
| `BLS_API_KEY` | 향후 BLS v2용 예약 항목. 현재 v1 client는 사용하지 않음 | [등록](https://data.bls.gov/registrationEngine/), [공식 FAQ](https://www.bls.gov/developers/api_faqs.htm) | 지금은 비워둬도 됨. 추후 v2를 선택하면 이메일 등록 및 최소 매년 갱신 |
| `BEA_API_KEY` | BEA 등록 UserID | [신청](https://apps.bea.gov/api/signup/) | 이름 또는 조직명·이메일·약관 동의 → 받은 UserID 입력 |
| `ESTAT_APP_ID` | e-Stat Application ID | [공식 이용 안내](https://www.e-stat.go.jp/api/api/api/index.php/en/api-info/api-guide) | 계정 가입 시 API 기능 선택 → 마이페이지의 API / Issue Application ID. 공개 사이트가 없으면 URL에 `http://localhost/` 사용 가능 |

FRED는 애플리케이션별 키를 사용하도록 안내하며 각 사용자가 본인 키를 사용해야 합니다. FRED API v1의 `api_key` query 방식과 v2의 bearer header 방식은 후속 adapter에서 API version에 맞춰 적용합니다. 키 발급 자체가 두 API version의 구현을 뜻하지 않습니다.

Census의 과거 안내에 있던 무키 500회/IP 기준을 현재 데이터 조회에 적용하지 않습니다. [2026년 공식 안내](https://www.census.gov/library/video/2026/adrm/requesting-a-census-data-api-key.html)는 데이터 요청의 키 의무화를 명시합니다. [2026년 6월 공식 뉴스레터](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23)는 metadata 조회는 키 없이 허용한다고 별도로 설명합니다.

Iteration 30 진단에서 현재 로컬 Census 키는 공식 `invalid_key.html`로 거부됐습니다. 활성화 링크를 완료했다는 사용자 확인이 있어도 실제 서버 판정은 별도로 봅니다. 발급 메일의 정확한 키를 `.env`에 다시 넣고 필요하면 공식 절차로 재발급하세요. 키를 대화로 보내지 마세요. 코드의 `invalid_api_key`는 키를 출력하지 않는 고정 진단명이며, 자동 redirect follow로 해결하지 않습니다. [진단과 1회 재검증 명령](../developer/testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md).

BLS FAQ의 등록 v2 기준은 하루 500회, 요청당 50개 series·20년이며, 등록 없는 v1은 하루 25회, 요청당 25개 series·10년입니다. 이 한도를 요청 목표량으로 채우는 방식으로 사용하지 않습니다. 자동 갱신 기능은 없습니다.

## 값을 넣는 파일

저장 위치는 저장소 루트 `C:/Projects/MacroAtlas/.env` 하나입니다. 아래 이름 오른쪽 `=` 뒤에 발급받은 값을 입력하고 저장합니다. 빈 항목은 미설정으로 처리합니다.

```ini
BEA_API_KEY=
ESTAT_APP_ID=
FRED_API_KEY=
CENSUS_API_KEY=
BLS_API_KEY=
```

이번 작업은 기존 줄과 값을 보존하고 없는 이름만 빈 줄로 추가합니다. 기존 `MACROATLAS_DATA_DIR`, `MACROATLAS_NETWORK_ENABLED` 설정도 보존합니다. 이 문서나 소스·테스트·대화에는 실제 값을 넣지 않습니다. `.env`는 Git 제외 파일이지만 로컬 평문 파일입니다.

설정 로더는 다섯 이름을 읽을 수 있습니다. **BEA/e-Stat 제한 client와 FRED/Census/BLS v1 client가 구현됐으며 source별 synthetic 응답→파일→read-back을 시험했습니다.** 실제 기관 키 인증·live 호출과 일반 workflow는 별도 미검증입니다. BLS v1은 키를 보내지 않습니다. 값을 저장해도 자동으로 API를 호출하지 않고, 실행 중 서비스는 설정 재로드/재시작이 필요합니다. 같은 이름의 프로세스 환경변수가 `.env`보다 우선합니다.

최신 overlay: Iteration 31에서 기존 BEA/e-Stat 키로 metadata API 1회씩을 성공했고 저장·재조회를 확인했습니다. 이 범위를 다른 dataset·메서드·관측치 전체의 권한으로 일반화하지 않습니다. Census·BLS는 사용자 지시로 보류했으므로 재개 전 key 재입력 요청이나 live retry를 진행하지 않습니다.

## Codex Cloud에서 API 사용

저장소에는 비밀값 없는 [`.env.example`](../../.env.example), API 연결 코드, 기관별 근거 문서, fixture와 테스트가 포함됩니다. 실제 키는 저장소나 대화에 넣지 않습니다. Codex Cloud 환경을 만들고 게시한 뒤, Codex Cloud의 개인 vault/environment variables에 필요한 값만 등록합니다. Cloud task에서 값이 필요할 때 같은 이름으로 선택해 사용하며, 각 작업은 연결된 GitHub 계정이 해당 저장소에 접근할 수 있어야 합니다.

현재 키가 필요한 활성 API 경로는 `BEA_API_KEY`, `ESTAT_APP_ID`, `FRED_API_KEY`입니다. Census와 BLS는 D-101에 따라 보류하며 키를 추가·요청하지 않습니다. BLS v1은 키를 쓰지 않습니다. 선택한 IMF 공개 metadata와 확인된 공개 SDMX/API 경로는 별도 비밀키 없이 요청합니다. 실제 API 호출에는 Codex Cloud 환경의 네트워크 접근 정책도 해당 공식 API 호스트를 허용해야 하며, 이는 GitHub 저장소 권한과 별개입니다.

## 21개 기관·서비스의 발급 판단

아래의 “추가 발급 안내 없음”은 확인한 공개 통계 경로에 별도 키를 신청할 근거가 없다는 뜻입니다. 인증 없음을 명시한 문서, 무키 요청 예시, 아직 미확인인 상태를 구별합니다. 기존 registry의 `authentication=unknown`을 문서 예시만으로 `none`으로 바꾸지 않습니다.

| ID | 기관·서비스 | 이번 발급 판단과 근거 |
|---|---|---|
| INT-01 | IMF | **선택한 공개 metadata는 key 불필요.** Iteration 34에서 공식 MATLAB/R public-user 안내의 root·CPI 식별자를 확인하고 CPI dataflow HTTP 200·archive/hash 검증을 무키 1회로 통과했습니다. Swagger 로그인 및 elevated/private data 인증은 별개이며 지원하지 않습니다. `IMF_API_KEY`는 추가하지 않습니다. [공식 근거](../developer/connectors/IMF.md). |
| INT-02 | BIS | **추가 발급 안내 없음.** [공식 API](https://stats.bis.org/api-doc/v2/)는 공개 통계·metadata GET 경로를 제시합니다. 경로의 `{key}`는 SDMX 차원 선택 key이며 발급받는 비밀 API key가 아닙니다. |
| INT-03 | OECD | **추가 발급 안내 없음.** [공식 안내](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)의 공개 SDMX 요청 예시는 키를 포함하지 않습니다. 무료 이용·약관·rate limiting은 별도 적용되며 인증의 live 검증은 하지 않았습니다. |
| INT-04 | World Bank | **키 불필요 명시.** [Indicators API 인증 안내](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)는 API key 등 인증이 필요 없다고 명시합니다. |
| US-01 | Federal Reserve Board via FRED | **`FRED_API_KEY`.** 원 통계 기관은 Board, API 제공자는 FRED입니다. [Board 안내](https://www.federalreserve.gov/data/data-download-fred-information.htm)와 FRED 키 규칙을 따릅니다. 별도의 `FED_API_KEY`는 추가하지 않습니다. |
| US-02 | FRED/ALFRED | **`FRED_API_KEY` 필수.** [FRED 공식 안내](https://fred.stlouisfed.org/docs/api/api_key.html). ALFRED용 별도 키 이름은 추가하지 않습니다. |
| US-03 | Treasury TIC | **발급 경로 미확인.** [공식 TIC 이용 안내](https://home.treasury.gov/data/treasury-international-capital-tic-system/contact-tic-using-tic)는 공식 파일 배포를 설명합니다. 기존 표별 API 조사 상태를 유지합니다. Treasury의 다른 서비스 키를 TIC에 전용하지 않습니다. |
| US-04 | BEA | **`BEA_API_KEY` 필수.** 등록 UserID. 위 발급표 참조. |
| US-05 | BLS | **현재 v1 client에는 키 불필요.** `BLS_API_KEY`는 향후 v2를 선택할 경우에만 사용하며 v2는 이번 구현에서 제외했습니다. |
| US-06 | Census | **`CENSUS_API_KEY` 필수: 데이터 조회.** Metadata 조회는 예외. 위 2026년 공식 안내 참조. |
| EU-01 | ECB | **현재 추가 발급 안내 없음, 재확인 제한 있음.** 기존 [Data Portal 공개 API 근거](https://data.ecb.europa.eu/help/api/overview)를 유지합니다. 이번에 help overview/data 문서 재열람은 503이어서 새 인증 확정 근거를 확보하지 못했습니다. 디지털 유로 등 다른 ECB API 인증을 통계 API에 적용하지 않습니다. |
| EU-02 | Eurostat | **추가 발급 안내 없음.** [공식 API 소개](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction)는 공개 통계 서비스와 무료 metadata/data 접근을 설명합니다. 웹사이트 로그인과 통계 조회를 구별합니다. |
| EU-03 | Deutsche Bundesbank | **현재 추가 발급 안내 없음.** [공식 SDMX 도움말](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448)은 URL 호출과 조회 예시를 제시합니다. 별도 키 발급 근거를 찾지 못했으므로 기존 auth unknown을 유지합니다. ExtraNet 등 다른 서비스 계정은 별개입니다. |
| EU-04 | Bank of England | **발급 경로 미확인.** [공식 통계 FAQ](https://www.bankofengland.co.uk/statistics/faqs)와 기존 파일/표별 API 조사 상태를 유지합니다. |
| EU-05 | INSEE BDM | **현재 직접 BDM 경로에 추가 발급 안내 없음.** [공식 BDM 문서](https://www.insee.fr/en/information/2868055)는 직접 `bdm.insee.fr` 조회 예시를 제공합니다. [새 API 카탈로그](https://www.insee.fr/fr/information/8184146)와 portal 구독은 별도입니다. Sirene의 API key 제도를 BDM에 그대로 적용하지 않습니다. 선택할 portal API의 인증이 확정되기 전 `INSEE_API_KEY`를 추가하지 않습니다. |
| JP-01 | BOJ | **추가 발급 안내 없음.** [공식 2026년 이용 안내](https://www.stat-search.boj.or.jp/info/nme_aphelp_en.html)는 누구나 JSON/CSV API를 이용할 수 있다고 설명합니다. API 세부 한도와 live 검증은 별도입니다. |
| JP-02 | 일본 MOF | **발급 경로 미확인.** [공식 통계 포털](https://www.mof.go.jp/english/statistics/index.html)과 기존 표별 조사 상태. 특정 MOF 통계가 e-Stat에 있으면 e-Stat ID를 사용하는지 해당 표별로 확인합니다. |
| JP-03 | e-Stat | **`ESTAT_APP_ID` 필수.** 모든 API 기능에 Application ID가 필요하다는 공식 안내를 확인했습니다. |
| CN-01 | PBOC | **발급 경로 미확인.** [공식 사이트](https://www.pbc.gov.cn/en/)와 기존 공개 통계 API 조사 상태. 임의 key 이름을 만들지 않습니다. |
| CN-02 | SAFE | **발급 경로 미확인.** [공식 사이트](https://www.safe.gov.cn/en/)와 기존 공개 통계 API 조사 상태. |
| CN-03 | 중국 NBS | **발급 경로 미확인.** [공식 National Data](https://data.stats.gov.cn/)와 기존 공개 API 조사 상태. 포털 접근과 공개 API 인증을 구별합니다. |

API 명세가 미확인인 여섯 기관은 기존 [기관 API 감사](reference/INSTITUTION_API_AUDIT.md)의 조사 상태를 계승합니다. 이번에는 공개 API가 없다고 새로 판정하거나 endpoint를 추측하지 않았습니다. IMF·INSEE의 서비스별 인증도 후속 상세 문서 gate에서 확정합니다.
