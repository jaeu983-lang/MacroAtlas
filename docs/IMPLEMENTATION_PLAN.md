# MacroAtlas 현재 구현 상태와 Gate 증거

> 기준일: 2026-10-27. 요구사항·우선순위의 단일 기준은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md)입니다. 이 문서는 현재 상태만 요약하고, 과거 실행의 수치와 원본 기록은 각 보고서에 보존합니다. 이전 회차의 “다음 단계” 문구는 당시 계획이며 최신 순서는 현재 기획서를 따릅니다.

## 현재 상태

원격 PR 현황을 2026-10-27에 확인했습니다. PR 57개 중 56개가 병합됐고, 열린 PR은 #50 하나입니다. #50은 `codex/iteration-28-evaluation-cases` → `codex/iteration-04-gate-a` draft PR이며 GitHub는 `MERGEABLE/CLEAN`으로 보고하고 등록된 CI 검사도 통과했습니다. 다만 27개 assistant-simulated 사례는 독립 검토 전이라 corpus gate는 계속 차단 상태입니다. 코드가 mergeable인 것과 평가 gate 통과는 별개입니다.

| 영역 | 현재 상태 | 남은 조건 |
|---|---|---|
| 공통 실행 제어 | `EngineRegistry`가 버전별 engine을 공통 Orchestrator에 등록하고 saved plan 재개를 지원합니다. | 기관별 통신·응답 adapter는 유지합니다. 대용량 worker도 별도 자원·복구 경계를 유지합니다. |
| 성능 계측 | monotonic stage/phase 측정과 개인정보 없는 `macro-perf report`가 구현됐습니다. offline fixture/stored 표본은 161개입니다. | 실사용 network 기준선은 자연 요청에서만 수집합니다. 실제 병목이 확인되기 전 최적화하지 않습니다. |
| 피드백 | SQLite append-only 로그, 검토 상태, 범위 지정 재사용이 구현됐습니다. | 피드백을 평가 사례로 보내는 승인 bridge와 규칙 자동 반영은 없습니다. |
| 최신성 | daily–annual 정책 평가가 일부 API connector와 CSV 재검증에 연결됐습니다. | 기본 허용 기간은 source 공표 달력의 보증이 아닙니다. 모든 일반 파일 경로와 검증된 series별 정책 연결이 남았습니다. |
| 평가·규칙 | 기존 synthetic scaffold와 evidence-backed v1 계약은 별도 경로로 보존합니다. | v1 고정 corpus 9/36, 27개 초안은 독립 검토 전. 실제 evaluator와 rule promotion 기록은 없습니다. |
| 시계열 모델 | provider별 observation parsing과 provenance가 있습니다. | 모든 provider에서 identity, field, unit/currency, frequency/calendar, period, raw/source lineage를 보존하는 공통 typed contract가 없습니다. |
| 파일 전달 | 완료된 World Bank GDP와 BOJ FXERD01 task를 제한 CSV로 전달합니다. XLSX 읽기 parser도 있습니다. | parser는 exporter가 아닙니다. 원자료 XLSX와 다중 series 비교 workbook은 미구현입니다. |

## A–G gate 상태

| Workstream | 상태 | 다음 완료 조건 |
|---|---|---|
| A–B 사례·세트 | **차단** | 27개 초안을 독립 검토하고 오류를 고친 뒤에만 고정 catalog/corpus에 명시적으로 반영합니다. 36개 목표, evidence hash, family/split audit를 통과해야 합니다. |
| C 기준/후보 평가 | **미구현** | 동일 case/catalog snapshot에서 candidate state, ranking, fields, evidence, false-exact와 금지 행동을 재현 가능하게 비교합니다. |
| D 규칙 승격 | **미구현** | 승인자·case version·전후 지표·적용/rollback commit을 연결하고 validation/holdout gate 전에는 승격하지 않습니다. |
| E 시계열·최신성 | **부분 구현** | 공통 typed series와 검증된 series별 freshness policy를 World Bank·BOJ부터 provider/file 경계까지 연결합니다. |
| F 원자료 XLSX | **미구현** | 원값·결측·provenance·호환성·충돌·최신성 경고를 보존하고 no-overwrite를 검증합니다. |
| G 비교 XLSX | **미구현** | 호환 series만 같은 sheet에 두고 별도 정렬 결과를 만듭니다. 결측은 빈칸이며 자동 보간/forward-fill은 하지 않습니다. |
| 최종 사용자 관찰 | **대기** | 28–39 gate가 통과된 뒤 40회차(기존 23회차 명칭)에서 분석가 1–2명을 관찰합니다. |

상세 수용 기준은 [제품 평가·시계열·Excel 실행 계획](PRODUCT_EVALUATION_ENGINE_PLAN.md)을 따릅니다. 27개 draft는 rankable/near-match를 포함하지만 현재 collector가 지원하지 않는 후보가 섞여 있습니다. `candidate_found`는 검색 후보 발견을 의미할 수 있으며 사용·수집 승인을 의미하지 않는다는 기대를 사례 리뷰에서 확인해야 합니다. `unrelated`도 고정 catalog 범위의 판정이지 MacroAtlas 전체의 부재 주장이 아닙니다.

## 별도 workstream

- TIC/BIS 반복 변경 감시는 현재 사용자 범위에서 제외돼 중지됐습니다. 과거 unchanged와 자연 변경 미관측 기록, Gate C의 제한 범위 판정은 보존합니다.
- 대용량 worker는 승인된 BIS flat ZIP 한 건의 Linux 구조 보존 경로만 완료했습니다. 모든 파일 형식이나 의미 정규화 지원은 아닙니다.
- Windows updater의 no-op/cleanup/lock 경로는 일부 검증됐습니다. Windows changed-candidate/failure 경로와 scheduler 실실행은 미검증이며 scheduler는 비활성입니다.
- 시간 예측은 qualification 15건, production 1건, paired forecast 0건으로 신뢰도가 낮습니다. 표본 확보만을 위한 작업은 하지 않습니다.

## 증거와 과거 기록

요구사항과 순서는 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md), 엔진별 구현 대조는 [`ENGINE_REQUIREMENTS_AUDIT_2026_10_27.md`](ENGINE_REQUIREMENTS_AUDIT_2026_10_27.md), 결정 이력은 [`DECISION_LOG.md`](DECISION_LOG.md)를 봅니다. `ITERATION_*_REPORT.md`, Gate 기록과 live report는 당시의 증거로 보존하며, 과거의 다음 단계 문구는 현재 순서를 바꾸지 않습니다. 원초 기획은 [`PROJECT_PLAN_ORIGINAL_2026_10_24.md`](../PROJECT_PLAN_ORIGINAL_2026_10_24.md)에 보존합니다.
