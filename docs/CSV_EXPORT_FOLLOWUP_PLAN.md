# 후속 기획안 — 검증된 수집 결과의 CSV 전달

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

상태: 우선순위 backlog다. 전체 실행 순서는 [제품 로드맵](ROADMAP_2026_10_26.md)을 따른다. PR #3/#4/#5와
유지보수 QA 경로는 통합됐다. BIS flat handoff는 19회차 review/CI 및 보존 원본 실행 후 별도 exporter adapter와
통합해야 한다. 대용량 JSONL artifact는 이 CSV exporter 범위에 포함되지 않는다.
Gate C 자연 이벤트 감시는 별도로 계속한다.

## 목표와 사용자 흐름

고정 World Bank USA GDP 또는 BOJ FM08/FXERD01 수집 task가 완료되면 사용자가 task ID로
검증된 관측값을 CSV 파일로 받는다. 현재 CLI summary만 보는 흐름을 실제 분석용 파일 전달까지 연결한다.

## 포함 범위

- 제안 명령: `macroatlas export TASK_ID --format csv --output data/exports/result.csv`.
- 로컬 저장 결과만 사용하고 네트워크 요청 없이 실행한다.
- 지원 대상은 완료된 World Bank USA GDP와 BOJ FXERD01 task로 고정한다. 기존 payload 계약을 구현 전에 확인한다.
- 원본·manifest hash와 task/stage 성공 상태를 검증하고 quality passed인 관측값만 내보낸다.
- 날짜, 값, 기관, dataset/series, 단위, 주기, 조회 시각, 원본·manifest 참조를 CSV와 별도 provenance manifest에 보존한다.
- 결측은 빈 값으로 표현하고 그 의미를 manifest에 기록한다. 원본 숫자를 반올림하거나 보간하지 않는다.
- workspace 내부 출력만 허용하고 기존 파일은 덮어쓰지 않는다. 임시 파일 작성 후 완성된 산출물로 전달한다.

## 제외 범위

임의 기관·자연어 검색, XLSX, TIC/BIS 범용 테이블 export, 수집 범위 확대, 자동 스케줄러 구현,
새 관측값 생성, source-change review 자동 승인, 환경 배포는 포함하지 않는다.

## 수용 조건과 검증

1. 두 지원 provider fixture task에서 CSV 관측값·null·식별자와 provenance가 원본과 일치한다.
2. FAILED/PARTIAL/NEEDS_REVIEW, changed 또는 quality 미통과 task는 새 파일을 만들지 않는다.
3. raw/manifest 변조·누락, 미지원 provider, 경로 탈출, symlink 및 기존 출력 파일을 차단한다.
4. export를 반복해도 raw와 기존 산출물이 바뀌지 않고 네트워크 호출이 없다.
5. CLI 문서·실패 안내를 갱신하고 Linux/Windows CI를 확인한다.

## 구현 순서와 선행 조건

PR #3/#4/#5 통합 및 기본 branch HEAD 확인 → 저장 payload와 provenance 계약 확인 → provider별 명시적 export adapter → 파일 보존·경로 가드 →
CLI 연결 → 정상·실패 수용 검증 → 사용자 안내·회차 보고서 → task branch commit/push 및 PR 검토.

완료 선언은 실제 파일과 검증 결과가 확보된 뒤 한다. 이번 작업은 기획서 작성까지이며 16회차 코드를 구현한 것으로 세지 않는다.

## 엔진 연결

입력은 ENGINE_CONNECTIONS.md의 검증된 artifact adapter로 받는다. exporter는 네트워크 수집·
원본 재파싱·대용량 작업 재개를 수행하지 않고, 완료된 지원 task/자식 task의 output manifest와
quality·hash를 검증해 로컬 파일로 전달한다. 대용량 출력 지원 확대는 별도 수용 기준을 정한 뒤 한다.
