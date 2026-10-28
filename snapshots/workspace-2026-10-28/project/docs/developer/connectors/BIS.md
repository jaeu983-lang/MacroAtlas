# BIS — 공식 API·통계 근거 프로필

**조사일:** 2026-10-25\
**기관 ID:** INT-02\
**상태:** API 문서와 대상 데이터셋 후보를 확인했고, Iteration 24에서 BIS SDMX v2 raw-response client와 mocked route test를 추가했다. provider 응답 parsing·workflow·실 API 수집은 미구현/미실행.\
**근거 유형:** BIS 공식 API 문서, BIS Data Portal, BIS FAQ 및 공식 통계 문서. 이 프로필은 live 호출 결과가 아니다.

## API 경로 근거

- BIS는 공개 통계와 메타데이터의 programmatic access를 위한 SDMX REST API v2를 문서화한다. API는 공식 SDMX REST 2.1의 부분집합이며, API 데이터 조회 응답은 SDMX 2.1 형식이라고 안내한다.
- 공식 문서의 데이터 요청 형식은 `/data/{context}/{agencyID}/{resourceID}/{version}/{key}`다. 구조·항목 및 reference metadata 조회 경로도 문서화돼 있다. MacroAtlas는 해당 route를 [SDMX client](SDMX_FAMILY.md)에서 구성하지만, 이번 회차는 mock session만 사용했다.
- BIS Data Portal의 공식 계열 페이지에서 `BIS,WS_TC,2.0` 및 예시 series key `Q.ID.N.A.M.USD.A`가 표시된 시계열을 확인했다. 포털의 표시 제목은 Indonesia, non-financial corporations, market value, US dollar, break-adjusted 계열이다. 이 예시의 key 구성요소를 DSD/codelist로 분해하거나 다른 국가에 그대로 적용할 수 있다고 확인하지 않았다.
- 기존 기관 API 감사표는 API 키가 필요 없다고 안내된 상태를 기록한다. 이번 조사에서는 인증 없는 요청을 시험하지 않았으므로 인증·쿼터·가용성은 live 미검증으로 유지한다.

## 대상 통계 후보: Credit to the non-financial sector

공식 BIS Data Portal의 `TOTAL_CREDIT` 주제는 정부 부문과 민간 비금융 부문의 차입/부채 잔액을 다룬다. 사용자가 말한 “국가별 총부채”와 자동으로 같은 개념이라고 간주하지 않는다.

| 확인 항목 | 공식 문서에서 확인한 내용 | 구현 전 남은 확인 |
|---|---|---|
| 데이터셋 식별 | 예시 series 페이지에 `BIS,WS_TC,2.0`이 표시됨 | 전체 flow/DSD/codelist와 버전 변경 규칙을 API discovery fixture로 확인 |
| 대상 부문 | 정부 부문과 민간 비금융 부문. 민간 비금융 부문은 비금융기업과 가계(가계 대상 비영리기관 포함)로 나뉨 | 사용자가 원하는 부문이 정부, 민간, 양쪽 합계 중 무엇인지 선택 필요 |
| 수단 | 부채증권, 대출, 통화·예금. 이 세 항목의 합을 BIS는 core debt라고 부름 | 원하는 “총부채”가 이 수단 범위와 일치하는지 결정 필요 |
| 대출자/차입자 의미 | 민간 비금융 부문에 대한 total credit은 국내 은행, 기타 국내 금융회사, 비금융회사, 비거주자를 포함한 모든 자금 제공처를 가리킴. bank credit은 국내 은행만 포함 | “total credit” 문맥이 차입자 부문 합계인지 민간 부문에 대한 대출자 범위인지 요청 단계에서 고정 |
| 빈도·시점·계절 조정 | 분기, 분기말 잔액(end of period), 계절조정 안 됨 | 요청 기간과 최신 관측치 정책을 정하고 API 응답의 실제 dimension 값을 확인 |
| 단위·평가 | 국내 통화, 미국 달러, GDP 대비 비율(일부 표는 PPP 기준 비율도 제공). SNA 2008 시장가치 원칙; 정부 부문에는 명목/액면가 계열도 제공 | 국가별 통화 환산·명목/시장가치 계열을 혼합하지 않도록 정확한 단위·평가 코드 선택 |
| 통합·총액 성격 | 민간 부문 계열은 비연결(unconsolidated), 일반정부 계열은 연결(consolidated). 해당 부문 자체 자산을 차감하지 않는 gross 기준 | BIS 집계의 구성과 다른 기관 데이터의 통합 기준이 비교에 적합한지 확인 |
| 계산된 단위 | BIS의 credit-to-GDP는 분기말 잔액을 최근 4개 분기 GDP 합계로 나눈 비율. BIS는 그 계산에 쓰는 기초 GDP series를 이 주제에서 배포하지 않는다고 FAQ에 설명 | MacroAtlas에서 독립 계산한다면 분모 원자료·개정·정렬을 별도로 추적해야 하며, 현재 계산 승인 없음 |
| 출처·coverage | 통계는 국가 자료원을 기반으로 함. 주제는 40개 초과 경제를 포괄한다고 설명하며 국가·부문별 평균 시계열 길이가 다름. coverage와 주요 수정 이력이 과거에 변경됨 | 정확한 국가 목록·국가별 최초/최종 관측치·국가별 원자료 출처는 metadata 단계에서 확인 |
| 개정/vintage | BIS는 dataset 변화와 주요 개정을 기록한다 | 과거 특정 시점의 발표본을 재현할 수 있는 vintage API 계약은 확인하지 못함. raw 응답과 retrieval time/hash 보존 필요 |

## 부채 분석과의 경계

- “Credit to the non-financial sector”는 총부채/재정 부채/총대외부채 같은 일반 표현을 요청자 확인 없이 대체하지 않는다. 핵심 수단과 부문 범위가 정해진 BIS 통계 후보일 뿐이다.
- 40개 초과 경제라는 공개 설명은 전 세계 모든 국가가 같은 시계열로 제공됨을 뜻하지 않는다. 결측 국가를 0으로 바꾸거나 다른 기관값으로 자동 대체하지 않는다.
- BIS가 공표하는 부채 잔액 또는 GDP 비율은 국가별 위험 가중치나 포트폴리오 비중이 아니다. 대상 모집단, 분모, 시점, 환율, risk formula는 통계 계열을 고르는 것과 별도 결정이다.
- 국가별 계열 출처·coverage·평가 차이를 확인하기 전에는 국제 합산이나 국가 간 비교가능성을 판정하지 않는다.

## 다음 구현 gate에서 필요한 증거

1. 요청 gap audit에서 부문, 부채 범위, 기간, 국가 universe, 결과 용도와 단위를 묻거나 보존할 기존 계약을 먼저 확인한다.
2. 그 선택이 좁혀진 뒤 기존 client route로 BIS 공식 SDMX 구조 API 요청을 제한된 mock payload fixture에 연결해 dataflow/DSD/codelist metadata parsing을 검증한다. 이 프로필만으로 구체 key를 조합하지 않는다.
3. fixture에 정확한 기관·flow·version·dimension·unit·frequency·valuation·break adjustment·원 URL을 기록한다. 관측치 어댑터와 저장/read-back은 별도 gate다.
4. 실 API 접근은 offline fixture/adapter gate 이후 별도 기관별 readiness와 승인 하에만 검토한다.

## 공식 출처

- [BIS SDMX API v2 문서](https://stats.bis.org/api-doc/v2/)
- [Credit to the non-financial sector — BIS Data Portal](https://data.bis.org/topics/TOTAL_CREDIT)
- [BIS Data Portal FAQ — Credit to the non-financial sector](https://data.bis.org/faq?stats-faqs=2)
- [예시 계열: Indonesia, WS_TC 2.0](https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.ID.N.A.M.USD.A)
- [변경 이력 문서](https://www.bis.org/statistics/totcredit/credchanges_doc.pdf)

## 검증 상태

| 증거 유형 | 상태 |
|---|---|
| 공식 문서 조사 | 완료 — Iteration 22 범위 |
| MacroAtlas BIS API route client | 있음 — Iteration 24; raw-response client만 |
| BIS source payload/metadata fixture | 아직 없음; Iteration 22에서 생성하지 않았고 Iteration 24는 route mocks만 추가 |
| 실 API endpoint 호출 | 실행 안 함 |
| 실 관측치 수집·저장·복구 | 검증 안 함 |
