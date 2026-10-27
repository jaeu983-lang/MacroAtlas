# 분석기 근거 부족 7건 재점검 및 개선 계획

2026-10-27. 보존 catalog를 읽기 전용으로 조회하고 pattern_cli를 재실행했다. insufficient_evidence_count=7을 재현했다. 외부 요청과 task 원본 수정은 하지 않았다.

## 확인 결과

| 대상 | 저장 근거 | 처리 방향 |
|---|---|---|
| qualification 5건: f3f12e10, a0e0349e, ae02b044, 1944aa18, 3aec5ff2 | trial_only=true, large_file_trial, qualification-fixtures 경로, origin_task_id와 deferral_event_seq | 합성 시험 이력으로 분류. 기관·dataset·concept을 만들어 채우지 않는다. 제품 운영 부족 건수와 분리하고 자원·파서 시험 분석에는 유지한다. |
| 2797e6d0-a8ac-40e5-aca4-066991a7c2e1 | tabular_file input의 BIS 공식 source_url, source_agency, 보존 ZIP 경로 | raw/manifest 및 불변 deferral event를 검증한 뒤 institution=bis, dataset=WS_GLI_csv_flat을 근거 참조와 함께 분석 projection에서 복구한다. |
| bea335ad-1819-42cb-8acd-797c6a452255 | bis_flat_probe input.url에 동일한 공식 flat ZIP URL | legacy adapter는 engine/version과 exact URL을 동시에 검사한다. 기관·dataset만 복구하고 과거 실패 상태는 보존한다. |

기존 문서의 “7건 모두 실제 source/scope 근거가 없다”는 표현은 과도했다. 2건은 source 식별 근거가 있으며 현재 SQL adapter가 이 경로를 읽지 않는다. 다만 두 파일 전체의 경제 concept을 URL에서 추론할 근거는 없다.

## 구현 순서와 완료 기준

1. **다음 우선 작업 — 25회차 scope 분석 후속:** evidence domain을 production, qualification fixture, legacy probe로 구분한다. trial_only만으로 fixture라고 단정하지 않고 저장된 origin/event의 시험 생성 근거까지 확인한다. 근거가 없으면 unknown으로 남긴다. 전체 건수와 domain별 부족 건수를 함께 제공한다.
2. **같은 작업에서 BIS 식별 복구:** exact official URL, engine/version, raw/manifest hash 또는 보존 event 연결을 검증하는 읽기 전용 adapter를 추가한다. filename, 자유문 request, 기관 라벨만으로 식별하지 않는다. 반환 필드별 근거 위치와 adapter version을 기록하며 원 task를 덮어쓰지 않는다.
3. **concept 필수 여부 분리:** 기관·dataset이 알려진 구조/자원 오류는 concept을 요구하지 않는 별도 technical pattern 유형에서만 집계한다. 경제 의미·품질 제안은 concept 미상일 때 계속 차단한다. 여러 dataset이나 engine을 같은 기술 오류라는 이유로 합치지 않는다.
4. **회귀 검증 후 QA·PR:** source 없는 fixture의 기관 오인 방지, raw hash 불일치 차단, legacy exact URL 이외 차단, concept 미상 의미 제안 차단, domain별 집계와 기존 3개 distinct task 임계값 유지를 검증한다. 보존 catalog 재분석 전후의 필드별 복구·미상 수를 비교하고 commit/push 및 검토 PR로 제출한다.

7을 0으로 만드는 것은 완료 기준이 아니다. 목표는 fixture 5건을 명확히 설명하고, BIS 2건의 확인 가능한 식별 정보만 복구하며, 남은 concept 미상과 단발 사례를 정직하게 표시하는 것이다. 두 BIS task는 서로 다른 engine/stage이므로 반복 개선 제안으로 자동 승격하지 않는다.

## 선행 조건과 병행 작업

이 작업은 로컬 read-only 분석기 개선이며 Codex updater CLI 재로그인이나 Gate C 자연 이벤트를 기다릴 필요가 없다. 따라서 scheduler pilot이나 신규 provider 확장보다 먼저 수행한다. Gate C 원본 비교·자연 장애 증거와는 별개의 완료 기준이다.
