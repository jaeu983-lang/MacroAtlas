# 11회차 완료 보고 — 범위 있는 사용자 피드백·지식 입력

일자: 2026-10-25\
상태: 11회차 통과, 사람 diff 검토 대기\
작업 브랜치: `codex/iteration-07-08-discovery`\
커밋/스테이징: 하지 않음

## 구현 범위

- Gate A 감사 피드백에 후보 묶음·질문 순서·출력 선호·출처 사실·개념 연결 등 수정 유형과 기관/데이터셋/개념/분류 축, 출처 버전, UTC 유효 기간, 근거 참조, 검증 상태를 붙인다.
- feedback 원문은 보존하고 편집·검토·취소를 append-only 이벤트로 기록한다. 낙관적 revision 비교로 오래된 편집을 거부하고, task·stage·관련 오류로 조회한다. 기존 Gate A task JSON과 관측치, SQLite `user_version=2`는 변경하지 않는다.
- `KnowledgeStore`는 사용자 주장·공식 근거·추론 입력을 출처 유형별로 저장하고 task/feedback 및 범위·버전·유효 기간·근거와 대체 관계를 보존한다. 취소·검토 역시 이벤트이며 원자료를 삭제하거나 덮어쓰지 않는다.
- 입력 등록은 해당 레코드와 제한된 인덱스만 갱신한다. 전 기관 재계산·ChatGPT 자동 대화 동기화·코드나 규칙 자동 승격은 없다.

## 주요 파일

- `src/macro_data_platform/storage/audit.py`: 기존 feedback API를 확장하고 revision/event 기록, 오류·기관·작업 인덱스 및 호환 읽기를 추가.
- `src/macro_data_platform/storage/knowledge.py`: 별도 append-only 지식 입력과 출처/검증/범위/버전 관계를 추가.
- `src/macro_data_platform/storage/__init__.py`: `KnowledgeStore` 공개.
- `tests/test_feedback_knowledge.py`: 작업/오류 범위, 수정·검토·취소 이력, legacy idempotency, provenance 및 지식 대체/취소 검증.
- `AGENTS.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`, `docs/developer/engines/KNOWLEDGE_ENGINE_PLAN.md`, `docs/developer/testing/REFERENCE_SCENARIOS.md`: 11 완료와 12 진행 기준 기록.

## 검증

- 신규 feedback/knowledge 및 기존 Gate A 집중 회귀: 통과.
- 전체 pytest: **573개 수집, 전체 통과** (종료 코드 0).
- `ruff check .`: 통과.
- `git diff --check`: 통과. 기존 CRLF 전환 안내만 출력됐고 whitespace 오류는 없었다.
- 모든 검증은 로컬 SQLite·fixture 기반이다. 외부 HTTP나 실제 기관 문서를 확인하지 않았다.

## 제한과 데이터 무결성

- 현재 저장 인터페이스는 명시 호출 Python API다. 저장소에 제품용 일반 명령 CLI가 없어 이번 회차에서 CLI를 새로 만들지 않았다. ChatGPT 대화 자동 수집도 없다.
- 공식 근거 참조는 저장하지만 외부 URL의 현재 응답·약관·내용을 확인하지 않았다. 새 공식 근거도 기본 `unverified`다. 이용자는 검토 API를 명시적으로 호출해야 한다.
- accepted feedback은 해당 지침이 검토됐다는 상태만 나타내며 공식 통계 사실이 아니다. inference는 기본적으로 `inferred`이며 verified/accepted 사실로 승격할 수 없다.
- 조회용 현재 투영, bounded knowledge search/cache, 동시 갱신·규모별 성능 측정은 12회차 Gate D 범위이며 아직 검증하지 않았다.

## 사람 검토

11회차 범위는 완료되어 12회차를 시작할 수 있다. 13회차는 시작하지 않는다. 미커밋 상태와 사람의 diff 검토 후 체크포인트/커밋 조건을 유지한다.
