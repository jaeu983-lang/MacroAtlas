# 보완 01 계약 확장 결과 — 2026-10-24

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

범위: 최신 기획의 파일/링크/둘 다·링크 가용 상태·후보 그룹/변형을 **값 계약으로만** 추가했다.
통합 보완 계획은 갱신했으며 보완 02·03과 04회차는 진행하지 않았다.
브랜치: codex/workflow-alignment-01-extensions. 커밋·병합·배포 없음.

## 시작 상태와 호환 전략

AGENTS/GUIDELINES, PROJECT_PLAN의 관련 절, IMPLEMENTATION_PLAN, OUTPUT_AND_VARIANT_POLICY,
WORKFLOW_ALIGNMENT_PLAN, 기본 값 모델/테스트와 결정 로그를 확인했다.
시작 전체 **241 passed in 6.16s**, Ruff 통과. 모든 시작 파일은 untracked 상태였다.

기존 모델에 선택 필드를 추가해 JSON/hash가 변하는 방식을 피하고 새 wrapper 모듈을 사용했다.
기존 workflow_contracts.py의 변경 전/후 파일 SHA-256은 동일했다.

```text
c32035793b586f10f743e912a6198f9deba7d5a7235d3baae3a9cf61225fbb9a
```

확장 전 JSON 5종(DataRequest/Candidate/CandidateProposal/OutputSpec/ConfirmedSelection)을
golden fixture로 저장하고 원문과 byte 단위 canonical JSON 왕복을 테스트했다.
기존 ConfirmedSelection의 고정 fingerprint도 동일하다.

```text
92b82d2b99402fba6a7704aed19e10db20dceb4345c1146f8a3d54d2cd8b7d96
```

새 wrapper는 별도 의미의 hash를 만들며 기존 확인과 같은 hash라고 주장하지 않는다.
새 기록도 JSON schema_version=1을 사용하지만 종류는 별도 클래스/필드 구조로 구분한다.
옛 기록은 기존 API로 읽으며 자동 업그레이드/승격·SQLite 이관은 하지 않는다.

## 변경 파일과 이유

| 파일 | 변경 이유 |
|---|---|
| src/macro_data_platform/workflow_extensions.py (신규) | 전달·링크·그룹/변형 및 확정 wrapper, 순수 선택지/일관성 계산 |
| tests/test_workflow_extensions.py (신규) | 신규 77개 결정적 계약·보안 경계·golden 호환 테스트 |
| tests/fixtures/workflow_v1_golden.json (신규) | 변경 전에 고정한 기존 JSON 5종 |
| docs/WORKFLOW_ALIGNMENT_PLAN.md | 확장 계약과 보완 02/03의 연결 계획을 통합 갱신 |
| docs/IMPLEMENTATION_PLAN.md | 확장 값 계약 범위와 후속 모드별 실행 의도 구분 |
| PROJECT_PLAN.md | 값 계약과 자동 탐색·질문/실행의 현재 상태 구분 |
| docs/OUTPUT_AND_VARIANT_POLICY.md | 정책의 값 계약 반영 부분·미구현 부분 명시 |
| docs/USER_WORKFLOW_REVIEW.md | 최신 확장 보고서 연결 |
| docs/ARCHITECTURE.md | 새 API·JSON/hash·link-only 검증·호환/보안 경계 문서화 |
| docs/DECISION_LOG.md | D-034 일부 해결, D-035~038 선택과 남은 문제 |
| docs/ALIGNMENT_01_EXTENSION_REPORT.md (신규) | 이 보고서 |

기존 생산 코드·테스트·오류 enum/ValueError 계약·의존성·Orchestrator·수집기·실행 정책은 변경하지 않았다.

## 구현한 값 계약

- DeliverySpec: None/file/link/both. 미지정은 requires_choice=True이며 확정 불가다.
  file은 기존 OutputSpec, link는 명시적인 link_ids를 쓴다. 누락 설정을 자동으로 채우거나
  불가능한 방식을 다른 방식으로 대체하지 않는다. link-only는 파일 설정을 받지 않는다.
- DataLink: available/unavailable/unknown/blocked, 실제 데이터/참조 링크 유형,
  후보·제안 개정·조건 hash, UTC 확인/만료 시각, 공식·공개 접근·공유 선언, 근거/제약을 보존한다.
  available에는 공개 데이터 URL·근거·확인 시각과 수동 필터 여부가 필요하다. 홈페이지 reference,
  차단/미확인/만료 링크는 선택지에서 제외한다. unavailable은 해당 조사 범위의 근거이지
  기관 전체에 링크가 없다는 주장이 아니다.
- VariantAttributes/CandidateVariant: 계절조정·가격/기준년·stock/flow·수준/변화율,
  주기·단위/배율·개정/방법론/대상·원코드와 근거를 보존한다. None을 비조정으로 바꾸지 않는다.
- CandidateGroup/GroupedProposal: 기존 제안을 수정하지 않고 그룹/변형을 연결한다.
  없는/중복 참조, 다른 concept, 알려진 stock/flow·level/rate 충돌 및 기존 주기/단위 모순을 거부한다.
  자동 분류·동일성 판정·숫자 합산·모든 변형 자동 선택은 없다.
- DeliveryOffer/ConfirmedDelivery: 선언된 형식·그 시각의 유효 링크로 가능한 전달 모드를
  계산하고, 선택·조건·요구 변형을 확인한다. 파일 부분은 기존 ConfirmedSelection을 사용한다.
  링크 전용은 로컬 collector/exporter나 그 API 키 설정을 요구하지 않지만 원자료의 의미/범위는
  확인돼 있어야 한다. 단위 변환을 링크로 수행했다고 표시하지 않는다.

target/confirmation hash는 request·제안/그룹/변형·요구 조건·선택 링크/전달 설정을 연결한다.
링크 URL/가용성/만료·조건·그룹 근거·변형이 바뀌면 기존 확인과 matches가 달라진다.
확인 시각/방법은 기록하되 내용 hash에서는 제외한다. 원본 파일 hash나 서명이 아니다.

## 전체 테스트와 Ruff — 실제 결과

기존 .venv Python 3.12.14/pytest 8.4.2를 사용했다. 실제 API·URL 접근·키/환경변수 조회 없음.
새 테스트의 official/public/available 선언과 근거는 합성 fixture이며 실제 검증을 뜻하지 않는다.

| 검사 | 최종 결과 |
|---|---|
| `.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_alignment01ext_final` | **318 passed in 6.66s**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py` | **All checks passed!**, 종료 코드 0 |
| 기존 모듈 변경 전/후 SHA-256 비교 | 동일, assert 통과 |
| 기존 JSON 5종과 기존 확인 hash 회귀 | 원문/해시 동일, 테스트 통과 |
| `.venv/Scripts/python.exe -m macro_data_platform.health` | 종료 코드 0 |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| `git diff --check` | 종료 코드 0. untracked 파일 검증을 대신하지 않음 |

기존 241개 + 신규 77개, 실패/건너뜀 없음.
로그는 reports/alignment_01_extension_pytest.txt, reports/alignment_01_extension_ruff.txt다.
개발 중 최초 전체 314개도 통과했으며, Ruff의 미사용 표현 1건은 수정 후 통과했다.

신규 테스트는 3모드/미지정·누락/미지원·무자동대체, 4링크 상태/조사 근거/공개 여부,
만료·확인 시각·조건/개정 불일치·reference/수동 필터, link-only의 파일/수집기 독립성,
원본/그룹 참조와 SA/NSA·다른 통계 개념 분리, 변형 미상/불일치, 새 hash 변조·변경,
기존 JSON/hash·오류 유지, 불변 복사·UTC·URL 비밀값 거부·무부작용을 포함한다.
링크만 제공하는 제품 실행기가 완성됐다는 테스트는 아니며 값 연산이 HTTP/DB/파일을
생성하지 않는 것을 확인했다. 실제 API 검증은 이번에 NOT_RUN이다.

## 보안·데이터 완전성 및 남은 문제

- 키·.env·TXT·자격증명 저장소를 읽지 않았다. 기존 관측치·raw·DB도 변경하지 않았다.
  통상 자격증명/signed query URL을 거부하고 repr/오류에 입력값을 넣지 않는다.
  자유문장과 모든 URL의 비밀값을 보편적으로 검출하는 필터는 아니다. JSON 원문은 로그에 주의해야 한다.
- 현재 가용성·공식성·공개 여부는 제공된 검증 기록이다. URL을 실제 열어 공식성·데이터 내용·
  권한/기간 일치를 확인하는 모듈은 없다. 저장된 확인의 복원은 현재 유효성을 보증하지 않는다.
- URL fragment는 데이터 링크에서 보수적으로 거부한다. 정상 문서 section anchor는 근거로 허용한다.
  정상 viewer의 fragment routing 등은 검증된 기관별 정책이 후속으로 필요하다.
- 그룹은 제공된 개념과 알려진 속성의 일관성만 검증한다. 모든 방법론·모집단의 통계적
  동등성을 판정하지 않는다. 확정은 한 후보이며 복수 변형 확정/자동 집계는 없다.
- 질문 서비스·실제 링크 발견/병행 실행·Excel/CSV 생성·사용자 선호 저장은 미구현이다.
  기존 v1에는 새 의미를 소급하지 않는다. 새 요청 경로가 wrapper를 쓰도록 연결하는 것은 보완 02다.
- 보완 03의 World Bank 실제 모드 분기·새 기관 지원, 04회차의 품질/정규화/피드백 작업은 하지 않았다.
- dependency lockfile·PowerShell 서명 정책·Git 체크포인트 제한은 남아 있다. 모든 파일이
  untracked이므로 병합 전 사람의 전체 변경 검토가 필요하다.

통합 계획 갱신과 보완 01 확장 수용 기준은 통과했다. 사람은 additive wrapper/보수적
링크 정책/그룹 한계를 검토해야 한다. 이번 범위를 끝내는 데 추가로 필요한 차단 결정은 없다.
보완 02·03과 04회차는 별도 요청 전까지 진행하지 않는다.
