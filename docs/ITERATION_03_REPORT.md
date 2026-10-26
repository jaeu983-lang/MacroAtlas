# 03회차 결과 — World Bank 공개 GDP 한 경로 수집

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

기준일: 2026-10-24. PROJECT_PLAN.md와 IMPLEMENTATION_PLAN.md 03 범위만 구현했다.
04회차는 진행하지 않았다. 작업 브랜치는 `codex/iteration-03`이다.

## 시작 상태와 선정 근거

- AGENTS/GUIDELINES/PROJECT_PLAN/IMPLEMENTATION_PLAN/INSTITUTION_CATALOG/
  REFERENCE_SCENARIOS/DECISION_LOG와 기존 코드·테스트·02회차 보고서를 확인했다.
- 시작 검증: 기존 전체 pytest **61 passed in 4.00s**, Ruff **All checks passed!**.
- codex/iteration-02에서 별도 03 브랜치로 전환했다. 모든 시작 파일은 여전히
  untracked다. 기존 파일 삭제·커밋·병합·배포는 하지 않았다.
- BIS bulk 대신 World Bank Indicators API를 선택했다. 키가 필요 없는 공개 경로와
  GDP 지표 예시가 공식 문서에 있어 한 국가·짧은 기간·작은 JSON으로 범위를 제한할 수 있다.

## 변경 파일 및 이유

| 파일 | 변경 이유 |
|---|---|
| src/macro_data_platform/connectors/worldbank.py | 고정 GDP 요청·opt-in 전송·HTTP 분류·독립 최소 파서 |
| src/macro_data_platform/ingestion/worldbank.py | WorldBankGDPEngine, raw 보존 후 파싱·기존 Orchestrator 연결 |
| src/macro_data_platform/storage/raw_downloads.py | 새 폴더/파일의 배타 생성으로 raw와 요청 manifest 보존 |
| scripts/verify_worldbank.py | --live 명시를 요구하는 03회차 실측 검증 보조 명령 |
| tests/fixtures/worldbank_gdp.json | 실제 통계값이 아닌 합성 응답: 숫자/null/0/관측 상태 사례 |
| tests/test_worldbank.py | 신규 57개 fixture/모의 HTTP·파일/Orchestrator 통합 테스트 |
| docs/connectors/WORLDBANK.md | 공식 근거·인증·URL·제약·오류·보존·실행 방법 명세 |
| docs/INSTITUTION_CATALOG.md | INT-04의 한 경로 실측 결과만 별도로 추가 |
| docs/REFERENCE_SCENARIOS.md | H의 제한적 부분 실행과 전체 NOT_RUN 구분 |
| docs/ARCHITECTURE.md | 03회차 모듈과 04회차 범위 경계 갱신 |
| docs/DECISION_LOG.md | D-019~023 설계 선택·미해결 사항 |
| README.md | 현재 지원 경로와 보고서 위치 안내 |
| docs/ITERATION_03_REPORT.md | 이 보고서 |

새 의존성 설치나 기존 계약·테스트 기준·Orchestrator 코드 변경은 없다.
PowerShell 실행 정책·예약 작업은 변경하지 않았다.

## 검증 1 — 공식 문서 조사

2026-10-24에 다음 공식 페이지를 웹 도구로 열어 확인했다. 문서 확인과 아래 실측은 별개다.

- [API/인증 안내](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392): 키 불필요.
- [호출 구조](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures):
  JSON·date·page/per_page.
- [지표 식별](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries):
  NY.GDP.MKTP.CD 및 WDI source 2 예시.
- [응답 확장](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886674-new-features-and-enhancements-in-the-v2-api):
  source 갱신일·국가 ISO3·관측 상태.
- [이용 조건 링크](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)는
  새 Terms & Conditions 페이지로 리다이렉트됐다. 개별 지표의 재배포 라이선스를
  전면 확인했다고 주장하지 않으며 로컬 소량 수집에 한정했다.

## 검증 2 — 실제 API 호출·수집

명령: `.venv/Scripts/python.exe -X utf8 scripts/verify_worldbank.py --live`.
고정 요청은 다음과 같다.

```text
https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD?source=2&date=2020%3A2022&format=json&per_page=100&page=1
```

| 시도 | 실제 결과 | 근거 |
|---|---|---|
| 기본 샌드박스 시도 | FAILED / TRANSIENT, 완전 응답 없음 | reports/iteration_03_live_4d96565839f04da98889c270d2b892eb.json |
| 승인된 네트워크 실행 | COMPLETED, HTTP 200, raw 724 bytes, 관측 행 3개 | reports/iteration_03_live_1994a5a8b887424c9823329fae501704.json |

전송 예외 상세는 저장하지 않으므로 첫 실패의 구체적인 네트워크 원인을 확정하지 않는다.
기본 시도 실패 후 승인된 재실행으로 성공한 사실만 기록한다. 자동 재시도는 하지 않았다.

- 성공 task_id: `9cf5063b-d164-47c7-a642-6e4343da6307`.
- 성공 수집 시각: `2026-10-24T02:12:07.442440+00:00` (한국 시각 11:12:07).
- raw: `data/raw/worldbank/c6b68353375646568084a1ee2af80831/response.json`.
- 요청 기록: 같은 폴더의 `request.json` (HTTP 상태·URL·시각·크기·mode 포함).
- 이력: `data/catalog.sqlite`. 최초 실패와 성공은 서로 다른 검증 작업으로 모두 보존했다.
- 응답의 sourceid=`2`, page/pages=`1/1`, total=`3`, lastupdated=`2026-10-08`.

실제 원본 행의 값은 다음과 같다. 원본 지표명은 GDP (current US$)지만 응답의 unit은
빈 문자열이므로 정규화 unit을 이름만 보고 채우지 않았다. 이는 통계 전체의 경제적
정당성·개정 비교·품질 검증을 마쳤다는 뜻이 아니다.

| 연도 | 응답 value |
|---|---:|
| 2020 | 21375281000000 |
| 2021 | 23725645000000 |
| 2022 | 26054614000000 |

### 최종 파서로 실제 원본 재해석 (추가 API 호출 아님)

`reports/iteration_03_live_replay.json`에 저장한 로컬 재해석 결과를 남겼다.
724 bytes·3개 행과 원본 JSON의 관측 행 동일성을 assert로 확인했다(종료 코드 0).
모드는 `local_replay_of_saved_live_response`, new_network_call=false다.

초기 성공 실행의 결과는 당시 lastupdated를 source_version 필드에 담았으나,
검토 후 최종 파서는 이를 source_last_updated로 분리하고 불변 source_version은 None으로
표시하도록 바로잡았다. 기존 성공 작업/원본 이력을 덮어쓰지 않았으며 최종 의미는
재해석 보고서에 기록했다. 실제 API 전송·원본 확보와 이 로컬 재해석을 구분한다.

## 검증 3 — 모의/로컬 테스트 및 정적 검사

모든 pytest는 네트워크 없이 실행했다. 실제 응답 수치를 fixture에 복사하지 않았다.
기존 61개 + 신규 57개 = **118개**다.

| 검사 | 최종 실제 결과 |
|---|---|
| `.venv/Scripts/python.exe -m pytest -ra --basetemp reports/pytest_iteration03_verified` | **118 passed in 7.73s**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m ruff check src tests scripts/verify_worldbank.py` | **All checks passed!**, 종료 코드 0 |
| `.venv/Scripts/python.exe -m macro_data_platform.health` | 종료 코드 0 |
| `.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| 실제 원본 로컬 재해석 | HTTP 200 기록·724 bytes·3개 행·원본 동일성 확인, 종료 코드 0 |
| `git check-ignore` | SQLite/raw/replay 보고서가 Git 제외 대상임을 확인 |
| `git diff --check` | 종료 코드 0. untracked 신규 파일 검증을 대신하지 않음 |

로그: reports/iteration_03_pytest.txt, reports/iteration_03_ruff.txt.
개발 중 첫 115개 테스트도 통과했으며 Ruff의 사용하지 않는 import 1건은 수정 후 통과했다.

신규 검증 범위는 요청 예산/호스트·식별자 고정, null/0/빈 단위·상태·정밀도 보존,
HTTP 401/403/429/5xx/리다이렉트/404, JSON·schema·country/indicator/date 불일치,
빈 값/부분 페이지 거부, 배타 저장·충돌·저장 오류, 네트워크 기본 거부와 명시적 True,
TLS/연결/timeout·크기/시간 예산, 암묵 인증·리다이렉트 미사용, Orchestrator 수동
재시도 연결, --live 없는 검증 명령 차단이다. 실제 403/429를 발생시킨 검증은 아니다.

## 보안·데이터 완전성

- 실제 API 키·.env·TXT·.netrc·브라우저·자격증명 저장소를 읽지 않았다.
  키가 필요 없는 World Bank 경로만 구현했으며 다른 기관 키를 요구하지 않는다.
- 네트워크는 고정 HTTPS 경로에 명시적으로 허용한 조회만 했다. TLS 검증을 유지하고
  리다이렉트와 암묵적 인증/프록시 설정을 사용하지 않는다. 예외 원문은 저장하지 않는다.
- raw와 요청 manifest는 새 디렉터리/파일에 배타 저장한다. 오류 응답도 완전히 받으면
  원본을 보존하고 성공으로 표시하지 않는다. 수신 중단/크기 초과는 완전 raw로 남기지 않는다.
- 원본 행을 수정·보정·합산하지 않았고 null/0을 구분한다. 빈 unit이나 불변 vintage 등
  없는 메타데이터는 None으로 두고 원문은 별도 raw에 보존한다.
- 원본·DB·로컬 보고서는 Git 제외 대상이다. 커밋·병합·공개 재배포·배포는 하지 않았다.

## 남은 문제와 검수 결론

- 지원 범위는 USA/GDP/source 2/짧은 연도 구간/1페이지 JSON뿐이다. 다른 기관·지표·
  국가·자동 검색·인증·파일 형식·다중 페이지 수집은 구현하지 않았다.
- 검토한 공식 문서에서 숫자로 명시된 호출 한도를 확인하지 못했다. 요청은 수동 1회씩이며
  429 이후 자동 재시도하지 않는다. 자동 HTTP backoff·Retry-After 스케줄링은 후속 범위다.
- .env 로더와 키 필수 기관의 실제 인증은 미구현이다. 조직 프록시/사설 CA 환경도 별도 설정이 필요하다.
- 원본/manifest 저장 도중 장애 시 부분 파일이 남을 수 있다. 기본 비덮어쓰기는 있으나
  원본 hash 카탈로그·종합 검증/격리·정규화 테이블·개정 비교·피드백 등록은 없다.
- 실제 수집은 H 시나리오의 World Bank 한 부분만 확인했다. A~H 전체, OECD 비교,
  완전한 Gate A 검증을 통과한 것으로 표시하지 않는다.
- 별도 지표 라이선스·재배포 조건의 전면 확인, 기존 PowerShell 서명 정책 문제,
  dependency lockfile 부재와 Git 체크포인트·사람 검토는 남아 있다.
- 02회차의 순차 실행·단계 경계 취소·수동 복구 제한도 유지된다.

**03회차 완료 조건은 충족했다:** 공식 근거로 선정한 공개 경로에서 실제 원본 확보,
최소 정상 파싱과 식별자·URL·시각 보존, 기존/신규 테스트 및 Ruff 통과.
사람은 지원 범위·원본 보존 방식·접근/이용 조건과 변경 사항을 검토해야 한다.
추가 결정 없이는 끝낼 수 없는 03회차 코드 차단 사항은 없다.
04회차의 통합 검증·오류/피드백 작업은 아직 시작하지 않았다.
