# Iteration 15 — API-first 기관 상태 레지스트리

**날짜:** 2026-10-25\
**결과:** Gate F PASS\
**범위:** A–H 시나리오의 14개 대표 기관. 기관별 상태 레지스트리와 문서 동기화만 구현했다.

## 구현 내용

- `src/macro_data_platform/discovery/source_registry.py`에 불변 기관 프로필과 조회 함수를 추가했다.
- 각 프로필은 공식 API 문서 상태, 접근 우선순위, API 계열, 인증 정책, 환경변수 이름, 비API 공개 경로, 현재 어댑터·fixture 상태, live 검증 범위, 공식 출처 및 조사일을 별도 필드로 가진다.
- 공식 API 문서가 있는 9개 출처는 `documented`/`api_first`, 명세를 찾지 못한 5개 출처는 `unconfirmed`/`api_audit_first`로 등록했다. `not_offered`는 확정된 기관이 없다. 문서 검색 실패만으로 API 부재를 확정하지 않는다.
- `docs/operator/reference/INSTITUTION_CATALOG.md`에 동일한 14개 기관 상태표를 추가했다. 테스트가 코드 레지스트리와 문서표 간 누락을 검사한다.
- `PROJECT_PLAN.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`에 API-first 상태 구분과 후속 한 회차 정책을 반영했다.

## 기관 범위

| 시나리오 | API 문서 확인 | 미확인 | 구현/검증 상태 |
|---|---|---|---|
| A — IMF | SDMX 2.1/3.0 |  | 합성 fixture; API 호출 없음 |
| B — BIS | SDMX REST 2.1 |  | 형식/사이트 fixture; API 호출 없음 |
| C — Treasury TIC |  | API 문서 미확인 | 파일·표 파서 fixture; live 없음 |
| D — BEA | REST API |  | 전용 어댑터 없음; API 키 필요 |
| E — ECB | SDMX REST 2.1 |  | 일반 SDMX fixture; live 없음 |
| E — Eurostat | Catalogue, SDMX 2.1/3.0, Statistics |  | 일반 SDMX/카탈로그 fixture; live 없음 |
| F — 일본 MOF |  | API 문서 미확인 | 공식 CSV/SDMX 파일 일부; 전용 어댑터 없음 |
| F — BOJ | JSON/CSV REST API |  | 전용 어댑터·live 없음 |
| F — e-Stat | REST API 3.0 |  | 전용 어댑터 없음; 앱 ID 필요 |
| G — PBOC |  | API 문서 미확인 | 시나리오 탐색 fixture만; 통계 API 호출 없음 |
| G — SAFE |  | API 문서 미확인 | 시나리오 탐색 fixture만; 통계 API 호출 없음 |
| G — NBS |  | API 문서 미확인 | 시나리오 탐색 fixture만; 통계 API 호출 없음 |
| H — OECD | SDMX REST |  | 전용 어댑터·live 없음 |
| H — World Bank | Indicators API v2 |  | USA/WDI/GDP 한 경로만 제한 live 검증 |

## 검사

- 신규 레지스트리 테스트: **9 passed**.
- 전체 pytest: **602개 테스트 수집**, 실행 종료 코드 0.
- Ruff 전체 검사: 통과.
- `git diff --check`: 통과. Git의 CRLF 변환 안내만 출력됐다.
- 기관 API 호출·다운로드는 수행하지 않았다. 공식 문서 조사와 테스트 fixture, 이전 live 수집 증거를 구분했다.

## 한계와 다음 단계

- 레지스트리는 기관 상태를 분리해 보고하는 기반이다. API 문서가 확인된 기관에도 전용 수집 어댑터가 추가된 것은 아니다.
- `documented`는 해당 기관 또는 서비스에 API 명세가 있다는 뜻이다. 요청한 각 통계가 그 API에서 제공되는지와 실제 접근 가능성은 데이터셋별로 확인해야 한다.
- IMF와 OECD 인증 상태는 미확인으로 남겼다. API가 없는 것으로 확정된 기관은 없다.
- 실제 키는 저장하지 않았다. `BEA_API_KEY`와 `ESTAT_APP_ID`는 설정 시 사용할 환경변수 이름만 기록했다.
- 후속 회차는 공통 SDMX 커넥터 또는 기관별 REST 어댑터를 한 회차씩 추가하고, fixture 테스트와 live 검증을 따로 보고해야 한다.

## 보안·데이터 무결성

- 공식 문서 링크는 HTTPS로 제한하고 URL 자격증명은 거부한다.
- 미확인 출처에는 API 프로토콜이나 호출 endpoint를 만들지 않는다.
- 소스 키 값과 인증 성공 여부를 레지스트리에 넣지 않는다.
- 상태표는 지원 완료나 데이터의 통계적 동등성을 주장하지 않는다.

**사람 검토:** API 상태와 분류는 공식 문서 범위에 기반한 현재 스냅샷이다. 기관별 연결기 구현 우선순위는 후속 회차에서 검토한다. 커밋·스테이징·병합·배포는 하지 않았다.
