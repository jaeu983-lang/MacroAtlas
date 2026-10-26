# 11회차 보고서 — 명시적 피드백 등록·범위·근거·이력

## 범위 및 게이트 상태

사용자가 Gate C 통과 전 11회차까지 진행하라고 명시해, 계획에 정해 둔 순서 예외로 구현했다.
Gate C는 계속 **미통과**다. 실제 개정 원자료 쌍의 변경 감지와 기관별 durable resume 증거는
미완료이며, 이번 구현은 이를 대체하거나 Gate D를 통과시키지 않는다. 12회차는 시작하지 않았다.

## 구현

- `FeedbackStore`는 기존 task/history schema와 Gate A feedback record를 변경하지 않고 별도
  SQLite current snapshot과 append-only revision history를 추가한다.
- `record`는 명시적 입력을 task에 연결하고 선택적으로 stage run 및 같은 task의 관련 audit record를
  확인한다. idempotency key로 같은 등록의 재요청을 안전하게 처리한다.
- 범위에 institution, dataset, concept, classification axis, source version 및 UTC 유효기간을
  기록한다. task/institution/category로 제한 조회할 수 있다.
- `knowledge_kind`는 `user_instruction`, `official_evidence`, `inference`로 분리한다.
  공식 근거에는 안전한 HTTPS 출처·버전·수집시각을 요구하고, 사용자 지시가 공식 근거로
  표시되는 것을 막는다. 추론도 타입을 유지하며 사실이나 공통 규칙으로 승격하지 않는다.
- 새 항목은 `unreviewed`로 시작한다. 리뷰, 내용 수정, 철회는 기대 revision을 요구해 경합을 막고,
  매 변경을 task event와 append-only revision으로 남긴다. 수정하면 재검토 상태로 돌아간다.
  철회는 삭제 대신 최종 상태로 보존한다. 대체 입력은 동일 task의 이전 피드백을 `superseded`로
  표시하고 새 항목에서 이전 ID를 참조한다.
- `macro-feedback` CLI는 `add`, `list`, `edit`, `review`, `withdraw`를 제공한다. 대화 자동 수집은
  구현하지 않았다. 별도 knowledge search/reuse와 자동 일반화는 12·13회차 범위다.

## 사용 예

```sh
macro-feedback add --task-id TASK_ID --text 'Keep holdings separate from transactions' \
  --category candidate_group --knowledge-kind user_instruction \
  --scope-json '{"institution_id":"treasury_tic","concept":"foreign holdings"}'
macro-feedback list --task-id TASK_ID --institution-id treasury_tic
```

`TASK_ID`는 이미 SQLite task history에 존재해야 한다. 근거 입력은 다음처럼 공식 URL을 명시한다.

```sh
macro-feedback add --task-id TASK_ID --text 'The guide defines this measure as holdings' \
  --knowledge-kind official_evidence \
  --evidence-json '[{"source_url":"https://example.org/guide","source_version":"v2"}]'
```

## 검증

- `tests/test_feedback.py`: task/institution 범위 분리, user/official/inference 분리, 공식 근거 URL
  검증, review/edit/withdraw/supersede 이력, stale revision 차단, idempotency, CLI 등록/조회.
- 전체 `python -m pytest -o addopts='' -q`: **564 passed in 3.53s**.
- `python -m ruff check .`: 통과.
- `git diff --check`: 통과.

## 제한

피드백은 task에만 수동 입력한다. 이메일/ChatGPT 대화 자동 동기화, feedback 검색 인덱스,
기관 간 재사용, 충돌 탐지, 벡터 검색, 지식 자동 검증은 포함하지 않는다. 리뷰의 `accepted`는
기록 검토 결과일 뿐 사실 검증이나 자동 적용 허가가 아니다. 원본 통계와 기존 task JSON은 변경하지 않는다.
