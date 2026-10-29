# 실제 분석가 사용성 조사 — 선택적 후속 연구

이 문서는 이전 23회차 CSV 관찰 계획을 대체한다. 현재 제품 Gate가 아니며 완료를 막지 않는다. 필수 Gate 41 AI workflow simulation과 별개로, 실제 분석가 1–2명이 확보됐을 때 정성 사용성 정보를 얻기 위한 절차다. 제품 범위와 완료 기준은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md), 현재 Gate 상태는 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)를 따른다.

## 목적과 범위

완료된 원자료 XLSX와 비교 XLSX를 사용자가 열고, 출처·시리즈·단위·기간·최신성·결측 및 비교 한계를 이해하는 과정에서 혼란과 잘못된 해석이 생기는지 관찰한다. 작은 표본은 정성 관찰로만 사용하며 성공률 추정이나 제품 Gate 통과 근거로 쓰지 않는다.

시나리오는 현재 AI acceptance가 있는 두 경로를 대상으로 한다. BLS 과제에는 가능하면 Iteration 42에서 만든 source-linked `Series metadata` 탭이 포함된 workbook을 사용하고, [Iteration 42 evidence](evidence/iteration_42_bls_live_metadata_freshness_performance_20261029.json)의 hash가 맞는지 사전 점검한다. artifact가 없으면 승인된 로컬 BLS sample을 다시 준비하고, 연구용 임시 자료인지 실제 조회인지 참가자에게 명확히 표시한다.

1. BLS 원자료 workbook에서 두 series의 공식 제목과 계절조정 여부, 발행기관, 기간, 데이터 상태와 provenance를 찾는다. dataset ID·unit·currency가 확인되지 않으면 그 상태를 설명한다. series title이나 `measure_data_type`만으로 unit/currency를 추론하지 않는다.
2. 같은 WDI nominal GDP 지표의 USA/Canada 비교 workbook에서 정렬 기준, 결측/빈칸과 0의 차이, 비교 해석의 한계를 설명한다.
Gate F/G 근거 파일은 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)의 evidence를 따른다. 실행 직전 깨끗한 임시 checkout에 필요한 artifact와 provenance만 복사하고 hash·재개방을 확인한다. 저장소의 운영 DB, 개인 자료, credential은 사용하지 않는다. 참가자 업무에 필요한 새 실자료 조회는 기본 시나리오에 넣지 않는다. 관찰 사실과 참가자 발언, 진행자 해석은 [기록 양식](ANALYST_OBSERVATION_RECORD_TEMPLATE.md)에 분리해 남긴다.

## 진행 및 기록

- 참가자에게 task 카드만 제공하고 명령이나 정답을 미리 설명하지 않는다. 참가자가 요청한 도움은 시점과 내용을 기록한다.
- 참가자에게 운영자용 feedback CLI나 평가 사례 작성 절차를 요구하지 않는다. 참가자가 스스로 수정 의견을 내면 동의 범위에서 익명 연구 메모로 보존하고, 운영자가 정식 FeedbackStore에 입력하는 일은 별도 절차로 수행한다.
- 동의 후 익명 참가자 ID, 통계 사용 맥락, 시작·종료, 명령·행동 순서, 오류·재시도, 도움 요청, 혼동한 문구, workbook 해석을 기록한다.
- 관찰 사실과 진행자의 해석을 별도 기록한다. 원자료 관측값, 개인 식별정보, API 자격 증명은 연구 메모에 복사하지 않는다.
- task 수행시간은 실제 세션에서만 사람의 수행시간으로 기록한다. Gate 41의 AI tool latency를 사람의 인지·작업시간으로 바꾸어 해석하지 않는다.
- 세션 중 오류가 나도 출력·원본을 덮어쓰거나 live 요청을 임의 재시도하지 않는다. 문제를 보존하고 해당 과제를 중단한다.

## 결과의 의미

이 연구는 실제 사람의 사용 경험을 기록하는 선택적 후속 작업이다. 1–2명의 관찰로 전체 사용자 만족도나 성공률을 일반화하지 않는다. 결과는 개선 후보와 실제 발언·행동 기록이며, 코드·지시문을 자동 변경하거나 피드백을 평가 사례·승격 결정으로 자동 변환하지 않는다. 사용자가 별도로 요청하면 후속 변경을 같은 고정 사례로 평가한다.

AI simulation, synthetic 사례, fixture, 저장 산출물 내부 검증은 실제 분석가 관찰을 대체하지 않는다. 실제 참가자 관찰이 미실행이어도 현재 Gate 41 AI simulation 또는 F/G의 범위별 acceptance 상태는 바뀌지 않는다.

## 세션 준비 상태

Iteration 42에서는 실제 참가자를 대상으로 세션을 진행하지 않았다. 위 두 과제, 참가자 동의 확인, 과제별 수행시간·도움 요청·혼란 기록, 실제 feedback의 별도 인계 양식은 준비되어 있다. 참여자가 확보되면 실제 세션 기록을 먼저 만들고, AI 검토나 제품 수정은 그 이후 별도 운영 절차로 처리한다.
