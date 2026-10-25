# SDMX API connector batch — Iteration 24

**Iteration 32 현재 overlay:** 아래 Iteration 24–26 원래 상태는 이력이다. 여섯 source에 각 1회, 총 6회·retry 0으로 metadata만 요청했다. BIS WS_TC 2.0·OECD QNA 1.1·Eurostat NAMA_10_GDP 1.0·Bundesbank BBEX3는 최초 계약/저장/hash 통과다. ECB ECB_EXR1 1.0은 최초 파서 실패를 보존하고 AttributeRelationship 차원 참조 처리 수정 후 같은 저장 bytes로 오프라인 재검증 통과했다. INSEE IPC-2015-COICOP 1.0은 HTTP 404 실패이며 추가 호출하지 않았다. [공식 경로/접근 조건 audit](SDMX_METADATA_CANARY.md)와 [Iteration 32 결과](../history/ITERATION_32_REPORT.md)를 따른다. JSON 성공 파싱·관측치·일반 workflow는 미검증이다. IMF도 SDMX API 기관이며 기존 client가 없어 별도 후보로 남는다.

**상태:** 공통 HTTP 전송 기초, SDMX 계열 transport wrapper, provider별 route adapter가 나뉘어 있습니다. Iteration 26에서 HTTP 기초를 World Bank/JSON 계열과 공유하면서 SDMX route·식별자·payload 계약은 유지했습니다. Iteration 25에서는 6개 SDMX source 응답을 파일로 보존하고 hash 확인 후 read-back하는 offline 검사를 추가했습니다. 공식 provider payload fixture, metadata/observation parsing, auth 성공과 live API 호출은 여전히 별도 미검증 단계입니다. 구조 세부는 [공통 HTTP 전송 설계](HTTP_TRANSPORT.md)를 참고합니다.

## 책임을 세 층으로 분리

| 층 | 코드/문서 책임 | 통과 기준 | 다른 층으로 전파하지 않는 항목 |
|---|---|---|---|
| **공통 HTTP 전송** | `connectors/http_transport.py`: opt-in, HTTPS host/path policy, GET, timeout/elapsed bound, redirect 거부, byte streaming, 응답 메타데이터 반환 | 공통 안전/크기/error 계약의 mock test | 기관 endpoint·식별자 의미·auth·fixture parsing·live 도달성 |
| **SDMX 계열 wrapper** | `SdmxApiTransport`: SDMX credential query 차단, status→SDMX error mapping, 8 MiB 정책과 SDMX response model | wrapper error/size/status 매핑 mock test | 기관별 route나 payload parsing pass를 대신하지 않음 |
| **기관별 adapter** | 각 client class: 공식 root, path template, data/structure operation, provider별 식별자·query 규칙 | 각 source route와 입력 제한을 따로 mock test | 한 기관의 route pass를 다른 기관 API/dataflow 성공으로 간주하지 않음 |
| **기관별 검증** | provider fixture, authentication/access limits, response parser, storage/read-back, live canary를 각 기관 ID와 dataflow/table 범위로 기록 | 각 항목별 독립 증거가 있어야 해당 항목만 pass | 공통 transport pass로 payload·auth·parse·live 성공을 대체하지 않음 |

공통 코드를 함께 사용해도 최종 결과는 기관별입니다. 특히 mock route fixture와 공식 기관 응답 fixture는 서로 다른 증거 유형입니다.

## 공통 안전 계약

- HTTP GET만 제공하고, 기관별 wrapper가 선택한 고정 공식 HTTPS root/path policy로만 요청한다.
- 설정의 `MACROATLAS_NETWORK_ENABLED=true`가 없으면 요청 전 중단한다.
- redirects를 따라가지 않고, `trust_env=False`, (5, 20)초 connect/read timeout, 최대 30초 elapsed bound를 적용한다.
- 응답은 최대 8 MiB까지만 받아들인다. 이를 넘으면 일부 데이터로 성공 처리하지 않는다.
- 원 응답 bytes, HTTP status, content type, UTC retrieval time, 요청 URL을 그대로 반환한다. SDMX 해석·저장과 API transport는 분리되어 있다.
- API key/header authentication은 이 batch에서 다루지 않는다. 401/403은 접근 조건 확인으로 남긴다.
- endpoint/template와 호출 경로는 mock tests에서 확인했다. 이것은 live reachability, provider의 현재 실제 응답, 데이터 정확성의 근거가 아니다. 공통 전송 구현은 [HTTP transport 설계](HTTP_TRANSPORT.md)를 따른다.

## 기관별 계약 및 현재 한계

| ID | 기관 | 공식 route 근거 및 호출 | 한계 / 미검증 |
|---|---|---|---|
| INT-02 | BIS | [BIS API v2](https://stats.bis.org/api-doc/v2/)의 `GET /data/{context}/{agencyID}/{resourceID}/{version}/{key}`와 `GET /structure/{structureType}/{agencyID}/{resourceID}/{version}`. Client는 원 경로를 제공한다. | 문서는 BIS 응답이 SDMX 2.1 형식이라고 설명한다. fixture 응답은 synthetic bytes; 데이터 flow/DSD/코드목록 실제 응답 미검증. |
| INT-03 | OECD | [OECD SDMX REST v1 Swagger](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1): `/rest/v1/data/{flowRef}/{key}/{providerRef}`, `/rest/v1/{structure}/{agencyId}/{resourceId}/{version}`. | 인증, flow/provider별 coverage, content negotiation, 실제 외부 도달성 미확인. |
| EU-01 | ECB | [ECB Data API](https://data.ecb.europa.eu/help/api/data): HTTPS root `https://data-api.ecb.europa.eu/service/`, data path `/data/{flowRef}/{key}`; metadata discovery/structure는 SDMX 2.1 resource query. | mock path만 검증. flowRef/차원 key와 응답 formats는 특정 series fixture 단계에서 확인해야 함. |
| EU-02 | Eurostat | [Eurostat SDMX 2.1 guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/sdmx2.1): `/dataflow/ESTAT/all`, `/dataflow/ESTAT/{id}/{version}`, `/datastructure/ESTAT/{id}/{version}`, `/data/{id}/{key}`; query format/time filters는 원문 parameter로 전달. | 특정 Comext/PRODCOM `DS-` dataset은 별도 base root이므로 이 client에서 미지원. API가 최신 관측치만 제공하고 과거 observation version은 없다는 문서 제한을 유지. 대량/async 경로 미구현. |
| EU-03 | Deutsche Bundesbank | [Bundesbank SDMX API](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448): `/data/{flowRef}/{key}`, `/metadata/dataflow/BBK/{resourceID}`, `/metadata/datastructure/BBK/{resourceID}`. | 문서에 설명된 SDMX-ML, SDMX-CSV 등 payload를 bytes로 보존하며 파싱하지 않음. 인증은 unknown. 대형 응답의 413/비동기 처리 미구현. |
| EU-05 | INSEE | [INSEE SDMX BDM service](https://www.insee.fr/en/information/2868055): `/data/SERIES_BDM/{idbank}` 및 `/data/{dataflow}/{key}`. 1–100개 숫자형 IDBANK만 요청하도록 client 제한을 둠. | 공식 서비스 문서는 IDBANK 최대 400개를 허용하지만 MacroAtlas는 URL·payload bound를 위해 100개로 제한. API portal sign-in 방식, 특정 series, 응답 parsing 미검증. |

## 기관별 현재 판정

| 기관 | 공통 전송 | 기관 route/query mock | 공식 응답 fixture | 인증·이용 제한 | provider parsing | file save/read-back | live |
|---|---|---|---|---|---|---|---|
| BIS | pass | pass | 없음 | 문서상 key 불필요; 별도 rate/quota 미확인 | 미구현 | mock round-trip pass | 미실행 |
| OECD | pass | pass | 없음 | 인증·접근 조건 미확인 | 미구현 | mock round-trip pass | 미실행 |
| ECB | pass | pass | 없음 | 문서상 key 불필요; 별도 rate/quota 미확인 | 미구현 | mock round-trip pass | 미실행 |
| Eurostat | pass | pass | 없음 | 문서상 key 불필요; Comext/Prodcom 등 별도 경로와 관측치 revision 제한 존재 | 미구현 | mock round-trip pass | 미실행 |
| Deutsche Bundesbank | pass | pass | 없음 | 인증 방식 미확인; 큰 응답 413/비동기 경로 미구현 | 미구현 | mock round-trip pass | 미실행 |
| INSEE | pass | pass | 없음 | API portal sign-in/auth 상세 미확인; client IDBANK 요청은 100개 이내 | 미구현 | mock round-trip pass | 미실행 |

여기서 **pass**는 로컬 mocked contract 검사만 뜻합니다. 실제 API가 해당 route를 현재 제공하는지 또는 선택한 통계를 반환하는지 확인한 결과가 아닙니다. `mock round-trip pass`는 response object를 local file에 저장하고 hash/manifest를 검증해 다시 읽었다는 뜻입니다. 해당 통계의 실제 응답 fixture와 parser가 준비되기 전에는 해당 기관의 source payload gate는 `not_ready`입니다.

## SDMX 계열에서 이번 회차가 제외된 기관

IMF는 공식 [IMF API 페이지](https://data.imf.org/en/Resource-Pages/IMF-API)에서 SDMX 2.1/3.0을 제공한다고 확인했지만, 상세 Swagger 탐색에는 beta portal 계정 로그인 안내가 표시된다. 이 작업공간에는 해당 API route/auth 자료가 없으므로 IMF Data Portal 호출 경로를 추정하지 않았다. 기존 IMF fixture-only 상태를 유지한다. 구체 route/auth 문서가 확보되면 IMF 전용 client와 fixture를 별도 source gate로 추가한다.

이 문서는 IMF의 API 미제공을 의미하지 않는다. API 문서 확인과 현재 adapter 구현 상태는 별도다.

## 다음 검증 gate

1. 기관별 공식 응답 fixture를 검증 가능한 retrieval 범위와 함께 확보한다. synthetic route fixture와 혼동하지 않는다.
2. source별 대표 dataflow/series, 인증·rate/access restrictions 및 용어·단위·주기를 정한 뒤 요청 scope를 제한한다.
3. 각 기관의 metadata/data payload parser를 독립 fixture로 구현·검증하고, 저장/read-back/recovery 연결은 별도 workflow gate에서 수행한다.
4. source별 offline gate가 통과한 뒤 해당 기관 bounded live canary를 별도로 실행한다. API 접근이 확인되지 않으면 live는 시도하지 않고 근거와 상태를 남긴다.

## 구현 및 테스트 파일

- `src/macro_data_platform/connectors/sdmx.py`
- `tests/test_sdmx_connectors.py`
- `src/macro_data_platform/storage/api_responses.py`와 `tests/test_api_response_storage.py` — Iteration 25 공통 보존/검증 경로. synthetic/mock body를 사용하며 official payload parsing은 하지 않음.
- [Iteration 24 report](../history/ITERATION_24_REPORT.md)
