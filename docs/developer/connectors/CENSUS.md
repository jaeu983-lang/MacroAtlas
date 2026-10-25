# Census Data API — metadata와 원형 table JSON client

**구현:** `connectors/census.py`, `CensusClient`. 합성 fixture의 요청·table 구조·파일 저장을 검증했다. 실제 ACS 2023 요청은 공식 `invalid_key.html` redirect로 실패했으며 live 인증·자료 성공은 미검증이다. [Gate U 진단](../testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md).

| 메서드 | 공식 GET 경로 | 인증 |
|---|---|---|
| `list_datasets()` | `/data.json` | 무키 metadata |
| `get_variables(dataset)` | `/data/<dataset>/variables.json` | 무키 metadata |
| `get_geographies(dataset)` | `/data/<dataset>/geography.json` | 무키 metadata |
| `get_data(dataset, variables, predicates)` | `/data/<dataset>?get=...&...` | Settings의 `CENSUS_API_KEY`만 사용 |

dataset은 공식 discovery에서 확인한 path를 사용한다. Client는 host·절대 URL·dot traversal·query 주입을 받지 않으며 1~8개 bounded path segment만 허용한다. 존재하지 않는 dataset·variable을 추측해서 검증됐다고 하지 않는다. 예: `2023/acs/acs5`, `timeseries/intltrade/exports/enduse`. 요청당 1~50개 서로 다른 variable 이름과 명시적인 predicate가 필요하다. `for`, `in`, `time` 등 source predicate를 그대로 보존하며 `get`·`key` 덮어쓰기는 거부한다. `group(...)` 확장 조회는 미지원이다.

응답은 `[header, row, ...]` 배열로 보존한다. 요청 column 존재, 중복 없는 header, 행 길이와 문자열/null 구조를 확인한다. 선행 0이 있는 국가/지역 code, `"0"`, null과 음수 sentinel을 바꾸지 않는다. Header만 있는 응답은 관측 행 0개 그대로 보존되며 데이터 적재 성공을 의미하지 않는다. 통계 단위·결측 코드 해석과 정규화는 별도다.

공통 HTTPS/redirect/네트워크 opt-in·timeout 정책과 응답 1 MiB, query 문자 예산 8 KiB를 적용한다. Root catalogue나 큰 variables metadata 및 넓은 data query는 이 cap을 넘을 수 있고 일부 payload를 성공으로 저장하지 않는다. 자동 분할/재시도는 없다. Dataset별 작은 요청 범위를 선택해야 한다.

데이터 요청에서만 공식 HTTPS host의 정확한 `/data/invalid_key.html`·`/data/missing_key.html` redirect를 각각 `AUTH_ACCESS`와 `invalid_api_key`·`missing_api_key`로 분류한다. `Location`은 메모리에서만 비교하고 repr/report에 남기지 않는다. query와 key를 출력하지 않으며 redirect body를 읽거나 후속 요청을 보내지 않는다. 알 수 없는 host/path·userinfo·port·fragment는 기존 redirect 거부 정책을 유지한다. 활성화 완료 여부와 서버의 key 유효 판정은 별개로 기록한다.

`save_api_response()`와 `read_api_response()`는 source `US-06` 경로에 키를 제거한 canonical JSON 및 manifest를 저장하고 hash를 확인한다. 안전한 query 조건은 남기고 credential `key`는 저장하지 않는다. 정확한 HTTP bytes·일반 workflow·정규화 DB·실 API 성공은 이 검증 범위가 아니다.

공식 근거: [개발자](https://www.census.gov/data/developers.html), [query 예시](https://www.census.gov/data/developers/guidance/api-user-guide.Example_API_Queries.html), [predicate](https://www.census.gov/data/developers/guidance/api-user-guide.Predicates.html), [한도](https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html), [metadata 키 예외 공식 안내](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23).

검사: `tests/test_us_rest_connectors.py`, `tests/fixtures/rest_api/census.json`. 예시 파일 생성: `python scripts/verify_rest_adapters.py --fixture` (실 HTTP 차단, `.env` 미사용). [Iteration 28 report](../history/ITERATION_28_REPORT.md).
