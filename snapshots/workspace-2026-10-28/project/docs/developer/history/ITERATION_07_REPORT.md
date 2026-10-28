# 07회차 완료 보고 — 메타데이터 탐색·정규화

- 일시: 2026-10-25 (Asia/Seoul)
- 브랜치: codex/iteration-07-08-discovery
- 상태: 제공된 문서 입력에 대한 07회차 구현·검증 완료. D-057 순차 예외의 선행조건 충족.

## 구현과 변경 파일

- src/macro_data_platform/metadata/models.py: 원문 문서, 필드 근거, 다국어 이름, 통계 변형 및 분류 축·버전·포괄/제외·관계 계약.
- src/macro_data_platform/metadata/adapters.py: 제공된 SDMX 2.1 구조 부분집합의 Dataflow/DSD/Codelist 참조 읽기, API catalogue JSON 및 추출된 표·시트 코드북 어댑터. 출처 도메인을 기존 기관 후보 근거와 대조한다.
- src/macro_data_platform/storage/metadata.py: 원문 bytes·SHA256·출처·수집일·근거와 정규화 결과를 분리 보존하는 append-only SQLite 저장 및 현재 문서 버전의 제한 조회. 기존 user_version=2 유지.
- tests/fixtures/metadata/*, tests/test_metadata_discovery.py: 합성 IMF 구조, World Bank형 catalogue, TIC형 추출 코드북 및 정상/누락/충돌/갱신 검증.
- docs/developer/IMPLEMENTATION_PLAN.md, docs/developer/testing/REFERENCE_SCENARIOS.md, docs/developer/history/DECISION_LOG.md: 완료 상태와 D-058의 근거/한계 기록.

## 검증

- 전용 수용 테스트: 10 passed in 0.45s.
- 전체 pytest: 468 passed in 39.93s.
- 전체 Ruff: All checks passed!
- 코드·정규화·SQLite 테스트는 모두 로컬 합성 fixture와 임시 DB를 사용했다. 새 공식 문서 조사, live 메타데이터/API 요청 및 실제 수집은 수행하지 않았다.

## 데이터 무결성과 범위

- 단위·주기 코드의 매핑은 입력 문서에 명시된 표만 사용한다. 없는 코드·단위는 만들지 않으며 직접 값과 코드 해석이 충돌하면 미상과 경고로 남긴다. 계절조정 미상을 비조정으로 치환하지 않는다.
- 기관·데이터셋·series ID/차원 키는 입력된 식별자만 보존한다. SDMX 구조에서 Cartesian 조합이나 실행 가능한 series 키를 생성하지 않는다.
- 원문 언어별 이름, 추출 필드/셀 위치, 원문 코드, 분류 관계의 축·버전·포괄/제외 근거를 보존한다. 동명만으로 등가 관계를 만들지 않는다.
- 원문은 1 MiB, 정규화 series는 문서당 200개, XML 구조는 10,000개 node로 제한한다. DTD/entity를 거부하고 원문·정규화 저장의 수정/삭제를 trigger로 차단한다.
- SDMX 3.0 전체 문법, 온라인 카탈로그 발견, PDF/XLSX 파일 파서, 실시간 API 가용성 검증은 포함하지 않는다. 표·시트 입력은 명시 column mapping이 있는 추출 JSON이다.
- 같은 원문 문서 ID에 다른 언어/정규화 결과를 덮어쓰지 않는다. 정책 변경으로 새 결과를 보존하려면 새 문서 스냅샷이 필요하다.
- A/B/C 전체 시나리오나 Gate B 완료를 주장하지 않는다. 08회차의 검색·확인·수집 연결은 이 보고서 이후 진행한다.

## 검토와 체크포인트

- 이전 06회차와 D-057 문서 변경을 미커밋 상태로 보존한 채 새 브랜치에 함께 유지했다. 커밋·병합은 하지 않았다.
- 사람은 어댑터 입력 범위, 미상/충돌 정책 및 fixture/live 한계를 검토해야 한다.
