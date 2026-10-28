# 보완 03 구현 보고서

기준일: 2026-10-24. 브랜치: `codex/workflow-alignment-03`.
최신 PROJECT_PLAN/IMPLEMENTATION_PLAN/WORKFLOW_ALIGNMENT_PLAN의 **보완 03만** 구현했다.
04회차·Gate A 구현 및 최종 사용자 설명서/PPT 제작은 진행하지 않았다.

## 구현 결과

확정 요청을 기존 World Bank USA/source 2/NY.GDP.MKTP.CD의 제한 수집 경로에 연결했다.
새 WorldBankRequestDispatcher는 보완 02에서 생성한 자식 task_id를 받아 현재 확인/개정과
지원 범위를 검사한다. 요청이 이미 완전하면 추가 질문 없이 기존 엔진까지 연결한다.
미확정 컨테이너·변경된 확인·불일치 계획은 전송 전에 거부한다.

| 전달 모드 | 동작/결과 위치 |
|---|---|
| file | 기존 수집 엔진의 raw_json과 manifest 경로. stages[0].result.payload |
| link | 제공된 유효 근거의 정확한 GDPQuery URL만 반환. delivery_result |
| both | collect→deliver. 최종 payload에 collection과 links를 함께 보존 |

link 전용은 plan=None/stages=[]이고 수집 엔진 생성/호출·HTTP·raw 생성이 없다.
별도 원자적 완료 시도/LINK_DELIVERED 이벤트로 수집 성공과 구분한다. both의 deliver 단계도
추가 GET을 하지 않는다. 근거·수동 필터·제약은 보존하며 URL을 새로 발견/검증하지 않는다.
반복 완료 호출은 추가 전송/파일/전달 이벤트를 만들지 않는다. 실패 재개는 같은 task_id를
사용하고 조건 변경은 새 확인/작업을 요구한다. 저장된 과거 원본을 덮어쓰지 않는다.

지원 범위는 다음처럼 의도적으로 좁다.

- institution_id=worldbank, dataset_id="2", series_id=None,
  series_key={source: "2", country: "USA", indicator: "NY.GDP.MKTP.CD"}.
  기관 조사대장의 INT-04는 문서 식별자다. 기관 별칭/명칭을 자동 변환하지 않는다.
- 요청/선택 후보 USA만, 추가 차원 없음, 네 자리 연도, 1960..2100의 연속 1~10년.
  주기 source/단위 preserve/vintage latest_available만 허용한다.
- 파일은 raw_json과 설정된 raw 디렉터리(기본 data/raw)만 허용한다. CSV/XLSX·다른 위치는
  전송 전에 거부하며 raw_json으로 바꾸지 않는다. 원본은 기존 UUID 하위 폴더 정책을 따른다.
- 링크는 GDPQuery가 생성하는 정확한 고정 API URL만 허용한다. 다른 쿼리 순서/표기,
  viewer, 일반 문서 URL을 동등한 것으로 추정하지 않는다. 선택하지 않은 URL은 전송하지 않는다.
- 비어 있지 않은 변형 requirements를 필터로 실행하는 기능은 없다. 지원 범위를 벗어나면
  사전 ValueError로 알리고 변형·단위·주기를 변환하지 않는다.

## 변경 파일 및 이유

| 파일 | 변경 이유 |
|---|---|
| src/macro_data_platform/ingestion/worldbank_request.py | v1 명시적 계획 builder, 새 wrapper dispatcher, 전달 모드 분기/사전 검증 |
| src/macro_data_platform/orchestration/workflow.py | 전용 링크 handler의 검증을 위한 선택적 allow_link 인자. 기본 수집 runner의 링크 금지는 유지 |
| scripts/verify_worldbank.py | 기본 --live를 구조화 확인→연결 작업→수집으로 전환. --legacy로 기존 경로 명시 지원 |
| tests/test_worldbank_request.py | 신규 42개 offline 통합/실패/호환 테스트 |
| PROJECT_PLAN.md | 제한 실행 연결의 현재 구현 상태 갱신 |
| docs/developer/IMPLEMENTATION_PLAN.md | 보완 03 완료·검증 및 04회차 미착수 표시 |
| docs/developer/planning/WORKFLOW_ALIGNMENT_PLAN.md | 보완 03의 현재 완료/제약 표시 |
| docs/developer/connectors/WORLDBANK.md | canonical 식별자·범위·호출/결과 위치·새 live 근거 |
| docs/developer/ARCHITECTURE.md | 기관별 어댑터와 링크/수집 분리·원자 저장·오류 경계 |
| docs/developer/history/DECISION_LOG.md | D-048~051 구현 결정과 후속 미해결 범위 |
| docs/developer/history/ALIGNMENT_03_REPORT.md | 이번 변경·시험·실제 근거·한계 보고 |

기존 connectors/worldbank.py, ingestion/worldbank.py, storage/raw_downloads.py는 수정하지 않았다.
기본/확장 값 계약, golden JSON, 기존 테스트, Task/Stage/오류 enum과 StageInput도 수정하지 않았다.
SQLite schema version 2를 유지하며 DB 이관은 없다.

런타임 산출물은 기존 data/catalog.sqlite의 새 요청/작업 이력, 아래 raw/manifest와
reports의 실행 보고서다. Git에서 제외되는 검증 자료이며 소스 변경과 구별한다.
현재 저장소는 기존부터 전체가 untracked여서 일반 git diff는 이번 변경 목록의 검증 근거가
될 수 없다. 자동 커밋/병합/배포는 하지 않았다.

## 모의 테스트·로컬 회귀 검증

| 실행 | 정확한 결과 |
|---|---|
| 변경 전 전체 pytest | 364 passed in 9.67s |
| 변경 전 Ruff | All checks passed! |
| 최종 전체 pytest | **406 passed in 12.63s**, 실패/skip 없음 |
| 최종 Ruff | **All checks passed!**, exit 0 |

```powershell
.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_alignment03_final
.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py
```

신규 42개와 기존 364개를 함께 실행했다. 신규 테스트는 HTTP 요청을 실패 처리하도록
차단하고 fixture transport·실제 로컬 SQLite/파일을 사용했다. 실제 통계 수치를 fixture에
넣지 않았다. 기존 TLS·리다이렉트·응답 크기/페이지·키 미접근 등의 회귀 테스트도 유지했다.

검증 범위는 3모드, 요청 기간의 정확한 입력 연결, 미확정/변경/잘못된 계획/만료 거부,
미지원 국가·지표·source·필터·변환·CSV/XLSX·저장 위치의 전송/쓰기 0회,
link 전용 수집기/GET/raw 0회와 완료 멱등성, 링크 이벤트 저장 장애 롤백,
503→재개와 원본 보존, both 단계 사이 링크 만료/전달 직전 변경의 검토 종료다.
null/0/빈 unit/obs_status/추가 필드/lastupdated는 fixture 원문과 비교했다.

개발 중 신규 테스트의 실제 시각/고정 fixture 시각 혼용과 None payload 검사 오류를
수정했다. 검증 조건을 완화하거나 기존 테스트를 삭제하지 않았다. 최종 전체 검증은 위와 같다.

기존 v1 JSON byte 왕복과 ConfirmedSelection fingerprint
`92b82d2b99402fba6a7704aed19e10db20dceb4345c1146f8a3d54d2cd8b7d96`가 그대로 통과했다.
기본 계약 파일 SHA-256은
`c32035793b586f10f743e912a6198f9deba7d5a7235d3baae3a9cf61225fbb9a`로 이전과 같다.
새 단계 fingerprint는 보완 02의 context 포함 방식을 사용하고 legacy 알고리즘은 바꾸지 않았다.
build_worldbank_plan은 v1 JSON에 새 전달 의미를 덧씌우지 않는 명시적 호환 진입점이다.

## 실제 API 검증 — 새 file 요청

공식 문서 신규 조사: **없음**. 기존 docs/developer/connectors/WORLDBANK.md의 문서화 프로필을 사용했다.
이 프로필 사용을 새 메타데이터 발견/공식 문서 재조사로 표시하지 않는다.

```powershell
.venv/Scripts/python.exe -X utf8 scripts/verify_worldbank.py --live
```

같은 고정 소규모 요청을 기본 환경에서 한 번, 네트워크 허용 환경에서 별도 수동 실행 한 번
시도했다. 자동 재시도 루프나 TLS/접근 제어 우회는 없다. 최초 실패도 보존한다.

| 시도 | 결과/근거 |
|---|---|
| 최초 기본 환경 | FAILED / TRANSIENT. HTTP 응답/원본을 확보하지 못함. 정확한 전송 원인은 단정하지 않음 |
| 네트워크 허용 실행 | **COMPLETED / HTTP 200 / live_api**, 원본 724 bytes, 2020~2022년 관측치 3개 |

- 실패 task_id: `7c216098-777e-436a-abc4-f62fd95af771`.
  [실패 보고서](../../../reports/alignment_03_live_cba90eaec4f143afa54b36bc8a7fc326.json)
- 성공 task_id: `cdc0799c-6cf6-4a7b-85fc-3c72a615fe08`.
  [성공 보고서](../../../reports/alignment_03_live_2d3cb7c2f92a4b949ef5544d2f9fd02c.json)
- 수집 시각: `2026-10-24T03:38:31.222275+00:00`.
- [실제 원본](../../../data/raw/worldbank/296888ff1dce4887b99c47b54276a815/response.json)
  및 [manifest](../../../data/raw/worldbank/296888ff1dce4887b99c47b54276a815/request.json).
- source_last_updated=`2026-10-08`. 원본 행의 빈 unit/obs_status를 보존했고
  정규화 frequency/unit/source_version은 None이다. 갱신일을 불변 vintage로 바꾸지 않았다.
- 저장한 새 실제 raw를 parse_gdp로 다시 로컬 해석해 보고서의 3개 관측치와 동일함,
  실제 파일 길이와 manifest byte_count가 모두 724임을 확인했다(exit 0).
  이 재해석은 추가 API 호출이 아니다.

이번 실제 검증은 **file 경로만** 증명한다. link/both의 동작·HTTP 0회/추가 호출 없음은
fixture 테스트 증거다. 과거 03회차 성공 기록을 이번 실행으로 대체하지 않았다.

## 남은 문제·보안·사람의 판단

- 04회차 원본 hash 카탈로그·정규화 관측치/품질·피드백 기록은 없다. Gate A는 미통과이며
  다음 회차를 시작하지 않았다. 실제 수집 성공을 전체 사용자 여정 검수로 확대하지 않는다.
- 자동 후보/기관/링크 발견, viewer 링크 일반화, URL query 동등성 판정, 자연어 UI,
  Excel/CSV exporter, 단위/주기/변형 변환과 다기관·대량 요청은 미구현이다.
- link의 available/official/public은 제공된 근거다. handler는 현재 조건/만료와 고정 URL을
  검사하지만 사이트를 다시 열어 최신성을 검증하지 않는다. 미확인 링크를 가용으로 승격하지 않는다.
- 네트워크 기본 거부·TLS 검증·리다이렉트 거부·GET 1회·1 MiB·1페이지 상한은 기존 코드 그대로다.
  파일 작업은 명시적 network_enabled=True가 있어야 실제 전송한다. fixture transport는 별도다.
- World Bank는 키 없이 접근한다. 키/자격증명 파일을 읽지 않았고 PowerShell 실행 정책도
  변경하지 않았다. 기본/확장 값 계약이 자유문장의 모든 비밀을 검출하는 도구는 아니라는
  기존 제한은 유지된다. 원본 삭제/덮어쓰기·임의 숫자 보정·스키마 이관·배포/병합은 없다.
- 이번 범위에 남은 실패 테스트는 없다. 제한된 고정 URL/raw 출력 정책의 인간 검토와
  향후 04회차 착수 결정은 필요하며, 별도 요청 전까지 진행하지 않는다.
