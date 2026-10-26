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
