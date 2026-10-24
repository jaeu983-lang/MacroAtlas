# 05회차 완료 보고 — 기관·사이트 탐색

- **일시:** 2026-10-25
- **브랜치:** codex/iteration-05-institution-site-discovery
**범위:** 기관 후보의 문서화된 공식 도메인 확인, 두 개 사이트 탐색 전략, 프로필 이력 저장.

## 구현 내용

- HTML navigation 전략과 XML sitemap 전략을 서로 독립적으로 구현했다.
- 공식 도메인은 기관 카탈로그의 기존 문서 근거를 입력으로 사용한다. hostname 정확 일치 또는 DNS label 경계를 갖는 하위 도메인만 공식 링크 후보로 분류한다.
- HTTPS가 아닌 URL, 사용자정보가 든 URL, 비표준 포트 및 query가 포함된 링크는 저장 대상에서 제외한다. 외부 링크는 URL을 보존하지 않고 hostname과 출처 문서·전략만 external_candidate로 남긴다.
- 같은 링크의 분류가 전략 사이에서 충돌하면 official_other로 낮추고 전략별 근거 분류를 보존한다.
- 기관 프로필에는 도메인 근거, 문서 URL, fixture/official_docs evidence, 수집 시각, 전략, 링크 분류, 외부 호스트 근거와 live 확인 상태를 기록한다. HTML/XML 본문은 프로필에 복사하지 않는다.
- 프로필 저장은 SQLite의 별도 append-only 테이블을 사용한다. 기존 schema user_version 2와 작업 이력 테이블은 바꾸지 않았다.
- discovery 모듈은 입력 문서만 처리하며 네트워크 클라이언트나 Orchestrator 연결은 포함하지 않는다.

## 변경 파일

- src/macro_data_platform/discovery/institution_sites.py — 문서·기관 후보 계약, URL/도메인 검사, HTML 및 sitemap 탐색, 프로필 생성.
- src/macro_data_platform/storage/institution_profiles.py — 프로필 fingerprint, append-only SQLite 저장·조회.
- src/macro_data_platform/storage/__init__.py — InstitutionProfileStore 공개.
- tests/fixtures/site_discovery/bis_navigation.html — 합성 HTML fixture.
- tests/fixtures/site_discovery/treasury_sitemap.xml — 합성 sitemap fixture.
- tests/test_institution_site_discovery.py — 전략, 공식 도메인 경계, 외부 링크, 충돌, 입력 제한, 저장 이력 검증.
- docs/IMPLEMENTATION_PLAN.md — 05회차 완료와 남은 06~08회차 범위 기록.
- docs/INSTITUTION_CATALOG.md — 기존 기관 문서 근거와 fixture/live 상태 구분.
- docs/REFERENCE_SCENARIOS.md — BIS/TIC fixture 검증과 B/C 전체 NOT_RUN 상태 기록.
- docs/DECISION_LOG.md — D-053, D-054 설계 결정을 기록.

## 테스트 및 검증

- 새 discovery 테스트: **12 passed**.
- 전체 pytest: **445 passed in 21.58s**.
- 전체 Ruff: **All checks passed**.
- 테스트는 합성 fixture와 테스트용 임시 SQLite DB만 사용했다. 기존 Gate A의 live World Bank 보고서를 다시 실행하거나 새로운 외부 HTTP 요청을 하지 않았다.

## 검증 범위와 한계

- BIS HTML 메뉴와 Treasury TIC XML sitemap 전략 두 가지가 fixture 입력에서 재현됐다. fixture URL/본문은 실제 사이트에서 가져온 것이 아니므로 실제 포털·문서 링크가 현재 유효하다는 증거가 아니다.
- official domain 상태는 카탈로그에 있던 문서 근거와 hostname allowlist 비교를 뜻한다. DNS, TLS 인증서, 도메인 소유권, 리다이렉트, HTTP 응답 및 약관을 live 검증하지 않았다.
- 링크 유형은 label/path의 제한된 규칙으로 분류한다. 의미가 충돌하면 official_other로 보수 처리하지만, 통계 적합성이나 다운로드 가능성을 판단하지 않는다.
- CLI, 자연어 검색, Orchestrator 실행 연결, 외부 검색, 이용 안내 수집 및 재사용, metadata/series 검색, 실제 data link 확인은 구현 범위가 아니다. 시나리오 B/C 전체와 Gate B는 NOT_RUN 상태다.

## 보안·데이터 무결성

- 문서 크기와 링크 수에 상한을 적용하고 XML DTD/entity를 거부한다.
- 외부 원문 URL과 query를 저장하지 않으며, 프로필 저장 API에는 update/delete 경로가 없고 SQLite trigger도 수정·삭제를 차단한다.
- 프로필은 후보 도메인 근거와 fixture 근거를 분리하고 site_live_tested=false, links_live_tested=false로 기록한다.
- 05회차 검증 과정에서 저장소의 ignored SQLite DB, raw data, live report를 수정하지 않았다. 네트워크 요청도 하지 않았다.

## 검토 필요 사항

- 변경 diff와 프로필 계약을 사람이 검토한 뒤 체크포인트/병합 여부를 결정해야 한다.
- 해결되지 않은 구현 결정을 따로 남기지 않았다. 06회차 이후 범위는 이번 작업에서 시작하지 않았다.
