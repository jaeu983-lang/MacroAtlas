# 2026-10-27 미해결 항목 snapshot — 데이터 처리와 서버 접속 분리

> 역사 기록: 이 문서는 2026-10-27 당시의 backlog와 Windows updater 증거를 보존한다. 현재 backlog·Gate 순서는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)와 [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md)를 따른다. 아래의 당시 '현재 남은 제품 과제' 문구는 지금의 실행 순서가 아니다.
>
> 2026-10-27 갱신: updater 코드 기준은 PR #34 merge commit `543c719be506350ce57fd14358173e54ede812b3`이다. 이후 Windows updater pilot evidence는 [27회차 보고서](ITERATION_27_PILOT_REPORT.md)에 기록했으며, 기관·dataset scope 근거는 PR #23–#26에서 보완했고 PR #28은 malformed task plan의 CSV export를 거부한다. 현재 남은 제품 과제는 대용량 예측 보정, 통계 의미 검증, 지원 범위 확대와 사용자 관찰이다. TIC/BIS 자료 변경상태 확인은 사용자 요청으로 현재 범위에서 제외했으며 updater scheduler의 실제 Windows 검증은 아래 별도 상태를 따른다.

후속 상태: Linux updater candidate QA/PR handoff와 Windows installer dry-run, no-op/cleanup, 교차 프로세스 lock 경합은 확인됐다. Windows no-op run `20261027T063907Z-d01e9247`은 base `aefd320`에서 cleanup과 retention 요약(`scanned=5, removed=0, preserved=5`)을 통과했다. Lock run `20261027T063105Z-60a54edf`는 네트워크 작업 없이 `ALREADY_RUNNING`을 반환했다. 사용자는 base `f8693f0`에서 updater·retention 대상 테스트 34개를 통과시키고, 최신 base `e25d944`에서 실제 updater run `20261027T084854Z-00b29eb9`의 `NO_ACTIONABLE_CHANGE`·cleanup 성공·retention (`scanned=7, removed=0, preserved=7`)을 확인했다. GitHub Actions는 기준 HEAD `7fbd67e` 및 merge commit `fb37234`의 4개 job이 step 실행 전에 실패해 자동 CI 결과를 제공하지 않았다. 실제 Windows 사용자-session candidate/handoff 및 scheduler invocation은 미확인이라 task는 비활성이다. [27회차 pilot 보고서](ITERATION_27_PILOT_REPORT.md)에 실행 결과를 기록한다.

기준일: 2026-10-27. 근거는 보존된 `data/catalog.sqlite`, raw/manifest, 최신 코드,
과거 네 provider live 결과와 문서화된 TIC/BIS exact-scope 감시 기록이다. 당시 TIC task
`2733c6a3-abb8-4201-9735-b3354fd32bd9`와 BIS task `30786cba-1024-4d8b-a599-51942bd91c63`는
완료·unchanged였으며 자연 개정이나 provider 오류는 발생하지 않았다. 과거 FAILED/BLOCKED 라벨만으로
현재 장애를 판정하지 않는다.
다른 기관 접속 상태나 다음 게시 주기까지의 상태는 이 결과에 포함되지 않는다.

2026-10-27 사용자 범위 갱신: TIC/BIS 자료 변경상태를 반복 확인할 필요가 없다는 요청에 따라
`Gate C 자연 증거 감시`와 `Gate C Source Watch` 자동화를 중지했다. 기존 baseline, 과거 `unchanged`
관측 및 Gate C 제한 판정은 그대로 보존한다. 변경 감지 기능의 과거 검증 이력은 기록으로 남지만,
새 TIC/BIS 변경·장애를 확인하는 작업은 현재 활성 backlog가 아니다.

## 1. 데이터 처리·전달에 남은 작업

| 항목 | 현재 확인된 상태 | 남은 작업 | 접속 문제 여부 |
|---|---|---|---|
| BIS GLI flat ZIP 구조 보존 materialization | PR #6 통합 후 child task `c244a486-17e5-4b60-a82b-287f8a37bbe7`에서 보존 event seq 1/raw를 한 번 처리. 24,378×21 문자열 JSONL, manifest/chunk hash, 원본 불변성, task attempt와 `handed_off/resolved` 확인 | 이 단일 BIS flat profile은 완료. 다른 provider·format·의미 정규화는 별도 qualification과 승인으로 계획 | 해결된 로컬 데이터 처리 항목. 접속 오류나 Gate C 자연 증거가 아님 |
| World Bank/BOJ 정규화 결과 CSV 전달 | 20회차에서 완료 task의 저장 evidence를 read-only 재검증해 CSV와 provenance sidecar를 만들고, 보존 World Bank/BOJ task로 확인 | 현재 좁은 provider scope를 유지. XLSX, BIS flat JSONL, 다른 기관 export는 별도 요구·검증 후 계획 | 이 제한된 로컬 전달 기능은 해결. XLSX/BIS export는 미구현 제품 범위이지 접속 장애가 아님 |
| 비API 대용량 시간 예측의 경험 보정 | 현재 catalog에 qualification 성공 사례 15건, production 1건, baseline/empirical paired forecast 0건 | 각 실행 전 예측과 실제 stage 시간을 기존의 승인된 작업에서 축적한다. 예측 표본을 만들 목적만으로 대용량 작업을 실행하지 않는다. Qualification과 production은 따로 보정 | 기능은 구현·통합됐다. 예측 정확도는 증거 부족으로 낮은 신뢰도 |
| 통계 의미·품질 범위 확대 | 고정 World Bank GDP 경로에서 indicator code/title 일치와 음수 값 격리를 확인하고 결측·0을 분리 보존한다. 저장된 2020–2022 원본은 3행, 결측 0, 음수 0, 이슈 없음이다. 별도 공식 metadata는 GDP (current US$) 및 미국 달러/current-price 정의를 확인했지만 structured unit field는 빈 값이고 frequency field는 없다. raw와 metadata capture는 보존했고 기존 정규화 unit/frequency unknown 판정은 유지했다. [근거](WORLDBANK_QUALITY_RECHECK_2026_10_27.md) | 주기/빈도 근거, 경제 이상치(음수 외), 개정 이력·기관 간 동등성 검증. 새 정규화 mapping은 공식 구조화 metadata가 있을 때 별도 설계 | 데이터 의미/검증 범위. 다운로드 실패 아님 |
| 시험 worker 강제 종료 복구 | lock 상속·미확정 NOT_EXECUTED 복구를 추가했고 당시 4조합 CI가 통과 | PR #4가 `25f3c87`에 이미 병합됨 | 완료된 제품 복구 항목. 서버 문제 아님 |
| 대용량 인계 후 실행·상태 관리 | PR #6에서 BIS flat 전용 `handed_off/resolved`, 승인 child, chunk/hash checkpoint와 same-task resume 구조를 통합했고 실제 보존 raw task가 완료됨 | 다른 provider, Windows resource worker, 더 큰 입력·pagination은 별도 qualification 후 평가 | BIS flat 제한 경로 완료. 범용 대용량 지원은 남은 제품 범위 |
| 추가 형식·기관과 Windows 대용량 worker | 현행 production worker는 BIS flat ZIP 한 경로의 Linux 자원 제한 실행만 지원. 다른 형식·기관 및 Windows 자원 worker는 지원 범위 밖 | 각 provider/format을 격리 qualification하고, Windows는 별도 process memory/time/cancel/orphan recovery 한도를 실제 Windows에서 입증한 뒤 한 경로씩 결정 | 제품 지원 범위 미구현. 서버 접속 오류로 분류하지 않음 |
| 실제 분석가 업무 관찰 | 내부 status→CSV dry run과 23회차 관찰안은 준비됐으나 독립 참가자 관찰은 아직 없음 | A–G 28–39회차 gate 후 최종 40회차에서 검증된 원본/비교 workbook과 feedback 기록 흐름을 관찰. 시나리오·task ID·기대 sheet를 실행 전에 갱신 | 참가자 evidence 대기. 자기 검토를 사용자 검증으로 계산하지 않음 |

BIS flat의 정상 인계는 16회차 정책 구현 완료 증거다. 19회차 flat JSONL 생성은 structural preservation이며
경제 의미를 정규화하지 않는다. 보존 원본 production 실행은 완료됐지만 이 경로를 일반 exporter나 추가 형식 지원으로
일반화하지 않는다. 이 둘을 하나의 ‘미해결 파싱 오류’로 합치지 않는다. 용량 가드는 그대로 적용한다.

## 2. 서버 접속·전송·인증 상태

| 경로/사례 | 현재 근거 | 판정 | 다음 행동 |
|---|---|---|---|
| World Bank GDP | task 0f968a54-9855-439c-aaf2-bb7022fb5c8c 수집/검증 완료 | 최신 지원 경로 접속 성공 | 새 실패가 발생하면 해당 task의 HTTP/TLS/proxy·Retry-After를 기준으로 진단 |
| BOJ FM08/FXERD01 | task 96f82a80-e84b-4b34-b282-204fb642afae metadata/data 완료 | 최신 고정 경로 접속 성공 | 다른 series의 성공으로 확대하지 않음 |
| TIC Table 5 | task 2720605a-199c-4355-ab2c-d18a8cfa27a3 완료·unchanged | 마지막 기록된 고정 URL 접속 성공 | 정기 변경 확인 불필요. 필요 시 요청된 단발 작업에서 확인 |
| BIS column ZIP | task e8a57a1a-b24e-4c5f-a4e7-ea557cc6a762 완료·unchanged | 마지막 기록된 고정 URL 접속 성공 | 정기 변경 확인 불필요. 필요 시 요청된 단발 작업에서 확인 |
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
| TIC/BIS 원자료 개정 감지 | 마지막 기록 exact-scope 비교는 양쪽 모두 unchanged; 실제 변경 쌍은 없음 | 사용자가 현재 확인을 불필요하다고 지정해 반복 감시 자동화를 중지함 | 활성 작업에서 제외. 과거 자연 변경이 미관측이라는 Gate C 이력은 그대로 보존 |
| 자연 장애 후 durable resume | World Bank API task `84a1afd9-4b56-454f-96ea-f6e59f245afc`에서 자연 `FAILED_RETRYABLE/TRANSIENT` 이후 같은 task의 attempt 2로 재개해 collect·validate가 성공했다. 최초 Retry-After는 없었고 max_attempts=3 중 1회 사용 상태였다. | World Bank 범위는 확인됨. TIC/BIS watch scope의 자연 retryable failure는 미관측이며, 정기 감시는 중지됨. 향후 사용자가 요청한 수집 중 실패하면 그 task를 보존해 재개 이력을 기록 | 현재 운영 장애가 아니며 추가 감시 과제가 아님. 사용자 재요청이 있으면 단발 task에서 증거를 남김 |

변경·503 fixture는 동작 검증에 사용하며 자연 발생 실측으로 다시 분류하지 않는다. World Bank 재개는 별도의 자연
실측으로 보존한다. TIC/BIS 변경쌍과 file-watch 장애 이력은 관측되지 않았지만 현재 요구 범위에서 제외됐다.
이는 현재 서버 장애 또는 현재 데이터 손상이라는 판정이 아니다.

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

Windows pilot에서 PR #34 installer dry-run과 updater `NO_ACTIONABLE_CHANGE`/cleanup이 통과했다. 기존 수동 run `20261027T062202Z-a897a292`은 base `689cd1b`, retention `scanned=3/removed=0/preserved=3`을 기록했다. lock run `20261027T063105Z-60a54edf`는 `ALREADY_RUNNING`, `network_requested=false`, `push_status=NOT_RUN`을 반환해 Windows 교차 프로세스 lock 차단을 확인했다. no-op run `20261027T063907Z-d01e9247`은 base `aefd320`, cleanup `PASSED`, retention `scanned=5/removed=0/preserved=5`를 기록했다. 이후 base `f8693f0`의 Windows updater·retention suite 34개가 통과했고, base `e25d944`의 updater run `20261027T084854Z-00b29eb9`는 `NO_ACTIONABLE_CHANGE`, cleanup 성공, retention `scanned=7/removed=0/preserved=7`을 기록했다. GitHub Actions matrix는 account usage limit으로 시작하지 못했다. 실제 Codex changed-candidate handoff와 scheduled invocation은 아직 관측되지 않으며 task는 비활성이다.
Linux에서는 첫 시도가 token refresh `401`로 중단됐지만 device-code 재인증 뒤 updater가 candidate QA/PR handoff까지 완료했고 PR #28이 병합됐다. Windows 사용자 세션에서 updater no-op/cleanup, OS lock contention 및 해당 updater 회귀 테스트는 통과했다. 실제 changed-candidate updater run과 Task Scheduler 동작은 아직 검증하지 않았다. 이 개발자 인증 이슈는 제품 data engine, Gate C 원자료 증거 또는 기관 서버 상태와 별도다. 상세 이력은 [26회차 차단 기록](ITERATION_26_PILOT_BLOCKER_REPORT.md)과 [27회차 pilot 보고서](ITERATION_27_PILOT_REPORT.md)에 있다.

## 다음 작업 우선순위

현재 확인한 제품의 활성 transport 장애는 없다. 실행 순서의 기준은 [통합 제품 기획](../PROJECT_PLAN.md)이며,
대용량 시험 성공을 정식 정규화 완료로 취급하지 않는다.

1. **완료:** 기능 구현과 기록된 pilot 증거가 통합됐다. updater 코드 기준은 `543c719be506350ce57fd14358173e54ede812b3`; 최신 Windows no-op run의 base는 `aefd320a67d0abb5779393b90d32f6d149efa77e`. Linux updater candidate path와 Windows no-op/cleanup/lock contention은 통과했으며 Gate C 자연 원자료 변경은 별도로 남아 있다.
2. **완료:** 기존 BIS flat event seq `1`을 단일 child task에서 처리하고 output manifest/chunk 해시, 원본 불변성, child/deferral 이력을 확인했다.
3. **완료:** World Bank/BOJ 검증 task CSV 전달. 666개 전체 test, Ruff, diff check와 실제 보존 task 2개의 로컬 export/hash 검증을 기록했다.
4. **완료(내부 dry run):** 저장 task 두 건에서 status→CSV 전달 경로·출력 hash·경고를 재확인했다. 이는 사용자 조사 통과가 아니다.
5. **최종 관찰 대기:** 분석가 1–2명의 실제 업무 관찰은 23회차이며, A–G 28–39회차 통과 후 마지막 40회차로 진행한다. 관찰 대상은 완성된 workbook과 feedback 기록 흐름이다. 절차는 [23회차 계획](ITERATION_23_PLAN.md)에 있고 세션은 미실행이다.
6. **예측 보정:** 승인된 qualification/production이 실행될 때 예측·실제 stage time을 축적한다. paired 표본이 각 operation에서 3건에 도달할 때 모델 오차를 재평가한다. 표본 생성만을 위한 실행은 하지 않는다.
7. **품질·범위 확대:** 실제 사용자 요구가 확인된 provider/format 하나씩 metadata 계약, 의미 검증, Linux/Windows 자원 한도와 복구 완료 기준을 정한 뒤 qualification한다.

남은 항목은 모두 같은 종류의 “실패”가 아니다. World Bank/BOJ 제한 CSV 전달과 19회차 BIS flat 단일 처리 경로는 완료됐다. 추가 provider/format과 Windows resource worker는 미구현 기능이다. TIC/BIS 원자료 변경은 과거 미관측으로 기록됐고, 현재 사용자 요청에 따라 정기 확인하지 않는다. World Bank에서는 자연 transient failure를 저장한 task의 same-task resume가 확인됐다. 과거 proxy 연결 문제는 설정을 바로잡은 뒤 성공 실측이 있어 해결된 이력으로 남긴다.

근거: [현행 Gate 재검증](GATE_REAUDIT_AFTER_ITERATION_16.md), [인계 목록](NON_API_DEFERRED_CATALOG.json),
[엔진 연결 설계](ENGINE_CONNECTIONS.md), [17회차 시험 계획](ITERATION_17_PLAN.md),
[CSV 후속 계획](CSV_EXPORT_FOLLOWUP_PLAN.md).

17회차의 합성 용량·BIS 원본 시험은 [보고서](ITERATION_17_REPORT.md)를 따른다. 시험 통과와 정식 처리 완료를 구분한다.
