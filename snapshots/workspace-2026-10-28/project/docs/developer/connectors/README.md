# 기관 connector 명세

- [API response file archive](API_RESPONSE_STORAGE.md) — 현재 client 9곳의 response 저장·manifest·hash 검증 read-back 범위와 한계
- [공통 HTTP 전송층](HTTP_TRANSPORT.md) — World Bank·JSON·SDMX API 계열의 공통 HTTP 책임과 분리 이유
- [SDMX connector batch](SDMX_FAMILY.md) — 공통 HTTP 아래의 BIS, OECD, ECB, Eurostat, Bundesbank, INSEE route clients와 검증 범위
- [BIS](BIS.md) — 공식 API·통계 근거 프로필 (SDMX client 구현, source payload·workflow·live 미검증)
- [BEA](BEA.md)
- [일본 e-Stat](ESTAT.md)
- [World Bank](WORLDBANK.md)
- [FRED/ALFRED v1](FRED.md) — metadata·검색·명시적 observation page, release/source, synthetic file round-trip
- [Census](CENSUS.md) — 무키 metadata·키를 사용하는 table 조회, synthetic file round-trip
- [BLS 1.0](BLS.md) — 키 없이 최대 25개 series·10년 POST; v2 미구현

각 기관 문서는 공식 근거, raw API client, source payload fixture, file archive, workflow 연결, live 범위를 구분합니다. HTTP 안전 실행은 [공통 transport](HTTP_TRANSPORT.md), SDMX 기관별 route 계약은 [일괄 명세](SDMX_FAMILY.md)에서 관리합니다. 추가 기관도 공통 ingestion 계약을 재사용하되 API·인증·식별자·제한과 성공 상태는 기관별로 남깁니다.
