# 계획·구현 정합성 점검 — 2026-10-26

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

이 문서는 D-068 Gate D 통합 이전의 시점별 감사 기록이다. 현재 게이트 상태는
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)와 회차별 최신 보고서를 따른다.

## 판정

기획의 제품 방향과 안전 원칙은 대체로 유효하지만, 구현 단계와 종료 게이트를 하나의
완료 상태처럼 읽으면 안 된다. 05~10회차에는 제한된 기능과 fixture 검증, BLS/Census live
smoke가 추가됐다. 이 보고서 작성 당시 Gate B/C는 미통과였다. 이후 D-060에서 MVP 입력 계약을
정리하고 Gate B를 engine/API의 제한 범위로 판정했다. Gate C는 미통과, 11회차 이후는 미실행이다.

이번 점검에서 코드와 계획의 직접 충돌 하나를 수정했다. 기존 계획의 TRANSIENT/X01은
backoff 재시도를 요구했지만, 실제 Orchestrator는 명시적 resume 방식이었다. 숨은 추가 요청을
만들지 않도록 수동 resume를 정책으로 확정하고, `Retry-After`를 보존해 서버가 정한 최소 대기
시간 전에 resume하지 못하도록 구현했다. 제품 계획, 공통 지침, X01, 구현 상태와 결정 로그를
함께 갱신했다.

## 요구사항과 현재 구현

| 범위 | 확인된 구현 | 판정 |
|---|---|---|
| 출처·원본 보존 | API/파일 결과와 manifest를 보존하고 해시·근거를 기록 | 제한 경로에서 충족; 전체 기관 범위는 아님 |
| 검색→수집 | 구조화 후보 순위, 명시 선택, World Bank fixture E2E | Gate B 제한 engine/API 범위 통과; 자연어 UI·일반 기관 검색은 미구현 |
| 파일/API | BLS/Census API와 CSV/TSV/TXT/HTML/ZIP/XLS/XLSX의 제한 파서 | 제한 형식에서 구현; provider-wide 및 queued chunk 실행은 미완료 |
| 장애 복구 | 오류 분류, 호출 예산, 명시적 resume, `Retry-After` 대기 강제 | 정책·구현 정합성 수정 완료; 자동 지수 backoff와 공용 rate limiter는 미구현 |
| 품질·변경 감지 | BLS/Census 행 진단과 동일 요청의 payload 비교 | 제한 구현; World Bank 비교와 완전한 vintage/통계 의미 검증은 미완료 |
| 지식·개선 엔진 | 계획 및 일부 관리자 기반 | 전용 지식 조회/갱신 실행은 미구현; 11~14회차 전제 기능으로 남음 |

## 게이트와 작업 순서

- Gate A: 통과 기록이 있다. 세부는 `docs/ITERATION_04_REPORT.md`를 기준으로 한다.
- Gate B: 제한 engine/API 범위 통과. 구조화 조건의 후보 순위, mismatched candidate 제외,
  explicit selection과 World Bank fixture collection E2E를 검증했다. 이 판정은 natural language UI,
  all-agency search 또는 BLS/Census candidate-to-live-collection을 포함하지 않는다. 근거와 범위 변경은
  `docs/ITERATION_08_REPORT.md` addendum과 D-060을 따른다.
- Gate C: 미통과. BLS와 Census 각 1회 HTTP 200 live smoke는 확인했지만 `REFERENCE_SCENARIOS.md`의
  기관별 파일/API와 변경·복구 표본이 아직 부족하다.
- Gate D/E: 미실행. 11회차 이후는 Gate C 검토가 끝날 때까지 보류한다.

사용자의 명시 지시로 08→09를 순서대로 진행한 것은 당시의 단일 회차 규칙을 넘긴 역사적
예외다. Gate B의 현재 제한 범위 판정은 이 실행 예외와 별개의 D-060 결정이다. 09의 제한 파일
파서 결과와 10의 제한 오류 진단만으로 Gate C를 통과하지 않는다.

## live smoke와 배포 추적성

현재 workspace 코드에서 BLS `CUUR0000SA0` 2024 요청과 Census ACS 2022 California
`B01001_001E` 요청이 각각 HTTP 200으로 완료됐고, 원본·manifest 해시 및 크기를 확인했다.
이 테스트는 당시 작업 트리의 동작만 증명한다. `origin/codex/iteration-04-gate-a`는
`2c4e11fa0534bae6458154abfa14a03d3617a15b`로 확인됐다. 05~10 코드 작업 트리는 별도 local
branch `codex/institution-discovery-05`의 미커밋/untracked 변경이었고, 이를
`7a2bb031d61061abc894ac206c45a95d8e45f5fd` local commit으로 고정했다. detached clean checkout에서
pytest 524개, Ruff, `git diff --check`를 통과했다. 원격 push와 환경 draft/publish는 하지 않았으므로
원격 ref는 새 코드의 배포 근거가 아니다.

이전 raw manifest에는 비교용 hash가 없어 source change status는 `unknown_history_integrity`로
남았다. BLS 응답의 volatile `responseTime`만 제외하는 canonical comparison은 구현했지만,
기존 원본의 무결성 이력이 없으므로 소급해 변경 없음으로 판정하지 않는다.

## 검증 및 다음 순서

이번 수정은 mocked `Retry-After` 초/HTTP-date 응답, BLS/Census 전파, resume 대기 차단 테스트로
검증했다. 전체 pytest **524개 통과**, Ruff와 `git diff --check` 통과. 외부 요청은 보내지 않았다.

이번 task는 Gate B/C 상태와 배포 추적성을 분리한다. Gate B는 D-060에 따라 엔진/API 제한
범위에서 통과했고, Gate C는 기관별 파일/API 및 변경·복구 시나리오 부족으로 미통과다.
local commit `7a2bb031`과 clean checkout 검증은 이 코드 snapshot을 재현 가능하게 하지만,
push/publish가 없으므로 실행 환경의 원격 checkout까지 해결하지 않는다. 자동 기관 지원 완료나
출시 준비로 표현하지 않는다.

## 게시 후 follow-up (2026-10-26)

이 보고서의 위 배포 추적성 판정은 이후 사용자가 환경을 게시하기 전 상태의 기록이다. 게시 후
새 실행 환경이 branch `codex/institution-discovery-05`의
`781827593924e35dadbc1188f09c7ea40a7b7c76`에서 clean checkout으로 시작했고, runtime observed
spec revision 4에서 running/connected임을 확인했다. 따라서 해당 게시 기준선의 추적성은 확인됐다.
이번 후속 World Bank X08 코드 변경은 이 게시 SHA에 포함되지 않아 local 검토 상태이며,
push/publish하지 않았다. `BLS_API_KEY`/`CENSUS_API_KEY` readiness와 network policy는 telemetry에서
계속 `unknown`; live API 호출은 하지 않았다. World Bank same-scope change detection은 local
후속 diff로 구현했고 TIC/BIS-shaped ingestion fixture를 추가해 pytest 534개, Ruff,
`git diff --check`를 통과했으나 게시 SHA에는 포함되지 않았다. Gate C는 기관별 공식 경로/API 및
복구 시나리오가 남아 있어 미통과다. 현행 상태는
`docs/IMPLEMENTATION_PLAN.md`의 상단을 따른다.

## 최신 후속 상태 (2026-10-26)

위의 revision 4/pytest 534 상태는 앞선 후속 시점의 기록이다. 이후 게시된 환경은 observed spec
revision 5에서 running/connected로 확인됐다. BLS `CUUR0000SA0` 2024 및 Census ACS 2022
California 요청의 새 HTTP 200 응답과 raw hash를 확인했고, 공식 Treasury TIC Table 5 TXT 한 건을
일반 파일 intake로 파싱해 원본·manifest·normalized hash를 대조했다. 이 TIC 표는 기간 말 보유잔액
(십억 달러)이다.

Local tabular intake는 동일 source URL/parser scope의 과거 원본을 검증해 비교한다. 변경 bytes나
검증 불가 이력은 raw만 보존하고 `NEEDS_REVIEW`로 멈추며, changed/unchanged/손상 이력과 서로 다른
URL 분기 테스트가 추가됐다. 그 시점에 **551 pytest**, Ruff, `git diff --check`가 통과했다. 아래
최신 follow-up은 그 뒤 사용자가 게시한 revision 5 runtime과 BIS/BOJ live 결과를 기록한다.

## 최신 Gate C 후속 — BIS bulk / BOJ 경로 (2026-10-26)

- 게시된 revision 5 runtime은 running/connected였고 현재 프로세스에서
  `MACROATLAS_NETWORK_ENABLED=true`가 읽혔다. telemetry의 network/key readiness는 여전히
  `unknown`이다. 이 task에서는 환경 draft를 변경하거나 게시하지 않았다.
- BIS official bulk page와 Global Liquidity column ZIP을 실제 호출해 HTTP 200을 받았고, ZIP→CSV
  raw/manifest/normalized intake와 SHA256 대조를 완료했다. 혼합 series를 한 시계열로 간주하지
  않는다. flat ZIP 대안은 HTTP 503으로 끝났으며 retry하지 않았다.
- BOJ API 공지는 HTTP 200, 연결된 manual은 HTTP 403이었다. API parameter/series mapping을
  확인하지 못했으므로 BOJ observation request는 미구성, collector 상태는 `BLOCKED`다.
- BIS/BOJ 실측과 Retry-After fixture를 반영한 전체 **556 pytest**, Ruff, `git diff --check` 통과.
  실제 source revision comparison과 기관별 복구/resume는 미완료라 Gate C 미통과, Gate D/11 미실행.
- 현재 branch `codex/institution-discovery-05`의 base HEAD는
  `781827593924e35dadbc1188f09c7ea40a7b7c76`; 후속 수정은 미커밋·미푸시다.

## 후속 상태 정정 (2026-10-26)

위 마지막 문단은 당시의 branch·gate 상태를 기록한 역사 자료다. 이후 D-067에서 Gate C를 검증된
범위로 제한 통과 처리했고, Gate D와 11~14회차 작업이 완료됐다. 현행 Gate C/D/E 상태, commit/push,
제한 범위와 미해결 자연 live 증거는 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md),
[`GATE_C_REVIEW_2026_10_26.md`](GATE_C_REVIEW_2026_10_26.md),
[`ITERATION_14_REPORT.md`](ITERATION_14_REPORT.md)를 따른다.
