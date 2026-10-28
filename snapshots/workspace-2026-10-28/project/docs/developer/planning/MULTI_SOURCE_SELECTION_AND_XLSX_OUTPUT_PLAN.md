# 다기관 탐색·선택·가공·XLSX 실행 기획

**기준일:** 2026-10-25
**상태:** 사용자 요청에 따른 기획안. 구현·API 호출·키 검증은 별도 승인 전까지 미실행.
**상위 문서:** [제품 기획](../../../PROJECT_PLAN.md), [아키텍처](../ARCHITECTURE.md), [운영 계획](../../operator/OPERATING_PLAN.md)
**보존하는 선행 결정:** [D-079](../history/DECISION_LOG.md), [D-080](../history/DECISION_LOG.md)

## 1. 목표

자연어로 요청한 국제 통계를 기관별로 찾고, 정의와 접근 가능성을 비교하고, 사용자가 조건을 확정한 뒤 API 우선으로 수집하며, 원자료·품질·변환·XLSX 산출물까지 추적 가능한 하나의 작업으로 연결한다.

예를 들어 “여러 국가의 총부채를 구해 국가별 위험 비중을 Excel로 보고 싶다”는 요청에는 통계 검색만으로 부족하다. ‘총부채’, ‘위험’, ‘비중’의 뜻과 국가·기간·분모를 먼저 정해야 한다. 시스템은 BIS를 자동 선택하거나 결측 국가를 0으로 처리하거나, 다른 기관 자료를 실패한 후보 대신 조용히 쓰면 안 된다.

목표 흐름은 다음과 같다.

1. 요청을 조건, 목적, 미확정 항목으로 구조화한다.
2. 독립된 기관 후보를 병렬로 찾아 공식 근거와 상태를 기록한다.
3. 방법론·비교가능성 엔진이 원 정의, 기간 의미, 단위, coverage와 API 준비 상태를 근거별로 평가한다.
4. 결과를 바꾸는 미확정 사항을 사용자에게 묻고 확인 snapshot을 만든다.
5. 확정 후보만 수집한다.
6. 원자료를 보존하고 품질과 coverage를 검증한다.
7. 승인된 공식만 변환 엔진에서 실행한다.
8. 출처·계산 근거가 연결된 XLSX와 raw/manifest를 제공한다.

## 2. 기준 상태와 D-079 보존

현재 기준 문서에는 21개 기관 프로필, API 문서 확인 15개, 명세 미확인 6개, 공식적으로 API 미제공이 확인된 기관 0개로 기록돼 있다. 이는 구현된 connector 수가 아니다. 실 API 검증은 World Bank USA/WDI/GDP 한 경로, BEA/e-Stat은 제한된 mock 범위다. 자연어 제품 UI와 XLSX writer는 현재 목표/미구현 기능으로 구분한다. 자세한 상태는 [ARCHITECTURE](../ARCHITECTURE.md), [INSTITUTION_CATALOG](../../operator/reference/INSTITUTION_CATALOG.md), [INSTITUTION_API_AUDIT](../../operator/reference/INSTITUTION_API_AUDIT.md)와 회차 보고서를 기준으로 한다.

D-079는 다음 기본선으로 유지한다.

- metadata/link-only 결과도 유효하며 관측치 수집은 하지 않는다.
- 통계 기관과 API provider, dataset/series ID를 분리한다.
- 선택된 source만 수집하고 자동 대체를 금지한다.
- 기본 원천 XLSX는 Data와 Definitions 두 시트, Excel 기본 서식이며 수식·차트·매크로를 임의 추가하지 않는다.
- 빈도·기간·차원 차이를 자동 join, 보간, forward-fill, resample하지 않는다.
- raw 응답, 요청 정보, 수집 시각, revision/hash는 XLSX와 별도로 보존한다.
- 공식 문서, fixture, connector, live API, live ingestion 증거를 각각 구분한다.

이 문서는 파생 계산 결과의 별도 계약을 제안한다. 기본 원천 XLSX 계약을 소리 없이 바꾸지 않으며, 구현 전에 별도 결정과 gate를 요구한다.

## 3. 사용자에게 보이는 에이전트·엔진 구조

사용자는 에이전트 이름만이 아니라 각 단계의 상태, 선택된 기관, 대기·실패 사유, 미지원 범위, 호출 budget과 승인 대기를 볼 수 있어야 한다. 한 source의 실패가 전체 성공으로 가려지지 않게 한다.

### 3.1 목표 흐름

사용자 자연어 요청
→ 요청 분석 에이전트
→ 오케스트레이터가 사용자별 작업 DAG와 budget 생성
→ 기관 탐색 역할들이 후보를 병렬 조사
→ 메타데이터 정규화 → 방법론·비교가능성 엔진 → 후보 비교
→ 후보 비교 / 필요한 사용자 질문
→ 사용자 확인 snapshot
→ 선택된 API connector
→ raw 보존 / 파싱 / 품질·coverage 검증
→ (요청 시) 별도 변환·가중 엔진
→ XLSX 작성기
→ 결과·근거·실행 이력 표시

피드백·최적화는 요청 처리와 구별되는 Track M/C 운영 흐름이다. 개선 에이전트는 후보와 증거를 제시하지만 코드 수정, 공통 규칙 승격, live 실행을 스스로 승인하지 않는다.

### 3.2 역할과 현재 경계

“에이전트”는 자연어를 이해하고 계획·질문·설명을 맡는다. 원자료 수집·변환·검증은 결정적 Python 엔진이 맡아 재현성을 유지한다. 에이전트가 원자료를 고치거나 공식을 임의로 만들어 실행하지 않는다.

| 보이는 역할 | 연결 엔진 | 책임 | 현재 상태 |
|---|---|---|---|
| 요청 분석 에이전트 | 입력 계약·확인 정책 | 통계·국가·기간·빈도·단위·목적·산출물을 추출하고 빠진 조건을 표시 | 자연어 제품 UI 미구현 |
| 오케스트레이터 | Python workflow/state, 실행 이력 | 단계 의존성, 병렬 탐색, budget, 확인, 중단·재개, 상태 표시 | 공통 workflow 일부 구현 |
| 기관 탐색 역할 | registry, catalog/API document discovery | 등록 기관별 공식 근거·검색 상태를 source별 반환 | 일부 registry/fixture; 전체 live 검색 아님 |
| metadata 정규화 역할 | metadata normalizer | 원문·원어·표준 필드·검색 근거를 연결 | 일부 계약·구성요소 구현 |
| 방법론·비교가능성 엔진(작업명; 최종 명칭 미확정) | 공식 방법론 근거 + 비교 규칙 | 기관 정의·측정 시점·stock/flow·단위·주기·coverage를 검토하고 비교 가능/조건부/불가/미확인을 판정 | 목표 기능; 명칭·계약 포함 구현 필요 |
| 개념 매핑 역할 | concept mapping | 통계 개념 관계와 차이를 근거와 함께 표현 | 일부 관계 분류 구현; 방법론 판정 전체를 대체하지 않음 |
| 기관 connector | source-specific API adapter | endpoint·auth·identifier·paging·response·revision·rate limit·attribution | 기관/데이터별 상이 |
| 수집·품질 엔진 | ingestion, parser, validators | raw·관측치·상태를 검증하고 제한 재시도 및 오류 분류 | 지원 경로만 구현 |
| 계산 역할 | deterministic transformation service | 승인된 공식만 실행하고 입력·공식 버전·분모·중간 상태 연결 | 미구현 목표 |
| XLSX 결과 역할 | workbook exporter/contract | 계산하지 않고 두 시트 및 허용 레이아웃으로 값 작성 | writer 미구현 |
| 개선 역할 | knowledge/improvement, Track M/C | 오류와 피드백에서 개선 후보를 요약 | 자동 수정·승인은 금지, 일부 후보 정리 구현 |

### 3.3 사용자별 엔진 화면과 격리

각 사용자에게 별도 Python 엔진 복제본을 두지 않는다. 공통 실행 엔진을 재사용하고 사용자별 프로필·작업 공간·결과 접근을 분리한다. 프로필에는 언어, 기본 설명 수준, 기관/국가 선호, 승인된 계산 preset, 기본 출력 형식, API budget, credential 참조 권한을 둔다. 사용자는 본인 작업에서 어느 엔진이 실행됐는지와 source별 진행 상태를 볼 수 있다.

사용자별 key, raw 데이터, 이전 선택과 feedback을 다른 사용자에게 노출하거나 검증 없이 공통 지식으로 승격하지 않는다. 비밀값은 secret/env 설정으로 전달하며 LLM 대화, 로그, manifest, XLSX에는 key 자체를 남기지 않는다.

### 3.4 사용자별 엔진 확장 모듈 제안 — 미구현

사용자가 특정 엔진의 작은 부분을 바꿔 써야 할 때 공통 Python 코드를 복사·수정하게 하지 않는다. 미리 계약을 정한 hook(예: 후보 필터, metadata 보강, 수집 후 승인된 변환, 결과 layout)에 사용자별 Python extension package를 연결한다. hook이 없는 엔진 경계는 임의 교체하지 않는다. 이 방식은 여러 기관에 공통 적용하되, hook 입출력과 이용 권한은 기관/source 데이터 범위에 맞춰 제한한다.

실행 코드는 저장소의 `src/`나 `docs/`가 아니라 사용자별 데이터 경로(제안: `MACROATLAS_DATA_DIR/extensions/<user_id>/<extension_id>/`)에 둔다. `.py`는 실행 코드, JSON/YAML manifest는 extension ID/version/hook/schema/capability/resource limits, `.md`는 설명과 사용법을 담당한다. Markdown을 실행하거나 manifest에서 임의 Python 표현식을 읽어 실행하지 않는다. 기본 권한은 네트워크·credential·raw 변경·저장소 직접 쓰기 불가다.

확장본은 실행 전에 문법·의존성·schema 계약과 deterministic fixture로 검증하고 run 시작 시 version/hash를 고정한다. 실행 중 hot-swap하지 않는다. Python 오류가 나면 해당 hook에서 안전하게 멈추고 입력·raw를 보존하며, 승인된 fallback이 명시되지 않은 한 공통 동작으로 조용히 대체하지 않는다. 구문/계약 오류는 파일·행과 수정 가능한 이유를 사용자에게 알려준다. 다른 사용자의 확장에는 접근하지 않는다. 실제 실행 격리·시간/메모리 제한을 검증하기 전에는 사용자 Python 실행을 허용하지 않는다.

## 4. 실행 병렬성

| 단계 | 실행 | 제약 |
|---|---|---|
| 기관별 문서·catalog 후보 조사 | 기관 간 병렬 | source별 timeout/error/evidence를 따로 남김 |
| metadata 정규화·방법론 조사 | 탐색 결과 이후 | 원문과 공식 방법론 근거를 보존하고 근거가 부족하면 미확인으로 둠 |
| 비교가능성·정렬 가능성 판정 | 방법론 근거가 모인 뒤, 사용자 확인 전에 | 월말 기준을 적용할 수 있는지 평가하고 불가능하면 이유와 대안을 제안 |
| 모호한 조건 확인 | 사용자 응답까지 대기 | 답 전 관측치 요청/계산 금지 |
| 실제 수집 | 확인된 후보별 실행, 허용 범위에서 병렬 | 미선택 후보 다운로드 금지, source별 rate/budget 적용 |
| raw parse/검증 | source별 병렬 가능 | provenance·상태·revision 연결 |
| cross-source 정렬·계산 | source와 사용자 정책 확정 뒤 | 자동 align/join/resample 금지 |
| workbook 생성 | 검증과 계산 뒤 | 같은 confirmation snapshot 사용 |
| Track M/C | 독립 offline 작업은 병렬 | live는 공통 platform 및 source gate 동시 충족 |

## 5. 사례: “BIS에서 국가별 총부채”의 정의 확인

### 5.1 먼저 질문할 것

“국가부채”는 정부 부채로 좁혀 이해될 수 있지만, 여기서 원하는 것은 기업·가계까지 포함한 총부채일 수 있다. 채권 위험 분석에서 필요한 입력도 단순 부채 stock 분포와 다를 수 있다. 최소한 다음을 한 번에 확인한다.

1. 부문: 정부만, 정부+비금융기업+가계, 금융기관까지 포함한 전체 경제 중 무엇인가?
2. 범위: 국내·외 채무 전체, 비금융 부문 credit/debt, 비거주자에 대한 외채 중 무엇인가?
3. 측정: stock/flow, gross/net, 연결/비연결, 시장가/액면가 중 무엇인가?
4. 수단: 대출·채권 중심인가, 예금·연금·기타 미지급금까지 포함하는 광의 부채인가?
5. 목적: 세계 전체 stock 대비 국가별 분포, GDP 대비 비율, 포트폴리오 exposure weight, 신용/위험 점수 중 무엇인가?
6. 국가 집합: 모든 국가·지역인가, 특정 공식 coverage 집합인가? 누락을 미완성으로 표시할지, 관측 가능한 국가만 분모로 할지?
7. 기간/주기: 연간/분기, 범위, 연말/분기말, 국가별 최신치 허용 여부?
8. 값 단위: 현지 통화/USD, 통화 환산 출처·시점·방법은 무엇인가?

답이 없어도 후보 정의를 보여줄 수는 있지만, 그 상태에서 “총부채”나 “위험 가중치”를 하나의 확정 지표처럼 계산하지 않는다.

### 5.2 공식 후보를 별개 개념으로 비교

이 표는 공식 통계 페이지를 읽어 만든 조사 출발점이며, MacroAtlas의 API 호출·adapter·live 검증 완료를 뜻하지 않는다.

| 후보 | 공식 범위와 적합 가능성 | 한계 및 구현 전 확인 |
|---|---|---|
| IMF Global Debt Database | 공공+민간 비금융 부문 total gross debt. IMF는 190개 경제의 unbalanced panel, 1950년부터라고 설명. 광범위한 비금융 부문 비교의 우선 탐색 후보 | unbalanced라 국가/연도 결측 가능. 지표별 단위와 GDP 대비 여부를 확인. 정확한 API schema/auth와 MacroAtlas adapter·fixture·live 범위를 확인 |
| BIS Credit to the non-financial sector | 40개 초과 경제, 분기 데이터. 정부와 민간 비금융 부문을 구분하며 가계·기업 세부가 있음. loans·debt securities·currency/deposits 등의 core debt 설명 제공 | 전 세계 전 국가 coverage 아님. credit과 사용자가 뜻한 모든 liabilities가 자동 동등하지 않음. 특정 series의 source/provider, instrument, valuation, 국가·기간을 확인 |
| World Bank IDS | 주로 저·중소득국 external debt. 국가별 총 외채 stock 질문 후보 | 외채는 국내 채무 포함 전체 부채가 아님. 일부 국가는 공공 외채만, 일부는 민간도 포함. 대체로 연간. indicator별 범위와 API 경로 확인 |
| World Bank/IMF QEDS | 참가국 분기 외채, 부문·만기·수단·통화 분해 가능 | 참여국이 제한되고 IDS와 방법·수정 주기가 다를 수 있음. IDS 값과 단순 병합 금지. 참가국, 표/API route, revisions 확인 |
| OECD Financial Indicators | 전체 경제 및 부문별 연간 금융 계정/대차대조표. 광의 부채 수단 포함 가능 | 부채 항목의 coverage가 국가/부문별로 다를 수 있어 비교 주의. 정확한 series, API/SDMX route, revision, adapter 상태 확인 |

공식 근거: [BIS Credit to the non-financial sector](https://data.bis.org/topics/TOTAL_CREDIT), [IMF Global Debt Database](https://data.imf.org/Datasets/FAD_GDD), [World Bank Debt Statistics FAQ](https://www.worldbank.org/en/programs/debt-statistics/faq), [IDS와 QEDS 차이](https://datahelpdesk.worldbank.org/knowledgebase/articles/826488-what-is-the-difference-between-external-debt-stoc), [OECD Financial Indicators dashboard](https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_FIN_DASH%40DF_FIN_DASH_S1M&df%5Bvs%5D=1.0&pg=0&snb=30&tm=health+coverage).

Iteration 22의 BIS 공식 문서 재검토는 이 후보의 해석을 더 구체화했다. BIS NFS 계열은 gross liabilities이며, 일반정부는 연결·민간 비금융부문은 비연결 기준이다. `total credit`은 표에 따라 차입자 부문 합계 또는 민간 비금융부문에 대한 모든 lender 범위를 가리킬 수 있다. 분기·분기말 잔액, 계절조정 없음, 국가별 상이한 기간/coverage를 보존해야 한다. 그러므로 이 자료를 일반 국가부채나 위험 가중치로 곧바로 바꾸지 않는다. API/dataflow 근거와 미확인 항목은 [BIS 공식 근거 프로필](../connectors/BIS.md)에 기록한다.

IMF GDD 공식 dataset page에 API/download가 표시된다는 사실도 해당 series가 MacroAtlas에서 API로 호출된다는 증거는 아니다. 실제 요청 계약·인증·adapter·응답을 별도로 검증한다. 이번 기획에서는 기관 API를 실행하지 않았다.

### 5.3 부채 비중과 위험 weight

단순 부채 비중은 승인된 절대 debt stock에 대해, 같은 시점의 지정 모집단 국가별 값/그 시점 분모 합으로 계산할 수 있다. 그러나 다음 조건이 먼저 정해져야 한다.

- 모든 분자 값이 같은 개념·단위·환산 규칙인지 확인한다.
- 분모에 포함하는 국가 모집단과 데이터 coverage를 기록한다.
- 결측 국가를 0으로 대체하지 않고, 관측 수/목표 수/coverage 및 분모를 남긴다.
- GDP 대비 부채율은 절대 stock이 아니므로 부채액 점유율 공식에 그대로 사용하지 않는다.
- 현지 통화를 합산해야 한다면 환율 source, 날짜, 방향, 환산 정책을 승인받는다.

이 계산은 **선택된 데이터 모집단에서의 부채 분포 비중**이지, 포트폴리오 exposure weight나 신용위험 weight가 아니다. 이처럼 계산 결과가 데이터 의미에 달린 경우 방법론·비교가능성 엔진이 부문·측정시점·분모·coverage와 사용 목적을 먼저 검토한다. 채권 위험 가중치는 위험 정의·포트폴리오 노출·만기/통화 등 별도 방법론을 확정해야 하며, 부채 비중을 자동으로 그 이름으로 출력하지 않는다.

## 6. API 우선과 source별 상태

각 후보는 다음을 따로 표시한다.

1. 공식 데이터셋/정의 URL 확인
2. 정확한 데이터셋의 API 문서와 route 확인
3. 인증·쿼터·rate limit·paging·이용 조건 확인
4. MacroAtlas source adapter 구현
5. 정상·empty·missing·auth failure·429·timeout·schema drift fixture 확인
6. 해당 데이터셋 bounded live 요청 여부
7. 수집·저장·read-back·raw lineage·복구 확인 여부

정확한 데이터의 공식 API가 검증된 경우 API를 우선한다. API 문서 미확인은 API 미제공이 아니다. endpoint를 추측해 호출하지 않는다. 공식적으로 해당 자료에 API가 없거나 부적합함을 확인한 뒤에만 공식 파일/SDMX bulk 경로를 별도 fallback으로 비교한다. browser scraping은 자동 대안으로 쓰지 않는다.

기관별 문서는 공통 항목(auth, IDs, response, language, revisions, licenses, limits, fixtures, live evidence)을 공유하되, 기관 고유 정의와 예외는 기관 문서 및 fixture로 남긴다. 21개 기관을 하나의 adapter나 한 구현 task로 처리하지 않는다.

### 6.1 카탈로그 18개 후보의 접근 경로와 현재 상태

아래 18개 프로필은 [21개 기관 카탈로그](../../operator/reference/INSTITUTION_CATALOG.md)에서 World Bank(INT-04), BEA(US-04), e-Stat(JP-03) 세 기준 프로필을 제외한 후보들이다. 세 기준 프로필도 나머지 기관과 같은 source gate를 거친다. 표의 분류는 공식 자료에서 확인한 **접근 경로의 종류**이지 MacroAtlas 구축 완료 상태가 아니다. 기존 공식 문서 감사의 전체 집계는 API 문서 확인 15개, 미확인 6개, 공식적으로 API 미제공 확인 0개다. `unconfirmed`는 API가 없다는 뜻이 아니다.

Federal Reserve Board와 St. Louis Fed FRED/ALFRED는 카탈로그상 각각 기관 프로필이지만, Board DDP 계열 중 일부의 제공 경로는 St. Louis Fed가 운영하는 FRED API다. 따라서 검색 결과에는 원 통계 기관과 API 제공자를 따로 기록하고, 같은 계열을 중복 후보나 독립된 두 관측치처럼 세지 않는다.

| 기관 프로필 | API 우선 후보 경로 및 공식 근거 | 확인된 보조 경로·주요 제약 | MacroAtlas 상태와 다음 gate |
|---|---|---|---|
| IMF (INT-01) | SDMX 2.1·3.0 Data API ([공식 안내](https://data.imf.org/en/Resource-Pages/IMF-API)) | API 탐색 도구 로그인이 API 인증 요건을 확정하지 않는다. dataset별 route·auth·정의·coverage 확인 | API 문서 확인; 기관 adapter·fixture·live 미완료. 구체 dataset 선정 후 request fixture |
| BIS (INT-02) | SDMX REST API v2, 데이터·구조·metadata 조회 ([공식 명세](https://stats.bis.org/api-doc/v2/)) | SDMX 2.1 응답 하위집합. 전체 국가를 포괄한다고 전제하지 않음 | 문서/일부 형식 fixture; 전용 adapter·live 미완료. 사용자 부채 사례의 대표 예시 중 하나이며 전기관 검증의 유일한/첫 우선 source로 한정하지 않음 |
| ECB (EU-01) | SDMX 2.1 REST ([공식 안내](https://data.ecb.europa.eu/help/api/overview)) | flow·DSD·코드 목록과 계열 정의를 dataset별 조사 | 일반 SDMX fixture만 있음; ECB 전용 adapter·live 미완료 |
| Eurostat (EU-02) | Catalogue API와 SDMX 2.1·3.0 데이터 API ([공식 안내](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction)) | catalog 검색과 observation 조회는 분리. 전체 다운로드는 비동기·용량 정책 점검 | 일반 SDMX/catalogue fixture; 전용 adapter·live 미완료 |
| OECD (INT-03) | SDMX REST ([공식 Swagger](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1)) | 외부 접근성·인증·쿼터는 실행 전 최신 문서와 제한된 요청으로 확인 | API 문서 확인; adapter·기관 fixture·live 미완료 |
| Federal Reserve Board (US-01) | Board DDP 계열 중 제공 대상은 FRED API 경유 ([Board 안내](https://www.federalreserve.gov/data/data-download-fred-information.htm), [FRED API](https://fred.stlouisfed.org/docs/api/fred/)) | 원 기관은 Board, API 제공자는 St. Louis Fed. 계열별 crosswalk·전환·이용조건 및 `FRED_API_KEY` 확인 | 별도 Board adapter 없음; FRED 경유 대상 계열과 출처 귀속을 확인하고 FRED 경로와 중복 계산하지 않음 |
| FRED/ALFRED (US-02) | FRED API v1/v2, series·release·vintage 탐색 ([공식 API](https://fred.stlouisfed.org/docs/api/fred/)) | 키 필요. series별 원 제공기관의 이용조건·revision/vintage 범위 기록 | API 문서 확인; adapter·fixture·live 미완료 |
| BLS (US-05) | Public Data API v1/v2 ([개발자 안내](https://www.bls.gov/developers/home.htm)) | 요청 시 정확한 series ID 필요. v2 등록과 요청 제한을 series/기간 요청별로 확인 | API 문서 확인; adapter·fixture·live 미완료 |
| U.S. Census Bureau (US-06) | Census Data API ([개발자 안내](https://www.census.gov/data/developers.html)) | dataset별 제공 변수와 필드가 다름. 데이터 요청 키·변수 수·프로그램별 조건 확인 | API 문서 확인; adapter·fixture·live 미완료 |
| Bank of Japan (JP-01) | Time-Series API, JSON/CSV ([공식 안내](https://www.stat-search.boj.or.jp/info/nme_aphelp_en.html)) | 표/시계열 식별자, 언어별 metadata, 이용 제한을 표별로 확인 | API 문서 확인; 전용 adapter·fixture·live 미완료 |
| Deutsche Bundesbank (EU-03) | SDMX REST, data·metadata ([공식 안내](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448)) | 형식·요청 크기·413/비동기 응답과 인증 상태 확인 | API 문서 확인; adapter·기관 fixture·live 미완료 |
| INSEE (EU-05) | SDMX 2.1 REST, BDM/idbank ([공식 안내](https://www.insee.fr/en/information/2868055)) | idbank와 차원/codelist를 연결하고 언어·수정 이력을 확인 | API 문서 확인; adapter·fixture·live 미완료 |
| Treasury TIC (US-03) | 정확한 표의 API 여부를 먼저 재조사. 현재 감사에서 일반 공개 API 명세는 미확인 | 공식 월간 ZIP archive는 HTML·TXT·CSV 등 여러 파일을 포함하며 릴리스 시점에 따라 형식이 다름 ([공식 archive](https://home.treasury.gov/archives-of-tic-monthly-data-releases)); API 경로가 표별로 확인되지 않을 때만 파일 파서 후보 | API `unconfirmed`; CSV/codebook fixture는 live 증거가 아님. 파일 manifest와 표별 parser를 확인 |
| Bank of England (EU-04) | 표별 API 제공 여부를 우선 조사; 현재 일반 공개 통계 API 명세 미확인 | Bankstats의 HTML·Excel·XML·CSV 다운로드 ([공식 DB](https://www.bankofengland.co.uk/boeapps/database/)); 파일 버전·표 구조 변경을 감지해야 함 | API `unconfirmed`; API 부재로 단정하지 않음. API 확인 뒤 파일 경로와 비교 |
| Japan Ministry of Finance (JP-02) | MOF 표별 API 및 다른 공식 배포 API(e-Stat 포함 여부)를 먼저 확인 | 일부 공식 표는 CSV·SDMX 파일을 제공 ([공식 데이터 목록](https://www.mof.go.jp/policy/international_policy/reference/official_reserve_assets/data/index.htm)); 기관 책임과 실제 배포 provider 구분 | API `unconfirmed`; 파일은 통계별 후보. API 확인 뒤 table-specific parser 검토 |
| PBOC (CN-01) | 영어 공식 API/catalogue 문서를 먼저 찾고 정확한 통계표별 공개 경로를 조사 | 안정된 공개 API 사양은 현재 확인되지 않음. 원문이 필요한 경우 중국어 자료와 영문 translation provenance를 보존 | API `unconfirmed`; 수집 미지원. API/파일 사양·약관·요청 가능성이 확인되기 전 adapter/live gate 미통과 |
| SAFE (CN-02) | BOP/IIP/외환 통계별 공식 API·download route와 이용조건부터 조사 | 공개 API 문서 미확인은 API 부재 증거가 아님. 영문 제공 여부를 표마다 확인 | API `unconfirmed`; 수집 미지원. 접근·이용조건 조사 gate 통과 전 구현 범위 확정 금지 |
| China NBS (CN-03) | National Data의 dataset/table별 API 또는 공식 download 명세를 조사 | 포털 접근만으로 안정된 공개 API를 추정하지 않음. 영어 우선, 미제공 시 중국어 원문 보존 | API `unconfirmed`; 탐색/수집 경로 미검증. table-level 사양·이용조건 조사 gate 필요 |

#### 구현 순서와 교차 기관 gate

1. **전기관 readiness와 공통 fixture gate**: 21개 기관을 모두 검증 대상으로 포함하고 API 문서·provider·fixture·adapter·live 상태를 분리한다. 전체 offline suite 통과를 source live 통과로 취급하지 않는다.
2. **SDMX 공통 전송 기능을 재사용하며 기관별로 확장**: IMF, BIS, ECB, Eurostat, OECD, Bundesbank, INSEE를 하나의 Max API-family batch로 분석할 수 있다. 다만 기관별 identifier·auth·language·revision·rate policy·methodology·fixture·live gate는 독립한다.
3. **개별 REST 경로**: World Bank, BEA, e-Stat, FRED/ALFRED, Board DDP via FRED, BLS, Census, BOJ. 공통 request/retry harness를 공유해도 기관·provider·series lineage와 access result는 분리한다.
4. **API 미확인 6개 표별 조사**: TIC, Bank of England, MOF, PBOC, SAFE, China NBS의 대상 표에 공식 API가 있는지 먼저 조사한다. API가 없거나 부적합하다는 표별 공식 근거가 확인된 뒤 공식 파일 경로를 검토한다. `unconfirmed`를 `not_offered`로 추측 변경하지 않는다.
5. **source별 offline E2E 후 bounded live**: 각 source의 fixture·저장/read-back·오류 복구 gate를 확인하고 준비된 provider만 minimal official request로 live canary를 수행한다. API 미확인 기관은 공식 접근 경로가 확정되기 전 호출하지 않는다.
6. **seeded random과 장기 시험**: offline source fixture 전체는 재현 seed와 함께 선택한다. 2h/6h live 시험은 provider budget·약관·rate limit에 맞는 승인된 source에 한정하고 외부 서버에 동시 부하를 주지 않는다.

오프라인 문서 조사·fixture 작업은 서로 독립일 때 병렬화할 수 있다. 각 코드 회차는 source 또는 명확한 공통 계약 하나로 제한하고 gate를 순차 통과한다. 실 API 호출은 그 source의 문서·fixture·adapter 및 공통 platform gate가 모두 통과한 경우에만 별도 승인 범위로 실행한다. 공식 문서의 존재, fixture 성공, API 응답, end-to-end 수집은 서로 다른 증거다.

## 7. 요청 파이프라인과 통과 gate

**Gate 0 — 요청:** 통계 개념·목적·국가 집합·기간/빈도·단위·출처 선호·metadata-only/data·파생 결과·레이아웃을 구조화한다. 핵심 의미가 불명확하면 질문한다.

**Gate 1 — 후보 검색:** 공식 API/document/catalog 근거로만 후보를 만들고 source별 검색 실패와 상태를 보존한다. API metadata 검색과 데이터 다운로드를 혼동하지 않는다.

**Gate 2 — 방법론 비교와 확인:** metadata와 공식 methodology 근거를 연결해 agency/provider, 개념, stock/flow, 측정 시점, 단위·빈도·범위·revision·언어를 비교한다. 비교가능성과 날짜 정렬 가능성 및 근거 수준을 표시한다. 영어 자료를 우선하고 영어가 없으면 일본어/중국어 원문을 유지한 뒤 영어 중간 표현을 거쳐 한국어 설명을 만든다. 식별자·숫자·단위는 번역하지 않는다. 사용자가 선택한 snapshot 없이는 수집하지 않는다.

**Gate 3 — 수집:** 선택한 source/dataset/period/dimensions만 호출한다. 기관별 fixture/source gate와 공통 platform gate가 모두 필요하다. 키는 출력하지 않는다.

**Gate 4 — 품질/coverage:** schema, duplicate, missing/zero/status, unit, country code, date/frequency, revision을 검증한다. 미지원 국가를 성공값처럼 숨기지 않는다.

### 방법론·비교가능성 엔진과 시계열 정렬

이 엔진은 raw 관측치를 바꾸지 않는다. 각 후보의 공식 methodology 문서, API metadata, classification/code list, 단위·빈도·측정 기준을 모아 비교 근거를 만든다. 원문 링크와 조회 시각을 보존하고, 자료가 부족하거나 출처끼리 충돌하면 unknown/review_required로 돌린다. 이름 유사성만으로 동등성이나 정렬을 승인하지 않는다.

먼저 기간 라벨과 관측 시점을 구분한다. 월별 label, 월평균, 월중 유량, 월말 stock, 분기말 stock, 일별 관측치는 같은 날짜처럼 보여도 다른 의미일 수 있다. 엔진은 stock/flow, reference period, end-of-period/average, calendar/business day, timezone, frequency, revision을 확인한다.

월말 정렬은 공식 방법론이 월말 stock임을 뒷받침하고 series의 관측 의미가 맞을 때만 가능한 정책으로 제안한다. 월별 평균이나 유량을 월말 stock으로 바꾸지 않는다. 일별 값에서 월말 관측치를 뽑으려면 마지막 영업일·실제 월말·이전 가용일 중 무엇을 쓸지와 결측 fallback을 승인받는다. 분기·연간 자료를 월별로 늘리거나 선형보간/forward-fill하는 것은 자동으로 하지 않는다.

판정은 aligned_without_transform, alignable_under_approved_policy, not_alignable, unknown_requires_review 중 하나와 이유/evidence를 반환한다. not_alignable 또는 unknown이면 cross-series 계산을 멈추고 사용자에게 대안을 제시한다: Data 시트에 source-native period를 long 형태로 둔다, 계열별 별도 시트를 둔다, 별도 workbook을 만든다, 비교 계산을 보류한다. 별도 시트 제안은 D-079 기본 Data/Definitions 두 시트 계약을 자동 변경하지 않으며, 사용자가 layout 변경을 명시적으로 선택해야 한다. 통계적으로 정렬할 수 없으면 불가 사유를 그대로 표시한다.

**Gate 5 — 가공·계산:** 방법론 엔진이 feasibility와 정책을 판정하고 사용자가 승인한 뒤에만 deterministic transformation engine을 실행한다. 입력 series ID/hash/revision, operation order, formula version, period별 denominator, missing/coverage, 환율·정렬 정책, 결과 hash를 연결한다. 분모 0, 단위 차이, 중복, 결측은 fixture로 검증한다.

**Gate 6 — XLSX:** Data/Definitions 두 시트와 기본 서식을 쓴다. 값만 작성하고 workbook 수식·차트·매크로를 만들지 않는다. raw와 manifest는 따로 보존하고 column-to-definition map을 검사한다.

**Gate 7 — live/soak:** 작은 bounded canary, 복구 확인, source별 batch, 승인된 2h/6h soak 순으로 확장한다. 장시간 실행은 source budget, 취소/재개, partial write, 중복, credential 만료, schema drift를 포함해야 한다. 이번 일은 live 실행이 아니다.

## 8. 국가별 XLSX의 출력 계약 제안

D-079의 일반 source-data 계약은 계속 적용한다. 계산이 승인된 사례에 한해 별도 derived artifact를 추가 제안한다.

- **Data:** 요청된 기간별 행과 국가별 비중 열을 배치할 수 있다. 동일 시점·주기·모집단과 계산 조건을 충족해야 한다. 계산된 값만 넣고 Excel 수식은 넣지 않는다.
- **Definitions:** 각 국가 열과 source series ID, 원 정의, agency/provider, unit, coverage, 기간, retrieval time, formula ID/version, denominator population을 연결한다.
- **Raw/manifest:** API 원응답, 정규화 source observation, 요청 조건, source/revision/hash, 계산 입력과 결과 연결은 workbook 밖에 보존한다.
- **기간 불일치:** 방법론·비교가능성 엔진이 통계적 근거로 월말 정렬 가능 여부를 먼저 판정한다. 가능하더라도 정책과 결측 fallback을 확인한 뒤 가공한다. 불가/미확인은 이유를 표시하고 source-native long Data, 계열별 별도 시트, 별도 workbook, 계산 보류 중 선택을 제안한다. 별도 시트는 D-079의 기본 2-sheet 계약 변경을 사용자가 승인한 경우에만 쓴다.
- **유형 구분:** source-data export와 derived export를 구분하고 raw 원자료가 파생 workbook에 의해 대체되지 않게 한다.

기본 source-data workbook이 원 관측치를 담는다는 D-079와 달리, 위 derived view는 Data에 파생 비중을 담는 신규 output 유형이다. 사용자가 이 확장을 검토하고 별도 구현 gate가 승인되기 전에는 이 출력 계약을 코드로 간주하지 않는다.

## 9. 향후 엔진·모듈별 실행과 모델 할당 권고 — 이번에는 미실행

실행 전에는 이 기획과 개발 문서를 먼저 검토·갱신한다. “엔진별 수정”은 조금 더 정확히 **엔진·모듈별 수정**이라고 부른다. 엔진은 책임과 입출력 경계이고, 모듈은 저장소에서 실제 편집할 수 있는 코드·테스트·문서 범위다. 5개는 현재 10개 세부 work package를 담는 상위 실행 묶음이며, 각 구현 task는 한 엔진이나 서로 맞물린 작은 모듈 범위로 좁힌다. AGENTS.md의 High iteration 하나/task 규칙과 기관별 source gate를 유지하므로, 5개 묶음은 5번의 거대 구현을 뜻하지 않는다.

| 상위 묶음 | 주로 수정할 엔진·모듈 | 이 묶음에서 하는 일 | 오케스트레이터 처리 |
|---|---|---|---|
| 1. 요청·탐색·metadata 기반 | 요청 분석/자연어 계약, `discovery/`, `metadata/`, `mapping/`, source capability registry | 요청 조건 구조화, 기관/series 검색, 원문 metadata 보존과 후보 근거 정규화 | 입력/출력 상태나 병렬 DAG가 바뀔 때만 별도 변경. 단순 parser·normalizer 내부 변경이면 그대로 둠 |
| 2. 방법론 판정과 BIS 세로 사례 | 방법론·비교가능성 모듈(작업명), `mapping/`, BIS `connectors/`·`ingestion/`·fixture | 공식 정의·coverage 판정, BIS debt 계열의 metadata→fixture→선택 수집 계약을 하나의 대표 흐름으로 검증 | 확인 질문·source 선택 상태·단계 의존성이 실제로 달라질 때 integration task로 연결 |
| 3. 기관 connector와 수집 품질 | `connectors/`의 기관별 SDMX/REST/file 모듈, `ingestion/` parser·validator·retry, raw `storage/` | API-first, 기관 인증/식별자/응답별 파싱, 원자료·출처·revision 저장 및 기관별 오류 fixture | 기관 connector 추가만으로 수정하지 않음. 공통 상태·오류/복구 계약이 바뀔 때만 연결 |
| 4. 결정적 가공과 XLSX | `analysis/` transformation, XLSX exporter, 계산 provenance/manifest storage | 승인된 정렬·집계·비중 계산, 정의와 입력 series lineage, source/derived workbook 출력 | 새 단계가 workflow DAG나 사용자 확인 상태를 바꿀 때 별도 연결 |
| 5. 오케스트레이터 통합·회귀·장기시험 | `orchestration/` runner/workflow, 통합 테스트, seed 기반 offline test runner, 승인된 soak 제어 | 엔진 계약을 연결하고 단계·상태·예산·실패·취소·resume·read-back을 end-to-end 검증 | 여기서 수정이 필요할 수 있음. 앞선 엔진 gate 통과 후 변경하고 전체 workflow 회귀를 통과시킴 |

5개 묶음은 work package를 기능 이름으로만 합친 것이 아니라 수정 대상 모듈과 연결 지점을 지정한다. 실제 task마다 바꿀 모듈과 손대지 않을 인접 모듈을 명시한다. 둘 이상의 엔진이 바뀌어야 하면 엔진별 변경과 통합 변경을 구분해 task/gate를 나눈다.

유지보수와 코드 효율화는 5개 뒤에 붙는 여섯 번째 순차 단계를 만들지 않는다. 모든 묶음과 현재 공통 모듈에 걸치는 **Track M**으로 운영한다. 즉 오류나 피드백이 `discovery/`에서 났으면 그 모듈을, 특정 connector에서 났으면 해당 source 모듈을, 여러 모듈의 계약에서 났으면 영향을 받는 모듈과 오케스트레이터 통합을 대상으로 한다. 기관 추가는 별도의 **Track C**로 두고 두 트랙은 독립된 offline 작업을 병렬로 할 수 있다.

아래 10개 work package는 산출물과 gate를 추적하기 위한 세부 체크리스트다. 한 번에 모두 구현하라는 요청은 아니다.

| # | 작업 묶음 | 주 산출물 / gate |
|---|---|---|
| 1 | 자연어 요청 schema와 모호성 질문 | 부채/외채/정부부채/위험 비중 구별 fixture |
| 2 | 사용자 profile과 orchestration status UI 계약 | 사용자별 격리, 실행 DAG, 단계/source 상태와 budget 표시 |
| 3 | API evidence/capability registry | 문서·auth·API/file route·adapter·fixture·live 독립 상태 |
| 4 | 기관별 병렬 discovery | 기관 간 검색 병렬화, 오류/evidence 분리, metadata-only 종료 |
| 5 | metadata 정규화·원문 보존 | source-native 필드·언어·정의·ID·evidence 매핑 |
| 6 | 방법론·비교가능성 엔진 | 공식 methodology evidence, stock/flow·시점·단위·주기 평가, alignment feasibility와 이유 |
| 7 | 선택된 source 수집 workflow | 확인 snapshot, API-first, 기관별 connector·fixture |
| 8 | 국가/기간 품질과 coverage | 결측·단위·국가 코드·period semantics·coverage 검증, 자동 align 방지 |
| 9 | deterministic transformation engine | 승인된 정렬/집계/가중 공식, input lineage, 결과/coverage fixture 검산 |
| 10 | XLSX, E2E, live readiness | 기본 2-sheet와 승인된 별도-sheet 제안, raw/manifest, read-back/resume, Q&A scenarios |

Luna Max 실행에서는 동일한 API protocol/공통 계약을 쓰는 source를 한 batch로 구현할 수 있다. 단, acceptance 결과는 source와 구체 dataset/table별로 분리한다. API 문서 미확인 6개는 표별 조사부터 하고 명세를 상상해 구현하지 않는다. 공통 계약이 다른 source는 별도 gate로 분리한다. 전체 21개 기관의 일정은 정확한 API, auth, 이용조건, fixture 복잡도를 확인한 뒤에만 산정한다. 운영계획의 단순 API 1–3일, SDMX/auth/revision/대용량 3–7일 이상은 초기 추정치이며 보장이 아니다.

### 9.1 엔진별 변경과 모델 배정

향후 일반 변경은 **한 번에 한 엔진**을 대상으로 한다. 구현 전에 해당 엔진의 책임, 입력·출력 계약, 바뀌지 않아야 할 동작, 연관 fixture, 통과 gate, 변경 허용 파일을 정하고 그 범위에 맞는 모델을 task 시작 때 배정한다. 모델 배정은 아직 MacroAtlas 기능이나 자동 라우터가 아니며, 사람이 실행 task에 지정하는 운영 절차로 제안한다.

| 변경 종류 | 기본 배정 원칙 | 사람 검토·상향 기준 |
|---|---|---|
| 경계가 안정된 단일 엔진의 제한된 수정 | 사용자가 task 시작 때 지정한 모델을 배정한다. 현재 전기관 검증 실행안은 Luna Max 기준으로 크기를 잡는다. | 계약 변경, 데이터 의미 변경, gate 실패 시 중지 후 재평가 |
| 기관 connector·parser | 한 기관과 구체 dataset/table을 한 High iteration으로 묶고, 문서 근거와 deterministic fixture를 같은 task에 포함 | 미확인 API/auth/이용조건은 구현을 멈추고 조사 gate로 분리 |
| 방법론·비교가능성 또는 가공 공식 | 각 엔진을 분리한다. 공식 정의·결측·분모·기간 의미를 fixture로 고정한 뒤 계산 엔진을 별도 검토 | 통계적 동등성, 월말 정렬, 환율, 위험 가중치처럼 결과 의미가 큰 판단은 강한 추론 모델과 사람이 근거를 검토 |
| 여러 엔진·공통 계약을 바꾸는 오케스트레이터/상위 구조 | 사용자 지정의 강한 모델로 별도 통합 task를 수행하고, 영향 엔진과 순서를 명시 | 변경 전 사람이 contract map과 영향 범위를 정하고, 각 엔진 gate 통과 후 통합 회귀 승인 |
| 사용자가 요청하는 대규모 구조 변경 | 자동화 묶음으로 쪼개지 말고 사용자가 지정한 좋은 모델과 사람 주도로 별도 기획·수정 | 범위·승인·통합 계획을 명시하고 단계별 리뷰 |

오케스트레이터 수정은 모든 엔진 변경에 자동으로 따라붙지 않는다. 아래 중 하나가 바뀔 때만 별도 integration task로 연다: 엔진 입력·출력 계약, DAG 의존성·순서·병렬성, source별 상태/오류 전파, retry·취소·resume, 사용자 확인 지점, budget·credential 전달, 결과 provenance. 엔진 구현과 단위 gate가 통과한 뒤 오케스트레이터가 계약을 연결하고 전체 workflow 회귀를 수행한다. 엔진 내부 변경이 기존 계약 안에 머물면 오케스트레이터는 건드리지 않는다.

각 실행 task에는 목표, 작업 대상 엔진, 배정 모델/추론 수준, 선행 계약, 허용 파일, fixture와 gate, 네트워크 허용 여부 및 budget, 중단 조건, 결과 보고 형식을 적는다. 모델이 변경 범위를 넓히거나 다른 엔진을 함께 수정할 필요를 발견하면 즉석에서 확장하지 않고 영향 분석과 다음 task 제안을 기록한다.

이번 문서 변경으로 모델 자동 선택, 에이전트 배정, 오케스트레이터 코드, connector, credential, live 실행은 구현하지 않는다. 이 운영 방식을 실제로 시작할 때 별도 승인된 High iteration과 task별 모델 지정이 필요하다.

### 9.2 유지보수·메모리 측정·코드 효율화 단계

매주 오류/사람 피드백을 재현하고, 2주마다 같은 workload에서 wall time·CPU·peak RSS·Python allocation·요청/중복/전송량을 측정한다. 수치로 확인한 병목만 대상 엔진·모듈과 변경 가설을 지정해 수정한다. 수정 전후의 동일 조건 결과와 hash·행 수·단위·결측/0·read-back·복구 결과를 비교하고 사람 diff 검토를 받는다. 개선이 반복 측정에서 확인되지 않거나 정확성·복구 조건이 나빠지면 수정하지 않거나 되돌린다. 근거가 부족하면 코드 변경 없이 기준선과 미해결 원인만 기록한다.

이 유지보수 loop는 [운영 계획의 Track M](../../operator/OPERATING_PLAN.md)과 같은 주기를 사용한다. 성능·메모리 측정은 대기 중인 모든 기관 추가가 끝날 때까지 기다리지 않는다. 다만 측정 workload와 수정할 모듈의 책임·입출력 계약은 고정한다. 개선이 여러 엔진의 계약이나 workflow 상태를 바꾸면 각 엔진 gate 뒤에만 오케스트레이터 통합 변경을 추가한다.

## 10. 무작위 전 기관 장기 테스트

랜덤 테스트 모집단은 임의 URL이 아니라 공식적으로 발견됐고 실행 가능한 dataset/series다.

- source·dataset·frequency·period·dimension·language 층으로 population을 정의한다.
- seed와 선택된 IDs, parameters, code version, response hash로 재현한다.
- 먼저 fixture에서 empty, missing, paging, revision, auth, 429, timeout, duplicate, schema drift, partial save/resume를 시험한다.
- live 표본은 source gate 후에만 선택하고 기관별 rate limit, request cap, 시간·비용 budget을 적용한다.
- 2h/6h soak은 취소/재개와 오류 회복을 검사하는 별도 단계다. 재시도로 서버를 과부하하지 않는다.
- 성공률, 실패 종류, 호출/중복 수, coverage, 복구 시간·성공률, 처리량, 미검증 기관을 기록한다.
- random seed는 선택 과정을 재현할 뿐 표본의 대표성을 보장하지 않으므로 strata별 coverage도 보고한다.

## 11. 인수 시나리오

1. “총부채 정의와 출처만 찾아줘” → 후보·정의·링크·API 상태만 반환, observation 호출은 없음.
2. “BIS에서 전 세계 국가 총부채” → BIS의 실제 coverage와 개념을 설명하고 전 세계 coverage가 아니면 다른 후보를 별도로 보여줌.
3. “BIS·IMF·World Bank 비교” → 서로 다른 dataset을 하나로 합치지 않고 기관/통계 provider/정의/coverage/API 상태별 비교.
4. “정부+기업+가계 비금융 gross debt” → 해당 정의 근거·정확한 series·단위·기간 확인 후 선택을 받음.
5. “국가별 부채 비중 계산” → 절대액/분모/국가 모집단/환율/missing/목적을 확인하기 전에는 계산하지 않음.
6. 승인된 동시점 stock으로 계산 → 계산 값, 공식 ID, 입력 revision, coverage/denominator를 기록; missing-to-zero 금지.
7. 두 series의 시계열이 다름 → 방법론 엔진이 월말 기준의 통계적 타당성을 검토. 타당하고 정책이 승인되면 변환 엔진이 정렬한다. 불가/미확인이라면 이유를 적고 long Data, 별도 시트, 별도 workbook, 계산 보류 중 대안을 제안한다. 별도 시트는 사용자 승인이 필요하다.
8. API docs는 있으나 connector 미구현 → 공식 링크와 미실행 상태만 제공, source 성공으로 세지 않음.
9. 403/429/timeout/schema drift → retryable/terminal/review를 분리하고 raw evidence와 source 실패 상태 보존.
10. wide XLSX 요청 → 동일 period/정의/계산 조건이 충족되면 date 행·country 열 제공. 모든 열은 Definitions로 추적.

## 12. 기존 결정과 미확정 제안

| 항목 | 현재 기준 | 확정 시점 |
|---|---|---|
| API-first | 정확한 dataset API를 먼저 확인. API 미확인은 no-API 아님 | 각 source task |
| 후보/수집 분리 | metadata-only는 정상 종료, 선택 후 관측치 수집 | D-079 유지 |
| 기본 source workbook | Data/Definitions, 기본 셀 서식, 수식/차트/매크로 없음 | D-079 유지 |
| 기간 mismatch | 방법론 근거 없이 자동 align 금지. 승인된 정책만 변환 엔진이 실행 | D-079 유지 |
| 방법론·비교가능성 엔진 | official methodology evidence를 바탕으로 의미와 시점 정렬 feasibility를 결정하고 불가/미확인은 중단·제안 | 신규 제안; 별도 구현 gate 필요 |
| derived workbook | Data에 계산값, Definitions에 formula/input map, raw 별도 | 제안; export 구현 전 결정 |
| 전 세계 모집단 | 국가/territory 목록, coverage threshold와 missing 정책 미확정 | 부채 사례 확인 때 |
| 위험 weight | debt share와 portfolio/risk weight 구분 | risk methodology 승인 전 |
| source API 경로 | 공식 docs에서 exact dataset API 재확인. API badge는 live 증거가 아님 | 각 기관 구현 전 |
| 여러 기관 파일 구성 | 기본은 source-native/선택 후보별 산출. cross-source derived 비교는 사용자 명시 선택 | exporter 구현 전 |

## 13. 운영 승인 순서와 범위

기획과 실행안을 분리한다. Iteration 21의 offline benchmark 재현성 작업은 Gate L, Iteration 22의 BIS 대표 통계 근거 조사는 Gate M, Iteration 23의 전체 21기관 readiness audit/offline suite는 Gate N으로 기록했다. BIS는 부채 분석 예시이지 전기관 검증의 유일한 source가 아니다. 이후 기관별 adapter·fixture·live, 변환/XLSX와 장기시험은 [Luna Max 실행안](../EXECUTION_PLAN.md)과 [전기관 검증 프로그램](../testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)의 source별 gate를 따른다.

1. **Plan review:** 역할 도식, 부채 정의 질문, 방법론 판정·가공 분리, 파생 파일 계약, 10개 작업 분할을 사람 검토.
2. **Iteration 선택:** 다음 High iteration 한 개를 별도 지정.
3. **Offline code/fixture:** 해당 gate의 deterministic fixture와 회귀 검증.
4. **Source gate:** 공식 docs/auth/terms, fixture, adapter, 정확한 dataset 범위 확인.
5. **Bounded live proposal:** common/source gate 통과 뒤 별도 live 범위와 API budget 승인.
6. **장기 시험:** 취소·복구·저장 안정성과 provider limit을 고려한 별도 승인 실행.
7. **Human review:** diff와 결과를 검토. 이 기획은 구현, credentials 사용, 실기관 호출, commit/merge 권한을 부여하지 않음.

## 14. 개발·운영·사용 문서와 PPT 후속 작업

문서는 물리 폴더까지 독자별로 나눴다. [docs 시작점](../../README.md)은 사용자 → 운영자 → 개발자 순서이며 `docs/user/`는 실제 요청·결과 검토, `docs/operator/`는 설정·운영·기관 reference, `docs/developer/`는 아키텍처·엔진·구현·검증·이력을 둔다. 개발자 아키텍처도 사용자 흐름을 먼저 설명한다. 기존 로컬 Markdown 링크를 새 위치로 갱신했다.

| 문서 묶음 | 독자와 사용 목적 | 들어갈 자료 예 |
|---|---|---|
| 개발 문서 | 코드를 구현·검증·유지하는 개발자. 내부 계약, engine 책임, adapter 구현·fixture·regression을 설명 | ARCHITECTURE, IMPLEMENTATION_PLAN, connector 개발 문서, methodology/transform 설계, test/benchmark/iteration 보고서, 개발 결정 |
| 운영 문서 | API 키·예산·운영 gate·오류 복구를 관리하는 운영자. 비밀값과 live 범위 관리 절차를 설명 | INSTALLATION, OPERATING_PLAN, API 상태·catalog, credential setup, live canary/soak 절차, 저장·복구·중단 runbook |
| 실제 사용 안내 | 통계를 요청·비교하고 workbook을 받는 분석가/사용자. 코드 용어보다 선택과 결과 읽기를 설명 | USER_GUIDE, 예시 질문·질문 응답, source 선택법, Data/Definitions와 coverage/missing 설명, XLSX 해석 |

기존 USER_GUIDE의 설치·테스트·API key·live 명령은 각각 개발자 안내와 운영자 runbook으로 분리했다. 사용자 안내에는 현재 지원 범위, 후보·수집의 차이, 정의와 기간 불일치의 해석을 남겼다. 자연어 UI나 변환 엔진이 구현되기 전에는 이를 실제 기능 사용법처럼 설명하지 않는다.

사용자 안내 PowerPoint는 Office 잠금 파일이 발견되어 `docs/` 루트에 그대로 뒀다. 운영·개발 통합 PPT는 operator reference로 분류했다. 링크 검사는 현재 완료 상태이며 PPT 내용 개정은 전체 engine·workflow·승인 계약을 확인한 뒤의 별도 작업이다.

PPT 개정은 전체 데이터 흐름, engine 경계, gate, output 계약과 명칭이 검토된 **후속 작업**이다. 현재 deck은 수정하지 않는다. 사용자/운영자 deck은 개발 용어보다 현장에서 쓰는 자연스러운 한국어로 요청·선택·결과·정렬 불가/미지원 상황을 보여준다. developer deck은 각 engine의 입력·출력·계약·근거·실패/복구·현재/목표 범위를 engine별로 자세히 설명하고 전문 용어를 정의한다. 두 deck은 오래된 상태값을 현재 기능으로 오인하지 않게 기준일과 검증 범위를 표시한다.

## 15. 공식 통계 근거와 검증 한계

후보 설명은 기관 공식 페이지 기반이다. BIS는 40개 초과 경제의 비금융부문 credit 및 정부/민간 비금융부문을 설명한다. IMF GDD는 공공·민간 비금융부문 총 gross debt의 190개 경제 불균형 패널을 설명한다. World Bank IDS/QEDS는 외채 통계이며 coverage·주기·추정/개정 방식이 다를 수 있다. OECD financial indicators는 광의 부채 수단을 포함할 수 있지만 국가와 부문별 coverage가 달라 cross-country caution을 안내한다.

이 공식 페이지 조사는 dataset의 모든 API endpoint, MacroAtlas connector, live 응답을 검증한 것이 아니다. 이번 작업에서 API 호출, 인증, fixture 실행, live ingestion, benchmark를 수행하지 않는다.

- [BIS: Credit to the non-financial sector](https://data.bis.org/topics/TOTAL_CREDIT)
- [IMF: Global Debt Database](https://data.imf.org/Datasets/FAD_GDD)
- [World Bank: Debt Statistics FAQ](https://www.worldbank.org/en/programs/debt-statistics/faq)
- [World Bank: IDS와 QEDS 차이](https://datahelpdesk.worldbank.org/knowledgebase/articles/826488-what-is-the-difference-between-external-debt-stoc)
- [World Bank/IMF: QEDS](https://www.worldbank.org/en/programs/debt-statistics/qeds)
- [OECD: Financial Indicators dashboard](https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_FIN_DASH%40DF_FIN_DASH_S1M&df%5Bvs%5D=1.0&pg=0&snb=30&tm=health+coverage)
