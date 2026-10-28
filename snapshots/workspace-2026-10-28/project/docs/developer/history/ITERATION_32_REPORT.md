# Iteration 32 — SDMX metadata 계약과 파일 재조회

**일자:** 2026-10-25. **브랜치:** `codex/iteration-32-sdmx-metadata`.

**Engineering Gate W: PASS.** 기관별 선택 metadata sub-gate는 5곳 PASS,
INSEE 1곳 FAIL이다. 전체 SDMX 기관·관측치·일반 workflow 성공을 뜻하지 않는다.
Census·BLS는 호출 0회, Gate U는 기존 NOT PASSED 이력으로 유지한다.

## 기관별 실제 결과

| 기관 | 선택 metadata | 최초 HTTP/계약 결과 | 최종 선택 metadata sub-gate |
|---|---|---|---|
| BIS INT-02 | BIS WS_TC 2.0 Dataflow | 200, 계약·저장/hash 통과 | PASS; 연결 DSD는 미조회 |
| OECD INT-03 | OECD.SDD.NAD DSD_NAMAIN1@DF_QNA 1.1 Dataflow | 200, 계약·저장/hash 통과 | PASS; 연결 DSD는 미조회 |
| ECB EU-01 | ECB ECB_EXR1 1.0 DataStructure | 200, 저장/hash 통과, 기존 파서가 duplicate DSD dimension 오류 | PASS after offline repair/revalidation of same archived bytes; 차원 6개. 최초 실패 보고서 보존 |
| Eurostat EU-02 | ESTAT NAMA_10_GDP 1.0 Dataflow | 200, 계약·저장/hash 통과 | PASS; 연결 DSD는 미조회 |
| Bundesbank EU-03 | BBK BBEX3 Dataflow, 반환 version 1.0 | 200, 계약·저장/hash 통과 | PASS; 연결 DSD는 미조회 |
| INSEE EU-05 | FR1 IPC-2015-COICOP 1.0 DataStructure | 404, endpoint not found | FAIL; 받아들인 HTTP 200 archive 없음, 추가 요청 없음 |

실제 metadata HTTP 요청은 **기관당 1회, 합계 6회, retry 0, 동시 요청 1개**다.
공식 문서 웹 조사는 이 canary 예산과 구분한다. 모든 canary는 기존 opt-in
설정으로 무키 GET을 실행했고 키/header·portal login은 사용하지 않았다.
`.env`와 실제 credential은 변경하지 않았다.

최초 runner는 4 PASS / ECB source review / INSEE request failure였다.
ECB의 `AttributeRelationship/Dimension`은 정의가 아닌 참조인데 기존 파서가
이를 재귀 수집해 중복으로 세었다. `DimensionList` 자식만 정의로 읽도록
고친 뒤, 추가 HTTP 없이 최초 artifact의 raw/manifest hash와 source 계약을
다시 확인했다. 최초 보고서나 archive는 덮어쓰지 않았고 별도 재검증 보고서에
기존 실패와 새 판정을 함께 기록했다. INSEE 404는 route 변경인지 resource
retirement인지 이 응답만으로 특정하지 않는다.

## 저장 파일과 실행 근거

- [최초 live 보고서](../../../reports/iteration_32_api_metadata_d958c5fd6a3147feb447934205031f52.json)
- [수정 후 오프라인 재검증](../../../reports/iteration_32_archive_revalidation_921d01c3ce674572b499c58792164b75.json), 새 HTTP 0회; 최초 보고서 hash도 보존
- [합성 실행 보고서](../../../reports/iteration_32_api_metadata_0c86c88c2bb647a5afd5f417920c03a9.json), HTTP 0회, 6/6 저장/hash 통과
- [Recorded XML과 provenance](../../../tests/fixtures/sdmx_metadata/recorded.provenance.json): 5개 공개 응답의 URL·UTC·content type·표현 형식·SHA-256·최초 판정. 별도 합성 fixture 6개와 구분

| 기관 | response / manifest 디렉터리 (`data/raw/api/` 아래) | 저장 bytes | SHA-256 |
|---|---|---:|---|
| BIS | `INT-02/82cd1cf245224873930156733cf9fba1/` | 1,172 | `451319d21ed316ef7740807c4401c73b4ff03078b0a1da9e4e1010309b4771e1` |
| OECD | `INT-03/cab6b274fa2c412d807e66e4e5ee1081/` | 9,063 | `253156e518e44b328605534081f29d98a5a471c73466588baea5ff4db6d398bc` |
| ECB | `EU-01/f7ee278287ff4ca78580d171288a4971/` | 24,416 | `6ccf83db9654b581b051c85c41c44e9b9884755c90819f084c5c52d001e93539` |
| Eurostat | `EU-02/810a75e79c004de5b9a68872a180ab1b/` | 4,574 | `34d55dbfdb4853f02bfb9e72418212dc6e58a457a04ed71ab85ee60c18c83a86` |
| Bundesbank | `EU-03/a42158a01d674e3286e38f6371701f36/` | 1,622 | `bed7d676637cf41d9cbd404d16139da2c382d627099bc45235ebd4e805483b47` |

각 디렉터리는 `response.bin`과 `request.json`을 포함한다. 원본/manifest와
실행 JSON은 기존 정책대로 local ignored storage에 보존하고, 공개 recorded
fixture·provenance·이 보고서는 feature commit에 포함한다. 저장 표현은
requests content decoding 이후 HTTP entity bytes이며 wire bytes라는 주장은 없다.

## 변경 파일과 이유

- `discovery/sdmx_metadata_validation.py`: 6개 공식 고정 선택과 source/URL/operation·HTTP·media type·namespace/root·message ID·agency/resource/version·이름·DSD 참조/차원을 검증한다. 오류/빈 결과/HTML/JSON/잘못된 ID/DTD·entity/과대 응답은 통과시키지 않는다.
- `connectors/sdmx.py`: metadata XML 2.1 negotiation, INSEE 공식 metadata 메서드, credential/본문 비노출 HTTP status/category 오류 진단. 기존 bounded HTTP를 재사용하고 retry·redirect는 추가하지 않았다.
- `metadata/adapters.py`: 기존 구조 파서를 순수 함수로 재사용하고 ECB에서 확인한 정의/참조 혼동을 수정했다. 중복 정의 검사는 유지한다.
- `storage/api_responses.py`: SDMX bytes에서 configured credential이 발견되면 원본을 변형해 저장하는 대신 저장을 거부한다. 기존 write-once/hash 계약은 유지한다.
- `scripts/verify_api_metadata.py`: 공통 runner·archive·report 사전 쓰기를 재사용한다. 기본 source는 BEA/e-Stat 그대로이며 SDMX는 `--source`로 명시한다. 혼합 budget·중복·Census/BLS는 거부한다. 요청 전 report에 시작 상태/예산을 기록하고 기관별 flush한다. `--read-back-report`는 HTTP 없이 기존 artifact를 재검증한다.
- `tests/test_sdmx_metadata_checks.py`, `tests/test_source_registry.py`, `tests/fixtures/sdmx_metadata/*`: 합성 안전/계약·실제 recorded hash·실패 분리·저장 변조·report 쓰기 실패·기본 범위 유지·ECB 회귀 검사를 추가했다. `.gitattributes`는 recorded bytes의 개행 변환을 막는다.
- `discovery/source_registry.py`: 5개는 metadata-only PARTIAL, INSEE는 FAILED와 정확한 실패 scope로 기록한다. 일반 인증·관측치 지원으로 승격하지 않는다.
- 제품/구현/실행 계획·API 감사표·기관 상태표·저장/SDMX 문서·decision log: 실제 판정·근거와 후속 경계를 반영한다. [공식 route/access/terms audit](../connectors/SDMX_METADATA_CANARY.md)를 따른다.

## 검증

- 소스 경로를 지정하지 않은 첫 baseline: import collection error 3건. `PYTHONPATH=src`로 수정했다.
- 저장소 내부 basetemp도 기본 샌드박스에서는 WinError 5: 51 passed, 27 setup errors. 승인된 shell의 repository-local basetemp로 재실행: **78 passed**.
- 초기 확장 관련 검사: **224 passed**. Import 정렬 Ruff 오류를 수정했다.
- live 전 전체 offline gate: **1,024 passed, 1 skipped, 0 failed (71.51초)**; Ruff PASS, 6곳 합성 runner PASS.
- ECB 수정 후 관련 parser/archive 검사: **155 passed**. 당시 import 정렬 Ruff 오류는 후속 수정했다.
- Recorded fixture·registry까지 반영한 전체 offline: **1,032 passed, 1 skipped, 0 failed (72.85초)**. 변경 Python Ruff PASS.
- 최종 보고서/증거 분류 반영 후 관련 회귀 **159 passed (3.17초)**, Ruff PASS. 변경 파일·fixture·report·raw/manifest **56개 파일의 실제 configured credential 비노출 검사 PASS**. diff 공백 검사에서 문서 EOF 빈 줄 2곳을 발견해 제거했다. Recorded 원 응답의 CRLF/후행 공백은 hash 보존을 위해 수정하지 않고 Git binary diff 속성으로 명시한다. Source 계약과 원본 hash 회귀 검사는 유지한다.
- Skip 1건은 Windows symlink 생성 제한이다. Windows ACL이나 사용자 Temp를 바꾸지 않았다. 테스트 경로는 `reports/pytest_i32_*`다.

## 한계·보안·남은 조치

Gate W는 engineering gate이며 전기관 live gate가 아니다. JSON 성공 파싱,
SDMX 3.0, dataflow 연결 DSD/codelist fetch, observation ingestion·단위/빈도
정규화·개정 coverage·비교가능성·가공/XLSX·일반 자연어 workflow는 제외한다.
XML/원문 식별자는 보존하며 결측을 0으로 바꾸거나 label만으로 매핑하지 않았다.
오류 본문·redirect 위치·실제 keys는 로그에 복사하지 않았다.

INSEE는 현재 유효한 metadata route/ID의 공식 근거와 **별도 새 요청 예산**이
필요하다. 재호출·fallback은 수행하지 않았다. IMF도 SDMX API 기관이지만
상세 route/auth 근거·전용 adapter/fixture 준비가 없어 이번 기존 client 6곳과
구분한다. BOJ 등 나머지 API도 별도 기관 gate 대상이다. 다음 기관/회차의
선택은 사람의 결정이며 이번 task에서 Iteration 33은 시작하지 않았다.
Feature branch에만 커밋하며 main merge·push·배포·외부 문의는 수행하지 않는다.
