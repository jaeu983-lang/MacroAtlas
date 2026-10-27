# 후속 기획안 — 검증된 수집 결과의 CSV 전달

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

상태: **20회차 구현·로컬 검증 완료.** 실제 사용법은 [사용자 안내서](USER_GUIDE.md), 증거는
[20회차 보고서](ITERATION_20_REPORT.md), 이후 순서는 [제품 로드맵](ROADMAP_2026_10_26.md)을 따른다.
PR #3/#4/#5/#6과 유지보수 QA 경로는 통합됐다. 19회차 BIS flat handoff는 보존 원본 실행까지 완료됐지만,
그 JSONL artifact는 이 CSV exporter 범위에 포함되지 않는다. 대용량 JSONL을 exporter에 연결하려면 별도의 artifact adapter와
수용 기준이 필요하다.
Gate C 자연 이벤트 감시는 별도로 계속한다.

현재 범위 정정(2026-10-27): 위 문장은 이 계획 작성 당시의 상태다. 사용자가 TIC/BIS 변경상태 확인은 현재
필요하지 않다고 지정해 반복 감시 자동화 두 개를 중지했다. 기존 결과와 Gate C 제한 판정은 보존하며, 새 단발
확인은 사용자가 다시 요청할 때만 범위와 목적을 정한다.

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

PR #3/#4/#5/#6 통합 및 기본 branch HEAD 확인 → 저장 payload와 provenance 계약 확인 → provider별 명시적 export adapter → 파일 보존·경로 가드 →
CLI 연결 → 정상·실패 수용 검증 → 사용자 안내·회차 보고서 → task branch commit/push 및 PR 검토.

20회차에서 이 계약을 구현했다. 두 provider fixture 검사, hash·stage·quality·source-change 거부,
경로·symlink·덮어쓰기 방지, read-only DB 검증을 통과했다. 보존된 성공 task도 네트워크 없이 export해
CSV와 sidecar hash 및 raw/manifest 무결성을 확인했다. 결과 수치와 한계는 회차 보고서에 기록했다.

## 엔진 연결

World Bank/BOJ 입력은 완료된 지원 task의 history·audit record·raw·request manifest에서 읽는다.
exporter는 네트워크 수집·task 이력 쓰기·대용량 작업 재개를 하지 않는다. 지원 원본을 다시 파싱해 stored
quality/hash와 대조한 뒤 로컬 파일로 전달한다. BIS 대용량 JSONL 출력 지원 확대는 별도 수용 기준을 정한다.
