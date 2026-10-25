# 08회차 완료 보고 — 시계열 검색·확인·수집 연결

- 일시: 2026-10-25 (Asia/Seoul)
- 브랜치: codex/iteration-07-08-discovery
- 상태: D-057의 07→08 순차 실행 완료. Gate B는 로컬 fixture 범위에서 통과했으며 live/full-scenario 검증은 미실행이다.
- 선행 근거: 07회차의 전체 pytest 468개/Ruff 통과와 docs/developer/history/ITERATION_07_REPORT.md 작성을 마친 후 08회차를 시작했다.
- 후속 개념군 보완: 최초의 Concept ID 동일 필터와 정의 문구 동일 그룹은 넓은 GDP 질의의 명목·실질 후보를 누락할 수 있었다. D-061에 따라 수정했으며 보완 결과는 docs/developer/history/CONCEPT_SEARCH_REVISION_REPORT.md, 수정 기획은 docs/developer/planning/CONCEPT_SEARCH_REVISION_PLAN.md를 따른다. 아래 499개 결과는 최초 검증이고, 보완 후 전체는 515 passed in 45.20s 및 Ruff 통과다.
- 후속 코드 리뷰 보완: 개념 미상 질의의 무차별 주요 후보와 명시 국가/기간 조건에 어긋난 관련 참고 노출을 수정했다. 이 보완의 현재 Gate B 재검증은 전체 516 passed in 32.08s, Ruff 통과다. 앞의 499/515 결과는 각 당시 기록으로 보존한다.

## 구현 결과

- 제공된 현재 메타데이터에서 근거 있는 검색 개념군/하위 유형·기관·국가·기간·차원·통계 변형을 확인하고 후보와 제외 사유를 반환한다. 이름 유사성만으로 개념이나 series key를 만들지 않는다. 기관 미지정 검색과 지정 검색을 지원하며 지정 기관에 후보가 없으면 검토 상태로 남긴다.
- 제한된 한국어/영어 어휘의 자연어 입력을 구조화 요청으로 변환한다. 모르는 개념·기간·단위 정책 등은 기본값으로 채우지 않는다. 모호한 기관명은 다른 기관으로 대체하지 않고 미해결 상태로 유지한다. 구조화 DataRequest 입력도 지원한다.
- 같은 검색 개념군에 속하는 변형은 근거와 함께 묶고 정의·조정/가격 등의 차이를 보존한다. 정의 문구가 다른 명목·실질 GDP도 같은 검색 그룹에 제시하되 통계적 등가성을 주장하지 않는다. 범위·stock/flow·measure 차이를 합치지 않으며 보유잔액과 거래액을 같은 유형으로 처리하지 않는다.
- 중앙은행 요청에 더 넓은 공공부문 자료만 있는 fixture는 명시 수용 전 수집할 수 없다. 수용은 새 확인 기록/개정과 discovery_context에 남고 요청 범위·원정의·분류 관계를 덮어쓰지 않는다. 관계 미상은 계속 검토 대상으로 남긴다.
- 기존 WorkflowService에 후보·조건·전달 확인을 연결한다. 전달 미지시는 사용 가능한 방식만 질문하며, 이미 명시된 조건을 반복해서 묻지 않는다. 원문 metadata revision 또는 연결된 SDMX 구조가 바뀌면 확인·실행을 무효화한다. 기존 WorkflowService/Orchestrator를 직접 호출해도 이 검사를 우회할 수 없다.
- 기존 고정 World Bank USA GDP 경로를 검색 결과와 연결하고 Gate A 수집·검증기를 재사용한다. 기관대장의 INT-04 ID와 기존 worldbank ID를 지원한다.
- 기관별로 등록하는 DeclaredCSVRoute는 원문에 명시된 URL과 period/country/value 열 매핑만 처리한다. 주입된 분류 명시 transport로 원문 CSV와 manifest를 새 UUID 경로에 보존한 후 요청 범위의 관측치를 파싱한다. 1 MiB, 1~120개 연/월 기간, 1~10개 국가로 제한한다. 누락 기간·중복·비유한 값·열 변화는 검토 상태로 중단하며 저장된 원문을 유지한다.
- file/link/both를 연결했다. 파일은 기존 raw_json 또는 최소 경로의 raw_csv만 지원하며 링크 전용은 transport·파서·자료 파일 없이 전달한다. 링크의 available/unavailable/unknown/blocked, 만료 및 메타데이터 개정을 보존한다. 링크 전달 성공을 다운로드 성공으로 취급하지 않는다.

## 변경 파일

- src/macro_data_platform/discovery/series.py: 자연어 부분 해석, 후보 검색·차이 질문·그룹, 근거와 범위 수용의 이력 연결, 실행 전 현재 근거 검증.
- src/macro_data_platform/ingestion/discovered.py: World Bank 경로 등록, 명시 스키마의 작은 CSV 경로, 원문/manifest/관측치와 링크 전달.
- src/macro_data_platform/orchestration/workflow.py: discovery_context가 있는 요청/작업에만 현재 메타데이터·통계 의미 검사를 적용. 과거 JSON·워크플로는 유지.
- src/macro_data_platform/ingestion/worldbank_request.py: 기존 경로의 공식 기관대장 ID INT-04 허용. 국가·지표·기간·출력 제한은 유지.
- src/macro_data_platform/metadata/models.py, metadata/adapters.py, storage/metadata.py: 출처에 명시된 접근 URL/스키마/유효 시각과 구조 스냅샷 연결의 추가 계약. SDMX 키를 실제 제공된 DSD/Codelist와 대조하며 낡은 구조는 해당 후보만 검토 대상으로 둔다.
- tests/test_series_discovery.py, tests/test_metadata_discovery.py 및 tests/fixtures/metadata/*: Gate B 정상·불일치·모호성·실패·근거 변경과 원문 무결성 검증.
- AGENTS.md, PROJECT_PLAN.md, docs/developer/IMPLEMENTATION_PLAN.md, docs/developer/history/DECISION_LOG.md: D-057 예외 사용 완료, D-059/D-060 및 최신 상태.
- docs/operator/reference/INSTITUTION_CATALOG.md, docs/developer/testing/REFERENCE_SCENARIOS.md: fixture 증거와 실제 기관/시나리오 미검증 구분.

## 검증 결과

- 최종 전체 pytest: **499 passed in 46.13s**.
- 최종 전체 Ruff: **All checks passed!**
- 코드 변경 후 전체 테스트를 실행했으며 real HTTP는 fixture 테스트에서 차단했다. 네트워크 설정을 변경하지 않았다.
- A형: 합성 IMF Dataflow→DSD→Codelist에 연결된 제공 series key를 검증하고 후보를 검색했다. 존재하지 않는 코드와 개정된 구조는 사용하지 않는다. IMF 실제 수집은 미지원이다.
- C형: 합성 TIC 코드북→보유잔액 후보→조건/전달 확인→CSV 원문 보존·최소 파싱 E2E를 통과했다. 123.5, 결측, 0을 구별하고 다른 국가 행을 요청 결과에 섞지 않는다.
- World Bank: 제공된 catalogue에서 기관 미지정/INT-04 지정 검색→기존 확인→고정 경로의 수집·Gate A 검증을 fixture transport로 통과했다.
- 메타데이터 변경 뒤의 직접 실행 차단, 명시 재확인과 이전 작업 취소/새 작업 연결, 재검증 시 확인 시각/작업 보존, 만료/차단 링크와 XLSX 미지원, network=false에서 live transport 호출 전 차단, 원문 및 manifest hash 재확인 등을 검증했다.

## 한계와 미검증

- 새 공식 문서 조사, 온라인 기관/카탈로그 검색, 실제 IMF/TIC API·파일 다운로드, 현재 링크·약관 검증은 하지 않았다. fixture URL/식별자/본문은 합성 자료다.
- Gate B 통과 주장은 위 로컬 fixture 서비스 범위에 한정한다. A/B/C/D/E 전체와 실제 서비스 증거는 PASS로 승격하지 않는다.
- 자연어 어휘와 기관 별칭은 제한된 명시 목록이다. 임의 문장의 완전한 의미 이해나 CLI/채팅 UI는 구현하지 않았다. 한국어/영어 외의 언어·복잡한 비교 요구는 구조화 입력이나 추가 확인이 필요하다.
- 메타데이터는 제공된 문서를 수동/프로그램으로 ingest한 저장소에서 검색한다. 자동 웹 조사·SDMX 3.0 전체·실제 XLSX/PDF 파서와 기관별 대규모 탐색은 포함하지 않는다.
- CSV 경로에는 기본 live HTTP client가 없다. 호출자는 별도 검증된 transport를 등록해야 하며 live mode는 network_enabled 설정을 요구한다. 이번 테스트는 fixture transport만 사용했다. 인증 필요/미상 경로는 파일 지원으로 승격하지 않는다.
- CSV의 단위·주기는 코드북 근거를 보존하며 CSV 본문에서 별도로 재검증하지 않는다. 최소 열/값/요청 범위 검증이 경제적 이상치·개정 이력·라이선스 검증을 의미하지 않는다.
- 09회차의 다중 파일 파서, Excel/변환 출력, 압축/대량 분할 및 10회차의 종합 품질·복구 기능은 별도 범위다.

## 보안·데이터 무결성과 검토

- 원문과 source evidence는 fixture/official-docs/live-ingestion 상태를 구분한다. 제공된 도메인 근거는 현재 TLS/소유권/접근성을 live 검증했다는 뜻이 아니다.
- raw/manifest는 저장소 내 새 경로에만 쓰고 기존 원문을 덮어쓰지 않는다. 관측치의 결측을 0으로 바꾸지 않으며 숫자의 원문 문자열도 남긴다. metadata 원문/정규화 이력은 append-only로 보존한다.
- 프로젝트의 실제 카탈로그 DB나 이전 raw/live 보고서를 수정하지 않았다. 테스트용 DB와 산출물만 사용했으며 기존 user_version=2와 과거 Task JSON을 유지한다.
- 06회차 미커밋 변경을 보존한 채 07~08회차 변경을 함께 남겼다. 커밋·병합은 하지 않았고, 09회차는 시작하지 않았다.
- 사람은 변경 diff, Gate B의 fixture 한정 범위와 남은 live/이용 조건 검증을 검토해야 한다. 이번 기술 검증을 사람의 diff 승인으로 대신하지 않는다.
