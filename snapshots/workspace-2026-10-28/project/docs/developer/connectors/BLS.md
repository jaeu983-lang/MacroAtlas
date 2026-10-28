# BLS Public Data API — 1.0 전용 client

**구현:** `connectors/bls.py`, `BLSClient.get_data(series_ids, start_year, end_year)`. 사용자 지시에 따라 **v1만** 사용한다. `BLS_API_KEY`를 입력하거나 발급받을 필요가 없고 v2 요청·자동 전환은 제공하지 않는다. `.env`의 기존 빈 키 항목은 보존하며 client는 사용하지 않는다.

공식 기간 지정 조회는 `POST https://api.bls.gov/publicAPI/v1/timeseries/data/`이며 JSON body에는 `seriesid`, `startyear`, `endyear` 세 필드만 넣는다. v1이 POST를 지원한다는 것은 v2 기능을 쓴다는 뜻이 아니다. v2 endpoint와 `registrationkey`는 JSON wrapper에서도 차단한다.

- 요청당 서로 다른 series 1~25개, 1900..2100 중 연속 최대 10개 연도(양 끝 포함)를 허용한다. Lowercase/잘못된 ID, 중복, 역전된 기간·초과 연도를 요청 전에 거부한다.
- 공식 FAQ상 무등록 v1은 하루 25회다. Client는 1회 POST만 수행하고 자동 재시도하지 않는다. 계정/IP별 일일 budget ledger와 스케줄링은 미구현이므로 운영자가 다른 작업의 요청까지 합산해 관리해야 한다.
- 공통 네트워크 opt-in, TLS 기본 검증, `trust_env=False`, redirect 거부, `(5,20)`초 timeout, chunk별 30초 elapsed budget, 1 MiB 응답 cap, 16 KiB POST body cap을 적용한다.

HTTP 200이어도 `REQUEST_SUCCEEDED`, 빈 `message`, 요청한 series 집합과 중복 없는 응답, 비어 있지 않은 data와 연도 범위를 확인한다. Warning·missing series·중복·실패 envelope는 성공으로 처리하지 않는다. 공식 signature 예시의 `Results: [{...}]`와 공식 Python 예시의 `Results: {...}`를 모두 검사하며 **저장한 원 payload 구조는 변환하지 않는다**.

Iteration 30 최신 진단에서는 고정 unemployment/CPI POST와 공식 single-series GET·예제 POST 비교가 모두 503 HTML이었다. 제한 표본의 Akamai·JavaScript 표식은 앞단 오류/접근 페이지 가능성을 나타내지만 차단 정책은 미확정이다. BLS v1 client 요청 형식을 변경할 근거는 확보되지 않았다. 실패 보고서에는 body 대신 고정 `failure_response_kind=html`을 기록한다. 추가 자동 재시도·v2 전환·브라우저 위장·파일 fallback 없이 기관/네트워크 확인 후 새 예산에서 단발 재검증한다. [증거와 재개 조건](../testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md).

원 문자열 값 `"0"`, `"-"`, period와 footnotes를 보존한다. `M13`은 원문 Annual period이며 월말로 바꾸지 않는다. v1은 v2의 catalog·계산 기능을 요구하지 않고, unit/frequency를 지표 이름만 보고 추정하지 않는다. API data validation은 응답 계약 검사이며 통계적 비교가능성/방법론 검증과 다르다.

`save_api_response()`와 `read_api_response()`로 `data/raw/api/US-05/<uuid>/response.json`, `request.json`을 저장·검증한다. Manifest에는 HTTP `POST`와 안전한 body 조건(series ID 목록·연도)을 남긴다. 저장물은 sanitized canonical JSON이고 정확한 HTTP bytes는 아니다. 일반 workflow·DB 정규화·live API 검증은 별도다.

공식 근거: [v1 signatures](https://www.bls.gov/developers/api_signature.htm), [v1 Python example](https://www.bls.gov/developers/api_python.htm), [v1/v2 한도·등록 FAQ](https://www.bls.gov/developers/api_faqs.htm). 제공기관 attribution과 [이용 안내](https://www.bls.gov/bls/linksite.htm)를 따른다.

검사: `tests/test_us_rest_connectors.py`, `tests/fixtures/rest_api/bls_v1.json`. 예시 파일 생성: `python scripts/verify_rest_adapters.py --fixture` (실 HTTP 차단, `.env` 미사용). [Iteration 28 report](../history/ITERATION_28_REPORT.md).
