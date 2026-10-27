# Documentation map

기준일: 2026-10-27. 이 페이지는 문서의 역할과 우선순위를 정리합니다. 오래된 회차 기록을
현재 제품 상태로 오해하지 않도록, 실행 전에는 아래의 현행 문서를 먼저 확인하세요.

## 현행 기준 문서

| 알고 싶은 내용 | 기준 문서 | 역할 |
|---|---|---|
| 지금 사용자가 실행할 수 있는 일 | [사용자 안내서](USER_GUIDE.md) | 설치, 지원 명령, 결과·오류 확인 |
| 사용자에게 빠르게 설명할 슬라이드 | [사용자 안내 PPT](MacroAtlas_User_Guide.pptx) | 현재 지원 경로·한계의 10장 요약 |
| 개발 환경과 기여 절차 | [개발자 안내서](DEVELOPER_GUIDE.md) | 구조, 개발·검수·자료 보호 |
| 제품을 어떤 순서로 만들지 | [제품 로드맵](ROADMAP_2026_10_26.md) | 우선순위, 선행 조건, 완료 기준 |
| 사용자·개발자 관점의 목표 아키텍처 | [제품 및 시스템 아키텍처](PRODUCT_ARCHITECTURE.md) | 제품 가설, 시스템 경계, 성장 단계 |
| 현재 구현·게이트·실측 상태 | [구현 상태와 게이트](IMPLEMENTATION_PLAN.md) | 현재 증거의 요약 |
| 현재 남은 문제와 원인 분류 | [미해결 항목](UNRESOLVED_ITEMS.md) | 데이터 처리, 접속, 미구현, 증거 대기 분리 |
| 코드의 실제 호출과 저장 경로 | [엔진 연결 설계](ENGINE_CONNECTIONS.md) | 현재 구현과 아직 없는 연결의 구분 |
| 제품 요구사항과 범위 정책 | [프로젝트 계획](../PROJECT_PLAN.md) | 장기 요구사항 목록; 구현 완료 선언이 아님 |

제품 요구사항은 `PROJECT_PLAN.md`, 현재 실행 가능 범위는 `USER_GUIDE.md`, 현재 증거는
`IMPLEMENTATION_PLAN.md`와 연결된 보고서, 앞으로의 순서는 `ROADMAP_2026_10_26.md`를 따릅니다.
설계 결정의 이유는 [결정 기록](DECISION_LOG.md)을 참고합니다. 문서 간 충돌을 발견하면 조용히
추정해 적용하지 말고 코드·테스트·실측을 확인해 기준 문서를 갱신합니다.

## 문서 분류

### 제품·운영

- [제품 및 시스템 아키텍처](PRODUCT_ARCHITECTURE.md): 어떤 문제를 먼저 풀고 엔진을 어디에 둘지에 대한 목표 설계.
- [사용자 안내 PPT](MacroAtlas_User_Guide.pptx): 사용자 안내서와 같은 기준일의 시각 요약.
- [대용량 엔진](LARGE_FILE_ENGINE.md): 비API 대용량 자료의 조사, 용량 시험, 미실행 규칙과 BIS flat 한 건의 승인 구조 보존 처리.
- [엔진 연결](ENGINE_CONNECTIONS.md): 현재 호출 경로와 대용량 엔진으로 넘어가는 계약.
- [기관 카탈로그](INSTITUTION_CATALOG.md), [`connectors/`](connectors/): 조사한 공식 자료와 connector별 확인 범위.
- [출력·변형 정책](OUTPUT_AND_VARIANT_POLICY.md), [시나리오](REFERENCE_SCENARIOS.md): 사용자 선택과 수용 사례.

### 계획·작업 추적

- [제품 로드맵](ROADMAP_2026_10_26.md): 다음 순서의 유일한 계획 기준.
- [엔진 통합·분리 개선안](ENGINE_CONSOLIDATION_PLAN.md): 제품 runtime engines와 개발자 유지보수 workflow의 경계, 중복 실행기 통합 순서.
- [미해결 항목](UNRESOLVED_ITEMS.md): 남은 코드·접속·관측 증거를 분류.
- [결정 기록](DECISION_LOG.md): 변경된 설계 선택을 날짜와 함께 보존.
- `ITERATION_*_PLAN.md`, `CSV_EXPORT_FOLLOWUP_PLAN.md`, `KNOWLEDGE_ENGINE_PLAN.md`,
  `WORKFLOW_ALIGNMENT_PLAN.md`: 당시 정한 범위의 계획 기록. 현재 실행 순서는 로드맵을 따릅니다.

### 검수·증거 기록

- `ITERATION_*_REPORT.md`, `ALIGNMENT_*_REPORT.md`: 해당 구현 당시의 변경·검사 기록.
- `GATE_*`, `BOJ_LIVE_*`, `PLAN_IMPLEMENTATION_AUDIT.md`, `USER_WORKFLOW_REVIEW.md`,
  `MAINTENANCE_QA_*.md`: 특정 날짜와 환경의 실측 또는 검토 기록.
- `LARGE_FILE_QUALIFICATION_RESULTS.json`과 `NON_API_DEFERRED_CATALOG.json`: trial 측정치와
  비API 인계 정책/목록의 기계 판독 자료. 범용 제품 지원 선언으로 읽지 않습니다.
- [사용자 안내 PPT](MacroAtlas_User_Guide.pptx): `USER_GUIDE.md`를 요약한 10장 시각 안내.
- 이 기록은 원래 결과를 보존합니다. 이후 상태가 바뀌면 과거 결과를 고쳐 쓰지 않고 현행 요약과
  새 날짜가 붙은 증거를 추가합니다.

## 지금 기억할 상태

2026-10-27 기준 제품은 고정된 구조화 CLI와 Python API 중심입니다. 전체 기관 탐색·대화형 UI,
일반 대용량 정규화·범용 CSV/XLSX 변환, 자연 TIC/BIS 개정은 완료된 제품 기능이나 증거로 표시하지 않습니다.
World Bank API에서 자연 transient failure를 보존한 same-task resume은 실측됐지만 TIC/BIS file-watch 범위의 자연
장애 재개는 별도 미관측입니다. 완료된 World Bank/BOJ task의 제한 CSV 전달은 20회차에서 추가했습니다.
변경될 때 `USER_GUIDE.md`, `IMPLEMENTATION_PLAN.md`, 로드맵의 상태를 함께 갱신합니다.

19회차는 보존된 BIS GLI flat ZIP 한 건을 명시 승인 아래 Linux worker에서 JSONL로 구조 보존 처리했습니다.
이 결과는 경제 의미 정규화도, 일반 파일 지원도, Gate C 자연 증거도 아닙니다.

20회차는 저장된 완료 World Bank/BOJ task를 read-only 검증한 뒤 CSV와 provenance sidecar로 전달합니다.
사용자 절차는 [USER_GUIDE.md](USER_GUIDE.md), 검증 근거는 [ITERATION_20_REPORT.md](ITERATION_20_REPORT.md),
작성자 내부 dry run은 [USER_WORKFLOW_DRY_RUN_2026_10_26.md](USER_WORKFLOW_DRY_RUN_2026_10_26.md),
후속 순서는 [ROADMAP_2026_10_26.md](ROADMAP_2026_10_26.md)를 참조하세요.

22회차는 대용량 qualification·BIS production 전에 예상 시간과 신뢰도를 알리고, 성공 task의 stage 실측으로 예측을
보정합니다. [구현 보고서](ITERATION_22_REPORT.md)와 [대용량 엔진 안내](LARGE_FILE_ENGINE.md)를 참고하세요.

개발자 측 analyzer와 Codex updater는 서로 다른 control plane으로 유지합니다. 목표 구조와 구현 순서는
[엔진 통합·분리 개선안](ENGINE_CONSOLIDATION_PLAN.md)에 기록했습니다. 24회차 공통 QA와 26회차 isolated updater→candidate
QA→review PR handoff까지 구현했습니다. Windows no-op/cleanup과 OS lock 경합 pilot은 통과했으며, changed-candidate/failure 경로 및 예약 실행 검토가 남아 있습니다. 세부 근거는
[26회차 보고서](ITERATION_26_REPORT.md)와 [27회차 pilot 상태](ITERATION_27_PILOT_REPORT.md)를 보세요. Linux candidate handoff, Windows installer dry-run, updater no-op/cleanup, 교차 프로세스 lock 경합을 확인했습니다. PR #34에서 scheduler용 base ref, principal, 중복 실행 lock과 report retention을 구현했습니다. GitHub Actions는 계정 결제/사용 한도 문제로 실행되지 않았고 candidate/failure 경로도 남아 있어 예약 task는 등록되지 않았습니다.

최종 실제 사용자 관찰의 진행 절차와 기록표는 [23회차 계획](ITERATION_23_PLAN.md)에 있습니다. A–G 평가·엔진·Excel
선행 작업이 끝난 뒤 실행하며, 계획 문서는 참가자 세션을 수행했다는 증거가 아닙니다.
