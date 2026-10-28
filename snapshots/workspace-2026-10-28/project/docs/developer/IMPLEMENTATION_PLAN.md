# 현재 구현·운영 계획

**기준일:** 2026-10-25
**상위 기준:** [PROJECT_PLAN.md](../../PROJECT_PLAN.md)
**반복 주기·승인 게이트:** [OPERATING_PLAN.md](../operator/OPERATING_PLAN.md)
**실행 task 크기·순서:** [Luna Max 전기관 검증 실행안](EXECUTION_PLAN.md)

이 문서는 과거 회차별 요구사항을 계속 덧붙이는 기록이 아니라, 지금 무엇을 유지하고 다음에 어떤 작업을 고를지 안내합니다. 01–28회차 구현·조사·검증은 각각의 회차 보고서와 변경 로그에 보존합니다.

## 현재 완료된 단계와 그 의미

- Iteration 01–14: 기본 계약·실행 이력·World Bank 제한 경로·탐색/fixture·오류/복구·피드백/지식/개선 승인 흐름의 해당 회차 범위를 보고서에 기록했습니다.
- Iteration 15–16: 21개 기관 API 상태 기반과 BEA/e-Stat의 보안된 로컬 설정·mock 클라이언트 범위를 기록했습니다. 실기관 인증과 workflow 전체 연결을 뜻하지 않습니다.
- Iteration 17–18: 통제 기준선과 사람이 읽는 Q&A 시나리오/fixture 계측 범위를 기록했습니다.
- Iteration 19: 기관 카탈로그와 실행 레지스트리 21개 정합성, 공식 API 상태 조사를 기록했습니다.
- Iteration 20: Track M/C 병렬 운영과 기관별 live gate를 정리했습니다. 고정 fixture 두 묶음은 통과했지만 run 간 편차가 과거 측정과 달라 공통 코드 최적화는 적용하지 않았습니다.
- Iteration 21: 고정 World Bank fixture E2E 30회 측정을 독립 실행 2회 재현하고 Git HEAD, code fingerprint, 실행환경 및 표본별 값을 보존했습니다. 두 run 모두 Gate L을 통과했습니다. 제품 엔진 최적화는 없고, 이전 Iteration 18/20과 동등 환경 비교도 주장하지 않습니다.
- Iteration 22: BIS SDMX API v2 문서와 `WS_TC` 2.0 통계 후보의 정의·범위·단위·통합 기준을 공식 문서로 조사해 Gate M을 통과했습니다. 이 범위는 조사만이며 adapter, fixture, live 호출은 없습니다.
- Iteration 23: BIS 한 곳이 아닌 전체 21개 기관·서비스를 대상으로 API/fixture/adapter/live readiness를 재분류하고 전체 offline suite를 실행했습니다. Gate N 통과: 625 passed, 1 skipped, 0 failed. 이는 전기관 live 통과를 뜻하지 않습니다.
- Iteration 24: 문서가 확인된 SDMX 제공자 중 IMF를 제외한 BIS·OECD·ECB·Eurostat·Bundesbank·INSEE 6곳에 고정 root 기반 raw-response client와 mock route 테스트를 추가했습니다. Gate O PASS: 전체 pytest 651 passed, 1 skipped, 0 failed; Ruff 통과. source payload fixture, workflow ingestion, live 검증은 아닙니다.
- Iteration 25: 현재 client가 있는 9개 API source의 응답 파일 보존과 hash-checked read-back을 공통 저장 계약으로 추가했습니다. World Bank 기존 경로를 유지하고, BEA/e-Stat 저장물은 정확한 HTTP raw가 아닌 redacted payload 재직렬화임을 기록합니다. Gate P PASS: 전체 offline pytest 666 passed, 1 skipped, 0 failed; 변경 Python files Ruff 통과. 9개 기관 mock round-trip은 [보고서](history/ITERATION_25_REPORT.md)에 기록했습니다. workflow 연결과 live 검증은 범위 밖입니다.
- Iteration 26: 반복 HTTP 실행을 공통 bounded GET primitive로 통합하고 World Bank·JSON·SDMX API 계약은 wrapper에 분리 유지했습니다. Gate Q PASS: 전체 offline pytest 685 passed, 1 skipped; Ruff 통과, live 요청 0회. 세부와 한계는 [회차 보고서](history/ITERATION_26_REPORT.md) 및 [HTTP transport 설계](connectors/HTTP_TRANSPORT.md)에 기록했습니다. source payload·auth·workflow·live 성공을 뜻하지 않습니다.

- Iteration 27: 추가 발급할 FRED/Census/BLS 키 이름과 strict Settings 지원을 준비하고, 기존 `.env` 내용을 보존하며 세 빈 항목을 추가했습니다. Gate R PASS: 전체 offline 688 passed, 1 skipped; Ruff 통과. [운영자 발급 안내](../operator/API_KEYS.md)와 [회차 보고서](history/ITERATION_27_REPORT.md)를 따릅니다. 세 기관 client와 실제 인증은 미검증입니다.

완료 근거는 [Iteration 01 보고서](history/ITERATION_01_REPORT.md)부터 각 최신 회차 보고서까지 보존합니다. 수치 기준선, 병목, 전후 비교, 회귀 결과도 별도 파일로 남깁니다.

- Iteration 28: FRED v1 page/metadata·Census metadata/table·BLS **무키 v1만** client를 추가하고 synthetic file round-trip을 검증했습니다. Gate S PASS: 전체 763 passed, 1 skipped; Ruff 통과; live 0회. 공통 archive 대상은 12개 source이며 3개 project-local 예시 파일과 [보고서](history/ITERATION_28_REPORT.md)를 보존했습니다. 일반 workflow·정규화·실기관 인증은 별도입니다.

## 지금의 개발·운영 큐

**현재 사용자 지시(D-101): Census·BLS는 보류하고 다른 기관 API에 집중한다.** 기존 Gate U는 NOT PASSED 이력으로 유지하며, 보류 두 기관을 재호출하지 않는다. Iteration 31에 이어 Iteration 32의 SDMX metadata 독립 source gate를 수행했다. 관측치 수집 전체나 자연어 workflow 성공으로 확대하지 않는다.

### Iteration 31 — BEA·e-Stat metadata API 검증 (Gate V)

- **공식 근거:** BEA GetDataSetList와 e-Stat v3.0 getStatsList. e-Stat은 영어 `lang=E`, `limit=1`만 요청한다.
- **구현:** HTTP 200과 source API 성공을 분리하는 기관별 envelope 검사, write-once archive/hash read-back, source별 report, synthetic fixture runner. Source API 오류도 성공으로 숨기지 않는다.
- **Gate V:** fixture에서 정상·오류·빈 목록·형식변화·키 redaction·저장/조회 계약을 통과하고 source별 live 상태를 정확히 기록한다. live sub-gate는 실제 metadata 계약과 저장/read-back을 모두 통과한 source만 성공이다. 코드 gate와 기관 live 성공을 분리한다.
- **live 예산:** BEA 1회, e-Stat 1회, 자동 retry 0. 네트워크 설정과 해당 key가 없으면 호출하지 않는다. Census·BLS·공식 파일 경로·추가 dataset/observation 요청은 이번 scope에 없다.
- **다음 큐:** SDMX 6곳의 provider payload/metadata 검증 → IMF·BOJ의 정확한 route/auth와 adapter → 기존 World Bank/FRED 범위 확장. 기관별 독립 회차로 수행하며 BEA/e-Stat 성공을 다른 기관에 전파하지 않는다.
- **실제 결과:** BEA 13개 dataset metadata, e-Stat 영어 요청 목록 1건이 HTTP 200·기관 계약·파일 저장/hash read-back을 통과했다. 합계 2회·retry 0, Census·BLS 요청 0이다. Source registry는 두 기관을 metadata-only PARTIAL로 표시한다. [회차 보고서](history/ITERATION_31_REPORT.md)에 fixture/live 증거와 검증 결과를 보존한다.
- **검증:** Engineering Gate V와 두 source의 metadata live sub-gate PASS. 전체 offline suite 884 passed, 1 skipped(66.66초), source별 합성 fixture와 실제 저장 응답의 recorded fixture를 구분한다. 다음 별도 task의 준비된 요청문은 [Iteration 32 handoff](planning/ITERATION_32_SDMX_HANDOFF.md)다.

### Iteration 32 — SDMX 6곳 metadata 계약 (Gate W)

- BIS·OECD·ECB·Eurostat·Bundesbank·INSEE의 현 raw client에 대해 공식 metadata route/ID·응답 계약·source fixture와 archive/read-back을 검증한다. 필요한 metadata 메서드는 공식 근거가 있는 범위만 추가한다.
- Engineering gate는 source별 fixture와 안전/저장 회귀다. live metadata sub-gate는 실제 source 계약·저장·hash 재조회가 통과한 기관만 성공이다. 준비되지 않은 source는 not_ready/not_run으로 기록한다.
- 실행 예산은 source당 1회, 총 6회, retry 0, 동시 요청 1개였다. BIS·OECD·Eurostat·Bundesbank는 최초 canary 통과, ECB는 최초 HTTP 200 응답의 파서 실패 후 같은 archive의 수정 후 오프라인 재검증 통과, INSEE는 HTTP 404 실패다. 최초 보고서는 수정하지 않았다.
- Census·BLS 보류, 기존 Gate U 실패 보존과 독립 source gate 원칙은 유지한다. 결과는 [Iteration 32 report](history/ITERATION_32_REPORT.md), 공식 route·인증/제한 근거는 [metadata audit](connectors/SDMX_METADATA_CANARY.md)를 따른다. IMF 역시 SDMX 기관이지만 기존 adapter가 없어 이번 6곳과 구분한다. INSEE 현재 route/ID 재조사와 IMF·BOJ 구현은 이후 별도 후보이며 Iteration 33은 시작하지 않았다.

### Iteration 33 — INSEE metadata 복구 (Gate X)

- 사용자 D-103은 33과 34의 순차 실행을 승인했다. 33의 engineering gate/보고서를 끝낸 뒤 34를 시작한다. Census/BLS 보류와 기존 Gate U·Iteration 32 실패 이력은 보존한다.
- 공식 INSEE user guide §IV에 명시된 작은 `codelist/FR1/CL_NATURE/1.0`을 별도 명시 선택으로 추가한다. 과거 IPC DSD 요청을 통과로 바꾸지 않는다. XML codelist의 ID·agency·version·이름·code/label·중복과 archive/hash를 검사한다.
- 합성 fixture·안전/저장 회귀를 통과한 뒤 새 예산에서 INSEE metadata 최대 1회, retry 0, concurrency 1로 호출한다. 문서/API 오류는 성공 처리하지 않는다. 전체 offline·Ruff·credential 비노출과 별도 보고서/feature commit으로 마무리한다.
- **완료:** Gate X engineering와 INSEE CL_NATURE 1.0 metadata sub-gate PASS. 단발 HTTP 200, 10,180 bytes와 archive/hash 확인. 기존 DSD 404는 실패로 보존한다. Live 전 전체 1,059 passed/1 skipped, recorded/registry 후 관련 250 passed와 Ruff PASS. [Iteration 33 report](history/ITERATION_33_REPORT.md).

### Iteration 34 — IMF 공식 API 준비 상태와 metadata (Gate Y)

- IMF 공식 API 페이지와 연결된 도구별 안내에서 정확한 root/route·ID/version·인증·이용/제한·표현 형식의 공개 근거를 먼저 확보한다. Swagger login과 데이터 API 인증을 혼동하지 않는다.
- 근거가 충분하면 source adapter·합성 fixture·계약·archive/read-back을 추가하고 offline gate 이후 IMF metadata 최대 1회, retry 0, concurrency 1로 검증한다. 근거/설정/접근이 부족하면 추정 endpoint·로그인 우회 없이 not_ready/not_run으로 명시하고 문서/readiness gate만 완료한다.
- 33의 source-only 실패는 다른 독립 IMF source를 전역 차단하지 않는다. shared engineering/safety gate 실패를 넘어가지는 않는다. 35·관측치 수집·main merge·push·배포는 제외한다.
- **실행 결과:** 공식 MATLAB 안내에서 public root, R 안내에서 IMF.STA/CPI를 확보하고 표준 SDMX 2.1 route를 조합했다. 무키 1회 요청은 HTTP 200, CPI dataflow version 5.0.0, 3,234 bytes, source 계약·archive/hash 통과다. 연결 DSD는 미조회로 남긴다. Live 전 전체 offline 1,084 passed/1 skipped 및 Ruff PASS. [공식 근거](connectors/IMF.md), [Iteration 34 report](history/ITERATION_34_REPORT.md).
- **최종 Gate Y:** 전체 offline 1,085 passed/1 skipped/0 failed, 변경 Python Ruff PASS. Engineering gate와 이 CPI metadata sub-gate만 PASS다. 33→34 예외는 완료 후 소진하며 다음 task는 다시 한 회차 원칙을 따른다.

모든 작업을 한 줄로 세워 순차 대기시키지 않습니다. Track M과 Track C는 독립된 offline 일을 병행하고, 외부 호출에 대해서만 공통 gate와 해당 기관 gate를 합칩니다.

### Track M — 공통 엔진 유지

1. 매주 사람의 피드백과 오류를 분류해 재현 가능한 사례부터 수정합니다.
2. 2주마다 고정 workload에서 peak RSS와 Python allocation, CPU/latency, API 요청량을 측정합니다.
3. 효과가 측정 변동보다 크고 정확성·복구 검증을 유지하는 경우에만 최적화를 적용합니다.
4. 확인할 병목이 없으면 코드는 바꾸지 않고 다음 측정 주기까지 기준선을 유지합니다.

### Track C — 기관별 API 확대

1. 사용자 수요를 기준으로 다음 기관과 구체적인 표/시계열을 선택합니다.
2. 공식 API 명세와 인증·쿼터·언어·개정·라이선스를 확인합니다.
3. 기관별 문서와 deterministic fixture를 만듭니다.
4. 기존 Python 엔진과 연결해 discovery/요청부터 저장·read-back·오류 복구까지 offline으로 검증합니다.
5. 해당 기관의 gate를 통과한 경우에만 공통 platform gate와 함께 live readiness를 검토합니다.

Track C의 목표는 21개 기관·서비스의 준비 상태와 선택 dataset/table별 검증 결과를 전부 남기는 것입니다. API 계열별 공통 transport와 parser를 묶어 효율화할 수 있지만 provider·agency·dataset 의미와 성공 상태는 source별로 판정합니다. API 문서 미확인 기관은 대상 표별로 먼저 조사하며 endpoint를 추정해 호출하지 않습니다. 한 source의 오류·인증 제한이 다른 source의 결과에 숨지 않도록 기관별 gate와 로그를 유지합니다.

### Iteration 21 — 기준선 재현성 보강 (Gate L PASS)

- **Track:** M, benchmark/reproducibility module.
- **범위:** `scripts/benchmark_workflow_e2e.py`와 고정 World Bank fixture, 두 회 독립 30회 측정, raw sample 저장, 실행환경과 코드 fingerprint 기록.
- **제외:** 제품 엔진 최적화, RSS 추정, 외부 API·credential 사용, 21개 기관 성능 일반화.
- **통과 gate:** 양쪽 run의 30회 완료, live HTTP 0, raw hash 검증, `123.5 / missing / 0` 관측 상태 유지, fingerprint·환경·개별 표본 보존.
- 결과와 제한은 [Iteration 21 보고서](history/ITERATION_21_REPORT.md)에 기록했습니다. 전체 pytest는 실행하지 않았습니다. 다음 공식 근거 조사 gate는 Iteration 22에서 완료했으며, 세부 근거는 아래에 기록했습니다.

### Iteration 22 — BIS 공식 API·통계 후보 조사 (Gate M PASS)

- **Track:** C, 기관 INT-02 공식 근거 조사.
- **범위:** BIS SDMX REST API v2의 문서화된 계약과 `Credit to the non-financial sector`의 후보 계열·정의·coverage·평가·빈도·단위·개정 근거를 정리합니다.
- **제외:** BIS adapter/fixture 추가, API 호출, 관측치 수집·저장·복구, “총부채” 또는 위험 가중치 산식의 확정.
- **통과 gate:** 공식 API 경로 템플릿과 데이터셋 후보가 식별되고, 문서상 사실과 미확인 항목을 분리하며, 전 세계 coverage·부채의 의미·위험 가중치를 임의로 확정하지 않습니다.
- **결과:** Gate M 통과. 세부 근거·한계는 [BIS 프로필](connectors/BIS.md)과 [Iteration 22 보고서](history/ITERATION_22_REPORT.md)에 기록했습니다. BIS는 다기관 검증에서 사용한 예시 기관이며 전기관 live 검증의 범위를 제한하지 않습니다.

### Iteration 23 — 전기관 검증 준비 상태와 offline suite (Gate N PASS)

- **Track:** C, 전체 기관 검증 프로그램 및 readiness.
- **범위:** 21개 registry profile과 구현·fixture·live 증거를 대조하고 Max 기준으로 API family batch를 설계합니다. 전체 offline pytest suite를 현재 workspace source에 대해 실행합니다.
- **결과:** [Iteration 23 보고서](history/ITERATION_23_REPORT.md)에 625 passed, 1 skipped, 0 failed를 기록했습니다. live 호출은 없었습니다. 상세 실행 조건과 21개별 상태는 [전기관 검증 프로그램](testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 있습니다.
- **한계:** 전체 offline suite 통과는 각 기관 API 통과가 아닙니다. 현재 live 일부 근거는 World Bank USA/WDI/GDP 한 경로뿐입니다.

### Iteration 24 — 문서 확인 SDMX API 첫 adapter batch (Gate O PASS)

- **Track:** C, source connector module.
- **범위:** BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE의 공식 문서 route에 맞춘 raw-response GET client, host/path allowlist, byte/time bounds, source별 mocked route tests와 상태 문서.
- **제외:** API 문서 미확인 6곳, IMF Data API의 beta portal 로그인 뒤 상세 route/auth 계약, API 키/인증, provider payload fixture 파싱, workflow·저장 연결, live network 요청.
- **통과 gate:** source별 route builder가 mock session에서 공식 route 형태를 만들고, raw response bytes를 보존하며, unsafe host/redirect, credential-like query field, 네트워크 미허용, 초과 크기를 거부한다. full offline suite가 통과한다.
- **결과:** Gate O PASS. 전체 offline pytest는 651 passed, 1 skipped, 0 failed입니다. skip은 기존 Windows symlink 지원 조건입니다. 변경 파일과 독립 scope는 [Iteration 24 보고서](history/ITERATION_24_REPORT.md), [SDMX adapter 명세](connectors/SDMX_FAMILY.md), [전기관 검증 프로그램](testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 기록했습니다. 이 결과는 endpoint 도달성·응답 parsing·통계 정확성·live 수집을 통과시키지 않습니다.

### Iteration 25 — 9개 API source 파일 보존·재조회 (Gate P)

- **Track:** C, API response storage module.
- **범위:** World Bank·BEA·e-Stat·BIS·OECD·ECB·Eurostat·Bundesbank·INSEE의 현재 response types를 source ID/기관·요청 정보·UTC 시각·상태·표현 형식·byte count·SHA-256가 든 별도 파일과 manifest로 저장하고, 경로·manifest/raw hash를 확인해 다시 읽습니다. World Bank의 기존 raw 경로와 실패 응답 보존 계약은 유지합니다.
- **포함:** BEA/e-Stat은 transport에서 redaction된 JSON payload를 canonical UTF-8로 저장하고 실제 원 HTTP bytes와 구별합니다. source별 mocked client 응답→파일→검증 read-back을 테스트합니다.
- **제외:** IMF 및 나머지 미구현 API adapter, source payload parsing/metadata normalization, 8개 비-World-Bank workflow 연결, normalized observation DB 적재, API key 확인, live 호출.
- **Gate P:** 통과. 9개 source의 올바른 기관 폴더 저장, 출처·시간·상태·표현·hash/길이 metadata 보존, 재조회, 비밀값 부재, path traversal·덮어쓰기·raw/manifest 변조 거부를 mock/fixture로 확인했습니다. 전체 offline pytest 666 passed, 1 skipped, 0 failed; 변경 Python files Ruff 통과입니다.
- **보고:** 구현 결과는 [API response file archive](connectors/API_RESPONSE_STORAGE.md), [Iteration 25 report](history/ITERATION_25_REPORT.md), [D-092](history/DECISION_LOG.md)에 기록했습니다. SDMX 공통 transport·provider adapter·source validation의 독립 경계와 기관별 미검증 상태는 [SDMX 명세](connectors/SDMX_FAMILY.md)에서 구분합니다. API 호출 성공은 fixture/mock 검증으로 간주하지 않으며 live evidence는 별도입니다.

### Iteration 26 — 공통 bounded HTTP 전송층과 source wrapper 재설계 (Gate Q)

- **Track:** C, shared connector transport module. 이 작업은 client가 있는 World Bank·BEA/e-Stat JSON·SDMX 6개 source의 반복 HTTP plumbing만 다룹니다.
- **목표:** HTTPS GET session/security/timeout/elapsed/response-byte streaming을 `connectors/http_transport.py`로 한 번 구현합니다. 기존 `WorldBankTransport`, `JsonApiTransport`, `SdmxApiTransport` 공개 경계와 기관별 route, status 분류, credential, parser, response model은 유지합니다.
- **설계 근거:** World Bank WDI JSON은 고정 country/indicator/query와 page-envelope 의미가 있고, SDMX는 provider마다 data/structure route·차원 key·payload 형식이 다릅니다. API request/response 계약은 분리하고 반복 HTTP 실행만 공유합니다. [HTTP transport 설계](connectors/HTTP_TRANSPORT.md)와 [아키텍처](ARCHITECTURE.md)에 이 경계를 기록합니다.
- **허용 범위:** 공통 transport 모듈 및 mock 단위 테스트, 세 wrapper의 내부 위임, 관련 회귀 테스트, HTTP/WB/SDMX 문서, execution/implementation plan, D-093 및 보고서.
- **제외:** endpoint/provider route 변경, 새로운 기관 지원, response schema parsing 변경, API key 정책 변경, workflow/storage/계산 변경, live/API network.
- **통과 gate:** 각 wrapper의 기존 route·credential·error/status·raw body·Retry-After·1/8 MiB bounds를 유지하는 mock 회귀 test, 공통 network-off/unsafe URL/redirect/TLS/transport failure/timeout/byte/content-length guard test, 전체 offline pytest와 수정 Python Ruff 통과. live 요청 0회.
- **중단 조건:** HTTP status/body 의미 변경, credential 또는 예외 세부 누출, 기존 source route 변경, 전체 suite 실패 시 gate를 실패 처리하고 다음 작업으로 넘어가지 않습니다.
- **결과:** Gate Q **PASS**. 전체 offline pytest 685 passed, 1 skipped, 0 failed; 변경 Python files Ruff 통과; live HTTP 0회. [Iteration 26 report](history/ITERATION_26_REPORT.md), [HTTP transport design](connectors/HTTP_TRANSPORT.md), [D-093](history/DECISION_LOG.md)에 보존합니다.

### Iteration 27 — API 자격 증명 조사와 입력 준비 (Gate R)

- **사용자 지시:** 21개 source의 키 발급 필요성을 조사하고, 사용자가 직접 넣을 수 있도록 `.env`에 확인된 이름을 추가합니다. 이전 IMF route/auth 후보를 이 요청으로 대체합니다.
- **범위:** 공식 문서 기반 발급·등록·갱신 조사, 운영자 키 안내, 기존 BEA/e-Stat 항목 보존과 FRED/Census/BLS 빈 항목 추가, strict `.env` loader 및 repr 비노출 설정 확장과 관련 회귀 검사.
- **제외:** 회원 가입·키 발급 대행, 기존 비밀값 교체/출력, 실제 데이터 API·키 유효성 검사, 미구현 source client 추가. IMF/INSEE의 다른 서비스 인증 방식을 추정해 변수로 추가하지 않습니다.
- **통과 gate:** 확인된 5개 변수의 빈 값/입력값/환경변수 우선순위/오류·repr 비노출 검증, 기존 `.env` prefix의 byte 보존 및 이름만 append 확인, full offline suite와 변경 Python Ruff 통과. 문서 조회와 live 데이터 API 증거를 구분합니다.
- **결과:** Gate R **PASS**. 설정·registry 관련 36 passed, 1 skipped; 전체 offline 688 passed, 1 skipped, 0 failed; 변경 Python Ruff 통과. `.env`는 기존 bytes 보존·세 이름 빈 값 추가를 확인했고 실제 비밀값은 출력하지 않았습니다. [회차 보고서](history/ITERATION_27_REPORT.md)와 D-094에 보존합니다. IMF 상세 route/auth 조사는 다음 별도 iteration 후보입니다.

### Iteration 28 — FRED·Census·BLS v1 clients와 파일 저장 (Gate S)

- **사용자 지시:** FRED/Census adapter와 BLS **1.0만** 구현하고 파일 저장·read-back까지 시험합니다. BLS v2와 키 사용은 제외합니다. 기존 IMF 상세 문서 후보는 후속으로 이동합니다.
- **공식 근거:** FRED v1 series/search/observations 및 release/sources, Census Data API guide, BLS v1 signature/Python 공식 예시. BLS의 기간 지정 다중 series 조회는 JSON POST이며 공통 bounded HTTP에 명시적 크기 제한 POST를 추가합니다.
- **범위:** source별 검증·입력 제한·safe JSON 전송, FRED/Census 키 가림, 무키 BLS1, 공통 archive의 세 source 등록과 HTTP method·요청 조건 보존, 합성 source fixture와 client→파일→hash/read-back tests, 사람이 볼 offline 결과 파일과 문서 상태 갱신.
- **통과 gate:** 기관별 source sub-gate(정상·결측/0·잘못된 응답·인증/HTTP/timeout·한도·비밀값 비노출·저장/재조회), 기존 HTTP GET/보존 동작 회귀, 전체 offline pytest·변경 Python Ruff 통과. FRED 페이지 결과는 전체 수집으로 표시하지 않고 원기관과 API provider를 구분합니다.
- **제외:** 실제 `.env`/비밀값 읽기·수정, live 데이터 요청·키 검증, 자동 pagination/재시도/스케줄러, 가공·정규화 DB/workflow/XLSX, BLS2. 단위·주기·원기관은 원 metadata 없이 추정하지 않습니다.
- **중단:** source identity/입력 범위 불일치, BLS v2/key 사용, credential 유출, 부분 BLS 결과·실패 envelope를 성공으로 채택, 회귀 실패 시 Gate S를 실패 처리하고 다음 iteration을 시작하지 않습니다.
- **결과:** Gate S PASS. 기관별 source 검증 71 passed; 전체 offline 763 passed, 1 skipped, 0 failed (70.76초); 변경 Python Ruff 통과. 실제 프로젝트 raw 파일 3개와 [합성 실행 보고서](../../reports/iteration_28_offline_1ed43019cf344e5d86c64d5d79105a79.json)를 생성·read-back 검증했습니다. [Iteration 28 report](history/ITERATION_28_REPORT.md), D-095 참조. BLS2·실제 key/live 요청·일반 workflow는 제외했습니다.

### Iteration 29 — API·공식 파일의 데이터셋별 실행 명세 (Gate T)

- **사용자 지시:** API와 비API 경로를 모두 데이터셋별로 준비합니다. 하나의 공통 dataset profile/실행·검증·저장 계약으로 묶고, 기관별 request/표 특성은 adapter와 validator에 둡니다. 이전 IMF 문서 후보는 후속으로 이동합니다.
- **범위:** version/hash가 있는 registry, 고정 source 선택·허용 요청, 기존 FRED GDP/Census ACS/BLS v1 두 series의 API binding 4개, Treasury TIC 역사 MFH·2023-01 Table 3D 및 BoE Bank Rate CSV file binding 3개, 공통 bounded GET 재사용, 원본/요청/프로필/검증 결과 저장·검증 read-back, 기관별 합성 fixture·오류 시험·예시 파일.
- **공식 근거:** 기존 REST 문서, Treasury의 공식 CSV 링크와 확인된 canonical ticdata host·표 구조, BoE help의 CSVF=TN·기간·시리즈 query와 IUDBEDR 식별 근거. CSV 표 구조를 웹으로 열람한 것은 repository live ingestion과 구별합니다.
- **제외:** 전체 21개 기관 완료 주장, 미확인 file endpoint 추정, 실제 `.env`/키 확인, repository live 수집, 자동 API→파일 fallback·의미 매핑·보간·계산·일반 대화 workflow. BLS는 계속 무키 v1만 사용합니다. 미구현 데이터셋은 등록·검증된 범위로 오인하지 않습니다.
- **통과 gate:** 7개 binding별 요청→검증→원본·manifest·profile receipt 저장→hash read-back, fixed selection/버전/비밀값·범위 검사, TIC 서로 다른 CSV 형식과 BoE 날짜/결측 계약, 실패·변조·redirect·네트워크 거부·source 변경 시 중단, 전체 offline suite·변경 Python Ruff.
- **원칙:** Parser 선택은 등록된 코드 ID만 사용합니다. API·파일 raw와 검증 결과를 별도로 보존하고 validation 실패를 수집 성공으로 바꾸지 않습니다. 공통 코어에는 기관명 조건문을 퍼뜨리지 않습니다.
- **결과:** Gate T PASS. 전체 offline 815 passed, 1 skipped, 0 failed (76.67초). 7개 synthetic dataset artifact를 원본·manifest·검증 receipt로 저장하고 hash read-back했습니다. BLS2·실제 키·live 통계 요청은 제외했습니다. [회차 보고서](history/ITERATION_29_REPORT.md) 및 [데이터셋 계약](connectors/DATASET_CONTRACTS.md) 참조.

### Iteration 30 — 7개 dataset bounded live canary (Gate U)

- **사용자 지시:** 합성 데이터셋 검사 다음에 가능한 실제 API·공식 파일 경로를 최대한 확인한다. 이번 작업은 등록된 API 4개와 CSV 3개, 각 1회만 대상으로 한다.
- **요청 범위:** FRED GDP 최대 8개 observation(2024–2025), Census ACS 2023 California 한 state row, BLS v1 두 series 각각 2024 한 해(총 POST 2회), TIC 등록 CSV 2개, BoE IUDBEDR 10일. 자동 재시도·pagination·v2/API fallback 금지. 완료 raw는 hash 검증 receipt와 함께 저장한다.
- **공식 이용 근거:** FRED key·rate/third-party terms, Census query budget, BLS unauthenticated v1 제한, Treasury TIC 배포/coverage 한계, BoE Database 재사용 조건을 [canary guide](connectors/DATASET_CONTRACTS.md)에 기록한다.
- **선행 조건:** `.env` 또는 명시 process setting `MACROATLAS_NETWORK_ENABLED=true`; FRED/Census user keys는 기존 local settings에서만 읽는다. live helper는 false면 네트워크 호출 없이 7개 `not_run_network_disabled` 결과만 쓴다. 자동으로 user setting을 켜지 않는다. BLS v1은 키를 쓰지 않는다.
- **Gate U 성공 기준:** source별 실제 요청 수·HTTP outcome·선택 identity·contract validator·raw 저장·hash read-back 결과를 구별. 7곳 전체가 성공할 때만 전체 통과. 일부 실패는 부분 결과로 기록하고 재시도하지 않는다. 초과호출·credential 출력·경로 이탈·응답 크기 초과·source mismatch 시 중단한다.
- **이력 판정:** Gate U는 **PARTIAL / NOT PASSED**다. 마지막 전체 canary는 4/7 통과였고, 후속 진단은 Census invalid-key redirect와 BLS 503 HTML이었다. 이 실패 이력은 유지한다. 이후 사용자 지시 D-101로 두 source를 보류하고 다른 기관은 독립 gate에서 진행한다. Census·BLS 자체의 재개는 사용자 지시와 [진단 조건](testing/CENSUS_BLS_GATE_U_DIAGNOSIS.md)을 따른다.
- **재현·진단 보강:** TIC Table 3D의 인식된 각주 경계를 합성 fixture로 검증한다. canary 실패 보고서는 앞으로 고정 `failure_reason` 및 있으면 HTTP status만 기록하고 메시지·응답 본문·비밀값은 제외한다. 원래 canary는 소급 수정하지 않는다.
- **검증 결과:** 최신 Census 오류 분류와 등록 profile 선택 실행은 관련 테스트 **146 passed, 1 skipped**, 전체 offline **846 passed, 1 skipped, 0 failed (72.70초)**, 변경 Python Ruff 통과다. Skip은 Windows symlink 생성 미지원이다. 기본 사용자 pytest Temp 접근 거부를 피하도록 저장소의 고유 `--basetemp`를 사용했다. 새 코드의 source별 추가 live 검증과 Gate U 전체 성공은 미검증이다. 이전 전체 canary JSON은 [후속 실행](../../reports/iteration_30_live_canary_02afcdd6b6254239adf01af824df4e64.json)에 보존한다.

## 다음 네 주 권장 일정

- D-101 이후: BEA/e-Stat metadata 검증을 Iteration 31로 수행했고, 다음은 기존 SDMX 6곳 payload/metadata다. IMF 상세 route/auth 조사는 이후 독립 후보로 유지하며 기존 client나 다른 기관 metadata 성공을 IMF 검증으로 간주하지 않습니다. Census·BLS는 보류 상태를 유지합니다.
- 2–3주차: FRED/Board, BOJ, World Bank generic path, BEA, e-Stat을 API family별 개별 작업으로 연결합니다. BLS·Census는 사용자 재개 전 보류합니다. 같은 batch 안에서도 제공자·기관·인증·응답 schema는 독립 판정합니다.
- 이후: SDMX와 REST clients에 source payload fixture/parser, workflow/storage/read-back, recovery gates를 추가합니다. API 미확인 6개 기관은 별도로 표별 공식 접근 경로를 조사하고, source-specific offline gate와 live readiness를 통과한 기관만 bounded live canary 후보로 둡니다. 일정은 기관 응답·인증·허용 조건에 따라 바뀔 수 있습니다.

각 source 작업의 예상 기간은 문서가 명확한 단순 API가 1–3 작업일, SDMX·인증·revision·대용량 등 복잡한 경우 3–7일 이상입니다. 이는 계획 추정이며 작업량을 줄이기 위해 gate를 생략하지 않습니다.

## 변경 시작 전 확인

- AGENTS.md, GUIDELINES.md, PROJECT_PLAN.md, 해당 source 문서, 관련 테스트와 최근 보고서를 읽습니다.
- 현재 git status와 변경 파일을 확인하고 기존 사용자 작업을 보존합니다.
- 한 코드 변경 작업은 한 회차/한 gate로 한정합니다. Track M과 C를 동시에 코드 변경하는 작업은 계약·충돌·검토 책임을 먼저 분리합니다.
- API 문서 조사, fixture 검증, live API 응답, live ingestion은 각각 따로 기록합니다.
- 키를 출력하지 않고 외부 요청은 명시적으로 준비된 승인된 단계에서만 수행합니다.
- 코드를 바꿨으면 해당 테스트와 가능한 전체 local suite를 실행합니다. 실패 gate를 넘어가지 않습니다.
- 회차별 보고서와 결정/성능 로그는 보존하며, 완료 기록을 현재 안내 문서에 복사해 누적하지 않습니다.

## 추적 문서

- 다기관 요청·방법론 비교·변환·XLSX 기획과 5개 상위 묶음/10개 세부 작업은 [다기관 실행 기획](planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md)에 있고, Luna Max 기준 API 계열별 실행 묶음과 전기관 판정 gate는 [실행안](EXECUTION_PLAN.md) 및 [검증 프로그램](testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 있다. 방법론 엔진은 작업명이며 전 세계 모집단, 분모, 위험 산식, 파생 XLSX 계약은 해당 단계 전 사용자 검토가 필요하다. 사용자·운영자·개발자 문서는 각각 `docs/user/`, `docs/operator/`, `docs/developer/`로 이동했다. 상세 설계 및 결정 기록은 [아키텍처](ARCHITECTURE.md)와 [결정 로그](history/DECISION_LOG.md) D-082–D-090을 따른다.
- 현재 기능 경계: [ARCHITECTURE.md](ARCHITECTURE.md), [USER_GUIDE.md](../user/USER_GUIDE.md)
- 기관/공식 API 상태: [INSTITUTION_CATALOG.md](../operator/reference/INSTITUTION_CATALOG.md), [INSTITUTION_API_AUDIT.md](../operator/reference/INSTITUTION_API_AUDIT.md)
- 운영 cadence와 live gate: [OPERATING_PLAN.md](../operator/OPERATING_PLAN.md)
- 성능 기준과 절차: [PERFORMANCE_OPTIMIZATION_PLAN.md](performance/PERFORMANCE_OPTIMIZATION_PLAN.md)
- 피드백/지식 범위: [KNOWLEDGE_ENGINE_PLAN.md](engines/KNOWLEDGE_ENGINE_PLAN.md)
- 증거: ITERATION_*_REPORT.md, DECISION_LOG.md, OPTIMIZATION_LOG.md, BASELINE_REPORT.md, BOTTLENECK_ANALYSIS.md, BENCHMARK_COMPARISON.md, REGRESSION_REPORT.md와 reports/ 측정 원시 파일.
