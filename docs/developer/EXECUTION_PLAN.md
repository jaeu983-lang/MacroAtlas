# 실행안: Max 기준 전기관 API·수집 검증

**기준일:** 2026-10-25\
**모델 작업 크기 기준:** Max 추론 기준\
**현재 작업:** Iteration 30 Gate U의 7개 bounded live canary를 한 번 실행했으나 **NOT PASSED**다. process-only opt-in으로 7개 요청을 시도했고 재시도는 0회였다. FRED·BoE contract validation 통과, TIC 2개 needs review, Census 보안 검토, BLS 2개 transient 실패다. `.env`의 `MACROATLAS_NETWORK_ENABLED=false`는 유지했다. 세부는 [canary 상태](testing/LIVE_CANARY_REPORT.md), [회차 보고서](history/ITERATION_30_REPORT.md), [실행 명세](connectors/DATASET_CONTRACTS.md)를 참조한다. Gate U 통과 전에는 Iteration 31을 진행하지 않는다.

## 실행 준비 상태

제품 범위, 사용자·운영자·개발자 문서 구조, 공통/기관별 책임, 방법론 판정과 가공의 분리는 정리되어 있습니다. 사용자가 원하는 검증 범위는 BIS 한 곳이 아니라 전체 21개 기관·서비스입니다. Iteration 25에서 기존 9개 API client 응답의 파일 보존·재조회 계약을 offline으로 검증했습니다. Iteration 26은 World Bank와 SDMX의 API route/parser는 분리하되 HTTP execution mechanics를 공유하는 구조를 구현합니다. 이어지는 기관별 payload fixture·parser·live 결과는 별도 source gate입니다.

| 상태 축 | 확인 결과 | 검증상 의미 |
|---|---|---|
| 기관 registry | 21/21 프로필 | source별 결과 record 기반이 있음 |
| API 문서 | 15 documented / 6 unconfirmed / 0 not_offered | unconfirmed는 API가 없다는 뜻이 아님 |
| MacroAtlas API clients | World Bank·BEA·e-Stat·FRED·Census·BLS v1 제한 client 6개 + SDMX raw client 6개 | 12개 source archive 가능. 새 3곳은 synthetic JSON 검증·파일 read-back; World Bank 외 일반 workflow 연결은 별도 |
| 공식 파일 clients | TIC·BoE 2곳, 등록 CSV 3개 | synthetic 표 구조·원본/manifest/receipt/hash read-back; API 상태는 unconfirmed 유지 |
| 다음 경로 검증 | Iteration 30, API 4개·공식 파일 3개의 1회 live canary | 7회 시도·재시도 0회, 2개 contract 통과·2개 needs review·3개 실패. Gate U 미통과, 다음 iteration 보류 |
| 문서 확인 API의 다음 대상 | Iteration 31 IMF 상세 route/auth 후보, BOJ·Board crosswalk, 기존 clients workflow/live 준비 | API 문서가 있어도 dataset/series·인증·이용 범위별 gate를 따름. BLS2는 현재 제외 |
| live | World Bank 고정 경로 과거 partial; Iteration 30 canary 7개 시도 | FRED·BoE만 contract validation 통과. 나머지 5개는 needs review/실패이며 7/7 성공 증거가 아님 |
| 전체 offline suite | 815 passed, 1 skipped, 0 failed | Iteration 29 전체 suite; 전기관 live 성공 증거 아님 |

이 제약은 공통 readiness audit와 offline fixture 작업을 막지 않습니다. 실제 series, 인증된 live 요청, 비교·계산·파생 XLSX는 source별 문서·용도·이용 조건을 확정한 뒤 해당 gate에서 결정합니다.

## Luna Max 한 작업의 권장 크기

모델의 추론 설정은 파일 수로 정하지 않습니다. 한 작업이 읽고 바꾸는 **계약과 gate의 수**로 정합니다.

- 한 작업은 하나의 검토 가능한 결과와 하나의 통과 gate를 가진다.
- Max에서 한 작업은 공통 계약·동일 프로토콜 기준으로 관련 기관을 더 넓게 다룰 수 있다. 예: 같은 SDMX transport를 쓰는 source 묶음의 공통 query/discovery behavior.
- 범위가 넓어져도 성공 기준은 기관·provider·dataset/table별로 분리한다. 한 source의 통과가 나머지 source에 전파되지 않는다.
- 기관이 다른 API version, auth, identifier, dimensions, revisions 또는 legal/rate rules를 사용하면 같은 batch에서 개별 source sub-gate와 fixture를 둔다. 공통 기술로 묶는 것과 source를 동등하다고 주장하는 것을 구별한다.
- live test는 최소한의 대표 API/table 요청으로 source별 분리 실행한다. 한 live run에 21개 무제한 수집을 넣거나 source 별도 budget을 합산하지 않는다.
- 대체로 구현 파일·해당 fixture/test·짧은 문서를 함께 묶는다. 3–8개 파일은 planning heuristic일 뿐 상한은 아니다. 파일 수가 적어도 여러 계약·엔진을 건드리면 분리하고, 같은 계약을 검증하는 fixture 파일이 늘어나는 것은 허용한다.
- 2개 이상 엔진의 입출력, workflow 순서, 사용자 승인, 상태·오류·재개 계약이 바뀌면 엔진 작업과 오케스트레이터 통합 작업을 나눈다.
- 방법론 해석, 통계적 동등성, 분모·위험 산식, 사용자별 비밀/권한 정책은 Luna Max가 임의 결정하지 않는다. 근거와 선택지를 만들고 통계 담당자/사용자 확인 gate에서 멈춘다.
- 작업 지시에는 목표, 선행 문서, 허용 파일, 변경하지 않을 동작, 네트워크 범위, 성공 조건, 중단 조건, 보고 형식을 넣는다. 고정 토큰 수나 시간을 보장하지 않는다.

## 순서와 독립 작업 트랙

Track M은 현재 코드의 정확성·오류·메모리·시간을 다룹니다. Track C는 새 기관의 공식 문서·fixture·adapter를 준비합니다. 서로 독립된 offline 조사와 fixture 설계는 병행할 수 있지만 현재 공유 작업공간에서는 충돌 없는 변경 단위를 먼저 정하고, 각각 High iteration 하나씩 순서대로 검토합니다. live 요청은 공통 platform gate와 해당 기관의 source gate를 모두 통과한 뒤 따로 승인합니다.

| 순서 | 묶음 / High iteration 작업 단위 | 주 대상과 산출물 | 종료 gate |
|---:|---|---|---|
| 0 | 기획·저장소 상태 정합화 — 완료 | 독자별 docs 이동 반영, 실행안, 첫 작업의 범위·판정 기준 | 문서 링크·계획 간 경로 일치 확인 |
| 1 | **Iteration 21 — 통제 기준선 재현성, Gate L PASS** | 고정 World Bank fixture benchmark에 코드 fingerprint·환경 식별·sample-level 결과를 남기고 두 번 실행. 제품 engine은 변경하지 않음 | 완료. 상세 수치와 한계는 [Iteration 21 보고서](history/ITERATION_21_REPORT.md) 참조 |
| 2 | **Iteration 22 — BIS를 예시로 한 공식 근거 조사, Gate M PASS** | BIS `WS_TC` 2.0 후보의 정의·coverage·API 문서 근거 | 기관별 debt/credit 개념 설명용 예시. 전기관 테스트 범위를 제한하지 않음 |
| 3 | **Iteration 23 — 21개 전체 readiness audit + offline suite, Gate N PASS** | registry/status 비교, 625 passed/1 skipped, API-family batch 설계 | [Iteration 23 report](history/ITERATION_23_REPORT.md); live 호출 없음 |
| 4 | **Iteration 24 — SDMX raw-response adapter 6곳, Gate O PASS** | BIS, OECD, ECB, Eurostat, Bundesbank, INSEE 고정 route/client 및 mocked route tests | raw transport만 확인. payload fixture parsing/workflow/live는 미검증 |
| 5 | **Iteration 25 — 9개 API client 파일 보존·read-back, Gate P PASS** | World Bank·BEA·e-Stat·SDMX 6곳의 mock client result→file→hash verification; 666 passed/1 skipped | workflow/live 성공이 아님. 세부 [storage spec](connectors/API_RESPONSE_STORAGE.md)과 [report](history/ITERATION_25_REPORT.md) |
| 6 | **Iteration 26 — 공통 bounded HTTP 전송층과 API family wrapper, Gate Q PASS** | 세 기존 HTTP loop를 공통 primitive로 이동; World Bank·JSON·SDMX API 의미는 각각 보존; 685 passed/1 skipped | live 0. 이유와 계층 설계는 [HTTP transport](connectors/HTTP_TRANSPORT.md), [report](history/ITERATION_26_REPORT.md) |
| 7 | **Iteration 27 — API 키 발급 조사·입력 준비, Gate R PASS** | FRED/Census/BLS 키 이름과 safe settings 확장, 기존 BEA/e-Stat 보존, 21개 source 키 발급 안내 | 688 passed/1 skipped. [report](history/ITERATION_27_REPORT.md); live 키 검증 제외 |
| 8 | **Iteration 28 — FRED/Census/BLS v1, Gate S PASS** | 기관별 JSON client, 한도·오류·비밀값 검사, 파일 저장/read-back과 합성 결과 파일 | 763 passed/1 skipped, live 0. [report](history/ITERATION_28_REPORT.md) |
| 다음 후보 | **Iteration 29 후보 — IMF 상세 route/auth 문서 gate** | 공식 IMF Data API Swagger는 beta portal 로그인 후 탐색하도록 안내됨; route/auth specification 확보 가능성을 판단 | 공식 route/auth 근거 없이는 경로를 추정하지 않고 IMF client 구현을 보류 |
| 후속 REST | 나머지 개별 REST 및 범위 확장 | BOJ, Board crosswalk와 기존 FRED/Census/BLS v1의 workflow/live 준비 | source별 auth·ID·quota·정규화 범위를 독립 검증. BLS2는 현재 제외 |
| 9 | 기존 REST client의 범위 확장 | World Bank general Indicators API, BEA, e-Stat | fixed/limited client를 dataset discovery·metadata·series data 및 workflow 연결로 확장; 각 기관 독립 gate |
| 10 | shared API conformance harness 및 request/metadata gap audit | 공통 timeout/error/provenance/fixture/result record, 현재 workflow/contracts와 문서 WP 대조 | 기존 field 보존; 기관 차이를 공통 필드에 억지로 강제하지 않음 |
| 11 | source-specific payload fixtures와 parsers | 15개 documented API를 family별로 순차 처리 | 실제 schema/차원/단위/개정 fixture 없이는 source parsing pass 선언 금지 |
| 12 | all-source offline E2E | source-specific fixtures 준비된 전체 documented sources; 이후 unconfirmed source는 근거 확인 뒤 | discovery→metadata→ingest→storage→readback→recovery; fixture 없는 source는 `not_ready` |
| 13 | API 미확인 6개 표별 조사 batch | Treasury TIC, Bank of England, Japan MOF, PBOC, SAFE, China NBS | API 문서 미확인을 API 미제공으로 오인하지 않고 대상 표별 공식 경로를 확정 |
| 14 | bounded live canary / long test | live-ready 기관·dataset별 minimal official request; 이후 승인된 source에 seeded soak | source별 성공/실패/blocked 기록; rate/terms/credentials gate, 외부 부하 제한 |
| 15 | 변환·XLSX·오케스트레이터·확장 | 데이터 품질과 source gates가 충족된 뒤 기획된 별도 엔진 batch | 통계 담당자 승인, lineage, user consent, 필요할 때만 orchestration integration |

이 순서는 모든 행을 한 직렬 프로젝트로 묶지 않습니다. Track M의 계측/유지보수와 Track C의 source validation은 독립성이 있으면 별도로 진행할 수 있습니다. API family batch 안에서도 source별 gate는 순차 확인하며, 한 source 실패를 넘어 다음 shared transport 변경으로 진행하지 않습니다. 변환은 의미·분모·period 정책 승인 전, live soak는 source별 API/fixture/readiness 통과 전 시작하지 않습니다.

## 기존 5개 상위 묶음과 10개 work package 연결

| 상위 묶음 | 기존 work package | 실행안에서 좁히는 경계 |
|---|---|---|
| 1. 요청·탐색·metadata | WP 1–5 | 이미 있는 request questions·series discovery·21-source registry를 먼저 감사하고 빠진 field/fixture만 보완 |
| 2. 방법론 판정과 대표 사례 | WP 6 및 BIS를 포함하는 selected source cases | 기관 사례는 여러 기관에서 선택한다. BIS는 부채 질문 예시 하나이며 유일한 우선 source가 아님. 비교 계약은 source-specific evidence를 유지 |
| 3. 기관 connector·수집 품질 | WP 7–8 및 기관별 adapter | source 1곳·dataset 1개씩, API-first 및 기관 fixture·저장 확인; 공통 conformance 변화는 별도 검토 |
| 4. 가공·XLSX | WP 9 및 WP 10의 exporter 일부 | 계산 정의·분모 승인이 먼저. transformation operation과 XLSX writer를 분리 |
| 5. 오케스트레이터·회귀·랜덤/장기시험 | WP 10 통합 부분 | 앞선 engine gate가 통과하고 계약 연결이 변한 경우에만 통합; fixture random과 live soak 별도 |

## 기관별 실행 roster와 분기 순서

기관별 공식 접근 경로와 현재 evidence는 [기관 API 감사표](../operator/reference/INSTITUTION_API_AUDIT.md)와 [다기관 계획 §6.1](planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md)에서 관리합니다. 아래 구분은 API 문서가 발견됐다는 이유로 구현/실행됐다고 표시하지 않으며, 각 행의 실제 task는 기관별로 별도 gate를 둡니다.

| 단계 | 기관·서비스 | 실행 방식 |
|---|---|---|
| SDMX source batch | BIS, OECD, ECB, Eurostat, Bundesbank, INSEE — Iteration 24 raw client 구현; IMF는 상세 route/auth 대기 | 여섯 기관의 고정 root와 raw route를 mock으로 확인했다. 각 기관의 flow/DSD/codelist/dimension/revision/auth/official payload/live는 별도 검증 |
| Individual REST batch | World Bank, BEA, e-Stat, BOJ, BLS, Census, FRED/ALFRED, Board via FRED | 공통 REST test harness는 재사용한다. 기관/서비스 제공자·series ID·auth·rate limit·revision은 source별로 유지 |
| API 조사 batch | Treasury TIC, Bank of England, Japan MOF, PBOC, SAFE, China NBS | target table별 공식 API 명세와 이용 조건을 먼저 조사. `unconfirmed`를 API 미제공이나 scraping 허가로 바꾸지 않음 |
| 대표 통계·방법론 사례 | BIS를 포함한 수요 기반 source 후보 | 사용자가 실제 요청한 질문에서 여러 기관을 함께 후보화할 수 있다. BIS는 전기관 테스트 대상을 대표하지 않는 단일 사례 |
| 기존 live evidence | World Bank USA/WDI/GDP | 과거에 확인된 좁은 live 범위만 유지. 나머지 source·dataset으로 일반화하지 않음 |

Max batch는 프로토콜/공통 계약이 같은 source들을 묶어 작업량을 줄입니다. 단, 21개 각각의 table/series 선택, fixture, auth, exact live scope, 결과 상태는 독립 레코드로 남깁니다. 전체 검증 matrix와 통과 기준은 [전기관 검증 프로그램](testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)을 따릅니다. source-specific offline gate를 통과한 기관부터 최소 요청량의 bounded live canary를 실행하며, API 표가 미확인된 기관은 조사를 먼저 끝냅니다.

## Iteration 21 실행 카드 — 완료된 첫 Luna task

**대상:** Track M, benchmark/reproducibility 모듈.\
**목표:** Iteration 18과 20 수치 차이가 코드 변화인지 실행환경/측정 차이인지 판단할 수 있도록, 다음 기준선부터 코드와 실행환경을 식별 가능하게 하고 개별 표본을 보존한다. 기존 결과와 코드 fingerprint가 없으면 과거 run을 동등 조건으로 단정하지 않는다.

**허용 범위:** `scripts/benchmark_workflow_e2e.py`, Iteration 21 원시 결과, 성능·병목·비교·실행 보고서, 구현 계획, decision log. 기존 benchmark의 mock World Bank fixture만 사용한다.

**금지 범위:** `src/` 제품 엔진 동작 변경, cache/transaction/retry 수정, 실제 네트워크·API/key 접근, memory 값 추정, 수치로 된 성능 개선 주장, 21개 기관에 대한 일반화.

**검증:** benchmark를 독립 실행 2회, 각 30회 반복한다. 각 run에 Python/platform/CPU 식별정보, HEAD와 source/test/fixture/script fingerprint, sample별 timing·CPU·요청·바이트·정확성 invariant를 저장한다. 두 run 모두 30/30 완료, live HTTP 0, raw hash 일치, `[123.5, missing, 0]` 값/상태 보존이어야 한다. RSS/native SQLite memory는 이 작업에서 미계측으로 남긴다.

**결과:** Gate L 통과. 세부 표본·환경 fingerprint는 [회차 보고서](history/ITERATION_21_REPORT.md)와 [`run 1`](../../reports/iteration_21_baseline_run_1.json), [`run 2`](../../reports/iteration_21_baseline_run_2.json)에 보존했다. 과거 Iteration 18/20과 동등 조건 비교나 성능 개선율을 증명하지 않는다.

**사람 검토·중단:** benchmark assertion 실패, live request 발생, fingerprint 누락, 원자료 invariant 불일치 시 gate를 실패 처리하고 다음 작업으로 넘어가지 않는다. 다음 task부터는 별도 High iteration 범위와 task별 모델 지정이 필요하다.

## Iteration 22 실행 카드 — BIS 공식 근거 조사 (Gate M PASS)

**대상:** Track C, BIS 기관 profile / dataset evidence.\
**목표:** 부채 관련 구현 전에 BIS의 API 문서 계약과 `Credit to the non-financial sector` 데이터셋이 제공하는 개념·범위·dimension 선택의 근거를 고정한다.

**허용 범위:** 공식 BIS SDMX API v2 및 BIS Data Portal/FAQ/통계 문서 조사, `docs/developer/connectors/BIS.md`, 회차 보고서, 실행 계획·구현 계획·기관 API 감사 및 결정 로그의 상태 갱신.

**금지 범위:** API/웹 endpoint 호출, source adapter·fixture 작성, 키 사용, live 수집, 통계 개념이나 위험 공식 선택, 다른 기관 자료와 자동 결합.

**통과 gate:** API 문서 route template와 `BIS,WS_TC,2.0` 후보를 공식 근거로 적는다. borrower/lender 의미, coverage, frequency, units, valuation, consolidation/gross basis, revisions를 구분한다. 불명확한 DSD/codelist·국가 universe·vintage·사용자 목적은 unknown/open question으로 남긴다.

**결과:** Gate M 통과. [Iteration 22 보고서](history/ITERATION_22_REPORT.md)에 근거와 실행 제한을 기록했다. API endpoint 요청·fixture·adapter·live는 모두 실행하지 않았다. BIS는 부채 질문을 설명하는 예시이고 전체 검증 범위는 21개 기관·서비스다.

## Iteration 23 실행 카드 — 전기관 readiness audit와 offline suite (Gate N PASS)

**대상:** Track C, all-source test readiness.\
**목표:** Max reasoning 기준으로 21개 기관의 현행 API/adapter/fixture/live evidence를 한꺼번에 정리하되, institution/provider별 verdict를 독립 유지한다.

**허용 범위:** `source_registry.py`, 기존 institution implementation/test-result 문서, 21개 기관별 테스트 파일·fixture 목록의 read-only audit, 전체 offline pytest 실행, 실행안·기관 상태·전기관 검증 프로그램·회차 보고서·decision log 갱신.

**검증:** repository `.venv`와 현재 checkout `PYTHONPATH`를 고정해 full offline suite 실행. 결과는 625 passed, 1 skipped, 0 failed, exit 0이다. skip은 Windows symlink 기능 미지원이다. Registry는 21개 profile, API documented 15, unconfirmed 6을 확인한다.

**금지 범위:** 모든 source live API를 즉시 호출하기, `.env`/credential value 확인·출력, adapter 없는 기관 endpoint 임의 조합, World Bank 좁은 live 경로를 다른 기관에 일반화하기, code/fixture behavior 변경.

**결과:** Gate N 통과. [Iteration 23 report](history/ITERATION_23_REPORT.md)와 [전기관 검증 프로그램](testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 그 시점 coverage 및 protocol-family batch를 기록했다. 현재 live 일부 검증은 과거 World Bank 고정 경로뿐이다. 사용자 요청에 따라 다음 작업을 gap audit에서 documented SDMX API adapter 구현으로 우선 변경했다.

## Iteration 24 실행 카드 — 문서 확인 SDMX adapter 첫 batch (Gate O PASS)

**대상:** Track C, SDMX connector module.\
**목표:** 공식 API 문서에 route가 명시된 6개 기관에서 source-specific raw-response client를 제공한다.\
**허용 범위:** BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE의 고정 HTTPS root·route builder·GET transport·mock route tests·registry/connector/readiness 문서 갱신.\
**금지 범위:** API 문서 미확인 6곳, IMF의 로그인 뒤 Swagger route/auth 계약 추정, 임의 API 키/header, live network, provider payload parsing, workflow/storage 연결, 통계 의미 매핑.\
**검증:** 각 source가 고유 official path를 만들고 raw bytes를 보존한다. network opt-in, fixed host/path allowlist, redirect refusal, bounded response, timeout, unsafe path/query rejection을 mock transport로 확인한다. 전체 offline pytest suite를 실행한다.\
**결과:** Gate O PASS. 전체 pytest 651 passed, 1 skipped, 0 failed; 변경 파일 Ruff 통과; live 호출 0회. 상세 근거와 한계는 [Iteration 24 report](history/ITERATION_24_REPORT.md)에 기록했다.\
**중단:** route contract 불일치, credential-like query 누출, network-off bypass, redirect follow, partial/oversize payload accepted, regression 발생 시 gate를 실패 처리한다. IMF는 공식 API 미제공이 아니라 구현 상세문서가 해당 task에 없어 대기한 상태다.

## Iteration 25 실행 카드 — 9개 API 응답 파일 보존·read-back (Gate P)

**대상:** Track C, shared API response storage module.\
**목표:** 현재 client 9곳의 정상 mock/fixture 응답을 source별 raw archive file과 manifest로 저장하고, 검증 가능한 reference를 사용해 재조회한다.\
**허용 범위:** World Bank·BEA·e-Stat·BIS·OECD·ECB·Eurostat·Deutsche Bundesbank·INSEE response serialization, write-once storage, safe manifest, hash/length/path verification, source-wise offline tests, plan/status documentation.\
**금지 범위:** network/live requests, `.env`/credential inspection, endpoint changes, unsupported API clients, provider payload parsing, observation normalization, non-World-Bank workflow/orchestrator integration, XLSX.\
**검증:** 9개 source 각각 client response→file→read-back path; exact source identity and response representation; response hash and length; credential sentinel absent; existing World Bank error-body preservation; path escape, overwrite and tamper rejection; full offline suite plus Ruff on modified Python files.\
**Gate:** PASS. 9개 client response object를 source별 file archive로 저장하고 manifest/raw hash로 read-back 검증했다. 전체 offline pytest 666 passed, 1 skipped, 0 failed; 변경 Python files Ruff 통과. 실제 기관 요청은 0회. 공식 payload fixture, provider parser, live/auth 성공은 미검증이다.\
**Report:** [Iteration 25 report](history/ITERATION_25_REPORT.md), [archive contract](connectors/API_RESPONSE_STORAGE.md), and decision D-092. 다음 source 작업은 IMF 상세 route/auth 문서 gate다.

## Iteration 26 실행 카드 — 공통 HTTP transport와 API 계열 분리 재설계 (Gate Q)

**목표:** World Bank, BEA/e-Stat JSON, SDMX connectors의 중복 bounded HTTP GET 구현을 하나의 안전 primitive로 정리한다. World Bank와 SDMX가 다른 이유와 공유할 수 있는 책임을 [HTTP transport 설계](connectors/HTTP_TRANSPORT.md)에 명시한다.

**허용 범위:** `connectors/http_transport.py` 추가; `WorldBankTransport`, `JsonApiTransport`, `SdmxApiTransport` 내부에서 공통 primitive 사용; transport 공통 mock tests와 source wrapper contract regressions; architecture, World Bank, SDMX, implementation/execution plans, D-093 및 Iteration 26 report 갱신.

**금지 범위:** World Bank/SDMX route나 source identifiers를 하나로 합치기; status→source error mapping, credentials/redaction, parsers, response types, file storage나 workflow 계약을 바꾸기; 새 기관/API 추가; `.env` 조회; 외부 HTTP/live 호출; stage/commit/merge.

**통과 gate:** 1) 공통 helper가 network opt-in, HTTPS policy, redirect refusal, TLS default, timeout/elapsed bound, content-length 및 streamed-byte limit, raw entity bytes와 response metadata를 검증한다. 2) World Bank 1 MiB/모든 HTTP status body/Retry-After, JSON 1 MiB/redaction/status behavior, SDMX 8 MiB/raw bytes/provider status mapping의 기존 mock contracts가 통과한다. 3) 세 관련 파일군과 full offline suite, Ruff를 통과한다. 4) live HTTP 0회.

**중단:** credential/예외 detail 노출, provider route 변화, 부분·초과 body를 성공으로 채택, World Bank 오류 body 손실, HTTP status 의미가 family 밖으로 이동, 또는 pytest/Ruff 실패이면 Gate Q FAIL로 기록하고 이후 task를 시작하지 않는다.

**결과:** Gate Q **PASS**. 전체 offline pytest 685 passed, 1 skipped, 0 failed (52.20초); 변경 Python files Ruff 통과; live HTTP 0회. 세부는 [Iteration 26 report](history/ITERATION_26_REPORT.md)와 [D-093](history/DECISION_LOG.md)에 기록했다.

**후속:** Iteration 27은 키 조사, Iteration 28은 사용자 지시로 세 REST client 구현을 완료했다. IMF 상세 문서는 Iteration 29 후보이며 공통 전송 refactor가 IMF 근거를 대신하지 않는다.

## Iteration 28 실행 결과 — FRED/Census/BLS v1 (Gate S PASS)

FRED의 명시적 page·real-time·metadata·release/source, Census의 무키 metadata·keyed table, 무키 BLS v1 POST만 구현했다. BLS2 route와 registrationkey를 막고 공통 JSON POST body를 16 KiB로 제한했다. source contract tests 71 passed; 전체 offline 763 passed, 1 skipped; 수정 Python Ruff 통과. 예시 파일 3개는 synthetic이며 HTTP를 차단한 스크립트로 생성했다. 실제 키 조회·통계 API 요청·일반 workflow/정규화/XLSX는 제외했다. [보고서](history/ITERATION_28_REPORT.md), [FRED](connectors/FRED.md), [Census](connectors/CENSUS.md), [BLS v1](connectors/BLS.md)를 따른다.

## Iteration 27 실행 카드 — API 키 조사와 입력 준비 (Gate R)

**목표:** 사용자가 직접 발급받아 저장할 key 이름과 공식 절차를 정리한다. 이전 IMF 상세 route/auth 후보를 사용자 지시에 따라 이번 범위로 대체하며 IMF 조사 후속은 별도 후보로 유지한다.

**범위:** FRED/Census/BLS를 기존 BEA/e-Stat과 같은 strict env loader에 추가하고 `repr` 비노출·빈 값·환경변수 우선순위를 검증한다. `.env` 기존 byte prefix와 설정값을 유지하며 없는 이름만 빈 값으로 추가한다. 21개 source 발급 판단과 실제 구현 범위를 운영자 문서에 표시한다.

**검증:** 가짜 credential과 임시 `.env`를 사용하는 설정 회귀, 전체 offline suite, 변경 Python Ruff. 실제 `.env`는 append-only byte 비교와 Git 제외 상태만 확인하며 값은 출력하지 않는다. 공식 문서 브라우징과 실제 통계 API 호출은 따로 기록한다.

**종료:** 발급·등록과 이메일 활성화는 사용자가 수행한다. 실제 API 인증 검증은 후속 source adapter/live gate에서 한다. 이번 gate는 로컬 입력 준비와 문서 근거만 판정하며 source adapter/live 인증 성공을 주장하지 않는다. 결과는 Iteration 27 report와 D-094에 기록한다.

**결과:** Gate R PASS. 관련 회귀 36 passed/1 skipped; 전체 offline 688 passed/1 skipped/0 failed (56.61초); 변경 Python Ruff 통과. 기존 `.env` byte prefix 보존·Git 제외와 세 빈 항목 추가를 확인했다. 키 발급·통계 데이터 API 호출은 수행하지 않았다. [report](history/ITERATION_27_REPORT.md), [운영자 안내](../operator/API_KEYS.md).
