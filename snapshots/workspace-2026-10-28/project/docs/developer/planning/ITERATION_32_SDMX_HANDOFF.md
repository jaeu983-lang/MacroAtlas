# 다음 채팅 요청문 — Iteration 32 SDMX metadata 검증

아래 요청문을 다음 채팅에 붙여 넣는다. 이 문서는 실행 요청 초안이며 Iteration 32 구현을 이미 수행했다는 뜻은 아니다.

```text
C:\Projects\MacroAtlas에서 Iteration 32 한 회차를 실행해줘.

현재 상태:
- 사용자 지시 D-101로 Census·BLS는 보류다. 두 기관의 키 입력 요청·live 호출·복구를 재개하지 마.
- Gate U는 과거 Iteration 30의 7개 고정 경로/5개 기관 검증이다. 마지막 전체 run은 4/7로 미통과였고 이력으로 보존한다. 사용자 지시로 다른 기관의 독립 gate는 진행할 수 있다. Gate U를 통과로 바꾸거나 현재 작업의 전역 차단 조건으로 쓰지 마.
- Iteration 31은 완료됐다. BEA GetDataSetList metadata 13개, e-Stat getStatsList(lang=E, limit=1) 목록 1건을 source당 1회 요청해 HTTP 200·source 계약·파일 저장/hash read-back을 통과했다. 관측치 수집 전체나 일반 자연어 workflow를 완성한 것은 아니다.
- Gate V는 metadata 검사/저장 구현과 위 두 source의 좁은 metadata sub-gate에만 PASS다. 전체 offline 기준은 884 passed, 1 skipped이며 skip은 Windows symlink 생성 제한이다.
- 프로젝트 network opt-in은 켜져 있다. .env나 실제 key를 출력·변경하지 말고, source별 공식 auth/호출 예산을 확인한 요청만 실행해.

먼저 AGENTS.md, GUIDELINES.md, PROJECT_PLAN.md, docs/developer/IMPLEMENTATION_PLAN.md의 Iteration 32 후보, docs/developer/history/ITERATION_31_REPORT.md, docs/developer/connectors/SDMX_FAMILY.md, 기관별 API audit와 관련 코드를 읽어줘. git 상태를 먼저 확인하고 새 codex/ 작업 브랜치에서 기존 변경을 보존해줘.

이번 목표는 기존 SDMX raw client 6곳의 공식 metadata 경로와 응답 계약을 검증하는 것이다:
BIS(INT-02), OECD(INT-03), ECB(EU-01), Eurostat(EU-02), Bundesbank(EU-03), INSEE(EU-05).

1. 각 기관의 공식 문서에서 현재 metadata route, resource/agency/version ID, 인증·이용 조건·요청 제한과 응답 형식을 확인해. 기존 mock의 ID를 실제 존재 근거로 사용하지 마. 특히 INSEE 기존 client는 data 경로 위주이므로 metadata 메서드가 필요하면 공식 근거와 fixture부터 마련해.
2. 공통 bounded HTTP/SDMX wrapper와 archive/read-back을 재사용하고, provider 차이와 XML/JSON source 계약을 각 기관별로 검사해. HTML 오류 페이지나 HTTP 200만으로 성공 처리하지 마. 응답 ID, XML namespace/root, 선택한 dataflow/DSD/관련 구조, 오류 envelope를 확인해. 기존 parser가 있으면 먼저 재사용 가능성을 검토해.
3. 정상·오류·빈 응답·잘못된 ID·HTML·과대 응답·출처 불일치·저장/hash 회귀를 deterministic fixture로 확인해. 실제로 받은 공개 응답을 fixture로 보존할 때는 키/개인 정보 제거와 URL·UTC 시각·hash·표현 형식을 기록하고 합성 fixture와 구분해.
4. offline engineering gate를 통과한 뒤 준비된 source만 최소 metadata live canary를 실행해. 새 예산은 source당 최대 1회, 합계 최대 6회, retry 0, 동시 요청 1개다. 공식 route/auth/이용 근거가 없거나 필요한 설정이 없으면 not_ready/not_run으로 남기고 추정 endpoint를 호출하지 마. 한 source 실패를 다른 source 성공에 숨기지 말고, 공통 안전 문제가 없다면 다른 독립 source의 제한 검증은 계속해.
5. 파일 저장·manifest·hash read-back과 source 계약을 모두 통과한 경우에만 그 metadata sub-gate를 PASS로 표시해. Engineering Gate W와 source별 live 상태는 별도로 판단해. 전기관 성공, 관측치 ingestion, 비교가능성, 가공/XLSX로 범위를 넓히지 마.
6. 기존 scripts/verify_api_metadata.py와 공통 저장 계약을 검토해 반복 코드를 줄여줘. 기존 기본 live 범위를 조용히 늘리지 말고, 이번 source를 명시적으로 선택하게 해. report 쓰기 가능 여부를 요청 전에 확인하고 기관별 결과를 보존해.
7. Windows 기본 pytest Temp 접근 거부가 있으면 저장소 reports 아래 고유 --basetemp를 사용해. 관련 테스트와 필요한 전체 local suite, 변경 Python Ruff, git diff --check, 실제 credential 비노출을 확인해.
8. source registry·기관 상태표·현재 실행 계획과 DECISION_LOG를 실제 근거에 맞게 갱신하고 docs/developer/history/ITERATION_32_REPORT.md에 요청 수·성공/실패/미실행·산출물·한계를 남겨줘. 검증 후 feature branch에 커밋하고 main 병합·push·배포는 하지 마. Iteration 33은 시작하지 마.

최종 답변은 기관별 실제 결과, 저장 파일, 검증 수치, 커밋, 남은 사람/외부 조치를 짧게 알려줘.
```

## 이어받을 근거

- [Iteration 31 report](../history/ITERATION_31_REPORT.md)
- [현재 구현 계획](../IMPLEMENTATION_PLAN.md), [실행안](../EXECUTION_PLAN.md)
- [SDMX 책임과 source별 현재 한계](../connectors/SDMX_FAMILY.md)
- [API archive 계약](../connectors/API_RESPONSE_STORAGE.md)
- [기관 API audit](../../operator/reference/INSTITUTION_API_AUDIT.md)
- [결정 D-101](../history/DECISION_LOG.md)

IMF·BOJ 신규 adapter, BEA/e-Stat 관측치 연결, World Bank/FRED 범위 확장은 이후 독립 회차 후보이며 이번 요청문에는 포함하지 않는다.
