# 06회차 완료 보고 — 이용 안내·기관별 전략

- **일시:** 2026-10-25
- **브랜치:** codex/iteration-06-guide-strategy
- **범위:** 안내 문서의 유형·출처·원문·추출 이력 보존 및 기관별 전략 선택·재사용. 07회차는 시작하지 않았다.

## 구현 내용

- GuideCategory는 API 가이드, 이용 정책, 코드북, 통계 해설을 구분한다. SourceGuide는 기관 ID, 유형, HTTPS 출처 URL, media type, 원문 bytes와 SHA256, 수동 제공 추출 텍스트·경로, retrieval/expiry/version, 증거 유형·참조를 검증하고 보존한다.
- GuideStore는 기존 SQLite user_version=2를 유지하며 별도 append-only 가이드·전략 테이블을 사용한다. 저장 전에 문서 URL을 기관 후보의 기존 공식 도메인 근거와 대조하고, 원문 크기를 1 MiB로 제한한다. 스냅샷과 전략 규칙은 UPDATE/DELETE trigger로 덮어쓰기와 삭제를 막는다.
- 읽을 때 원문에서 SHA256과 guide ID를 재계산해 저장된 식별자와 대조한다. 저장 데이터의 hash/identity 불일치가 있으면 조용히 사용하지 않고 오류로 중단한다.
- 기관별 전략 규칙은 명시 태그, 우선순위 및 정확한 가이드 snapshot ID를 저장한다. 더 구체적인 규칙을 우선 선택하고, 같은 점수의 모호성은 NEEDS_REVIEW로 반환한다. 만료는 GUIDE_EXPIRED, 최신 스냅샷의 원문·추출·버전·만료 등 의미 있는 변경은 GUIDE_CHANGED로 반환하며 자동 대체하지 않는다. 만료 시각이 없으면 경고한다. 단순 재조회 시각 변경은 그 자체로 내용 변경으로 취급하지 않는다.
- IMF 문서는 API_GUIDE, Treasury TIC 문서는 USAGE_POLICY로 구분한다. 두 입력 본문은 합성 fixture이며 공식 페이지에서 복사하지 않았다.

## 변경 파일

- src/macro_data_platform/discovery/guides.py — 가이드 유형·스냅샷·전략 선택 계약, 입력 검증, 해시 및 만료/변경 상태.
- src/macro_data_platform/storage/guides.py — SQLite append-only 스냅샷·전략 규칙 저장 및 기관 도메인 근거 확인.
- src/macro_data_platform/storage/__init__.py — GuideStore 공개.
- tests/fixtures/guide_documents/imf_sdmx_api_guide.txt — 합성 IMF API 안내 fixture.
- tests/fixtures/guide_documents/tic_usage_policy.txt — 합성 TIC 이용 정책 fixture.
- tests/test_source_guides.py — 문서 유형 왕복, 원문/추출 이력, 해시, 도메인 경계, 기관별 재사용, 변경·만료·모호성 검증.
- PROJECT_PLAN.md, docs/developer/IMPLEMENTATION_PLAN.md — 최신 완료 범위와 07~08회차 잔여 계획 기록.
- docs/operator/reference/INSTITUTION_CATALOG.md, docs/developer/testing/REFERENCE_SCENARIOS.md — fixture와 미검증/live 상태 기록.
- docs/developer/history/DECISION_LOG.md — D-055와 D-056 설계 기록.
- docs/developer/history/ITERATION_06_REPORT.md — 이번 범위와 검증 결과.

## 테스트 및 검증

- 전체 pytest: **458 passed in 26.54s**.
- 전체 Ruff: **All checks passed!**
- git diff --check: 통과. Git은 수정된 Markdown 파일의 LF를 다음 기록 시 CRLF로 바꿀 수 있다는 경고만 출력했다.
- 테스트는 로컬 코드, 합성 fixture 및 테스트용 SQLite DB만 사용했다. 실행에 필요한 PYTHONPATH는 저장소의 src 디렉터리로 설정했다.
- IMF/Treasury 웹사이트, SDMX/TIC API 또는 기타 네트워크에 접속하지 않았다.

## 검증 범위와 한계

- 카탈로그에 이미 기록된 IMF/Treasury URL을 후보 공식 도메인 대조에 재사용했다. 이 작업에서 URL의 현재 응답, 페이지 내용, 리다이렉트, 약관 및 이용 조건을 확인하지 않았다. 문서 URL이 official domain 규칙에 맞는다는 것은 live 도메인 소유·TLS·접근성 검증을 뜻하지 않는다.
- 원문 bytes와 이미 제공된 추출 텍스트·경로를 저장하지만 HTML/PDF 내려받기, 파싱, 문서 변경 자동 탐지는 구현하지 않았다. 변경 감지는 새 SourceGuide 스냅샷이 저장된 뒤 비교한다.
- 코드북·통계 해설은 모델과 SQLite 저장 왕복을 지원한다. 이번 회차 fixture 사례와 기관 전략은 IMF API 안내 및 TIC 이용 정책에 한정한다.
- 자연어 요청 태깅, Orchestrator/CLI 연결, dataset/series 검색·수집, 실제 IMF/TIC API 흐름은 범위에 없다. 시나리오 A/B/C 전체와 Gate B는 NOT_RUN이다.

## 보안·데이터 무결성

- 외부 URL은 HTTPS이며 사용자정보와 query가 없어야 하고, 저장 시 기관 후보에 기록된 공식 도메인 또는 하위 도메인인지 확인한다. 이는 기존 문서 근거를 이용한 hostname 규칙이며 live 검증은 아니다.
- 원문과 추출 텍스트의 크기를 각각 제한한다. 원문은 bytes로 보존하고 hash를 저장하며 스냅샷 및 규칙을 append-only로 유지한다. 원문 수정·삭제는 자동화하지 않는다.
- 이번 테스트는 무작위 임시 DB를 사용했다. 프로젝트의 실제 카탈로그/프로필 DB, 기존 raw 자료 및 04회차 live 보고서는 수정하지 않았다.
- 가이드 저장은 이용·재배포 권한을 부여하거나 API 호출을 승인하지 않는다. 적용 전에 해당 기관·자료의 이용 조건을 별도로 검토해야 한다.

## 검토 필요 사항

- 변경 diff와 D-055/D-056 정책을 사람이 검토한 뒤 체크포인트/커밋 여부를 결정해야 한다. 이번 작업은 커밋을 만들지 않았다.
- 07회차 메타데이터 탐색·정규화는 별도 지시를 기다린다.
