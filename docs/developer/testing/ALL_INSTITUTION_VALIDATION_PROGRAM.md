# 전기관 API·수집 검증 프로그램

**기준일:** 2026-10-25\
**목표:** BIS를 포함하되 특정 기관을 중심으로 삼지 않고, 카탈로그의 21개 기관·서비스를 각각 API 우선으로 조사·fixture 검증·bounded live 검증한다. API를 확인하지 못한 기관은 API를 추측하지 않고 표별 조사를 먼저 수행한다.\
**추론/작업 크기:** Luna Max 기준으로 공통 계약 감사와 동일 API 계열 작업은 넓게 묶는다. 단, 테스트 결과와 통과 gate는 기관·provider·dataset별로 분리한다.

## 현재 기준선

**최신 scope(D-101):** Census·BLS는 보류하고 다른 기관 API를 독립 source gate로 검증한다. Gate U는 7개 고정 경로의 과거 미통과 이력이며 현재 전체 프로젝트의 차단 조건이 아니다. Iteration 31은 BEA/e-Stat metadata만 실제 요청·archive/read-back을 통과했고, 전체 offline 결과는 884 passed, 1 skipped다. 다음 작업 요청문은 [Iteration 32 SDMX handoff](../planning/ITERATION_32_SDMX_HANDOFF.md)를 따른다.

Iteration 23에서 현행 registry와 전체 offline suite를 확인했다.

| 구분 | 확인된 현황 | 의미 |
|---|---:|---|
| 기관·서비스 프로필 | 21/21 | 레지스트리 분류가 읽히고 프로필 계약 테스트를 통과했다는 뜻 |
| 공식 API 문서 확인 | 15 | 그 기관의 모든 표/API가 지원된다는 뜻은 아님 |
| 공식 API 문서 미확인 | 6 | API가 없다는 뜻이 아니며 표별 조사 필요 |
| 부분 connector/client | 3 | World Bank, BEA, e-Stat; 동작 범위는 제한되어 있음 |
| fixture 전용 | 8 | 합성/일반 fixture 검증일 뿐 live endpoint 검증 아님 |
| 기관 어댑터 미구현 | 10 | 실제 source query 경로가 없음 |
| 과거에 확인된 live 일부 경로 | 1 | World Bank USA/WDI/GDP 고정 경로만 해당; 이번 Iteration 23에서는 live 요청하지 않음 |
| 전체 offline suite | 625 passed, 1 skipped, 0 failed | network를 사용하지 않은 전체 회귀·fixture 결과 |

전체 suite에서 registry 21개 행을 검증했어도 각 기관의 통계 API가 통과한 것은 아니다. 전체 실행 세부사항은 [Iteration 23 보고서](../history/ITERATION_23_REPORT.md) 및 [엔진·기관별 오프라인 결과](ENGINE_INSTITUTION_TEST_RESULTS_2026-10-25.md)를 참고한다.

**Iteration 24 상태 delta:** BIS, OECD, ECB, Eurostat, Bundesbank, INSEE 여섯 source에 fixed-root SDMX raw-response clients와 mocked route tests가 추가됐다. 이는 실제 API payload fixture, metadata/data parsing, workflow E2E, 인증·network/live 검증으로 계산하지 않는다. IMF Data API의 exact endpoint/auth 문서는 beta portal 로그인 안내 때문에 미확인으로 남아 있으며, API 문서 상태 자체는 `documented`를 유지한다. 구현 상세는 [SDMX batch 명세](../connectors/SDMX_FAMILY.md), 실행 결과는 [Iteration 24 보고서](../history/ITERATION_24_REPORT.md)를 본다.

**Iteration 25 상태 delta:** 현재 client가 있는 9개 source의 응답을 파일로 저장하고 manifest/raw SHA-256을 확인해 재조회하는 공통 storage helper를 추가했다. 9개 client-to-file round-trip은 mocked/fixture transport로 통과했고 full offline suite는 666 passed, 1 skipped였다. BEA/e-Stat JSON 보존은 비밀값을 제거한 payload의 canonical 재직렬화이며, 정확한 원 HTTP bytes가 아니다. World Bank 외 8개 API client의 사용자 workflow 연결, provider payload parse, 기관 live test는 여전히 미검증이다. 세부는 [API response file archive](../connectors/API_RESPONSE_STORAGE.md)와 [Iteration 25 report](../history/ITERATION_25_REPORT.md)를 본다.

SDMX 결과는 세 층으로 별도 판정한다. **공통 전송**의 TLS/host/path, timeout, redirect refusal, size bound와 raw entity-byte 반환은 공통 transport gate다. **기관 adapter**의 endpoint/path/identifier/query는 기관마다 독립 route mock gate다. **기관 검증**의 공식 응답 fixture, auth/access limits, parsing, file save/read-back, live canary는 각각 독립 증거이며 앞 단계 통과를 물려받지 않는다. Iteration 25 storage round-trip은 이 중 file preservation만 검사한다. 6개 SDMX 기관별 현재 판정표는 [SDMX connector 명세](../connectors/SDMX_FAMILY.md)를 본다.

## 기관별 현재 상태와 검증 묶음

**Iteration 28 delta:** FRED v1·Census·BLS v1 client와 source-specific synthetic JSON 계약 검사·파일 저장/read-back을 추가했다. FRED의 페이지·real-time 조건, Census header/row 문자열·null·sentinel, BLS v1만의 무키 POST·25 series/10년 한도와 warning/부분 선택을 검증한다. BLS2는 제외한다. Provider payload의 실기관 수집, live/auth, normalized DB 및 일반 workflow는 이 결과로 통과시키지 않는다. [Iteration 28 report](../history/ITERATION_28_REPORT.md)와 [FRED](../connectors/FRED.md)/[Census](../connectors/CENSUS.md)/[BLS v1](../connectors/BLS.md)을 따른다.

**Iteration 29–30 delta:** 고정 API profile 4개(FRED·Census·BLS 2개)와 공식 CSV profile 3개(TIC 2개·BoE 1개)를 collector로 연결해 fixture/save/read-back을 검사했다. Iteration 30의 첫 canary와 후속 canary는 각각 7회·retry 0회였다. 첫 실행 pass는 2/7(FRED·BoE)이었고, 저장된 TIC raw의 후속 offline 검증은 그 시점 source-response 근거를 4/7로 보강했다. 별도의 후속 live run은 4/7(FRED·TIC 2개·BoE) 통과, Census 302 redirect refusal, BLS 503 두 건으로 Gate U에 실패했다. 이 결과는 전기관 지원이나 자연어 workflow E2E를 뜻하지 않는다. 자세한 사항은 [Iteration 30 보고서](../history/ITERATION_30_REPORT.md)와 [live canary 결과](LIVE_CANARY_REPORT.md)를 따른다.

아래 상태는 `source_registry.py`와 기존 기관 구현 현황표를 기준으로 한다. `fixture_scope`가 `generic` 또는 `scenario_only`이면 그 기관의 실제 API 응답을 재현한 fixture가 아니다.

| ID | 기관 / API 제공자 관계 | API 문서 상태 | 현재 코드 / fixture | live evidence | 검증 묶음 |
|---|---|---|---|---|---|
| INT-01 | IMF | documented | fixture-only / source-specific synthetic | 미실행 | SDMX |
| INT-02 | BIS | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |
| US-03 | Treasury TIC | unconfirmed | fixture-only / source-specific parser | 미실행 | API 표별 조사 → 공식 파일 검토 |
| US-04 | BEA | documented | partial JSON client / synthetic·recorded metadata | GetDataSetList 13개 metadata와 archive/read-back 부분 통과 | 관측치·일반 workflow 별도 |
| EU-01 | ECB | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |
| EU-02 | Eurostat | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |
| JP-02 | Japan MOF | unconfirmed | adapter·기관 fixture 없음 | 미실행 | API 표별 조사 → 공식 파일 검토 |
| JP-01 | Bank of Japan | documented | adapter 없음 | 미실행 | 개별 REST |
| JP-03 | e-Stat | documented | partial JSON client / synthetic·recorded metadata | getStatsList(E, limit=1) metadata와 archive/read-back 부분 통과 | 관측치·일반 workflow 별도 |
| CN-01 | PBOC | unconfirmed | fixture-only / scenario-only | 미실행 | API·공식 배포 경로 조사 |
| CN-02 | SAFE | unconfirmed | fixture-only / scenario-only | 미실행 | API·공식 배포 경로 조사 |
| CN-03 | China NBS | unconfirmed | fixture-only / scenario-only | 미실행 | API·공식 배포 경로 조사 |
| INT-03 | OECD | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |
| INT-04 | World Bank | documented | partial fixed GDP client / source fixture | 부분 확인: USA/WDI/GDP만 | 기존 REST 범위 확장 |
| US-01 | Federal Reserve Board | documented | adapter·fixture 없음; 제공자는 FRED | 미실행 | 개별 REST·provider/agency 분리 |
| US-02 | St. Louis Fed FRED/ALFRED | documented | partial v1 page/metadata client; synthetic JSON/file round-trip | 미실행 | 개별 REST·인증, 원기관 별도 |
| US-05 | BLS | documented | partial **무키 v1만** POST; synthetic JSON/file round-trip | 미실행 | 개별 REST v1·quota, v2 제외 |
| US-06 | U.S. Census Bureau | documented | partial metadata/table client; synthetic JSON/file round-trip | 미실행 | 개별 REST·인증 |
| EU-03 | Deutsche Bundesbank | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |
| EU-04 | Bank of England | unconfirmed | adapter·기관 fixture 없음 | 미실행 | API 표별 조사 → 공식 파일 검토 |
| EU-05 | INSEE | documented | partial SDMX raw client / mocked route; provider payload fixture 없음 | 미실행 | SDMX |

기관/API 제공자와 통계 작성기관은 별도 ID로 기록한다. 특히 Board DDP → FRED와 FRED/ALFRED는 같은 API 제공자를 사용할 수 있지만 자료 출처·series lineage를 합치지 않고 각각 요구 범위를 검증한다.

## Max 기준의 실행 묶음

Max 추론은 관련 계약을 함께 비교하고 반복 작업을 줄이는 데 쓴다. 무관한 인증·API 형식·통계 정의를 한 성공 판정으로 합치지 않는다. 각 묶음은 기관별 fixture와 판정 레코드를 유지한다.

| 묶음 | 기관 범위 | 공통으로 묶는 이유 | 독립 판정 경계 |
|---|---|---|---|
| 1. 전기관 공통 검증 계약 | 21개 전체 | readiness matrix, 공통 timeout/error/provenance/test record | source별 API 문서·dataset·인증·응답 fixture 상태 |
| 2. SDMX 계열 | IMF, BIS, OECD, ECB, Eurostat, Bundesbank, INSEE | dataflow/structure/code-list/discovery transport 공유 가능 | API 버전, agency/dataflow, dimension order, unit/revision 의미, 각 기관 fixture |
| 3. 개별 REST 계열 | World Bank, BEA, e-Stat, Board/FRED, FRED/ALFRED, BLS, Census, BOJ | REST request/retry/response harness 재사용 가능 | 각 API의 인증·쿼터·ID 체계·provider lineage와 series fixture |
| 4. API 미확인 계열 조사 | Treasury TIC, Bank of England, Japan MOF, PBOC, SAFE, China NBS | 문서 검색·접근 조건 기록 절차 재사용 | 정확한 표별 API 확인 전에는 API 호출 금지; API 부재와 미확인을 구분 |
| 5. 전기관 offline E2E | source별 fixture가 준비된 21개 | common request→discovery→metadata→ingestion→storage/error harness | fixture가 없는 기관은 통과로 셈하지 않고 `not_ready` 유지 |
| 6. bounded live canary | live-ready 기관별 표/series 1개 | API family별 재사용 test runner | 각 기관별 result/endpoint/period/rate/auth를 따로 남김; 한 기관 실패가 다른 기관 결과를 가리지 않음 |
| 7. seeded·장기 시험 | offline 전체, 이후 승인된 live-ready subset | 동일 seed·공통 계측 형식 재사용 | 외부 서버에는 병렬 부하를 주지 않으며 각 source budget/약관에 맞춰 개별 실행 |

한 묶음의 공통 transport 변경은 같이 개발할 수 있지만, 그 묶음 안에서 미시험 기관을 “통과”로 표시하지 않는다. source-specific fixture와 data contract가 실제로 다른 경우에는 Max 작업 안에서도 별도 검증 sub-gate를 둔다.

## 기관별 검증 단계와 성공 조건

각 기관·선택 dataset/table은 다음 단계를 순서대로 기록한다.

1. **문서 gate:** 공식 API/파일 규격, API 제공자, 인증, request quota, 이용 조건, 응답 언어, 개정·vintage를 확인한다. API 문서 미확인은 API 부재로 표시하지 않는다.
2. **발견/metadata fixture:** dataflow/catalog/table/series 식별자, 차원·코드 목록·정의·단위·주기·coverage가 공식 문서와 fixture에서 일치해야 한다. 모르는 필드는 unknown으로 둔다.
3. **mock ingestion fixture:** 정상·결측/0·빈 응답·잘못된 응답·timeout·429/5xx 및 retry 제한을 확인한다. 실 서버에 일부러 오류를 발생시키지 않는다.
4. **offline E2E:** 요청 범위 제한, raw 원문과 hash, 출처 URL·UTC 시각·기관 ID·dataset/series ID, 정규화 값·상태, 저장/read-back 및 복구를 검증한다.
5. **live readiness:** 정확한 공식 endpoint와 하나의 대표 dataset/series, 필요한 환경변수 이름, 최소 요청량·timeout·rate limit·중단 조건을 문서화한다. 비밀값은 읽거나 출력하지 않고 설정 여부만 확인한다.
6. **bounded live canary:** 별도 네트워크 준비와 source readiness 이후 metadata 요청 및 가능한 최소 단위의 관측치 요청을 수행한다. 한정된 국가/series/기간만 요청하고 원응답과 결과를 보존한다. HTTP 성공만으로 데이터 정확성 통과를 선언하지 않는다.
7. **최종 판정:** `live_pass_for_scope`, `live_failed_with_reason`, `blocked_credentials`, `blocked_network`, `blocked_terms_or_quota`, `api_unconfirmed`, `official_api_not_offered_for_table`, `not_ready` 중 정확한 상태를 남긴다. 기관 전체 통과로 과장하지 않고 검증한 table/series 범위를 쓴다.

API 경로가 선택한 표에 없거나 이용 조건상 부적합하다는 공식 근거가 확인된 뒤에만 해당 표의 공식 파일 경로를 시험한다. 근거 없이 scraping을 대체 경로로 사용하지 않는다.

## 결과표에 반드시 남길 값

`institution_id`, 작성기관과 API provider, dataset/table/series ID, 접근 경로 유형, API 문서 링크, auth 상태(환경변수 이름만), API 버전, 정확한 요청 범위, HTTP/파일 상태, request count/bytes, retrieval time UTC, raw SHA256, 응답 schema/차원/코드, unit/frequency/time/country coverage, revision/break/vintage, validation 결과, 재시도·오류·복구, rate-limit 근거, live scope, 실패 이유, 재현 seed(offline)를 보존한다.

live 원응답에 credential, query secret 또는 개인 식별 정보가 들어갈 가능성을 검토하고 저장 전에 제거한다. API key는 URL, fixture, logs, reports, Excel, Git에 기록하지 않는다.

## 긴 실행과 완료 정의

- 모든 21개에 source-specific offline fixture/E2E가 있어야 offline full-source gate를 통과한다.
- 15개 `documented` API는 선택한 대표 table/series별로 bounded API discovery와 observation canary를 실행하거나, 왜 준비되지 않았는지 상태를 남긴다. API documentation만 있는 상태는 live 통과가 아니다.
- 6개 `unconfirmed` 기관은 대상 표별 공식 API 여부 조사를 먼저 끝낸다. API가 공식 문서로 확인되면 같은 API gate를 적용한다. 특정 표에서 API가 없다고 확인되면 공식 파일 수집 경로를 별도 통과시킨다. 공식 출처가 없거나 접근 조건이 미확인이면 blocked/unconfirmed로 남기며 억지로 통과시키지 않는다.
- 21개 모두를 live 요청할 수 있다는 보장은 없다. “전기관 검증 완료”는 21개 모두에 대해 근거 있는 최종 상태와 범위가 기록되고, 성공 가능한 공식 경로가 각각 검증된 상태를 뜻한다. 미지원·접근 차단은 성공과 구별한다.
- seeded offline 시험은 모든 준비된 기관 fixture를 반복/무작위 선택하되 seed와 선택 목록을 저장한다. live long-run은 source별 budget·약관·호출한도를 확인한 뒤 별도 승인된 ready subset에만 수행한다. 2시간/6시간 시험은 기관 서버에 대한 병렬 부하 시험으로 사용하지 않는다.

## 현재 다음 단계

Iteration 25의 공통 file-save/read-back gate를 통과한 다음 documented API coverage를 이어간다. IMF의 official API 상세 route/auth 근거를 확보할 수 있는지 먼저 조사하고, 확인되는 범위만 IMF client로 구현한다. 그 뒤 Board/FRED·FRED/ALFRED·BOJ·BLS·Census의 신규 clients와 World Bank·BEA·e-Stat 제한 client 확장을 API family별로 수행한다. provider payload fixture/parser, 각 기관의 workflow 연결과 live canary는 별도 gate다. API 문서 미확인 6곳은 전 documented API 작업과 구분해 이후 표별 조사한다.
