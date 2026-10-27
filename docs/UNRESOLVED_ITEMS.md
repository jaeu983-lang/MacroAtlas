# 현행 미해결 항목 — 데이터 처리와 서버 접속 분리

> 2026-10-27 갱신: 이 maintenance follow-up의 base에는 PR #1–#16이 병합돼 있었고 HEAD는 `5ade536bc09ff2fcf0e2204a226ab9c9a4bbe208`였다. PR #9의 `7723afe`는 당시 CSV 전달 병합점이며 PR #4의 worker 복구도 `25f3c87`로 통합됐다. 고정 World Bank GDP에 음수값 격리 및 indicator title/identity 검사를 추가했다. 이 보고서는 자연 증거·대용량 예측 보정·통계 의미 검증·지원 확대·사용자 관찰의 남은 조건을 정리한다.

후속 상태: PR #17–#19도 병합됐다. 격리 updater→candidate QA→review PR handoff와 Codex CLI 옵션 호환성을 통합했고, 실제 updater 시도에서 확인한 Codex `401`을 `CODEX_AUTH_REQUIRED`와 재로그인 안내로 보고한다. 최신 pilot 및 CI 결과는 [차단 보고서](ITERATION_26_PILOT_BLOCKER_REPORT.md)를 참조한다. 이 기능의 실제 pilot은 Codex CLI 재로그인 후 이어갈 수 있다.

기준일: 2026-10-27. 근거는 보존된 `data/catalog.sqlite`, raw/manifest, 최신 코드,
과거 네 provider live 결과와 문서화된 TIC/BIS exact-scope 감시 기록이다. 당시 TIC task
`2733c6a3-abb8-4201-9735-b3354fd32bd9`와 BIS task `30786cba-1024-4d8b-a599-51942bd91c63`는
완료·unchanged였으며 자연 개정이나 provider 오류는 발생하지 않았다. 과거 FAILED/BLOCKED 라벨만으로
현재 장애를 판정하지 않는다.
다른 기관 접속 상태나 다음 게시 주기까지의 상태는 이 결과에 포함되지 않는다.

## 1. 데이터 처리·전달에 남은 작업

| 항목 | 현재 확인된 상태 | 남은 작업 | 접속 문제 여부 |
|---|---|---|---|
| BIS GLI flat ZIP 구조 보존 materialization | PR #6 통합 후 child task `c244a486-17e5-4b60-a82b-287f8a37bbe7`에서 보존 event seq 1/raw를 한 번 처리. 24,378×21 문자열 JSONL, manifest/chunk hash, 원본 불변성, task attempt와 `handed_off/resolved` 확인 | 이 단일 BIS flat profile은 완료. 다른 provider·format·의미 정규화는 별도 qualification과 승인으로 계획 | 해결된 로컬 데이터 처리 항목. 접속 오류나 Gate C 자연 증거가 아님 |
| World Bank/BOJ 정규화 결과 CSV 전달 | 20회차에서 완료 task의 저장 evidence를 read-only 재검증해 CSV와 provenance sidecar를 만들고, 보존 World Bank/BOJ task로 확인 | 현재 좁은 provider scope를 유지. XLSX, BIS flat JSONL, 다른 기관 export는 별도 요구·검증 후 계획 | 이 제한된 로컬 전달 기능은 해결. XLSX/BIS export는 미구현 제품 범위이지 접속 장애가 아님 |
| 비API 대용량 시간 예측의 경험 보정 | 현재 catalog에 qualification 성공 사례 15건, production 1건, baseline/empirical paired forecast 0건 | 각 실행 전 예측과 실제 stage 시간을 기존의 승인된 작업에서 축적한다. 예측 표본을 만들 목적만으로 대용량 작업을 실행하지 않는다. Qualification과 production은 따로 보정 | 기능은 구현·통합됐다. 예측 정확도는 증거 부족으로 낮은 신뢰도 |
| 통계 의미·품질 범위 확대 | 고정 World Bank GDP 경로에서 indicator code/title 일치와 음수 값 격리를 확인하고 결측·0을 분리 보존한다. 저장된 2020–2022 원본의 read-only v2 재검증은 3행, 결측 0, 음수 0, 이슈 없음이며 단위·빈도 unknown 경고는 유지됐다. 원 기록은 v1로 보존했다. [근거](WORLDBANK_QUALITY_RECHECK_2026_10_27.md) | 공식 metadata로 단위·빈도·정의 확인; 경제 이상치(음수 외), 개정 이력·기관 간 동등성은 별도 검증 | 데이터 의미/검증 범위. 다운로드 실패 아님 |
| 시험 worker 강제 종료 복구 | lock 상속·미확정 NOT_EXECUTED 복구를 추가했고 당시 4조합 CI가 통과 | PR #4가 `25f3c87`에 이미 병합됨 | 완료된 제품 복구 항목. 서버 문제 아님 |
| 대용량 인계 후 실행·상태 관리 | PR #6에서 BIS flat 전용 `handed_off/resolved`, 승인 child, chunk/hash checkpoint와 same-task resume 구조를 통합했고 실제 보존 raw task가 완료됨 | 다른 provider, Windows resource worker, 더 큰 입력·pagination은 별도 qualification 후 평가 | BIS flat 제한 경로 완료. 범용 대용량 지원은 남은 제품 범위 |
| 추가 형식·기관과 Windows 대용량 worker | 현행 production worker는 BIS flat ZIP 한 경로의 Linux 자원 제한 실행만 지원. 다른 형식·기관 및 Windows 자원 worker는 지원 범위 밖 | 각 provider/format을 격리 qualification하고, Windows는 별도 process memory/time/cancel/orphan recovery 한도를 실제 Windows에서 입증한 뒤 한 경로씩 결정 | 제품 지원 범위 미구현. 서버 접속 오류로 분류하지 않음 |
| 실제 분석가 업무 관찰 | 내부 status→CSV dry run과 23회차 관찰안은 준비됐으나 독립 참가자 관찰은 아직 없음 | 익명 기록·동의 절차를 사용해 분석가 1–2명이 저장 task 결과를 찾고 CSV를 설명하는 세션 수행 | 참가자 증거 대기. 자기 검토를 사용자 검증으로 계산하지 않음 |

BIS flat의 정상 인계는 16회차 정책 구현 완료 증거다. 19회차 flat JSONL 생성은 structural preservation이며
경제 의미를 정규화하지 않는다. 보존 원본 production 실행은 완료됐지만 이 경로를 일반 exporter나 추가 형식 지원으로
일반화하지 않는다. 이 둘을 하나의 ‘미해결 파싱 오류’로 합치지 않는다. 용량 가드는 그대로 적용한다.

## 2. 서버 접속·전송·인증 상태

| 경로/사례 | 현재 근거 | 판정 | 다음 행동 |
|---|---|---|---|
| World Bank GDP | task 0f968a54-9855-439c-aaf2-bb7022fb5c8c 수집/검증 완료 | 최신 지원 경로 접속 성공 | 새 실패가 발생하면 해당 task의 HTTP/TLS/proxy·Retry-After를 기준으로 진단 |
| BOJ FM08/FXERD01 | task 96f82a80-e84b-4b34-b282-204fb642afae metadata/data 완료 | 최신 고정 경로 접속 성공 | 다른 series의 성공으로 확대하지 않음 |
| TIC Table 5 | task 2720605a-199c-4355-ab2c-d18a8cfa27a3 완료·unchanged | 최신 고정 URL 접속 성공 | 게시 주기 감시 유지 |
| BIS column ZIP | task e8a57a1a-b24e-4c5f-a4e7-ea557cc6a762 완료·unchanged | 최신 고정 URL 접속 성공 | 게시 주기 감시 유지 |
| 과거 ProxyError·World Bank 직접 연결 실패 | 당시 실행 권한/proxy 설정 문제를 확인·수정했고 이후 실측 성공 | 해결된 환경/전송 구성 문제. 현재 기관 서버 장애로 분류하지 않음 | 설정 proxy/CA 유지. 과거 실패 이력은 보존 |
| 과거 BIS 503 | 당시 HTTP 응답 관측은 있었지만 실패 task 저장이 없었음. 이후 성공과 현재 column 성공 확인 | 과거 일시 제공자 오류. 현재 지속 장애 증거 없음 | 재발하면 저장된 task로 상태·응답·대기시간·재개 이력 확보 |
| 기타 기관·인증 경로 | 이번 재검증에서 해당 기관 observation 요청을 보내지 않음 | 접속·인증 상태 미확인. 현재 401/403/차단을 주장할 근거 없음 | 공식 endpoint·요청 범위 및 구현 여부를 먼저 확정해 제한 실측 |

**최신 네 지원 경로에서 확인된 활성 서버 접속 차단은 없다.** 이 판정은 이 네 경로의 최근 실측 범위에 한정된다.
접속 실패 시에도 DNS/TCP/proxy/TLS/HTTP 인증·권한/429·5xx를 분리하며, 로컬 권한 실패를 기관 서버 장애로 기록하지 않는다.

## 3. 수집 기능 미구현 — 접속 오류와 분리

- IMF·BEA·ECB/Eurostat·중국 기관의 광범위 observation 수집: 현재 connectors/CLI에 해당 경로가 없음.
  서버가 막혀서 실행하지 못한 것으로 분류하지 않는다. 공식 문서 조사·metadata mapping·adapter 구현이 선행 작업이다.
- 다른 BOJ series·MOF·e-Stat, OECD 비교·다국가 검색, 일반 자연어/기관 전반 검색: 현재 검증된 고정 경로 밖의 제품 기능이다.
- BLS/Census는 제한 connector와 fixture 검증이 있으나 이번 네 경로 실측에 포함되지 않았다.
  과거 응답이나 키 설정만으로 현재 접속·인증 성공/실패를 새로 단정하지 않는다.

## 4. 증거 미관측 — 현재 고장과 분리

| 항목 | 이번 관측 | 남은 조건 | 판정 |
|---|---|---|---|
| 실제 원자료 개정 감지 | 마지막 기록된 exact-scope 비교는 TIC/BIS 모두 unchanged | 같은 scope의 실제 변경 raw 쌍, `changed/NEEDS_REVIEW`, 양쪽 원본 보존 및 새 정규화 차단 | 미해결. 자연 개정 대기 |
| 자연 장애 후 durable resume | World Bank API task `84a1afd9-4b56-454f-96ea-f6e59f245afc`에서 자연 `FAILED_RETRYABLE/TRANSIENT` 이후 같은 task의 attempt 2로 재개해 collect·validate가 성공했다. 최초 Retry-After는 없었고 max_attempts=3 중 1회 사용 상태였다. | 이 실측은 World Bank API collector 범위다. TIC/BIS file watch에서의 natural retryable failure는 아직 관측되지 않았다. source-specific 증거가 요구되면 같은 URL/scope의 저장 task를 재개 | World Bank 범위의 자연 durable resume는 확보. Gate C 자연 source revision은 별도 미해결 |

변경·503 fixture는 동작 검증에 사용하며 자연 발생 실측을 대신하지 않는다. World Bank 재개는 별도의 자연
실측으로 저장됐지만 TIC/BIS 변경 쌍을 대체하지 않는다. 이는 현재 서버 장애 또는 현재 데이터 손상이라는 판정이
아니다.

## 5. 작업 상태와 원인을 혼동하지 않는 규칙

이번 조회는 보존된 SQLite task와 event를 읽기 전용으로 확인했다.
`NEEDS_REVIEW`인 flat 재검증 task 2797e6d0-a8ac-40e5-aca4-066991a7c2e1은 reason=cells의 정상 인계다.
과거 task bea335ad-1819-42cb-8acd-797c6a452255의 SCHEMA_CHANGED는 과거 parser 판정으로 보존한다.
World Bank task `84a1afd9-4b56-454f-96ea-f6e59f245afc`는 2026-10-26에 collect가 `FAILED_RETRYABLE/TRANSIENT`로 끝났고, 2026-10-27에 같은 task를 한 번 재개해 collect·validate 성공으로 완료됐다. 첫 실패와 재개 attempt/event는 모두 보존됐다.
plan·stage가 없는 CREATED snapshot들은 네트워크/데이터 실패로 계산하지 않는다.
과거 task 상태를 새 성공으로 덮어쓰거나 삭제하지 않았다.

## 6. 개발자 유지보수 자동화에 남은 연결

공통 QA runner는 전체 base/candidate SHA를 detached worktree에서 검사하며, `run_improvement.py`가 Codex 작업을 별도 Git
worktree로 격리하고 허용 경로를 검사한 뒤 candidate commit→동일 SHA QA→통과 시 push/PR 흐름을 연결한다. no-op에서는 작업
worktree와 생성 branch를 정리하고, QA 실패·범위 밖 변경은 push하지 않는다. 자동 merge/publish 권한은 없다.

남은 검증은 실제 Windows 환경에서 감독자가 시작하는 Codex pilot 1회와 scheduler 중복 실행·base ref·로그 보존 확인이다.
Linux에서 첫 updater 시작은 Codex CLI의 approval 옵션 순서 오류로 prompt 전에 종료됐다. 인자 위치와 CLI preflight를 수정해 병합했지만,
두 번째 실행은 Codex 서비스의 `401 Unauthorized`와 access token 갱신 실패로 prompt 전에 종료됐다. worktree는 clean임을 확인하고
정리했으며 candidate/QA/push/PR은 만들지 않았다. 실제 updater pilot을 이어가려면 사용자가 Codex CLI에 다시 로그인해야 한다.
이 인증 문제는 제품 data engine, Gate C 원자료 증거 또는 기관 서버 상태와 별도다. 근거는 [26회차 보고서](ITERATION_26_REPORT.md),
[CLI 호환성 기록](ITERATION_26_FOLLOWUP_REPORT.md), [인증 차단 기록](ITERATION_26_PILOT_BLOCKER_REPORT.md)에 있다.

## 다음 작업 우선순위

현재 확인한 제품의 활성 transport 장애는 없다. 실행 순서의 기준은 [제품 로드맵](ROADMAP_2026_10_26.md)이며,
대용량 시험 성공을 정식 정규화 완료로 취급하지 않는다.

1. **완료:** PR #1~#19 병합. 이번 maintenance follow-up의 시작 base는 `5ade536bc09ff2fcf0e2204a226ab9c9a4bbe208`; PR #9 `7723afe`와 PR #4 `25f3c87`은 개별 병합점이며 PR #17–#19는 updater handoff와 인증 차단 보고를 추가했다.
2. **완료:** 기존 BIS flat event seq `1`을 단일 child task에서 처리하고 output manifest/chunk 해시, 원본 불변성, child/deferral 이력을 확인했다.
3. **완료:** World Bank/BOJ 검증 task CSV 전달. 666개 전체 test, Ruff, diff check와 실제 보존 task 2개의 로컬 export/hash 검증을 기록했다.
4. **완료(내부 dry run):** 저장 task 두 건에서 status→CSV 전달 경로·출력 hash·경고를 재확인했다. 이는 사용자 조사 통과가 아니다.
5. **관찰 대기:** 분석가 1–2명의 실제 업무 관찰 후 다음 provider·UI·자연어 범위를 정한다. 절차는 [23회차 계획](ITERATION_23_PLAN.md)에 있고 참가자 관찰은 미실행이다.
6. **자연 증거:** TIC/BIS 감시는 기존 baseline과 exact scope로 유지한다. 실제 개정 쌍이 생기면 변경 raw 두 개, `changed/NEEDS_REVIEW`, 정규화 차단을 검토한다. World Bank 자연 resume는 확보됐으나 provider-specific Gate C 검토를 대체하지 않는다.
7. **예측 보정:** 승인된 qualification/production이 실행될 때 예측·실제 stage time을 축적한다. paired 표본이 각 operation에서 3건에 도달할 때 모델 오차를 재평가한다. 표본 생성만을 위한 실행은 하지 않는다.
8. **품질·범위 확대:** 실제 사용자 요구가 확인된 provider/format 하나씩 metadata 계약, 의미 검증, Linux/Windows 자원 한도와 복구 완료 기준을 정한 뒤 qualification한다.

남은 항목은 모두 같은 종류의 “실패”가 아니다. World Bank/BOJ 제한 CSV 전달과 19회차 BIS flat 단일 처리 경로는 완료됐다. 추가 provider/format과 Windows resource worker는 미구현 기능이다. 실제 TIC/BIS 원자료 개정은 여전히 미관측이다. World Bank에서는 자연 transient failure를 저장한 task의 same-task resume가 확인됐다. 과거 proxy 연결 문제는 설정을 바로잡은 뒤 성공 실측이 있어 해결된 이력으로 남긴다.

근거: [현행 Gate 재검증](GATE_REAUDIT_AFTER_ITERATION_16.md), [인계 목록](NON_API_DEFERRED_CATALOG.json),
[엔진 연결 설계](ENGINE_CONNECTIONS.md), [17회차 시험 계획](ITERATION_17_PLAN.md),
[CSV 후속 계획](CSV_EXPORT_FOLLOWUP_PLAN.md).

17회차의 합성 용량·BIS 원본 시험은 [보고서](ITERATION_17_REPORT.md)를 따른다. 시험 통과와 정식 처리 완료를 구분한다.
