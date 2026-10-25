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

### H 보완 — 넓은 GDP 질의와 가격 유형

- “미국 GDP”에서 명목/실질이 서로 다른 Concept ID 또는 같은 ID의 다른 속성으로 제공되는 두 경우 모두 주요 후보를 제시한다.
- 명목/실질은 같은 검색 개념군 안에서 가격 기준을 구별한다. 증가율·1인당 GDP는 관련 참고로 구분하고 GNI/부채/관계 미상 후보는 주요 GDP에서 제외한다.
- 수집 전 필요한 유형/후보 선택을 확인한다. 명목을 기본값으로 정하거나 지원되지 않는 실질 GDP를 명목 경로로 대체하지 않는다.
- 이 보완의 정상/미상/충돌/정책 개정 회귀 테스트는 docs/developer/planning/CONCEPT_SEARCH_REVISION_PLAN.md를 따른다.
- 보완 실행: 서로 다른/동일 ID의 GDP 명목·실질 포함과 관련 지표 구분, 명시 유형 선택·변경, 미상/충돌과 정책 개정 차단을 fixture로 통과했다. 이후 코드 리뷰에서 미상 개념의 과다 노출과 요청 조건에 어긋난 관련 후보를 고쳐 전체 pytest 516개/Ruff로 Gate B를 재검증했다. H 전체·실제 실질 GDP 수집의 PASS를 뜻하지 않는다. docs/developer/history/CONCEPT_SEARCH_REVISION_REPORT.md 참조.

| ID | 투입 조건 | 기대 시스템 행동 |
|---|---|---|
| X01 | API 429 또는 일시 5xx | backoff 후 상한 내 재시도, 실행 이력 저장 |
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
- Gate B(08): A/E의 메타데이터 경로 + 후보 검색; C 또는 D의 검색과 수집 연결.
- Gate C(10): C/TIC 파일·B/ZIP·F/일본 기관 연결; X01~X04, X07/X08.
- Gate D(12): X05/X06과 기관별 규칙 분리.
- Gate E(14): A~H의 사용 가능한 정상·실패 매트릭스와 남은 BLOCKED를 공개.
- Gate F(15): A–H 출처별 API 문서·접근 우선순위·어댑터·fixture·live 상태 레지스트리. 이 단계는 시나리오 실행이나 기관별 API 지원 완료를 의미하지 않는다.

## 03회차 실행 근거 (2026-10-24)

- H의 World Bank 단일 GDP 수집 부분 경로만 실제 실행: USA, source 2,
  NY.GDP.MKTP.CD, 2020:2022. HTTP 200, 관측 행 3개와 raw 724 bytes 보존.
- H 전체는 NOT_RUN이다. OECD·다국가 탐색·정의 비교·자동 선택은 실행하지 않았다.
- X01의 429/5xx/전송 오류 분류와 X02의 접근 거부, X03 형태 변화의 제한적 대응은
  합성 fixture/모의 HTTP로 검증했다. 실제 429/403을 유발하거나 HTTP backoff를
  구현한 것은 아니다. Orchestrator의 수동 재시도 연결도 fixture로 검증했다.
- 원본·최종 파서 재해석 및 모의 테스트 근거는 docs/developer/history/ITERATION_03_REPORT.md 참조.
  이 항목은 당시 03회차 부분 검증 기록이다. 04회차 Gate A의 후속 실측은 아래에 기록한다.

## 04회차 Gate A 실행 근거 (2026-10-25)

- H 중 World Bank USA GDP 고정 경로만 실제 수집·검증했다: source 2, `NY.GDP.MKTP.CD`, 2020:2022. HTTP 200, 724-byte 원본, 원본·manifest hash, SQLite 관측치 3개 및 검증·feedback 이력을 보존했다.
- 저장 보고서 `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`의 `live_path_passed=true`를 확인했다. pytest 433개 및 Ruff도 통과했다.
- H의 OECD 비교, 다국가 탐색, 정의 비교와 자동 후보 선택은 여전히 NOT_RUN이다. 경제적 이상치, revision history, cross-source equivalence도 확인하지 않았다.
- Gate A 상세와 한계는 `docs/developer/history/ITERATION_04_REPORT.md` 참조.

## 05회차 fixture 탐색 근거 (2026-10-25)

- HTML navigation 전략은 BIS 후보의 통계 포털·SDMX 문서 링크 fixture와 도메인 경계, 서드파티 링크 제외를 통과했다.
- XML sitemap 전략은 Treasury TIC 후보의 공식 호스트 페이지와 외부 호스트 분리 fixture를 통과했다.
- 두 실행은 합성 fixture만 사용했다. 실제 BIS/Treasury 페이지 방문, sitemap 존재 확인, 링크 응답·리다이렉트 검증은 하지 않았다.
- 시나리오 B와 C 전체 상태는 NOT_RUN으로 유지한다. 이번 검증은 해당 시나리오의 완료나 Gate B 통과가 아니다.
- 상세 구현·테스트 결과: docs/developer/history/ITERATION_05_REPORT.md.

## 06회차 이용 안내·기관별 전략 fixture 근거 (2026-10-25)

- IMF SDMX API 안내 유형과 Treasury TIC 이용 안내 유형을 서로 다른 GuideCategory로 저장하고 기관별로 분리된 명시 전략 규칙의 재사용을 검증했다.
- 원문은 합성 fixture다. 공식 IMF/Treasury 페이지를 방문하거나 본문·약관을 확인하지 않았고 실제 SDMX/TIC API도 호출하지 않았다.
- 원문 변경은 새 append-only 스냅샷으로 저장되며, 기존 전략이 참조하는 가이드가 변경·만료됐거나 동일 점수 전략이 겹치면 선택 상태를 재검토로 돌린다. 새 스냅샷으로 자동 대체하지 않는다.
- 시나리오 A/B/C 전체 상태는 계속 NOT_RUN이며 Gate B는 통과하지 않았다. 이 회차는 가이드 데이터 구조와 선택 정책의 fixture 검증만 완료했다.
- 상세 구현·테스트 결과: docs/developer/history/ITERATION_06_REPORT.md.

## 07회차 메타데이터 fixture 근거 (2026-10-25)

- A형 합성 IMF SDMX Dataflow/DSD/Codelist의 참조와 다국어 이름을 파싱했다. 존재하지 않는 참조는 unresolved로 기록하며 series 키를 만들지 않는다.
- C형 합성 TIC 추출 코드북에서 원래 단위/주기 코드와 stock/flow·시트/열 근거를 보존했다. World Bank형 API 목록 입력은 기존 고정 수집 경로의 식별자를 제공하지만 새 live 증거가 아니다.
- 원문/정규화 저장, 누락·언어 fallback·충돌·범위 관계·버전 갱신을 로컬 테스트했다. A/B/C 전체 및 Gate B 상태를 승격하지 않는다.
- 상세: docs/developer/history/ITERATION_07_REPORT.md.

## 08회차 Gate B 로컬 fixture 근거 (2026-10-25)

- A 부분 경로 PASS(fixture): 합성 Dataflow→DSD→Codelist에 연결된 제공 series key 검증과 후보 검색. 코드가 없거나 구조가 개정됐으면 해당 후보를 검토 상태로 둔다. IMF 실제 수집은 미지원이다.
- C 부분 경로 PASS(fixture): 합성 TIC 보유잔액 코드북→후보 검색→조건/전달 확인→CSV 원문/manifest 보존·최소 파싱. 결측/0, 보유잔액/거래액, 기관·범위, 잘못된 열/값, 링크 상태·만료와 근거 변경을 검증했다.
- 기존 World Bank 고정 경로도 catalogue 후보→확인→수집/Gate A 검증에 fixture transport로 연결했다. 이전 live 보고서를 재실행하지 않았다.
- Gate B 주장은 위 로컬 서비스 범위다. A~H 전체와 IMF/TIC 실제 요청·현재 URL/약관은 NOT_RUN으로 유지한다. 전체 pytest 499개와 Ruff가 통과했다.
- 상세 범위·한계·체크포인트: docs/developer/history/ITERATION_08_REPORT.md.

## 10회차 Gate C 로컬 fixture 근거 (2026-10-25)

- X01: mocked World Bank 429/Retry-After와 파일 route 429를 `TRANSIENT`로 기록했다. retry due 전 재개는 거부되고 due 이후에만 재시도된다. 지원 대기 상한보다 큰 Retry-After는 자동 재시도를 예약하지 않고 `NEEDS_REVIEW`로 전환한다.
- X02: 403은 `AUTH_ACCESS` 검토로 멈추고 인증 우회·다른 기관 자격증명 fallback을 하지 않는다.
- X03: 선언 포맷과 다른 응답 media type 또는 변경된 열/행 구조는 `SCHEMA_CHANGED`; 원본은 보존하고 관측치 결과를 내지 않는다.
- X04: 개념이 미상인 검색은 clarify로 보내고, 잔액/거래액 차이와 주기·단위 조건이 충돌하는 후보를 수집하지 않는다.
- X07: durable unit ledger는 성공 단위를 보존하고 retryable/NOT_RUN 단위를 구분해 재개한다. metadata revision 변화나 예산 초과는 남은 단위를 멈춘다.
- X08: 최신 metadata snapshot이 수집 중 바뀌면 raw response만 보존하고 기존 확인에 따른 파싱/관측치 반환을 차단한다. 실제 원자료의 기관 vintage 개정은 재현하지 않았다.
- link 조건은 기존 workflow fixture에서 만료·blocked/권한·요청 fingerprint 불일치·credential URL을 검증했다. 링크를 실제 HTTP로 재검증하지 않았고 link delivery와 데이터 수집 완료는 별도 이력으로 유지한다.
- 결과: Gate C PASS (local fixtures/mocks). 전체 pytest 568개 및 Ruff 통과. A~H 전체/실제 기관 링크·API 경로 PASS를 뜻하지 않는다. 상세: docs/developer/history/ITERATION_10_REPORT.md.

## 11회차 X05 피드백·지식 입력 fixture 근거 (2026-10-25)

- X05: 사용자 교정은 명시 호출로 task와 World Bank 기관·WDI dataset·GDP concept·가격 기준 축에 연결된다. 편집은 revision 이벤트로 남고, 오래된 revision 편집·다른 task의 오류 연결은 거부된다. 오류 코드로 해당 task에 연결된 피드백을 조회한다.
- 후보 묶음·질문 순서·출력 선호 유형, 원문, 검토 상태, 유효 범위, source version, evidence ref, 취소/대체 관계를 기록한다. 수정/취소는 기존 행이나 기록을 지우지 않는다.
- 사용자 주장·공식 근거·추론은 provenance와 validation status를 분리한다. 사용자의 검토 승인은 기관의 공식 통계 사실로 바꾸지 않고, inference의 verified/accepted 승격은 거부한다.
- 결과: 11회차 PASS (local SQLite); 전체 pytest 573개/Ruff/diff check 통과. 공식 페이지·실제 URL·기관 API 검증은 없다. X06의 일반 규칙 생성/승격은 이번에 수행하지 않았고, Gate D의 격리 검증에 포함한다. 상세: `docs/developer/history/ITERATION_11_REPORT.md`.

## 12회차 Gate D X05/X06 지식 재사용 fixture 및 benchmark (2026-10-25)

- X05: 같은 기관·정확히 맞는 공식 근거만 조건 충족 후 재사용 가능하다. 기관/데이터셋/개념/축의 요청 범위보다 넓은 공식 주장은 후보로만 남기며, user statement는 현재 입력 확인을 요구한다. 다른 기관 기록은 섞이지 않고 교정/취소 또는 별도 저장소 인스턴스의 갱신은 색인 세대를 바꿔 캐시 재사용을 무효화한다.
- 개념 검색: 명시된 versioned `subtype` 관계에 따라 GDP 검색에서 합성 명목·실질 후보 둘 다 반환한다. 두 후보의 ID·경로·정책 근거를 표시하고 통계적 등가성으로 주장하거나 자동 대체하지 않는다. `related` 링크는 포함하지 않으며 child concept는 형제 항목으로 확장하지 않는다.
- X06: 반복 지식/추론은 일반 사실 조회에서 격리된다. inference 승인과 verified 승격 시도는 차단된다. 공통 규칙 자동 생성·승인·기관 간 배포는 13회차 이후 범위로 남겼다.
- 크기별 결과: synthetic SQLite 100/1,000/10,000행, Windows 11/Python 3.12.14/SQLite 3.53.1. 앱 캐시 미사용 indexed query p95 8.516/16.625/13.793ms, warm cache p95 4.309/8.175/5.944ms, 최대 Python allocation 49,536/71,022/127,673 bytes. 10,000행에서 p95 250ms 및 Python allocation 1MiB 구현 상한 이내다. native SQLite memory 및 process RSS는 제외한다.
- 결과: Gate D PASS (local SQLite/fixtures/synthetic benchmark); 전체 pytest 578 passed, Ruff 및 `git diff --check` 통과. 고정 read snapshot 도중 다른 저장소 인스턴스의 writer가 시작해도 한 query 결과가 서로 다른 세대의 색인/근거를 섞지 않는 deterministic interleaving을 테스트했다. 처리량/경합 stress는 측정하지 않았다. 실제 기관 원문/API 및 전체 제품 workflow는 미실행. `docs/developer/history/ITERATION_12_REPORT.md` 및 `reports/iteration_12_benchmark.json` 참조.
