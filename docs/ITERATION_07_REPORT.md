# 07회차 구현 보고서 — 메타데이터 탐색·정규화

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

2026-10-26. 브랜치 `codex/institution-discovery-05`에서 기존 미커밋 05·06회차 작업을
보존한 채 진행했다. 환경 설정 draft나 게시 상태는 변경하지 않았다.

## 구현

- `connectors/metadata.py`가 고정된 공식 BLS v2 catalogue 경로와 Census ACS variable 경로를
  호출한다. 입력은 단일 BLS series 또는 단일 Census variable로 제한한다. BLS 키는 POST body,
  Census 키는 HTTPS 요청 query에만 들어가며 반환 source URL에는 제거된다.
- `ingestion/metadata.py`는 `bls_metadata/1`, `census_metadata/1`, `codebook_metadata/1`,
  `sdmx_metadata/1` Orchestrator engine 구현을 제공한다. Orchestrator에는 기존 방식대로
  `(engine_name, version)` mapping으로 주입한다. 네트워크 API engine은 설정의
  `network_enabled`가 true가 아니면 전송하지 않는다.
- 공통 정규화 결과는 `known`, `unknown`, `conflict` 상태와 원문 pointer를 가진다. BLS의
  catalogue title, area, seasonality 및 공개 차원은 source field에서 옮겼다. Census label은
  원문 표기를 보존하고 concept/predicate 필드는 source attributes로 남겼다. 근거 없는
  definition, unit, frequency, geo/time coverage는 unknown이다.
- SDMX-ML 2.1 parser는 Dataflow, DataStructure, Codelist와 multilingual Name, 구조 참조,
  dimension ID와 code 목록을 읽는다. XML 2 MiB 상한을 두고 DTD/entity를 거부한다.
  Codebook adapter는 이미 읽은 행을 입력받아 언어별 열 매핑, alias 간 값 충돌, 중복 ID의
  불일치를 표현한다. XLS/XLSX 자체를 읽는 parser는 포함하지 않았다.
- 원본 수신 직후 write-once raw JSON/XML과 request manifest를 저장한다. 정규화가 성공하면
  별도 processed 경로에 JSON과 최종 hash manifest를 기록한다. 정규화 실패에도 수신한 raw는
  남기고 결과를 review 상태로 돌린다.

## Live 확인

두 요청 모두 설정된 키를 엔진 내부에서 사용했고 HTTP 200으로 끝났다. 키 값은 보고서나
산출물에 기록하지 않았다.

| 기관 | 요청 | 결과 | 확인된 필드 및 미상 |
|---|---|---|---|
| BLS | `CUUR0000SA0`, 2024, `catalog=true` | HTTP 200, record 1 | name, geo coverage, seasonal adjustment, dimensions 확인. definition, unit, frequency, time coverage 미상 |
| Census | ACS 2022 1-year, `B01001_001E` | HTTP 200, record 1 | label과 concept/predicate source attributes 확인. definition, unit, frequency, geo/time coverage 미상 |

로컬 raw·normalized 파일과 두 SHA256은 각각 manifest 값과 일치했다. 실제 키 문자열은 두
패키지의 raw response, normalized JSON, manifest에서 발견되지 않았다. 파일 경로는
`data/raw/metadata/{bls,census}/<package>/`와
`data/processed/metadata/{bls,census}/<package>/`이다. 이 디렉터리는 Git ignore 대상이다.

## 검증과 한계

신규 정규화, SDMX fixture, XML 제한, codebook 다국어/충돌, 원본·표준 층 분리 및 Orchestrator
연결 테스트를 추가했다. 전체 `python -m pytest` 결과는 **470 passed**, `python -m ruff check
src tests`와 `git diff --check`도 통과했다.

IMF/BIS SDMX API의 실제 호출, 기관 전체 API 목록 순회, XLS/XLSX reader, 재배포 조건 판단,
분류 범위·중첩의 의미 모델과 후보 검색은 구현하지 않았다. 따라서 이번 실측은 BLS와 Census의
각 metadata endpoint 한 건에만 해당하며 기관 전체 준비도나 통계적 동등성의 증거가 아니다.
