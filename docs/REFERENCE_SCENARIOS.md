# Reference Scenarios — 표준 제품 수용 테스트

> 목적: 아키텍처를 실제 국제금융 데이터의 차이로 검증. 아래는 **시나리오/테스트 사양**이며 테스트 성공을 주장하지 않는다. 각 결과는 `PASS / FAIL / BLOCKED / NOT_RUN`으로 기록.

## A | IMF — 복잡한 SDMX 국제통계

- 사용자 요청: "IMF에서 미국·일본 국제수지 금융계정의 포트폴리오 투자 분기 데이터를 찾아줘."
- 기관 및 근거: IMF Data Portal, SDMX API 문서.
- 정상 경로: IMF 공식성 확인 → Dataflow 후보 → DSD/Codelist → 국가·항목·주기 조합 → series 후보 → 단위·표준(BPM) 확인 → 수집.
- 검수: 임의 series 키 생성 금지; 정확한 정의·코드·출처 제시; 국가·기간 필터 확인.
- 실패 변형: 명칭은 같은데 flow 개편 / API 응답 버전 차이 → 구조 재탐색.

## B | BIS — 대용량·다차원 은행통계

- 요청: "BIS 글로벌 유동성 통계에서 미국 달러 표시 비은행 차입자 관련 데이터를 찾아줘."
- 경로: 주제 목록→Dataflow/DSD→통화·차입자·국가→API 또는 ZIP bulk 선택→수집.
- 검수: 선택된 개념·국가집계·주기·통화 기록, ZIP 압축 안전 검사, 대용량 제한.
- 실패: 동일 개념 명칭이지만 통계 커버리지/차원 차이; 과도한 전체 다운로드 금지.

## C | Treasury TIC — 웹표·아카이브 파일

- 요청: "미국 재무부 TIC에서 국가별 미국 국채 보유잔액의 월별 시계열을 찾아줘."
- 경로: 공식 TIC→Monthly Holdings/Major Foreign Holders→표·설명서·변경 안내→HTML/CSV/TXT/ZIP 등 확인→표 구조 해석→수집.
- 검수: **보유잔액 vs 증권 거래액** 구분, TIC에서 직접 제공하는 실제 파일 형식 확인, 출처·개정/단절 근거 보존.
- 실패: 예전 데이터 링크 위치 변경·표 헤더 변경·신구 시리즈 구분.

## D | BEA — 파라미터 선탐색형 API

- 요청: "미국 국제수지 금융계정의 직접투자와 증권투자 시계열을 찾아줘."
- 경로: dataset 목록 → parameter 목록/값 → 경제계정 범위 → 정확한 series/data query 구성 → API 수집.
- 검수: API 키 비노출, 같은 명칭의 자산/부채·순액/총액 구분, 가능한 주기 확인.
- 실패: 유효하지 않은 parameter 값 또는 권한 문제 → 적절한 종료.

## E | ECB + Eurostat — 같은 지역의 서로 다른 통계기관

- 요청: "유로존 은행대출·소비자물가를 공식 출처로 찾아줘."
- 경로: 통계별 적합 기관 선택 → ECB SDMX/Eurostat CATALOGUE → DSD/코드 검색 → series 발견 → 데이터 API 수집.
- 검수: 유로존 구성 변화, 계절조정, 대출 정의, HICP 분류; 출처를 혼동하지 않음.
- 실패: 지역 집계 코드·Dataflow 변경.

## F | 일본 MOF + BOJ + e-Stat — 연결 기관·새 API

- 요청: "일본 국제수지의 해외증권투자와 외환 관련 시계열을 찾아줘."
- 경로: MOF 공식 자료·해설 탐색 → BOJ 자세한 시계열 안내·JSON/CSV API → 필요시 e-Stat 목록·메타 확인.
- 검수: 공식 공표 주체와 실제 series 호스팅 기관 구분; 잠정/수정치, 일본어/영어 제목 연결.
- 실패: BOJ 기존 flat file와 2026 API의 코드/데이터 불일치.

## G | 중국 PBOC + SAFE + NBS — 주제별 기관 선택·다국어

- 요청: "중국 외환보유액, 사회융자총량, 산업생산의 공식 통계를 찾아줘."
- 경로: 주제별 적정 기관 선택 → 공식 도메인 검증 → 중국어/영어 통계명 검색 → 안내·표/파일 확인 → 허용된 형식으로 수집.
- 검수: PBOC/SAFE/NBS의 역할 분리, 단위(억 위안 등)와 발표 기준, 접근경로 미확인시 추정 금지.
- 실패: 자료 페이지에서 직접 다운 불가, 접근제한, 페이지 개편 → `NEEDS_REVIEW`로 보고.

## H | OECD + World Bank — 중복 데이터의 출처·정의 비교

- 요청: "미국·일본·독일의 장기 GDP와 물가 데이터의 공식 정의 및 출처를 비교해줘."
- 경로: 지표 후보 → 국가·주기·기준년/산정법·원출처 확인 → 가능한 시계열 경로 정리 → 선택해 수집.
- 검수: 기관 간 이름 일치만으로 매핑하지 않음; 원출처·재가공 관계 기록.
- 실패: 기준년/계절조정/단위 차이를 무시한 단순 결합 차단.

## 공통 오류·피드백 시나리오

| ID | 투입 조건 | 기대 시스템 행동 |
|---|---|---|
| X01 | API 429 또는 일시 5xx | 호출당 1회 요청 후 `TRANSIENT`로 기록. `Retry-After`가 있으면 명시적 resume를 최소 대기시간 전까지 차단하고, 없으면 장애 해소 후 운영자가 resume. 단계별 호출 상한과 실행 이력 유지 |
| X02 | 403, 키 만료, 접근권한 부족 | 인증 우회 없이 `NEEDS_REVIEW` |
| X03 | 이전 파일의 열명/시트 변경 | schema drift 보고, 원본/이전 버전 유지 |
| X04 | 잔액 대신 거래액 후보를 발견 | 매칭 거부·후보 불일치 이유 제시 |
| X05 | 사용자가 특정 기관의 수집 경로 수정 | 해당 기관 지식에 등록, 다음 실행 조건부 적용 |
| X06 | 여러 기관에서 같은 파서 오류 반복 | 공통 개선 제안, 검증·승인 이전 코드 변경 금지 |
| X07 | 중간 수집 실패 후 resume | 승인된 유효 산출물 재사용, 실패 지점부터 재개 |
| X08 | 데이터 소급 수정 | 이전 raw/vintage 보존, 변경점 보고 |

## 시나리오 공통 기록 포맷

```yaml
scenario_id: C
run_id: null
environment: local_windows
mode: live | fixture
status: NOT_RUN
source_docs_verified: false
expected_evidence: [source_url, metadata_definition, series_key_or_table, raw_file_hash, normalized_output, quality_report]
actual_evidence: []
issues: []
reviewer: null
run_date: null
```

## 단계별 적용

- Gate A(04): B의 공개 파일 또는 H의 간단 API 중 한 자료로 실측 수집; X01/X07 기본.
- Gate B(08): H의 World Bank evidence-backed seed를 사용한 구조화 요청→후보 순위→명시 선택→
  대표 collector E2E. A/E와 C/D의 일반 메타데이터/API 연결은 기관 확대 시나리오로 남긴다.
- Gate C(10): C/TIC 파일·B/ZIP·F/일본 기관 연결; X01~X04, X07/X08.
- Gate D(12): X05/X06과 기관별 규칙 분리.
- Gate E(14): A~H의 사용 가능한 정상·실패 매트릭스와 남은 BLOCKED를 공개.

## 03회차 실행 근거 (2026-10-24)

- H의 World Bank 단일 GDP 수집 부분 경로만 실제 실행: USA, source 2,
  NY.GDP.MKTP.CD, 2020:2022. HTTP 200, 관측 행 3개와 raw 724 bytes 보존.
- H 전체는 NOT_RUN이다. OECD·다국가 탐색·정의 비교·자동 선택은 실행하지 않았다.
- X01의 429/5xx/전송 오류 분류와 X02의 접근 거부, X03 형태 변화의 제한적 대응은
  합성 fixture/모의 HTTP로 검증했다. 실제 429/403을 유발하거나 HTTP backoff를
  구현한 것은 아니다. Orchestrator의 수동 재시도 연결도 fixture로 검증했다.
- 원본·최종 파서 재해석 및 모의 테스트 근거는 docs/ITERATION_03_REPORT.md 참조.
  이 항목은 당시 03회차 부분 검증 기록이다. 04회차 Gate A의 후속 실측은 아래에 기록한다.

## 04회차 Gate A 실행 근거 (2026-10-25)

- H 중 World Bank USA GDP 고정 경로만 실제 수집·검증했다: source 2, `NY.GDP.MKTP.CD`, 2020:2022. HTTP 200, 724-byte 원본, 원본·manifest hash, SQLite 관측치 3개 및 검증·feedback 이력을 보존했다.
- 저장 보고서 `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`의 `live_path_passed=true`를 확인했다. pytest 433개 및 Ruff도 통과했다.
- H의 OECD 비교, 다국가 탐색, 정의 비교와 자동 후보 선택은 여전히 NOT_RUN이다. 경제적 이상치, revision history, cross-source equivalence도 확인하지 않았다.
- Gate A 상세와 한계는 `docs/ITERATION_04_REPORT.md` 참조.

## Gate C X08 World Bank fixture follow-up (2026-10-26)

- Same official URL and exact year-range request scope: changed JSON observations preserve both raw
  captures and return `NEEDS_REVIEW`; no normalized observations are published.
- Reordered JSON object keys/formatting are unchanged at the canonical payload level even though raw
  byte hashes differ. A different request scope starts a separate baseline.
- A tampered prior raw package makes history comparison unknown and emits
  `prior_response_comparison_unavailable`; a verified legacy artifact without comparison metadata
  can be used as a baseline.
- TIC TSV/HTML and BIS ZIP/CSV-shaped fixture files also pass through `TabularFileEngine`; raw,
  manifest, and normalized table hashes are checked.
- This is fixture evidence. It does not establish live change detection or official TIC/BIS provider
  workflows, Japan API support, or Gate C completion.

## Gate C live TIC and tabular change-guard follow-up (2026-10-26)

- Scenario C: **PARTIAL live**. One official Treasury Table 5 TXT response was imported from the
  saved inbox file; the source page identifies end-of-period holdings in billions of dollars.
  HTTP/content-type provenance, source URL, and raw/normalized hashes were checked. The Japan row is
  retained as holdings data, not interpreted as a transaction flow.
- X08: **fixture PASS for tabular intake**. Same source scope plus changed bytes preserves both raw
  captures and returns `NEEDS_REVIEW` before normalized output. Unchanged bytes across capture times
  compare as unchanged; a tampered previous raw file makes history unknown and blocks normalization.
- X08 live TIC delta: **NOT_RUN**; only one live file capture was made. A subsequent source revision
  must be captured before claiming live change-detection evidence. Gate C remains not passed.

## Gate C live BIS bulk and BOJ access follow-up (2026-10-26)

- Scenario B: **PARTIAL live**. The official BIS bulk page returned HTTP 200 and linked
  `WS_GLI_csv_col.zip`; ZIP download returned HTTP 200 and passed raw archive → normalized table
  intake (225 rows, 220 columns). The file includes multiple series/units and was not treated as one
  homogeneous series. The flat CSV alternative returned HTTP 503; no retry was sent.
- Scenario F: **BLOCKED** for BOJ API collection. The official API notice returned HTTP 200 and
  describes JSON/CSV time-series access, but its linked API manual returned HTTP 403. No BOJ API
  request was formed because request parameters and series identifiers could not be verified.
- X01: the live BIS 503 was recorded without retry. A deterministic guide-fetch fixture verifies a
  503 `Retry-After: 17` is persisted as a retry hint and no automatic retry occurs. This does not
  substitute for a real provider recovery/resume cycle.
- X08 live TIC/BIS source delta and provider-specific recovery remain **NOT_RUN**. Gate C remains
  **not passed**; Gate D/Iteration 11 stays unstarted.
