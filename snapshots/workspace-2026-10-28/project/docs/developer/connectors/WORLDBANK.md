# World Bank WDI GDP — 03회차 제한 수집 경로

## 선정 및 검증 상태

World Bank Indicators API를 BIS bulk 대신 선정했다. 공식 문서에 키 없는 API와 GDP
지표 코드 예시가 있어 기관 한 곳·한 나라·짧은 기간으로 첫 수집을 제한하기 쉽다.
전체 World Bank API 지원이나 자동 지표 검색을 뜻하지 않는다.

- 공식 문서 확인일: 2026-10-24.
- 실제 API: USA / WDI source 2 / NY.GDP.MKTP.CD / 2020:2022의 HTTP 200 응답 확보.
- 최종 파서는 저장한 실제 원본을 로컬 재해석해 동일 관측 행 보존을 확인했다.
- pytest는 별도의 합성 fixture/모의 HTTP만 사용한다. 실제 수치는 fixture로 사용하지 않았다.

## 공식 근거

| 목적 | 공식 URL 및 확인 내용 |
|---|---|
| 인증 | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 — Indicators API는 키/인증 불필요 |
| 요청 | https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures — date 범위, JSON, page/per_page |
| 지표 식별 | https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries — NY.GDP.MKTP.CD, GDP (current US$), source 2 예시 |
| 응답 부가정보 | https://datahelpdesk.worldbank.org/knowledgebase/articles/1886674-new-features-and-enhancements-in-the-v2-api — source 갱신일·ISO3·관측 상태 |
| 이용 조건 | https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets — 확인 시 https://www.worldbank.org/ext/en/legal/terms-conditions 로 이동 |

데이터셋별 이용 조건을 확인해야 하며 전체 자료에 동일 라이선스를 추정하지 않는다.
이번 작업은 소규모 로컬 검증이며 공개 재배포하지 않았다. 개별 지표의 재배포 조건을
전면 확인한 상태는 아니다. 출처 표기와 이용 조건 링크를 원본 manifest/결과에 보존한다.
검토한 API 문서에서 수치형 호출 한도는 확인하지 못했다. 무제한으로 간주하지 않는다.

## 허용 요청과 인증 정책

`GET https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD`

- 고정 source=2, format=json, per_page=100, page=1.
- date=시작연도:종료연도. GDPQuery는 1960..2100 범위의 연속 1~10년만 허용한다.
- 국가/지표/출처/호스트는 고정하며 URL을 사용자 입력으로 받지 않는다.
- `auth_requirement=none`, `credential_env_var=null`. World Bank 키를 요구하지 않고
  다른 기관의 키도 읽지 않는다. .env·TXT·브라우저·.netrc를 조회하지 않는다.
- 네트워크는 Settings.network_enabled가 명시적 True일 때만 실행한다.
  기본값은 False이며 fixture transport 주입은 네트워크 없이 별도로 시험할 수 있다.
- 세션 trust_env=False로 암묵적 인증/프록시 설정을 읽지 않고 기본 TLS 검증을 유지한다.
  조직 프록시/사설 CA가 필요한 환경은 별도의 명시적 설정을 추후 검토해야 한다.

## 전송 예산과 오류

요청당 GET 1회, 연결/읽기 timeout 5/20초, 응답 1 MiB 상한이다. 공유 bounded HTTP
전송 primitive는 세션, TLS, redirect, streaming과 byte/time 상한을 처리하고, World Bank
wrapper는 고정 WDI route, 실패 상태 분류, 오류 body 보존, Retry-After 해석을 유지한다.
30초 경과를
청크 수신마다 검사하므로 총 지연이 정확히 30초에서 끊긴다고 보장하지는 않는다.
완전 수신하지 못한 응답은 완전한 raw로 저장하지 않는다. 리다이렉트는 따라가지 않는다.
자동 재시도/대기 루프는 없고 02회차 Orchestrator의 수동 resume·호출 상한을 따른다.
429/5xx는 즉시 반복 호출하지 말고 운영자가 충분히 기다린 후 재개해야 한다.

| 상황 | 결과 |
|---|---|
| 네트워크 미설정/TLS 실패/리다이렉트 | NEEDS_REVIEW / LICENSE_SECURITY |
| 401/403 | NEEDS_REVIEW / AUTH_ACCESS |
| 429/5xx/전송 예외 | FAILED_RETRYABLE / TRANSIENT |
| 404/410 | FAILED_TERMINAL / SITE_CHANGED |
| 기타 HTTP/잘못된 JSON/다른 지표·국가·연도/빈 결과/여러 페이지 | NEEDS_REVIEW / SCHEMA_CHANGED |
| 로컬 저장 실패 | FAILED_TERMINAL / INTERNAL_BUG |

전송·파일 예외의 원문은 로그/결과에 넣지 않는다. HTTP 오류의 완전 응답도 raw로
보존하지만, 임의 응답 텍스트를 오류 메시지에 복사하지 않는다.

## 원본과 최소 파싱

`data/raw/worldbank/<새 UUID>/response.json`에 requests의 content decoding 이후
엔터티 바이트를 그대로 저장한다(전송 압축 전 wire bytes를 뜻하지 않음).
같은 폴더의 request.json에는 URL·UTC 수집 시각·HTTP 상태·형식·크기·mode·출처 링크를 남긴다.
폴더·파일을 배타적으로 생성해 기존 raw를 덮어쓰지 않는다. 저장 도중 장애가 나면
부분 파일이 남을 수 있으며, 성공으로 보고하거나 기존 파일을 자동 삭제하지 않는다.

예상 JSON은 `[페이지 메타데이터, 관측 행 배열]`이다. 선택 범위가 작으므로 1페이지만
지원하며 pages>1인 결과를 부분 성공으로 처리하지 않는다. 데이터 식별자·연도·숫자형을
확인하고 원본 행 순서와 필드를 그대로 반환한다. null과 0, unit 빈 문자열, obs_status,
decimal 및 추가 필드를 보존하며 결측·단위·스케일을 보정하지 않는다.

명시적 series ID/주기/단위/불변 vintage를 응답이 제공하지 않으면 정규화 필드는 None이다.
조합은 series_id를 만들어내지 않고 series_key로 표기한다. YYYY 기간 형식과 원본 지표
명칭은 별도로 보존한다. lastupdated는 source_last_updated이며 불변 source_version은 아니다.

## 실행 연결 및 범위 경계

WorldBankGDPEngine을 `(worldbank_gdp, 1)` 키로 Orchestrator에 등록하고 StageSpec.input_data에
start_year/end_year만 전달한다. 실제 검증 보조 명령은 다음과 같다.

```powershell
.venv/Scripts/python.exe -X utf8 scripts/verify_worldbank.py --live
```

이 명령은 허용된 네트워크 환경에서만 실행한다. --live가 없으면 호출하지 않는다.
04회차 Gate A 경로를 새로 실측해야 할 때는 `--live --gate-a`를 함께 명시한다. 이는
고정 World Bank 경로를 실제로 다시 호출하므로, 저장된 결과와 해시만 확인할 때는 실행하지 않는다.
기본 명령은 보완 03의 구조화 요청→확인→새 작업→수집 경로를 검증한다.
작업·오류 이력은 기존 data/catalog.sqlite에, 보고서는 reports/alignment_03_live_*.json에
추가한다. 기존 저수준 경로는 --live --legacy로 명시 실행하며 보고서 이름은
reports/iteration_03_live_*.json이다. 최종 사용자 CLI/설명서가 아니다.

04회차 Gate A는 이 고정 경로에 한해 `WorldBankRequestDispatcher(..., gate_a=True)`를
명시했을 때 동작한다. 원본·manifest SHA256과 경로를 감사 기록에 추가하고, 기존
SQLite schema version 2를 유지하면서 검증 보고서·관측치·incident·feedback을 별도
테이블과 이벤트에 기록한다. 실패한 품질 검사는 정규화 관측치를 공개하지 않는다.

통과 실측과 검증 범위는 `docs/developer/history/ITERATION_04_REPORT.md`를 따른다. 다른 국가/지표/형식,
단위·주기 추론, 경제적 이상치, 개정 이력, 다른 기관과의 동등성 및 전체 H 시나리오는
검증하지 않았다. 데이터셋별 이용 조건을 별도로 확인해야 하며 이 결과는 재배포 승인이 아니다.

## 보완 03의 요청·전달 연결 — 2026-10-24

ingestion/worldbank_request.py의 WorldBankRequestDispatcher가 보완 02의 연결된 자식 작업을
받는다. prepare/run/resume은 현재 확인 개정과 고정 경로 지원 범위를 먼저 검사한다.
미확정 컨테이너/legacy 작업은 이 새 진입점에서 거부하고 기존 Orchestrator API는 유지한다.
build_worldbank_plan(ConfirmedSelection, settings)은 명시적인 v1 호환 계획 생성 진입점이다.

필수 기관 식별은 institution_id=worldbank, dataset_id=2, series_id=None,
series_key={source: 2, country: USA, indicator: NY.GDP.MKTP.CD}다(각 값은 문자열).
기관 조사대장의 INT-04는 문서 식별자이며 자동 별칭 추론을 하지 않는다.
요청/선택 후보 국가는 USA만, 추가 dimensions는 빈 매핑, 기간은 기존 1960..2100의
연속 1~10년이다. source 주기/preserve 단위/latest_available만 허용한다.
변형 속성 요구를 필터로 실행하는 기능은 없으므로 비어 있지 않은 requirements는 거부한다.

- file: raw_json과 설정된 raw 디렉터리만 지원한다. 기본값은 data/raw다. 기존 엔진의
  raw_path/manifest_path를 반환하며 CSV/XLSX나 임의 출력 위치로 대체하지 않는다.
- link: 제공된 available·유효 근거의 URL이 GDPQuery의 정확한 고정 URL과 같아야 한다.
  다른 API query, viewer, 일반 문서 링크는 지원하지 않는다. URL의 재작성/새 발견/GET은 없다.
  수동 필터 여부·제약·근거를 그대로 반환하며 로컬 파일 수집기가 없어도 전달할 수 있다.
  plan=None/stages=[]이고 별도 원자적 LINK_DELIVERED 이력과 delivery_result로 완료한다.
- both: collect 단계의 기존 결과를 보존하고 다음 deliver 단계에서 collection과 links를
  반환한다. 실제 GET은 수집 단계의 1회뿐이다. 링크 실패/만료 시 파일을 보존하고 검토 상태로 멈춘다.

파일은 stages[0].result.payload, 둘 다의 최종 결과는 stages[-1].result.payload,
링크 전용은 delivery_result에서 조회한다. link 완료는 수집/파싱 성공을 뜻하지 않는다.
동일 완료 작업의 반복 run은 GET/파일/전달 이벤트를 추가하지 않는다(현재 확인은 재검사한다).
실패 재개는 같은 task_id의 resume으로만 하며 조건 변경은 새 확인/새 작업이다.

실제 검증은 새 file 작업으로 실행했다. 기본 환경의 최초 시도는 TRANSIENT였고,
네트워크 허용 환경의 별도 수동 검증은 2026-10-24T03:38:31.222275+00:00에 HTTP 200,
724 bytes/2020~2022년 3행으로 완료했다. source_last_updated=2026-10-08이며 vintage가 아니다.
link/both는 fixture만 검증했다. 공식 문서 신규 조사는 없고 기존 문서화 프로필을 사용했다.
전체 406개/Ruff 통과. 자세한 파일/시도별 근거는 docs/developer/history/ALIGNMENT_03_REPORT.md를 따른다.
