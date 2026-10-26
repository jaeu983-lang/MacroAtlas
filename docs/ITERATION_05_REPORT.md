# 05회차 — BLS·Census 공식 탐색 및 제한 수집

2026-10-26. 브랜치: `codex/institution-discovery-05`.

## 범위와 실제 기반

현재 체크아웃은 04회차 Gate A 이후 상태다. 대화에 붙여 넣은 과거 보고서의
Census 커넥터, BLS 변수 풀, Q1~Q6 관리자는 이 체크아웃에 없다.
그 구현이나 과거 테스트 수치를 현재 구현으로 간주하지 않았다.
AGENTS.md의 한 작업 한 회차 지침에 따라 05회차만 진행했다.

## 변경

- `discovery/institutions.py`: BLS·Census 어댑터, 기존 기관대장 URL seed 전략,
  제공된 HTML fixture의 상대/절대 링크 전략, 정확한 공식 호스트 검증.
- 동일 기관의 공식 도메인만 허용한다. HTTP, 사용자정보, 다른 포트, query/fragment,
  위장 도메인, 역슬래시/공백 URL은 제외한다. query URL을 모두 제외하는 보수적 정책이므로
  정상적인 query 기반 통계 링크도 이번 범위에서는 지원하지 않는다.
- 입력 HTML 64 KiB, 앵커 200개 상한. 네트워크 요청과 키 값 조회는 없다.
- 프로필에 전략·검사 시각·근거 유형·인증 변수명·API 목적지를 기록하고 매번 새 파일을 쓴다.
  검사는 도메인 소속만 확인하며 live 검증일과 인증 상태를 추정하지 않는다.
- 기존 Orchestrator에 `('institution_discovery', '1')` 엔진으로 등록할 수 있다.
  입력은 `{"institution_id": "bls"}` 또는 `census`이며 선택적으로
  `page: {source_url, html}`을 제공한다. 자동 자연어 라우팅은 추가하지 않았다.
- `.env.example`에 두 변수 이름의 주석 예시를 추가했다. 실제 키는 기록하지 않았다.
- `connectors/{bls,census,statistical_http}.py`, `ingestion/{bls,census}.py`,
  `storage/statistical_downloads.py`: BLS v2와 Census ACS 공식 API용 검증·수집·저장.
  응답은 2 MiB 상한, redirect 거부, TLS 검증을 사용한다. API 키는 각 지정 도메인으로만
  전달하고 응답 URL·manifest·작업 이력에 저장하지 않는다. Census API의 자동 지역코드 열도 보존한다.
- 엔진 등록 키는 `('bls', '1')` 및 `('census', '1')`; 네트워크는 Settings에서 명시적으로 켠다.
  BLS 입력은 series ID 목록/연도 범위, Census 입력은 ACS dataset/연도/변수/`us:1` 또는
  `state:NN` 지리 범위다. 자동 자연어 요청 라우팅과 변수 후보 자동 선택은 없다.

## 검증

`test_institution_discovery.py` 6개와 `test_bls_census_ingestion.py` 10개가 통과했다.
두 기관의 오프라인 탐색, 입력 경계, API parsing, query 검증, 키의 저장 URL 제거,
SQLite Orchestrator 실행과 키 없는 manifest를 검증했다.

실제 BLS API v2 요청은 `CUUR0000SA0`, 2024년에서 `REQUEST_SUCCEEDED`와 월별 관측치
12개를 반환했다. 실제 Census API 요청은 2022 ACS 1-year의 `NAME`, `B01001_001E`,
California(state 06) 한 행을 반환했다. 두 요청 모두 HTTP 200이었고 키 포함 요청이
허용됐다. Census 응답에서 API가 덧붙이는 `state` 열을 발견해 parser를 보완하고 재수집했다.
재수집한 원본과 manifest는 다음에 있다.

- BLS: `data/raw/bls/c0a1106965334732b06807c70052b169/`
- Census: `data/raw/census/dada0b0e2dc5411fafd73653fde9f3a8/`

저장된 BLS/Census raw·manifest를 실제 키와 대조 검사해 키 문자열이 없는 것을 확인했다.

`python -m pytest`는 `No module named pytest`로 시작하지 못했다.
전체 회귀 통과나 과거 433/514/542개 통과를 이번 실행 결과로 주장하지 않는다.
구문 검사(`compileall`)와 `git diff --check`는 통과했다.
Ruff는 `No module named ruff`로 실행하지 못했다. 인증은 키 포함 요청의 성공 응답으로만
확인했으며 secret readiness 상태 자체는 `unknown`이다. 공식 문서 전반의 링크/정의 조사,
단위·주기 의미 검토, Census/BLS 전체 변수 풀 평가, 전체 회귀 검증은 남아 있다.

## 남은 작업과 판단

05회차는 제한된 탐색·수집 경로다. 일반 검색, live 페이지 변경 감지, HTML 원문 보존,
검증된 공식 문서 기반 링크 재확인은 남아 있다. fixture는 실제 페이지를 내려받은 증거가 아니다.
BLS 시리즈 정의와 Census 변수 메타데이터·단위는 자동 추정하지 않았다.
전체 테스트 환경 부재로 전체 회귀 검증을 하지 않았으므로 Gate B 통과를 선언하지 않는다.

새 게시 환경에서 두 secret 바인딩이 존재하고 현재 프로세스에 값이 들어온 것을 확인했다.
이번 작업에서는 환경 설정을 수정하거나 게시하지 않았다. 코드 변경은 branch에 남겨두었다.

## 후속 전체 회귀 확인

후속 06회차에서 개발 의존성을 설치하고 전체 pytest 456개 및 Ruff를 통과했다.
이 결과는 05·06회차 변경을 함께 포함하며, 최초 05회차 작업 때 pytest가 없었다는 기록을 보완한다.
