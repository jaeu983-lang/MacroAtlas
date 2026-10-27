Warning: truncated output (original token count: 12210)
Total output lines: 478

# MacroAtlas 현재 구현 상태와 Gate 증거

> 2026-10-27 갱신: PR #1–#28이 병합됐으며 최신 merge HEAD는 `bb94bba38711002adb7fb4948ef5643c3d54b628`다. PR #23–#26에서 evidence domain, provider scope, BLS metadata 한계를 정리했고 PR #28은 malformed task plan의 CSV export 차단을 추가했다. device-code 재인증 뒤 Linux updater candidate QA/PR handoff는 성공했지만 supervised Windows pilot은 남아 있다. Gate C 자연 증거와 updater pilot의 범위는 각각 [Gate C 증거표](GATE_C_REVIEW_2026_10_26.md), [27회차 pilot 보고서](ITERATION_27_PILOT_REPORT.md), [미해결 항목](UNRESOLVED_ITEMS.md)를 따른다.

> **이 문서는 현재 구현·게이트·검증 증거의 요약 기준이다.** 다음 작업 순서는
> [제품 로드맵](ROADMAP_2026_10_26.md), 요구사항은 [`PROJECT_PLAN.md`](../PROJECT_PLAN.md),
> 역사 보고서는 당시의 증거, [`DECISION_LOG.md`](DECISION_LOG.md)는 설계 선택의 이력을 담는다.
> 기본 규칙은 한 task에 한 회차이며, 실패하거나 관측되지 않은 증거를 통과로 취급하지 않는다.

## 현재 상태 — 2026-10-27

19회차 BIS flat 대용량 production handoff는 PR #6으로 통합되어 보존 원본 1건에서 실제 실행됐다. 이 실행은
정해진 BIS flat scope의 구조 보존 materialization이며 Gate C natural evidence나 일반 기관·파일 지원 확대가
아니다. 구현 계약과 당시 실측은 [19회차 기획안](ITERATION_19_PLAN.md), [19회차 보고서](ITERATION_19_REPORT.md)를 따른다.

20회차에서는 완료·quality-passed인 World Bank USA GDP와 BOJ FM08/FXERD01 task만 CSV로 전달하는 read-only
exporter를 구현했다. 저장 raw/manifest를 검증하고 재파싱하며, UTF-8 CSV와 provenance sidecar를 새 경로에
생성한다. 보존된 task 0f968a54… (World Bank, 3 rows)와 96f82a80… (BOJ, 30 rows·11 null)을 local export해
hash와 DB 불변성을 확인했다. PR #9의 merge commit은 `7723afe`이며 Ubuntu/Windows × Python 3.11/3.12 CI가
통과했다. 전체 666 tests, Ruff, diff check도 통과했다. [20회차 보고서](ITERATION_20_REPORT.md)를 따른다.

후속 내부 dry run은 같은 보존 task로 status→CSV export 경로를 다시 따라가 산출물 hash 일치와 상태 경고
표시를 확인했다. 작성자에 의한 오프라인 검토여서 목표 사용자 연구로 계산하지 않는다. 실제 참여자 확인 전
다음 사용자 인터페이스·provider 범위를 정하지 않는다. [검토 기록](USER_WORKFLOW_DRY_RUN_2026_10_26.md).

22회차에서는 비API qualification과 BIS flat production/resume의 실행 전 시간 예측을 구현하고 PR #10으로 통합했다.
통합 HEAD는 `1a00c18`이다. 최대 256 KiB의
bounded profile과 엔진별 성공 task wall-time history로 범위·신뢰도·shadow model을 계산하고, 무실행 preview를
제공한다. 전체 **675개 테스트**, Ruff, diff 검사가 통과했다. 현지 catalog에서 확인한 qualification 기록은 15건,
production 기록은 1건이고 새 paired forecast는 0건이므로 초기 보정 상태는 낮은 신뢰도다. 원격 Ubuntu/Windows ×
Python 3.11/3.12 checks도 8/8 성공했다. 실제 read-only preview와 한계는 [22회차 보고서](ITERATION_22_REPORT.md)에 둔다.

다음은 실제 분석가 1–2명의 저장 결과→CSV 관찰이다. 23회차 세션 절차와 관찰표는 준비했지만 참가자가 없어 세션을
실행하지 않았다. 사용성 통과나 다음 provider/UI 범위를 아직 선언하지 않는다.

17회차 [대용량 격리 시험](ITERATION_17_REPORT.md)을 구현했다. 정식 정규화는 미실행이며,
애매한 후보도 명시 시험 후 미실행/시험 통과를 기록한다. 19개 합성 용량 사례와 BIS 보존 원본을 확인했다.
후속 검토에서 강제 종료 시 orphan worker·scratch 복구 공백을 확인해 17회차 branch에서 보완했다.
코드 commit `e2e72a5`에서 전체 645개 테스트, Ruff, diff 검사가 통과했고 해당 HEAD CI run
[`40359478210`](https://github.com/jaeu983-lang/MacroAtlas/actions/runs/40359478210)에서 Ubuntu/Windows × Python 3.11/3.12 네 조합이 모두 성공했다.
이 검증은 해당 코드 HEAD에 대한 증거다. 이후 문서 전용 commit을 포함한 현재 branch HEAD의 CI 상태와
열린 PR의 base/head는 작업 시 원격에서 다시 확인한다.

엔진의 실제 진입점·전달 계약·대용량 후속 연결은 [엔진 연결 설계](ENGINE_CONNECTIONS.md)를 따른다.

16회차 이후 현재 코드·실측으로 Gate A–E를 [재검증](GATE_REAUDIT_AFTER_ITERATION_16.md)했다.
BIS flat은 현재 셀 상한에 따라 정상 인계되어 parser 결함 목록에서 제외한다.
과거 회차의 실패 상태를 현행 판정에 그대로 적용하지 않는다.

14회차 로드맵은 완료됐다. Gate A와 D는 통과, Gate B/C는 제한 범위 통과, Gate E는 제한 범위 로컬
v1 검토 통과다. 통합 PR #1은 `9986472f983a70aacc86209ee54883cca558c5e9`로 기본 브랜치에 병합됐고,
병합 checkout에서 592개 테스트, Ruff, `git diff --check`, World Bank live 검증을 다시 통과했다.
후속 네 갈래는 별도 브랜치의 [15회차 보고서](ITERATION_15_REPORT.md)에 기록한다.

Gate C의 D-067 제한 범위는 바뀌지 않았다. 당시 exact-scope live watch에서 TIC와 BIS 원본은 모두
`unchanged`였으며 그 실행 중 natural provider failure는 발생하지 않았다. 통제 변경과 simulated 503 재개는
자동 시험으로 확인했다. 이후 World Bank API에서 natural failure→persist→same-task resume은 확인됐지만
TIC/BIS source revision과 해당 file-watch scope의 retryable failure→resume은 별도 증거 대기다.
현재 watcher는 요청·stage를 네트워크 전송 전에 저장한다. 판정 범위와 실제 원본 증거는
[Gate C 증거표](GATE_C_REVIEW_2026_10_26.md)와 [source watch 기록](GATE_C_SOURCE_WATCH.md)을 따른다.
최신 반복 감시 task `2733c6a3-abb8-4201-9735-b3354fd32bd9` (TIC)와
`30786cba-1024-4d8b-a599-51942bd91c63` (BIS)도 모두 unchanged여서 Gate C 판정 변화가 없다.

후속 네 갈래는 (1) TIC/BIS exact-scope natural event watch, (2) BOJ FM08/FXERD01 한 달 collector,
(3) bounded structured `macroatlas` CLI 및 같은 task의 status/resume, (4) Linux/Windows CI 검증이다.
BOJ collector는 실제 metadata/data HTTP 200과 30행·11 null 값을 확인했지만 해당 시리즈·한 달에만
적용된다. 일반 자연어 또는 기관 전반 지원으로 확대하지 않는다.

| 게이트 | 상태 | 판정 근거 |
|---|---|---|
| A / 04 | **통과** | 제한된 World Bank USA GDP file 경로 실측·원본/manifest/SQLite 검증. [보고서](ITERATION_04_REPORT.md) |
| B / 08 | **제한 범위 통과** | 구조화 `DataRequest`→근거 후보 순위→명시 선택→World Bank fixture collector E2E와 불일치 후보 차단을 확인. 일반 자연어 parser, 기관 전체 검색은 아직 미구현. 현재 fixed-path CLI는 Gate B 범위 확대가 아니다. [보고서](ITERATION_08_REPORT.md) |
| C / 10 | **제한 범위 통과** | live capture/hash, TIC controlled-copy guard, simulated 503→대기→재개 E2E, exact-scope TIC/BIS live watch를 확인. 자연 revision/recovery는 미검증. BOJ는 후속에서 FM08/FXERD01 한 달만 연결했다. [재검토](GATE_C_REVIEW_2026_10_26.md) |
| D / 12 | **통과** | 동일 BLS/CPI task 흐름에서 명시 선택한 accepted, exact-scope `source_method`로 search stage를 생략해 반복 stage 실행을 2→1로 줄였다. 다른 기관, broader scope, conflict, inference, unreviewed, stale index는 차단; current instruction 우선. 30회 local E2E 측정은 [12회차 보고서](ITERATION_12_REPORT.md). |
| E / 14 | **제한 범위 통과** | A–H/X01–X09 matrix, World Bank 대표 live 경로, simulated 복구, 보안 검토, 사용자 안내서/PPT를 검수했다. 미지원·미검증 경로를 별도 공개한다. [보고서](ITERATION_14_REPORT.md) |

후속 15회차는 코드·문서 및 Windows CI를 검증해 별도 review branch로 push한다. 이 작업은 실행 환경에
publish하지 않는다.

Gate B는 **제한된 엔진 API 기준으로만 통과**했다. 이 결과는 CLI·자연어 UI나 BLS/Census의
후보 선택을 통한 live 수집까지 제공함을 뜻하지 않는다. Gate C 제한 범위 통과는 자연 live
revision/recovery나 BOJ collector/Orchestrator 통합을 포함하지 않는다. 11회차는 사용자의 명시적 순서 예외 지시에 따라
구현했다. 12회차 역시 당시 사용자의 후속 실행 지시로 예외 진행했으며, 초기 storage-only report는
D 통과로 보지 않았다. 이번 후속 Orchestrator integration과 Gate D 증거는 D-068 및 12회차 보고서에
기록했다. 사용자가 이전에 지시한 08→09 진행은 당시
넓게 잡힌 gate 조건을 넘긴 별도 역사적 예외였으며, 현재 scope clarification으로 그 이력을 덮어쓰지 않는다. Gate 상태는
코드가 존재하거나 한 번의 live 요청이 성공했다는 이유만으로 승격하지 않는다.

**배포 추적성은 별도 상태다.** Gate 판정과 혼합하지 않는다. 이번 task는 코드·문서 checkpoint를
task branch에 기록하지만 실행 환경에 publish하지 않는다.

### 구현 자산과 한계

| 회차/기능 | 구현·검증된 범위 | 아직 제공하지 않는 것 |
|---|---|---|
| 01~04 | 공통 계약, SQLite Orchestrator, World Bank 제한 경로, Gate A 기록 | 범용 기관 자동 검색 및 완전한 통계 의미 검증 |
| 05~07 | BLS/Census 제한 API·metadata, 공식 안내 저장, 일부 metadata 정규화 | 모든 기관 검색, live SDMX, 광범위한 분류 의미 모델 |
| 08 | 로컬 hash-verified metadata와 WDI seed의 lexical ranking, 명시 선택 기록, World Bank fixture E2E | 자연어 parser/CLI, 전체 기관 검색, 미확인 BLS/Census 후보의 자동 승격 |
| 09 | CSV/TSV/TXT/HTML/ZIP/XLS/XLSX 제한 parser, 수집량 planning helper | PDF/fixed-width, output exporter, queue형 chunk 실행·resume |
| 10 | BLS/Census/World Bank 제한 API, TIC/BIS live file intake, source-change guard, `Retry-After` 수동 재개; Gate C 제한 범위 통과 | 자연 live revision/recovery, 다른 BOJ series, automatic backoff/rate limiter, 기관 전반 검증 |
| 11 | 명시적 feedback store·CLI·revision history | 사용자 지식 자동 재사용·전체 문서 대화 동기화 |
| 12 | institution-scoped SQLite projection, bounded refresh/lookup, explicit feedback selection through Orchestrator, scoped stage skip, current-instruction precedence | automatic feedback application, cross-institution promotion, UI-level consent, common-rule promotion |
| 13 | 범위별 recurring proposal을 read-only `draft`로 생성하고 상한·근거를 검증 | 운영 이력 기반 후보와 실제 코드 자동 수정·승격은 미제공 |
| 14 | Gate E 제한 범위 시나리오 검수, 지원 한계 안내, 사용자 설명서/PPT 완료 | 모든 기관 완전 지원, 환경 publish, main 병합 |
| 15 후속 | fixed-path structured CLI, BOJ FXERD01 monthly collector, persisted TIC/BIS watch, Windows CI | natural TIC/BIS revision 및 provider failure/resume, 일반 자연어·전체 기관 지원, environment publish |
| 17 | 불변 인계 event에 결합한 격리 시험 task, 자원 한도·미실행 응답, 19개 합성 용량 사례·BIS 원본 시험; 후속 보완에서 worker lock 상속·중단 결과 UNKNOWN 복구 | 정식 대용량 정규화·원격 수집·Windows resource worker·GB/TB 일반화 |
| 16 | 비API 용량 가드·SQLite 인계 목록/이력·조회 CLI, BIS flat 보존 원본 정상 인계, 현행 Gate 재검증 | 자연 revision/recovery; 일반 CSV 전달은 후속 exporter 범위 |
| 19 (완료) | BIS flat 한 건에 한정한 명시 승인 child handoff, Linux chunk/checkpoint worker, deferred event lifecycle, source/hash guard, read-only event sequence 조회; PR #6 통합·4조합 CI·보존 원본 production run 완료 | 다른 provider/format, Windows resource worker, semantic normalization, World Bank/BOJ CSV export |
| 20 | 완료·품질 통과 World Bank/BOJ task의 UTF-8 CSV/provenance 전달, read-only revalidation, no-overwrite/path guard; PR #9 merge 및 4조합 CI 완료 | XLSX, BIS flat JSONL export, arbitrary provider, 독립 사용자 검증 |
| 22 | 비API qualification과 BIS production/resume 전에 실행 시간·범위·신뢰도를 표시하고 실측 history로 shadow forecast를 계산; PR #10 통합 | 현재 catalog 표본 qualification 15, production 1, paired forecast 0. 예측 정확도는 낮은 신뢰도 상태 |
| 23 | 저장 결과→CSV 업무 관찰 protocol·시나리오·동의와 익명 기록 절차 준비; PR #11 통합 | 실제 분석가 참가 세션 미실행. 실제 사용성 판단은 독립 참가자 관찰 후 수행 |
| 24 | pytest/Ruff/diff/CLI/health를 공통 Python runner로 통합, Windows wrapper 및 report/log artifacts; PR #12 통합 | read-only analyzer와 updater→candidate QA handoff는 엔진 통합 계획의 후속 단계 |

세부 구현 수치와 해당 당시 테스트 수는 각 회차 보고서에 둔다. 현재 전체 테스트 수는 최신
검증 결과 섹션만 갱신한다.

## 실패·미충족 항목과 해결 계획 — 2026-10-27

현행 미해결 항목은 [데이터 처리·서버 접속 분류표](UNRESOLVED_ITEMS.md)를 따른다.
아래 과거 실패의 상태와 현재 제품 미구현·정상 인계·증거 대기를 혼합하지 않는다.

20회차 구현 commit `cb7fdcd`에서 666개 테스트, Ruff, diff 검사 및 보존된 World Bank·BOJ task export hash와
SQLite 불변성을 확인했다. PR #9는 `7723afe`로 통합됐고 CI 네 OS/Python 조합이 통과했다. 19회차 구현 HEAD에서…5210 tokens truncated… 의도 질문으로 해소된 부분과 원통계에 남은 불확실성을 별도로 보고한다.
  중앙은행 요청에 더 넓은 공공부문 자료만 있는 것 같은 fixture에서 정확 일치로 오표시하지 않는다.
  사용자가 더 넓은 대리 범위를 수용하면 새 조건/확인 기록으로 남기며 원정의를 덮어쓰지 않는다.

### Phase 3 — 수집 확대와 안정화 (09~10)

#### 09 | API/파일 기반 파서 확장
- 2026-10-26 제한 구현: `data/inbox/`의 명시된 파일을 CSV/TSV/delimited TXT, HTML table,
  ZIP member, XLS/XLSX로 읽는 bounded adapter와 Orchestrator engine을 추가했다. 원본과
  parsed table은 별도 보존하며 row duplicates는 남기고 위치만 보고한다. ZIP 탈출/링크/암호화/
  bomb 제한, sheet/table/member 명시 선택, 동일 파일/옵션 재실행 idempotency를 검증했다.
  World Bank GDP/BLS/Census의 제한된 sample/full 계획기는 연도·series·variable/geography별
  청크를 나누고 요청은 전송하지 않는다. 예상 크기는 호출자가 주지 않으면 unknown으로 남긴다.
  PDF/fixed-width, 범용 API 검색·호출, 큐 기반 청크 실행/재개, 관측치 변환 및 파일 exporter는
  미구현. 전체 pytest 499개/Ruff 통과.
  세부: `docs/ITERATION_09_REPORT.md`.
- 구현: 기존 어댑터 유지 + 실수요 높은 API, CSV, TSV/TXT, ZIP, HTML 표, XLS/XLSX. PDF는 주로 가이드/근거; 숫자 자동 추출은 신뢰도 정책 적용.
- 완료: TIC형 파일/표, BIS형 ZIP/SDMX를 포함한 변형 fixture 테스트. 파일 안전 검사 및 중복 처리.
- 대규모 요청 범위: 샘플/본 수집을 구분하고 공식 bulk 또는 국가·지표·기간별 분할 계획,
  예상량(미상이면 미상), 지원 출력/분할 저장 방식을 제안한다. 무제한 다운로드는 금지한다.
- 파일 전달: 실제 구현된 출력 형식만 선택지로 제시한다. 링크만 요청한 경로는 대량 다운로드/
  파일 생성을 하지 않으며, 미지원 형식·링크를 임의의 다른 출력으로 대체하지 않는다.

#### 10 | 품질 검증·오류 분류·복구
- 2026-10-26 제한 구현: BLS/Census 결과의 중복 기간·중복/불일치 geography·빈/결측 셀을
  보수적으로 진단하고 원값을 보존한다. 단위·주기·개정 vintage가 없으면 unknown 경고를 낸다.
  동일한 공식 URL·요청 범위의 기존 원본 SHA256과 새 응답을 비교해 changed면 새 raw도 보존하고
  `NEEDS_REVIEW`로 보낸다. 과거 hash 검증 실패나 1,000 package/64 MiB 비교 예산 초과는
  비교 불가로 표시한다.
- HTTP 401/403은 `AUTH_ACCESS` 검토, 429/5xx와 timeout은 `TRANSIENT` 수동 재개, redirect는
  `LICENSE_SECURITY`, 예기치 않은 4xx는 `SITE_CHANGED`, 파싱 drift는 `SCHEMA_CHANGED`로 분류한다.
  전송당 자동 재시도는 하지 않으며 Orchestrator의 max_attempts와 명시적 resume을 사용한다.
  후속 계획 정합성 수정에서 `Retry-After` 초/HTTP-date를 저장하고 지정된 최소 대기시간이 지나기
  전에는 resume를 거부하도록 보완했다. 자동 지수 backoff와 공용 rate limiter는 여전히 미구현이다.
  후속 사용자 요청에 따라 현재 workspace 엔진으로 BLS `CUUR0000SA0` 2024 및 Census ACS1
  California `B01001_001E`를 각각 1회 live 실행: 두 요청 모두 HTTP 200, BLS 12행/Census 1행,
  raw·manifest SHA/크기 일치, 키 필드 비노출. 기존 raw manifests에 SHA가 없어 변경 비교는
  `unknown_history_integrity`; 세 BLS capture의 observation은 같고 top-level `responseTime`만 달랐다.
  비교기는 이제 이 volatile 필드를 제외한 canonical JSON hash를 사용하며 raw bytes는 보존한다.
  설정의 repository ref는 `codex/iteration-04-gate-a`, 현재 미커밋 코드 workspace는
  `codex/institution-discovery-05`였다. 당시 실측은 current workspace만 증명했고 fresh checkout ref는
  증명하지 않았다. 게시 후 기준선 검증은 상단 배포 추적성 섹션의 후속 기록을 따른다.
  환경 상태 telemetry는 네트워크·키 `unknown`; live 호출 성공은 이를 바꾸지 않는다. 따라서
  live smoke는 확인했지만 Gate C는 미통과. 당시에는 World Bank 변경감지가 미구현이었다. 이후
  local 후속으로 same-request JSON/bytes comparison을 추가했으나 fixture만 검증했고 live 확인은 없다.
  자동 지수 backoff/공용 rate limiter, 의미 outlier·단절 판정은 여전히 미구현.
  전체 pytest 518개/Ruff 통과. 상세: `docs/ITERATION_10_REPORT.md`.
- 구현: 빈값/중복/단위/주기/개정 상태 확인, schema drift, 시간 제한·재시도·rate limit, 중단 지점 재실행.
- 완료(Gate C): 429, 403, 형식 변화, 통계 의미 불명, 최신 원자료 변경을 각각 재현하여 안전한 분기 확인.
- 대규모 요청 검수: 확정한 시간·호출·용량 상한에서 안전 중단하고, 단위별 성공·실패·미실행
  목록과 재개를 검증한다. 정의/단위가 다른 자료를 자동 병합하지 않는다.
- 링크 재검증: 만료·권한 제한·조건 불일치·키 포함 URL을 재현해 공유를 중단하고,
  링크 제공 완료와 실제 수집/검증 완료를 다른 실행 근거로 기록한다.

### Phase 4 — 피드백의 지식화 (11~12)

#### 11 | 사용자 지시·교정 피드백 기록
- 구현: 명시적 사용자 입력/CLI에 기반한 피드백 생성, task/stage/institution 링크, 원문·검토상태·변경 이력.
- 완료: 피드백을 실제 작업·오류에 연결해 조회, 후속 편집/취소 가능. ChatGPT 대화의 자동 연동은 전제로 삼지 않음.
- 후보 묶음/질문 순서/출력 선호 교정의 원문·기관/개념/작업 범위와 변경·취소를 기록한다.
- 지식 엔진 입력: 사용자 설명·공식 근거·추론을 구분하고 기관/데이터셋/개념/분류 축·버전·
  유효 시점·검증 상태·대체/취소 관계를 보존한다. 짧은 등록 때문에 전체 지식 재계산을 실행하지 않는다.

#### 12 | 경험 재사용·공통 규칙 승격 정책
- 구현: 기관별 경험 조회, 새로운 작업에서 조건부 재사용, 공통 규칙 후보 격리 및 승인 상태.
- 완료(Gate D): 동일 기관 재시도 효율 개선; 다른 기관에 잘못 전파되지 않음; 근거 없는 규칙 승격 차단.
- 표현 정책은 현재 명시 지시를 우선한다. 유효한 범위의 선호만 재사용하고, 출력 지시가
  없는 새 요청은 과거 선호로 자동 실행하지 않고 선택을 묻는다. 오적용·취소·상충 테스트 포함.
- 기관·개념 지식 엔진: SQLite의 범위/상태/버전 색인과 제한 조회, 필요한 근거만 읽기,
  bounded 캐시·무효화와 별도 갱신 작업을 구현한다. 전체 이력 JSON/원본을 프롬프트마다
  역직렬화하지 않는다. 초기 전용 벡터 DB·거대 온톨로지·상시 전기관 조사는 요구하지 않는다.
- Gate D 추가 검수: 범위 오적용·추론의 사실 승격·상충 누락·구버전 캐시를 차단한다.
  조회/시간/메모리 예산 초과 시 미검토 범위를 보고하며, 필수 불확실성을 숨기지 않는다.
  기준 환경/예산을 명시한 규모별 benchmark에 p50/p95·최대 메모리·읽은 행/바이트·확장 깊이와
  검색 정합성을 기록한다. 구체 예산은 구현 시 수치화하고 측정 없이 성능 통과로 처리하지 않는다.

### Phase 5 — 공통 개선 엔진 (13~14)

#### 13 | 반복 패턴 집계·개선안 생성
- 상태: 구현·로컬 검증 완료 (2026-10-26). 결과와 실제 한계는 `docs/ITERATION_13_REPORT.md`.
- 입력: Orchestrator의 완료/실패 task·stage 결과와 상태가 accepted인 명시 사용자 feedback만 읽는다.
  raw provider payload, 비밀값, 미검토 추론은 pattern source로 사용하지 않는다.
- 반복 판정: 같은 fingerprint가 서로 다른 **3개 이상 task ID**에 있어야 recurring candidate가 된다.
  한 task의 retry 횟수는 독립 사례로 세지 않는다. fingerprint는 알려진 institution, engine/version,
  stage, error code/category, dataset/concept scope를 포함한다. 값이 다르거나 미상인 차원은
  서로 합치지 않고 별도/insufficient evidence로 남긴다.
- 입력 한도: 실행당 최대 500 task와 2,500 stage/feedback records를 읽고, 최대 20개 proposal과
  proposal당 evidence reference 10개를 반환한다. 상한에 닿으면 partial/incomplete를 명시하고
  "반복 없음"으로 판정하지 않는다. `scripts/benchmark_iteration_13.py` 측정 후 이 환경 기준
  bounded run 참조 예산을 warm p95 150 ms, traced Python allocation 8 MiB로 설정했다.
- 산출물: fingerprint와 scope, 서로 다른 task 수, 관측 시점, 대표 evidence IDs, 심각도 근거,
  예상 영향, counterexample/불확실성, 검증할 regression test, 위험, priority, `draft` review status.
  동일 task 안의 재시도, 1~2개 task의 반복, 충돌은 recurrence와 구분해 별도 보고한다.
- 완료: 반복 오류/교정에서 traceable proposal을 만들고 one-off, insufficient, recurring을 구분한다.
  기관·dataset scope가 다르면 후보도 분리하고, inference는 `not_promoted`, proposal은 승인 전
  `draft`로 유지한다. 조회 상한 및 불완전 입력을 숨기지 않는다.
- 승인 경계: task/feedback/source data를 수정하거나 지식을 accepted로 올리지 않고 코드를 고치지
  않는다. 변경 구현은 14회차의 격리 branch·회귀·인간 승인 절차에서만 다룬다.
- 검수: X09에서 같은 오류를 서로 다른 3개 task로 만들어 draft가 생기는 경우, 동일 task retry만
  늘려도 recurring이 되지 않는 경우, 기관/dataset/engine 차원의 분리, withdrawn/unreviewed/inference
  제외, 충돌·부분 입력·500/2,500·20/10 상한과 evidence trace를 검증한다. 100/1,000/5,000 records
  에서 p50/p95, 최대 Python allocation, 읽은 행/논리 바이트, candidate 수와 scope relevance를 잰다.
- 실제 검증: `tests/test_patterns.py` 11개 fixture, 전체 pytest **591 passed**, Ruff 및 diff 검사 통과.
  100/1,000/5,000 stage-record 측정은 각각 p50/p95 5.113/5.448, 45.653/51.023,
  125.960/134.287 ms였으며, 5,000 입력은 2,500 상한에서 `partial`이었다. 5,000 입력 기준
  최대 Python allocation은 5,484,768 bytes였다. 상세 측정·제한: `docs/ITERATION_13_REPORT.md`.

#### 14 | 격리 수정·검증·인간 승인·릴리스
- 구현: 격리된 Git 브랜치에서 코드 변경 후보와 회귀 테스트; diff, 결과, 롤백 경로, 승인 게이트. 승인 전 main 병합/배포 금지.
- 완료(Gate E): A~H 중 환경에서 지원 가능한 대표 시나리오 실행 결과·비지원 목록·복구 테스트·보안/비용 검토 포함한 v1 릴리스 보고서.
- 최종 안내 산출물: PROJECT_PLAN.md §10.3에 따라 `docs/USER_GUIDE.md`와
  `docs/MacroAtlas_User_Guide.pptx`를 실제 완성된 기능 기준으로 작성한다.
  실행 방법, 기관별 선택적 API 키 설정, 수집 결과 확인, 오류·한계를 포함한다.
  설명서의 대표 절차 재현 결과와 PPT 표시·내용 일치 검수를 완료 보고에 기록한다.
  이 자료는 14회차에 제작하며 현재 단계에서는 만들지 않는다.

## 사용자 흐름 보완 실행 순서

docs/WORKFLOW_ALIGNMENT_PLAN.md는 01~03회차 최소 보완의 상세 명세다.
보완 01 기본/확장, 보완 02·03 및 04회차 Gate A는 완료했다. Gate A 보고서는
`docs/ITERATION_04_REPORT.md`다. 다음 회차는 별도 작업으로 한 번에 하나씩 진행한다.
현재 전체 기준은 pytest 433개와 Ruff 통과이며 기존 오류 계약을 유지한다.
소급 요구사항을 이유로 과거 01~03회차 실측/테스트 기록을 덮어쓰지 않는다.

## 검수 게이트

| 게이트 | 회차 | 종료 조건 | 통과하지 못하면 |
|---|---|---|---|
| A | 04 | 지정 데이터 실제 수집+원본·이력 보존 | **통과** — `docs/ITERATION_04_REPORT.md` |
| B | 08 | 기관/메타/시계열 검색→수집 연결 | 09 금지, 탐색 계약 수정 |
| C | 10 | 제한 live baseline + 통제 변경/복구 integration proof | **제한 범위 통과:** 자연 live revision/recovery·BOJ 및 미검증 기관 제외; 상세 범위는 Gate C review 참조 |
| D | 12 | 피드백 재사용, 잘못된 일반화 차단 | **통과:** explicit exact-scope Orchestrator reuse; detailed E2E proof in Iteration 12 report |
| E | 14 | 회귀·보안·원본 검증, 승인 절차 | v1 출시 보류 |

## 각 회차 종료 보고서 형식

```text
회차:
구현한 사용자 가치:
변경 파일:
테스트 목록과 실제 결과:
실제 외부 서비스 확인 여부 / 모의 테스트 여부:
남은 한계와 미검증 가정:
보안·출처·통계 의미 영향:
다음 회차 선행 조건 충족 여부:
사람이 결정해야 할 사항:
```

## 사용자 추가 요구 — 비API 대용량 인계

16회차 우선순위를 [비API 대용량 분류·인계](ITERATION_16_PLAN.md)로 변경했다. 임계 조건 이상이면
현재 엔진 처리를 중단하고 영속 목록으로 모은 뒤 별도 엔진에 인계한다. 정책·목록 구현은 완료했고 별도 대용량 엔진 실행 연결은 대기 상태다.
확인된 BIS flat ZIP은 [초기 대상 목록](NON_API_DEFERRED_CATALOG.json)에 등록했고, CSV 출력 계획은
[후속 계획](CSV_EXPORT_FOLLOWUP_PLAN.md)으로 보존했다.

## 16회차 구현 결과

비API 대용량 사전 검사·bounded parser 중단·SQLite 인계 목록/이력·CLI 조회를 구현했다.
[16회차 보고서](ITERATION_16_REPORT.md)의 범위와 한계를 따른다. 별도 엔진 실행은 향후 작업이다.
