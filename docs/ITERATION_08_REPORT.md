# 08회차 구현 보고서 — 후보 검색과 수집 연결

> 아래 첫 판정은 회차 종료 당시의 넓은 Gate B 조건을 기록한다. 현재 제한 범위 판정은 하단
> ‘후속 Gate B 범위 판정’과 `docs/IMPLEMENTATION_PLAN.md`를 따른다.

2026-10-26. 이전 변경은 유지하고 08회차를 09회차와 순차 진행했다. 실행 환경 조회에서
HTTP policy는 `unrestricted`이나 적용 상태가 `unknown`, API secret readiness도 `unknown`이었다.
이번 회차는 외부 API를 호출하지 않고 local catalog와 deterministic fixture로 검증했다.

## 구현

- `discovery/series_search.py`의 `CandidateSearchEngine`은 `DataRequest` 구조화 조건과 검색어를
  받아 후보를 점수순으로 반환한다. hash-verified BLS/Census metadata archive를 로컬에서 읽고,
  Gate A에서 이미 실측한 World Bank USA GDP 2020–2022 경로 한 건을 evidence-backed seed로
  포함한다. 검색 시 외부 네트워크 요청은 없다.
- 점수는 용어 겹침률이며 통계적 동등성 점수가 아니다. 명시된 기관·국가·주기·기간·차원과
  알려진 충돌은 제외한다. 정의·지역·기간·주기·차원·가용성이 unknown이면 `review_required`로
  표시한다. 완전한 known metadata와 metadata_verified 근거가 모두 있을 때만 `exact`가 가능하다.
- `ConfirmedSelection`이 명시적으로 확인된 경우에만 collection plan을 만든다. `record_selection/1`
  stage가 후보 스냅샷, proposal revision, evidence refs, 확인 시각과 fingerprint를 collector보다
  먼저 기록한다. 현재 `raw_json`만 허용한다.
- confirmed World Bank/BLS/Census 후보는 해당 Phase 1 engine의 제한 입력으로 mapping한다.
  미상 BLS/Census metadata는 기존 `ConfirmedSelection` validation에서 collection 전에 차단된다.

## 검증

- 전체 `python -m pytest`: **477 passed**.
- `python -m ruff check src tests` 및 `git diff --check`: 통과.
- fixture E2E: GDP 후보 검색 → explicit selection → persisted selection receipt → 기존 World Bank
  engine의 fixture collection → raw response 보존을 확인했다. 추가로 BLS/Census plan mapping,
  오국가/오기관 후보 제외, 미상 메타데이터 review 분기를 확인했다.

Gate B 전체를 통과했다고 기록하지 않는다. 요청/조건 추출의 자연어 의미 분석, 공식 출처 전체
검색, Treasury TIC 또는 BEA 실제 검색·수집, BLS/Census live selection-to-collection E2E가 남아
있다. 현재는 기존 07 metadata archive 중 live API record도 해당 기준에서 빠지며, unit/frequency/
availability unknown을 임의로 채우지 않았다.

## 후속 Gate B 범위 판정 — 2026-10-26

이 보고서의 Gate B 미통과 판정은 당시 Gate B에 자연어 조건 해석과 넓은 기관 경로를 함께
요구했던 기준을 따른다. 제품 계획의 MVP 입력은 구조화 요청이고 자연어·대화형 UI는 별도
인터페이스 범위임을 명확히 한 뒤, D-060에서 Gate B를 **검색 엔진/API의 제한 범위**로 재정의했다.
현재 Gate B는 구조화 `DataRequest`→evidence-backed candidate ranking→명시 선택→World Bank
fixture collection E2E, known mismatch exclusion 및 explicit confirmation 분기로 제한 통과했다.

이 판정은 CLI/자연어 파서, 전체 기관 검색, Treasury TIC/BEA, BLS/Census candidate에서 live
collector로 이어지는 검증을 포함하지 않는다. 이러한 미완료 범위는 제품/기관 확대 요구로 계속
남아 있으며, 제한 Gate B 판정이 전체 사용자 제품의 출시 준비를 뜻하지 않는다. 현재 게이트 표는
`docs/IMPLEMENTATION_PLAN.md`를 따른다.
