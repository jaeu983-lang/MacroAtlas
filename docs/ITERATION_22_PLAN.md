# 22회차 기획 — 비API 대용량 작업 소요 시간 예측

기준일: 2026-10-26. 사용자 요청에 따라 실행 전 예측을 격리 qualification과 명시 승인형 BIS production 두 경로에
추가한다. 기존 실행·안전 경계와 Gate 판정은 바꾸지 않는다.

## 사용자 문제

비API 파일을 처리하기 전에 작업이 몇 초 또는 몇 분 걸릴지 알기 어렵다. 특히 지원 한도에 가까운 파일은 실행을
결정하기 전 소요 시간, 예측 신뢰도, 실제 worker 상한을 함께 볼 필요가 있다. 예측만 확인하려고 task를 새로 만들거나
파일을 다시 처리해서는 안 된다.

## 범위

- `large-check`의 bounded qualification과 `large-run`의 BIS flat production, `large-resume`의 남은 production 작업.
- 실행 전 stderr 요약: 점 추정, 범위, 신뢰도, 유사 실측 수, worker wall 상한.
- `large-estimate qualification|production <DEFERRAL_ID> [--event-seq N]` read-only preview 및
  `large-estimate resume <TASK_ID>` checkpoint 기반 잔여 작업 preview.
- 파일 형식·크기·행/열·셀·예상 JSONL 출력량을 보수적으로 표본화한다. 파일 본문은 최대 256 KiB만 읽고,
  표본의 원문 값은 로그·task·예측 결과에 저장하지 않는다. ZIP은 기존 경로/압축률/멤버 제한을 적용한다.
- 추정치와 집계 프로필은 새 task의 계획에 저장한다. 원래 idempotency key·task 재사용 의미·실행 예산을 바꾸지 않는다.
- 완료 task의 stage 시작/종료 시각으로 실제 wall time을 계산하고 CLI 요약에 기록한다. 성공 결과만 모델 학습에 쓴다.
- qualification과 production의 이력을 분리하고 최근 500 task 이내에서 baseline과 유사 workload 후보를 함께 예측한다.
  두 후보 모두 실제 결과와 shadow 비교한다. paired forecast 3건 전에는 유사 성공 실측이 3건 이상이면 경험 모델을
  선택하고, 그렇지 않으면 warm-up baseline을 쓴다. paired forecast가 3건 이상 쌓이면 중앙 APE가 낮은 후보를 고르고
  오차·표본 수를 함께 노출한다.

## 안전·범위 경계

- `large-estimate`는 SQLite와 파일을 읽기 전용으로 열며 task·event·출력 파일을 만들지 않는다.
- 일반 `large-check`/`large-run`은 기존 task를 먼저 저장한 다음 worker 실행 직전에 예측을 표시한다.
- 예측은 승인, 통과 판정, 실행 가능성 또는 worker budget을 바꾸지 않는다. 실제 실행은 기존 명시 동의, exact event/raw,
  qualification, platform/resource 및 source hash guard를 계속 요구한다.
- 이 예측은 엔진 stage wall time이다. 사용자 대기, 외부 다운로드, 사람 검토, 미지원 포맷의 별도 엔진 시간은 예측하지 않는다.
- 예측 후보 간 shadow A/B를 사용한다. 실제 production 요청을 임의로 나누거나 인위적으로 지연시키지 않는다.

## 완료 조건

1. 두 신규 task plan에 구조 프로필과 두 모델 예측이 저장되고, 같은 입력 재요청은 같은 task를 반환한다.
2. worker 실행 직전 예측이 범위·신뢰도·실측 수·wall 상한과 함께 표시되며, 완료 시 actual stage seconds가 제공된다.
3. 별도 estimate preview는 DB hash와 task 수를 바꾸지 않고, 256 KiB 이상 입력에서도 표본 크기 제한과 원문 비보존을 검증한다.
4. resume preview는 checkpoint row 수만큼 예상 처리량을 줄이고, checkpoint 불명 시 낮은 신뢰도로 전체 작업 fallback을 쓴다.
5. 최소 3 paired forecast의 shadow APE로 모델 선택이 달라지는 단위 테스트와 기존 실행 정책 회귀 테스트가 통과한다.
6. Gate C evidence, API 경로, 기존 worker 예산과 production 승인 계약은 변경되지 않는다.
