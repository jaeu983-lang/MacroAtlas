# 28회차 보고 — 평가 사례 v1 계약과 초기 코퍼스

기준일: 2026-10-27

작업 branch: `codex/iteration-28-evaluation-cases`

범위: A — 평가 사례 형식과 근거가 있는 초기 사례

## 구현

- `EvaluationCase` v1 immutable value contract를 추가했다. 기존 `DataRequest` snapshot을 재사용하고 case/split/type/state,
  query variants, 후보 기대 분류, 후보별 known/unknown/conflict 필드, 근거 pointer, 금지 동작, Excel 출력 기대를 검증한다.
- UTF-8 JSONL reader는 중복 JSON key/case ID, 공백 행, 잘못된 version 및 초과 크기를 거부한다.
- 고정 catalog reader는 `Candidate` snapshot을 검증하고 case의 후보 ID 참조를 대조한다. manifest는 case/schema/catalog hash와
  분포를 검증하며 case evidence가 가리키는 저장 파일 SHA-256도 다시 확인한다.
- 초기 Excel policy는 호환되지 않는 시계열 분리, 겹치는 값의 보존 또는 검토, source period, 집계·변환·보간·forward-fill 없음,
  결측 빈칸을 기록한다. 이는 사례의 기대 정책이며 XLSX exporter 구현을 의미하지 않는다.
- 피드백 참조는 `feedback_id`와 revision만 받는다. 이 변경은 FeedbackStore를 읽거나 고치지 않고, 사례를 자동 생성하거나 규칙을
  수정하지 않는다.

## 사례와 gate

고정 snapshot에는 코드에서 사용 중인 World Bank USA GDP WDI 후보 하나만 들어 있다. 공식 indicator metadata response 및
2020–2022 Gate A 실행 보고서의 로컬 hash를 연결했다. structured unit과 frequency는 source가 제공하지 않아 unknown으로 둔다.

초기 코퍼스는 **9개**다.

| split | rankable | near_match | insufficient_evidence | unrelated | 합계 |
|---|---:|---:|---:|---:|---:|
| development | 1 | 0 | 1 | 1 | 3 |
| validation | 1 | 0 | 1 | 1 | 3 |
| holdout | 1 | 0 | 1 | 1 | 3 |

목표는 split당 12개, 각 유형 3개다. 따라서 초기 manifest의 gate 상태는 **blocked**다. 27개를 더 채워야 하고, 지금 보존된
근거만으로는 near-match 정답·오답 후보 쌍을 만들 수 없다. BLS/Census의 기존 테스트 payload는 synthetic fixture라서 공식
candidate snapshot으로 둔갑시키지 않았다. Unrelated 기대는 초기 1-candidate snapshot에만 해당하며, MacroAtlas 전체 또는 공식
기관에서 해당 통계가 없다는 주장을 하지 않는다. 이 gate 상태로 29회차 split/feedback bridge나 30회차 evaluator를 시작하지 않는다.

## 변경 파일

- `src/macro_data_platform/evaluation/`: case contract와 JSONL/manifest/candidate reader.
- `tests/fixtures/evaluation/v1/`: v1 schema, 9개 case, 고정 catalog, 초기 manifest 및 hash.
- `tests/test_evaluation_cases.py`: cross-field 거부, immutable snapshot, hash tamper, reader 경계 검사.
- `docs/DECISION_LOG.md`, `docs/IMPLEMENTATION_PLAN.md`: D-095 결정과 현재 gate 상태.

## 검증과 한계

검증 결과: 전체 pytest **745 passed**, `ruff check .` 통과, `git diff --check` 통과, `compileall` 통과다.
네트워크/API/key/SQLite/raw/export 경로는 사용하지 않았다.

이 작업은 검색 점수·순위·거절 동작을 실행 평가하지 않는다. 피드백 수집/검토, split leakage 검증, 피드백 case draft,
규칙 승격, freshness 및 Excel writer도 구현하지 않는다. Gate는 사례 수와 evidence snapshot을 확장할 때까지 차단한다.

## 검토 판단

코드·데이터 무결성 변경은 별도 review branch에서 검토할 수 있다. Iteration 28의 acceptance gate는 미통과이므로 다음 회차를
시작할 준비가 된 것으로 선언하지 않는다. gate 해제에는 보존 가능한 official evidence가 있는 추가 후보와 유사하지만 다른
기대 답을 갖는 verified distractor가 필요하다.

## 후속 계약 확장

후속 작업에서는 AI 모의 사례를 사람 관찰로 오인하지 않도록 Python value contract에 작성 provenance와 별도 evidence 종류를
추가했다. Synthetic fixture evidence는 후보 ID와 로컬 SHA-256을 가리키며 official URI나 조회 시각을 가질 수 없다.
기존 v1 JSONL·manifest·9개 사례는 그대로 유지한다. 36개 모의 코퍼스 초안은 holdout에 날짜만 바꾼 동일 템플릿이 반복되고
manifest가 없어 반영하지 않았다. 따라서 코퍼스 gate는 여전히 차단이며 엔진 회귀 평가는 실행되지 않았다.
