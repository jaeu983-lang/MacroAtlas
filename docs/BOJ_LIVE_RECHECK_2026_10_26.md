# BOJ API 기존 차단 판단 재검토

기존에 manual의 `/getLayerCode` 표기 차이 때문에 모든 API 호출을 보류한 판단은 과도했다.
이 차이는 별도의 명확한 `/getMetadata`와 `/getDataCode` 경로를 검증하는 데 장애가 아니었다.

2026-10-26 UTC에 공식 매뉴얼의 FM08 metadata를 GET 한 번 요청했다.
`https://www.stat-search.boj.or.jp/api/v1/getMetadata?format=json&lang=en&db=FM08`
응답은 HTTP 200, JSON STATUS 200, 25,555 bytes, SHA256
`101f4822f48ef210f611a5940ebff604f197b45371ec35db171d3b1d48897466`였다.
여기서 FXERD01의 명칭·단위·주기를 확인했다.

검증된 코드로 2026-09 한 달만 GET 한 번 요청했다.
`https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM08&code=FXERD01&startDate=202609&endDate=202609`
HTTP 200, JSON STATUS 200, 995 bytes, SHA256
`272ec6edd427b6cbaba9d1e893ae2307d26a47e46316db14182f4bad8840add2`였다.
시리즈는 Tokyo Market 09:00 JST 달러/엔 현물환율이며 단위는 Yen per U.S. Dollar, 주기는 DAILY다.
날짜/값 배열 길이 각 30, NEXTPOSITION null을 확인했다. 결측값은 원본 null 그대로 보존했다.

두 호출은 설정된 proxy/TLS와 명시적 network permission을 사용했다. 호출별 timeout 5/20초,
응답 상한 2 MiB, redirect 및 자동 retry 없음. 원본과 manifest는 gitignored
`data/raw/boj_recheck/`에 보존했다. 이는 직접 HTTP 실측이며 플랫폼 collector/정규화/Orchestrator
연결 완료를 뜻하지 않는다. `/getDataLayer`는 호출하지 않았고 자연 장애 복구나 원자료 개정도
실증하지 않았다. Gate C 제한 통과 범위는 확대하지 않는다.

## 동일 범위 재시험 — D-073 (2026-10-26)

2026-10-26 12:52 UTC에 같은 metadata 요청과 같은 FM08/FXERD01/202609 요청을 각각 한 번 더
실행했다. 둘 다 HTTP 200 및 JSON STATUS 200이었다. Metadata 응답은 25,555 bytes로 기존과 같은
SHA256 `101f4822f48ef210f611a5940ebff604f197b45371ec35db171d3b1d48897466`였고, FXERD01의
명칭, 단위, DAILY 주기, 시작·종료일을 확인했다.

데이터 응답은 995 bytes, SHA256
`9633b5794015ffa16494228f84746152fdf02c7dc08f044d5bdb9f115a4264b2`였다. 응답 구조는
`RESULTSET[0].VALUES.SURVEY_DATES`와 `RESULTSET[0].VALUES.VALUES`이며 각 배열은 30개,
숫자 19개와 null 11개다. 직전 응답과 비교해 달라진 것은 동적 `DATE` 필드뿐이고 요청 범위의
날짜·값은 동일했다. 정규화된 범위 해시는 두 실행 모두
`7785e82d3512b4670dbd39fd176f5fad58377f25bfc5b336854636cf10ba42ab`다.

재시험 중 첫 로컬 검사기는 배열을 `RESULTSET[0]` 바로 아래에서 찾으려 해 구조 검증에 실패했다.
추가 HTTP 요청은 하지 않았고, 보존한 응답 원문을 확인해 매뉴얼/API의 중첩 구조에 맞게 검사기를
수정한 뒤 동일 응답으로 검증을 완료했다. 이번에도 collector·Orchestrator 연결은 만들지 않았으며
새 원자료 변경도 관측되지 않았다. 반복 manifest와 응답은 gitignored
`data/raw/boj_recheck_20261026_repeat/`에 보존했다. 이 결과는 API 접근·응답 형식의 재현 확인이며
Gate C 판정 범위를 확대하지 않는다.

## 후속 제한 collector

이 문서의 D-072/D-073 당시에는 collector가 없었다. 이후 FM08/FXERD01 한 달에 한정한 두-stage
Orchestrator collector가 추가됐고, live 수집 30행 중 11 null을 보존했다. 현재 동작·한계는
[`connectors/BOJ.md`](connectors/BOJ.md)와 [`ITERATION_15_REPORT.md`](ITERATION_15_REPORT.md)를 따른다.
