# FRED / ALFRED — 제한 v1 JSON client

**구현:** `connectors/fred.py`, `FREDClient`. 공식 요청 계약에 맞춘 합성 fixture 검증이며 live·인증 성공은 미검증이다.

| 메서드 | 공식 GET 경로 | 의미 |
|---|---|---|
| `search_series_page(text, limit=100, offset=0)` | `/fred/series/search` | 최대 1,000개 한 페이지; count/offset/limit 보존 |
| `get_series(series_id)` | `/fred/series` | 한 series의 제목·단위·주기·정의 등 원 metadata 보존 |
| `get_observations_page(series_id, start, end, ...)` | `/fred/series/observations` | 기본 1,000개, client 상한 10,000개 한 페이지. 날짜 범위와 pagination 일치 검사 |
| `get_series_release(series_id)` | `/fred/series/release` | series의 release 정보 |
| `get_release_sources(release_id)` | `/fred/release/sources` | 원 통계 작성기관을 확인할 source 정보 |

`FRED_API_KEY`는 Settings에서만 읽고 v1의 `api_key`와 고정 `file_type=json`으로 요청한다. 반환 객체·파일·manifest에서는 키 이름/값을 가린다. `realtime_start`와 `realtime_end`는 둘 다 명시할 수 있고, 응답의 real-time 범위가 요청과 다르면 거부한다. 날짜별 값 `"."`, `"0"`, 숫자 문자열을 원문으로 보존하며 단위/주기 변경·집계·자동 pagination은 하지 않는다. `count`가 페이지보다 커도 자동으로 전체 수집 성공을 뜻하지 않는다.

FRED는 API provider다. 파일의 `original_source_agency`는 근거 없이 채우지 않고, release/source metadata 원문을 별도로 저장할 수 있다. Board DDP series crosswalk나 전체 Board coverage, 자동 lineage 연결은 미구현이다. FRED v2는 구현하지 않았다.

공통 전송의 `(5,20)`초 timeout, chunk별 30초 elapsed budget, redirect 거부, 1 MiB JSON cap, 네트워크 opt-in을 적용한다. 각 메서드는 1회 요청하며 자동 재시도·daily quota scheduler는 없다. 큰 페이지는 cap 초과 시 거부하므로 limit를 줄여야 한다. HTTP/API 오류·잘못된 페이지는 고정 메시지로 실패하며 원 오류 본문을 로그에 복사하지 않는다. FRED 및 제3자 series의 이용 조건을 각각 확인한다.

`save_api_response(settings, response, dataset_id=..., series_id=...)`로 `data/raw/api/US-02/<uuid>/response.json`과 `request.json`을 저장하고 `read_api_response()`로 hash를 검증한다. JSON은 키를 제거한 canonical payload이며 정확한 HTTP 원 bytes가 아니다. 일반 workflow/정규화 DB·사용자 UI 연결은 별도다.

공식 근거: [API/key](https://fred.stlouisfed.org/docs/api/api_key.html), [search](https://fred.stlouisfed.org/docs/api/fred/series_search.html), [series](https://fred.stlouisfed.org/docs/api/fred/series.html), [observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [release](https://fred.stlouisfed.org/docs/api/fred/series_release.html), [sources](https://fred.stlouisfed.org/docs/api/fred/release_sources.html), [이용 조건](https://fred.stlouisfed.org/docs/api/terms_of_use.html).

검사: `tests/test_us_rest_connectors.py`, `tests/fixtures/rest_api/fred.json`. 예시 파일 생성: `python scripts/verify_rest_adapters.py --fixture` (실 HTTP 차단, `.env` 미사용). [Iteration 28 report](../history/ITERATION_28_REPORT.md).
