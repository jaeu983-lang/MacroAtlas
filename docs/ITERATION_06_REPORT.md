# 06회차 — 기관별 공식 안내와 수집 전략

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

2026-10-26. 현재 작업 브랜치 `codex/institution-discovery-05`에서 이어 수행했다.
선행 05회차의 미커밋 변경과 live data는 그대로 보존했다.

## 구현

- `src/macro_data_platform/discovery/institution_guides.py`에 고정 공식 URL catalog,
  institution strategy 선택, 안전한 fetch, HTML visible-text/JSON 추출, write-once archive,
  최신 유효 가이드 hash 재검증과 TTL 기반 재사용 판단을 추가했다.
- fetch 입력은 curated `guide_id`뿐이다. HTTPS exact-host, redirect 거부, 기본 TLS 확인,
  2 MiB·30초 제한을 적용한다. HTTP 실패는 body를 저장하지 않고 status manifest를 남긴다.
- 성공 시 원본 body, 추출 텍스트, SHA256·조회 시각·원본 URL·추출 방법·라이선스 미평가
  manifest를 별도 UUID 경로에 저장한다. 동일 guide를 refresh할 때 새 파일을 쓰고 직전
  hash와 비교해 `changed`/`unchanged`를 남긴다. 링크는 같은 공식 host·HTTPS·query 없음만
  후보로 보존하고 상태는 `candidate_unverified`다.
- `read_strategy_guides(settings, institution_id, max_age_seconds=...)`는 로컬 archive를
  hash 검증한 뒤 해당 기관이 참조하는 가이드 경로를 반환한다. `max_age_seconds`를 생략하면
  신선도는 `unknown`; 자동 갱신이나 고정 TTL은 없다.
- 등록 엔진 식별자는 `guide_documentation/1`; 전략은 `select_strategy("bls"|"census"|"imf"|"treasury_tic")`로 고른다.
  BLS/Census는 기존 제한 수집 엔진을 참조하고 IMF/TIC 수집 방식은 미구현 상태로 표시한다.

## live 공식 문서 확인

공식 fetcher로 9페이지를 HTTP 200에서 받아 raw HTML·추출 텍스트·manifest를 보존했다.
IMF 안내는 첫 요청에서 403이 나왔지만, 이후 `MacroAtlas/0.1` 식별 User-Agent를 포함한
정상 HTTPS 요청에서는 200을 받았다. 인증이나 redirect 우회는 사용하지 않았다.

| 전략 | 가이드 | 확인한 내용 |
|---|---|---|
| BLS | API Signatures v2.0 | 한 series는 3년, 등록된 다중 series는 3년 동안 최대 50 ID, 최대 20년 요청/선택 파라미터는 registration key 조건 |
| Census | API guide, API key, query limits, core concepts, Terms | 각 data query에 key 필요, 최대 50 variables, dataset별 필수 변수와 geography 확인 필요 |
| IMF | API page | SDMX 2.1/3.0, Swagger 탐색은 beta portal 로그인 필요 |
| Treasury TIC | portal, Contact TIC & Using TIC | 대부분 TXT/tab TXT/CSV/HTML/PDF; Excel 제공 안 함, 연간 securities 일부 MHT 예외 |

실제 archive 예시는 `data/raw/guides/imf_api/cd4d428bcdb44bce801c0c09943e9f7b/` 및
`data/raw/guides/tic_usage/1c9c15a60c454409a677795cd041cff1/`에 있다. 전체 가이드는
`data/raw/guides/<guide_id>/<capture_id>/`에 보존된다. 해당 raw 폴더는 `.gitignore` 대상이다.

## 검증과 미완료

새 `tests/test_institution_guides.py`는 7개 테스트를 포함해 allowlist, 텍스트 추출,
실패 상태, hash 무결성, TTL, 변경 시 새 archive 생성, Orchestrator 등록을 확인한다.
`python -m pip install -e '.[dev]'`로 현재 실행 환경에 개발 의존성을 설치한 뒤 전체
`python -m pytest` 456개가 통과했다. `python -m ruff check src tests`와 `git diff --check`도 통과했다.

HTML/JSON만 텍스트로 추출한다. PDF는 원본만 저장하고 검토 상태로 둔다. Terms 페이지를
보존했지만 라이선스/재배포 판단은 수행하지 않았다. 링크 후보는 열어 검증하지 않았고,
자동 주기 실행도 없다. IMF/TIC 수집기와 일반 대화 라우팅은 여전히 미구현이다.
환경 설정 draft나 publish 상태는 변경하지 않았다.
