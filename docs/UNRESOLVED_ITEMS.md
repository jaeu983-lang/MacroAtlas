# 현행 미해결 항목 — 데이터 처리와 서버 접속 분리

기준일: 2026-10-26. 근거는 17회차 시험, 현재 저장소 상태, 과거 네 provider live 결과와
최신 TIC/BIS exact-scope 감시다. TIC task `2733c6a3-abb8-4201-9735-b3354fd32bd9`와
BIS task `30786cba-1024-4d8b-a599-51942bd91c63`는 모두 완료·unchanged였다. 이 감시에서 자연 개정이나
provider 오류는 발생하지 않았다. 과거 FAILED/BLOCKED 라벨만으로 현재 장애를 판정하지 않는다.
다른 기관 접속 상태나 다음 게시 주기까지의 상태는 이 결과에 포함되지 않는다.

## 1. 데이터 처리·전달에 남은 작업

| 항목 | 현재 확인된 상태 | 남은 작업 | 접속 문제 여부 |
|---|---|---|---|
| BIS GLI flat ZIP 실제 정규화 | 보존된 공식 원본 재처리에서 500,010개 셀을 확인하고 500,000개 상한으로 정상 deferred. 격리 시험은 24,378행·21열을 읽음 | 정식 handoff, 변경 가능한 상태 lifecycle, segmented artifact manifest, checkpoint/resume, 의미·품질 검증과 normalized output이 아직 없음 | 로컬 처리 기능. 접속 오류가 아님 |
| 정규화 결과 CSV/XLSX 전달 | 현재 구조화 CLI는 저장 경로·상태를 제공하며 범용 exporter가 없음 | CSV 출력 후속 계획의 provenance·무결성·덮어쓰기 방지 구현. XLSX는 별도 범위 | 로컬 결과 처리 기능 |
| 통계 의미·품질 범위 확대 | World Bank 고정 실측은 quality passed이지만 normalized unit/frequency unknown 경고가 있음. 경제 이상치·개정 역사·기관 간 동등성은 검사 범위 밖 | 공식 metadata로 단위·빈도·정의 확인 및 범위별 품질 검증 설계 | 데이터 의미/검증 범위. 다운로드 실패 아님 |
| 시험 worker 강제 종료 복구 | 17회차 구현에서 RUNNING task와 orphan scratch 복구가 빠져 있었음. lock 상속·미확정 NOT_EXECUTED 복구를 추가했고 코드 HEAD `e2e72a5`의 645개 로컬 테스트/Ruff 및 4조합 CI run 40359478210이 통과 | 구현 검증 완료. PR #4 통합은 PR #3 다음 순서 | 제품 내부 복구 결함. 서버 문제 아님 |
| 대용량 인계 후 실행·상태 관리 | 현재 엔진의 중단·영속 목록·조회와 17회차 불변 event 결합 격리 시험 성공 | 정식 정규화 실행 계약, 명시적 인계·완료 상태 변경, 목록 pagination 등 후속 구현 | 제품 내부 처리·운영 기능 |

BIS flat의 정상 인계는 16회차 정책 구현 완료 증거다. flat 자료의 실제 정규화는 아직 별도 엔진 대기다.
이 둘을 하나의 ‘미해결 파싱 오류’로 합치지 않는다. 용량 가드는 그대로 적용하고 상한을 올려 우회하지 않는다.

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

| 항목 | 이번 관측 | 충족에 필요한 증거 |
|---|---|---|
| 실제 원자료 개정 감지 | TIC/BIS 모두 unchanged | 같은 scope의 실제 변경 raw 쌍, changed/NEEDS_REVIEW, 양쪽 원본 보존 및 새 정규화 차단 |
| 자연 장애 후 durable resume | 이번 live 실행에서는 자연 장애가 발생하지 않음 | 자연 retryable 실패를 저장한 같은 task/stage에서 Retry-After 준수 후 재개 성공 및 attempt/event 이력 |

변경·503 fixture는 동작 검증에 사용하며 자연 발생 실측을 대신하지 않는다. 이 두 항목은 Gate C 확대 범위의
증거 대기다. 현재 서버 장애 또는 현재 데이터 손상이라는 판정이 아니다.

## 5. 작업 상태와 원인을 혼동하지 않는 규칙

이번 조회는 로컬 SQLite의 최근 최대 60개 task snapshot을 읽기 전용으로 확인했다.
`NEEDS_REVIEW`인 flat 재검증 task 2797e6d0-a8ac-40e5-aca4-066991a7c2e1은 reason=cells의 정상 인계다.
과거 task bea335ad-1819-42cb-8acd-797c6a452255의 SCHEMA_CHANGED는 과거 parser 판정으로 보존한다.
World Bank 과거 task 84a1afd9-4b56-454f-96ea-f6e59f245afc의 FAILED/TRANSIENT는 이력이며 이후 새 성공 task와 함께 해석한다.
plan·stage가 없는 CREATED snapshot들은 네트워크/데이터 실패로 계산하지 않는다.
과거 task 상태를 새 성공으로 덮어쓰거나 삭제하지 않았다.

## 다음 작업 우선순위

현재 확인한 제품의 활성 transport 장애는 없다. 실행 순서의 기준은 [제품 로드맵](ROADMAP_2026_10_26.md)이며,
대용량 시험 성공을 정식 정규화 완료로 취급하지 않는다.

1. **완료:** 17회차 trial의 강제 종료 복구를 구현했다. 코드 HEAD `e2e72a5`에서 645개 테스트, Ruff, diff 검사와 4조합 CI가 통과했다.
2. **통합:** PR #3은 열려 있고 PR #4는 PR #3 branch를 base로 하는 stacked PR이다. #3 검토·통합 후 #4를 기본 branch 기준으로 다시 확인해야 한다. 아직 통합 전이므로 제품 기본 경로에 반영된 것으로 표시하지 않는다.
3. **유지보수 QA 경로:** pattern analyzer는 read-only이며 PowerShell launcher는 현재 환경에서 재현되지 않았다. cross-platform runner, isolated worktree, 실행 fingerprint·전체 검사 결과, no-auto-merge를 수용 조건으로 둔다.
4. **다음 제품 구현:** 유지보수 QA 바탕을 정리한 뒤 BIS GLI flat ZIP 하나를 대상으로 정식 대용량 handoff를 만든다. 불변 event와 parent/child task, 명시적 `handed_off/resolved` 상태, 원본 hash·manifest, chunk/checkpoint/resume, output validation을 수용 조건으로 둔다. 단위·경제 의미는 문자열 값에서 추론하지 않는다. 실패·미지원 입력은 본 실행을 중단하고 원인을 `NOT_EXECUTED`로 남긴다.
5. **그다음:** 완료·검증된 artifact 계약에 연결되는 World Bank/BOJ CSV exporter를 구현한다. 기존 raw·manifest 확인, null 처리, provenance, 경로·덮어쓰기 방지가 선행 조건이다. XLSX는 별도 결정이다.
6. **후속 범위:** provider 확대, Windows resource-limited worker, 일반 자연어/다국가 탐색, 경제적 outlier·개정 의미 검증은 아직 미구현이다. 각각 공식 자료·명시적 수용 범위가 정해질 때 별도 작업으로 시작한다.
7. **병행 증거 대기:** TIC/BIS 감시는 유지하되 unchanged는 알림이나 Gate 승격으로 처리하지 않는다. 실제 개정 쌍과 자연 장애→같은 task/stage 재개가 생길 때만 Gate C 확대를 재판정한다. 인위적으로 장애를 만들거나 baseline을 바꾸지 않는다.

이번 계획에서 넘어가지 않은 것은 모두 같은 종류의 “실패”가 아니다. PR #3/#4는 통합 대기, BIS 정규화·CSV 전달·provider 확대는 미구현 기능, 자연 개정/장애는 아직 관측되지 않은 증거다. 과거 proxy 연결 문제는 설정을 바로잡은 뒤 성공 실측이 있어 해결된 이력으로 남긴다.

근거: [현행 Gate 재검증](GATE_REAUDIT_AFTER_ITERATION_16.md), [인계 목록](NON_API_DEFERRED_CATALOG.json),
[엔진 연결 설계](ENGINE_CONNECTIONS.md), [17회차 시험 계획](ITERATION_17_PLAN.md),
[CSV 후속 계획](CSV_EXPORT_FOLLOWUP_PLAN.md).

17회차의 합성 용량·BIS 원본 시험은 [보고서](ITERATION_17_REPORT.md)를 따른다. 시험 통과와 정식 처리 완료를 구분한다.
