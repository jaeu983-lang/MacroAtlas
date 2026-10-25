# Iteration 22 — BIS 공식 API·통계 후보 조사

**Date:** 2026-10-25\
**Result:** Gate M PASS\
**Track:** C — 기관 공식 근거 조사\
**Institution:** INT-02 BIS\
**Scope:** BIS SDMX REST API v2 문서와 `Credit to the non-financial sector` (`BIS,WS_TC,2.0`) 통계 후보의 의미·범위·메타데이터를 공식 문서로 확인했다.

## 공식 문서에서 확인한 내용

- BIS SDMX API v2는 공식 SDMX REST 2.1의 일부를 구현하고, 데이터 질의는 SDMX 2.1 형식으로 반환된다고 문서화한다. 데이터 route template는 `/data/{context}/{agencyID}/{resourceID}/{version}/{key}`이며 구조 및 reference metadata query도 문서화돼 있다.
- BIS Data Portal의 예시 series page에서 `BIS,WS_TC,2.0`과 `Q.ID.N.A.M.USD.A`를 확인했다. 이 예시가 Indonesia의 비금융기업, 시장가치, US dollar, break-adjusted series인 것은 공식 페이지 제목으로 확인했다. 모든 dimension code 의미를 해당 key 하나에서 추론하지 않았다.
- `Credit to the non-financial sector`는 정부 및 민간 비금융부문 잔액을 제공하며, 민간 부문은 비금융기업과 가계/가계 대상 비영리기관으로 세분된다. 대출·부채증권·통화/예금의 합은 core debt로 정의된다.
- 데이터 주제의 공식 개요는 40개 초과 경제, 분기 데이터, 정부 약 20년 평균 및 민간 비금융부문 45년 초과 평균 이력을 설명한다. 실제 coverage는 국가와 부문별 metadata 확인이 필요하며 전 세계 국가 완전성을 뜻하지 않는다.
- 빈도는 분기, collection indicator는 분기말, 계절조정은 없음이다. 단위 선택에는 국내통화, USD, GDP 대비 비율이 포함된다.
- SNA 2008 기준으로 outstanding credit instruments의 시장가치 원칙을 설명한다. 정부에는 nominal/face-value 계열도 있다. NFS aggregate에서 government debt는 market value가 이용 가능하면 이를 사용한다.
- BIS FAQ는 자료가 국가별 자료원에서 오고, 민간 비금융 부문 계열은 비연결, 일반정부 계열은 연결이며, 자산을 빼지 않는 gross basis라고 설명한다. Credit-to-GDP는 분기말 잔액을 직전 네 분기 GDP 합계와 비교하며 기초 GDP는 해당 데이터셋에서 배포하지 않는다고 설명한다.
- FAQ 및 dataset change 문서는 coverage 확장과 주요 수정 이력이 있음을 확인시킨다. 이 회차에서 과거 vintage API/스냅샷 재현 계약은 확인하지 않았다.

## 분석상 경계와 미해결 사항

“총부채”만으로 BIS 계열을 선택할 수 없다. 사용자가 원하는 부문(정부, 민간 비금융, 양쪽 합계), lender/borrower 관점, 수단 범위, market/nominal valuation, break-adjusted 여부, 단위, 국가 universe, 기간, 목적을 구분해야 한다. 국가별 debt share의 분모·환율과 포트폴리오 위험 weight는 BIS 시계열 선택의 일부가 아니다.

MacroAtlas는 결측 국가를 0으로 처리하거나 타 기관 수치로 자동 대체하지 않는다. 정확한 국가 목록, 국가별 역사 범위·출처·실제 dimension codes, API vintage 가능성은 metadata/API discovery 단계로 남긴다.

## Gate 결과

Gate M은 통과했다. 이 gate의 기준은 공식 API/dataflow 후보를 식별하고, 통계 정의와 coverage 사실 및 미확인 항목을 분리해 기록하는 것이었다. 통과는 MacroAtlas adapter 준비 완료나 선택된 부채 지표의 사용자 승인을 의미하지 않는다.

| 증거 유형 | 실행 여부 및 결과 |
|---|---|
| 공식 BIS 문서 조사 | 완료; API v2, `WS_TC` 2.0 후보, 개념·주기·단위·coverage 근거 확인 |
| MacroAtlas 전용 fixture | 실행하지 않음; 새 fixture 미작성 |
| MacroAtlas BIS adapter | 없음; 구현하지 않음 |
| 실 BIS API 호출 | 실행하지 않음 |
| 관측치 수집·저장·재조회·복구 | 미검증 |
| 코드 테스트/전체 pytest | 실행하지 않음; 문서 조사만 수행 |

## 변경 문서

- `docs/developer/connectors/BIS.md` — BIS 공식 API/통계 source profile.
- `docs/developer/EXECUTION_PLAN.md` — Iteration 22 결과와 다음 task 후보 반영.
- `docs/developer/IMPLEMENTATION_PLAN.md` — 중복 Iteration 21 요약 제거, Iteration 22 완료 gate 추가.
- `docs/operator/reference/INSTITUTION_API_AUDIT.md` — BIS 조사 profile 링크.
- `docs/developer/planning/MULTI_SOURCE_SELECTION_AND_XLSX_OUTPUT_PLAN.md` — BIS 비교가능성 주의사항 보강.
- `docs/developer/history/DECISION_LOG.md` — D-089 조사 결과와 미승인 경계.

## 다음 단계

작성 시점에 제안한 다음 후보는 Iteration 23 request·metadata contract audit였다. 사용자가 후속으로 BIS는 사례일 뿐이고 21개 기관을 모두 검증해야 한다고 범위를 명확히 해 Iteration 23은 전기관 readiness audit 및 offline suite로 재설정했다. 실제 수행과 결과는 [Iteration 23 보고서](ITERATION_23_REPORT.md)에 기록한다.

문서 조사 결과는 live API·fixture·ingestion 검증으로 계산되지 않는다. 본 회차 변경은 stage/commit하지 않았으며 사람의 diff 검토가 남아 있다.

## 공식 출처

- [BIS SDMX API v2](https://stats.bis.org/api-doc/v2/)
- [BIS Credit to the non-financial sector](https://data.bis.org/topics/TOTAL_CREDIT)
- [BIS FAQ: Credit to the non-financial sector](https://data.bis.org/faq?stats-faqs=2)
- [BIS example series: Indonesia, WS_TC 2.0](https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.ID.N.A.M.USD.A)
- [BIS changes to the data set](https://www.bis.org/statistics/totcredit/credchanges_doc.pdf)
