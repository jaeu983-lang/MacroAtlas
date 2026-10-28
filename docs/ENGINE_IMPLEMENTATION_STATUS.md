# 엔진 구현 현황과 데이터 접근 한계

> 대조 기준: 기본 브랜치 `codex/iteration-04-gate-a`의 HEAD `21086bf` (PR #78 merge; 2026-10-28). 이후 엔진 실행 검증은
> [2026-10-28 smoke 기록](ENGINE_RUNTIME_SMOKE_2026_10_28.md)에 보존한다. 이 문서는 런타임 코드와 현재 제품 현황을
> 처음부터 끝까지 연결해 설명한다. **지원되지 않는 일**은 기관 API/데이터 계약 또는 접근 권한 때문에 현재
> 인터페이스로 할 수 없는 일, **미구현**은 기술적으로 확장 가능하지만 코드에 아직 연결하지 않은 일로 나눈다.
> provider 제한은 현재 어댑터의 검증 범위와 공식 API 형태를 뜻하며 기관 전체 데이터의 한계를 뜻하지 않는다.
> 완료 조건과 게이트 판정은 [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)를 따른다.

## 현재 구현을 한 줄로 보면

MacroAtlas는 자유 질문에 바로 답을 생성하는 완성형 대화형 데이터 제품이 아니다. 구조화 요청을 받아 후보를
근거와 함께 찾고, 운영자가 출처·범위를 확인한 다음, 공통 실행기가 제한된 provider adapter를 실행한다.
수집한 원본은 보존하고 구조·품질·최신성을 검사하며, 현재 연결된 두 provider의 검증 결과만 CSV로 내보낸다.
사례 평가와 피드백은 이 검색·수집 흐름과 분리된 검토 도구다. AI는 코드나 지시문을 자동 변경하지 않는다. 운영자가 별도로 지시하면 지시문은 수동으로 편집·버전 고정하고 동일 사례로 전후 결과와 시간을 비교한다.

## 시작부터 끝까지의 동작

| 순서 | 엔진/모듈 | 현재 동작 | 현재 경계 |
|---|---|---|---|
| 1. 요청 | `workflow_contracts.py`, CLI | 기관 힌트, 개념, 기간, 주기·단위 요구, 선택/출력 범위를 구조화한다. 미확정 값은 unknown으로 보존한다. | 범용 자연어 parser나 대화형 질문 해소기는 없다. CLI는 문서화된 고정·제한 query만 실행하며 그 밖의 조립은 Python API 호출자 책임이다. |
| 2. 후보 탐색 | `discovery/series_search.py`, `macroatlas search` | 고정 WDI seed와 해시 검증된 BLS/Census metadata archive를 오프라인 lexical ranking하고 후보 근거·불확실성을 반환한다. 요청/결과는 task history에 저장한다. | 공식 catalog를 가져오거나 갱신하지 않는다. English token search only이며 전체 기관 검색, 자동 선택·수집은 없다. 순위는 의미 일치의 증명이 아니다. |
| 3. 확인/계획 | `workflow_extensions.py`, `acquisition_planning.py` | 후보 선택은 명시적으로 확인하고, 지원 범위·해석된 기간·출력 조건을 검사한다. API 수집 계획은 제한된 요청 chunk로 산출한다. | 검색만으로 수집하지 않는다. 자동 선택, 자동 승인은 없다. chunk 계획기는 queue/병렬 실행기가 아니다. |
| 4. 공통 실행 | `orchestration/registry.py`, `composition.py`, `runner.py` | `(engine, version)` registry가 저장된 plan을 조립한다. 선형 stage를 순차 실행하고 상태·시도·근거·결과를 SQLite에 기록한다. 성공 prefix 재사용은 fingerprint·TTL·검증기 조건을 모두 요구한다. | 일반 DAG·분산 worker queue·강제 중단·자동 HTTP 재시도/backoff는 없다. Retry-After와 재개는 수동이다. 외부 파일/HTTP와 SQLite를 하나의 원자적 트랜잭션으로 묶지 못한다. |
| 5. source 호출 | `connectors/*`, `ingestion/*` | WB·BOJ·BLS·Census 어댑터가 각 고정 요청을 만들고 응답 구조를 검사한다. 공통 HTTP 전송·raw 저장·stage 결과 계약을 공유한다. | 기관별 endpoint·식별자·응답 스키마는 다르므로 adapter는 남는다. 일반 series를 임의 요청하거나 기관 웹사이트를 자동 탐색하지 않는다. |
| 6. 원본/메타데이터 | `storage/raw_downloads.py`, `statistical_downloads.py`, `metadata_archives.py` | 다운로드 원본과 credential-free manifest를 저장하고 해시·출처·수집 시점을 연결한다. 메타데이터 원본과 제한 정규화본도 별도 보존한다. | 범용 관측치 카탈로그와 모든 원본의 장기 보존·버전 마이그레이션은 완성되지 않았다. 저장 성공은 경제적 의미 검증을 뜻하지 않는다. |
| 7. 구조·품질·최신성 | `connectors/*` parser, `ingestion/statistical_quality.py`, `freshness.py` | 구조/식별자, 수치·결측, 중복/범위, 원본 변경 여부, 최신성 평가를 시행한다. freshness anchor는 non-null 값이 있는 최신 period를 사용하며 결측 원본행은 보존한다. | 공통 typed TimeSeries/Observation, 신뢰할 release calendar, 모든 파일·시계열의 의미/단위 검증은 없다. 주파수별 기본 허용 일수는 정책이지 기관의 실제 발표 일정 증명은 아니다. |
| 8. 사용자 출력 | `ingestion/csv_export.py`, `cli.py` | 완료된 검증 World Bank GDP와 BOJ FXER task를 read-only 검증 후 CSV 및 provenance sidecar로 출력한다. BLS/Census CLI는 조회 결과와 저장 경로를 task 요약에 보여준다. | BLS/Census export, 원자료 XLSX 출력, 다중 series 정렬/비교 XLSX는 미구현. 값·단위·빈도 호환성을 추측해 합치지 않는다. |
| 9. 평가/피드백 | `evaluation/*`, `storage/feedback.py`, `storage/promotion.py`, `feedback_cli.py` | split/hash 검색 비교, confirmation boundary trace, 고정 로컬 성능 budget, one-time holdout, append-only feedback 및 hash-chain promotion ledger를 지원한다. 제품 Gate C는 fixed v2 search scope에서 PASS다. | 후보는 평가 전용이며 아직 승격되지 않았다. AI는 별도 로그에 `hold` 의견을 기록했지만 공식 Gate D 원장에는 실제 사람 결정이 없다. CLI는 독립 사람 self-attestation·hash·commit을 기록하지만 신원을 인증하지 않는다. Trace는 계획 생성 경계까지이며 provider/API/raw-write/export 내부 동작, 통계적 동등성, 사람 관찰은 측정하지 않는다. |
| 10. 운영 성능 | `performance/*`, `large_file_*` | stage와 지원되는 phase를 monotonic clock으로 계측하고 비민감 집계(p50/p95·처리량·표본 수)를 출력한다. Linux 대용량 별도 qualification/production worker가 있다. | live 성능 표본은 승인된 자연 요청만 가능하며 아직 충분한 운영 표본이 아니다. 대용량은 BIS GLI 단일 flat ZIP profile뿐이고 경제 의미 해석은 안 한다. |

### 검색·피드백의 안전한 반자동 루프

현재 가능한 흐름은 **사용자 피드백을 append-only revision으로 보존 → 운영자가 검토 → privacy clearance가 있는
accepted `user_instruction`만 불완전한 development draft로 내보냄 → 사람이 근거·기대 결과·금지 조건을 채우고
사례 심사/평가를 수행 → 통과 결과를 별도 명시 변경으로 반영**이다. 이전 revision은 로그에 남는다.
분류를 구현할 경우에도 입력 snapshot에 대한 분류 결과를 별도 버전으로 저장하고 입력·출력 count/key/hash를
대조해야 한다. 분류기는 라벨·정리 제안만 만들며 기존 질문을 삭제·덮어쓰거나 지시문을 자동 수정하지 않는다.
현재 AI 일괄 분류와 코드 A/B 실행 기능은 구현되지 않았다. 추후 분류를 넣을 때는 모델 호출 시간/비용과
snapshot 작성·검증 등 로컬 처리 시간을 별도 계측해야 하며, 현재 성능 report에는 분류 모델 비용 항목이 없다.

## 엔진별 구현 및 한계

“엔진”은 기관 이름마다 독립 실행 시스템이 있다는 뜻이 아니다. 공통 stage lifecycle과 registry 위에 목적별
engine 및 기관 adapter가 플러그인처럼 연결된다.

| 엔진/경계 | 구현 | 현재 한계 |
|---|---|---|
| Engine contract / Registry | [`contracts.py`](../src/macro_data_platform/contracts.py), [`registry.py`](../src/macro_data_platform/orchestration/registry.py), [`composition.py`](../src/macro_data_platform/orchestration/composition.py): `StageInput → StageResult`, engine/version 고정 등록, 공통 조립 및 saved plan resume | registry는 호출 가능한 engine 인스턴스를 조립한다. 자격증명 발급, provider 접근권한, 자동 선택은 담당하지 않는다. |
| Orchestrator / History | [`runner.py`](../src/macro_data_platform/orchestration/runner.py), [`history.py`](../src/macro_data_platform/storage/history.py): 순차 실행, idempotency key, task/stage attempt, 오류 상태, 수동 retry/resume, 성공 prefix 재사용 | 분산 동시성·lease·worker 강제 종료·자동 retry/backoff 없음. 외부 side effect exactly-once 보장 안 됨. |
| Candidate Search | [`series_search.py`](../src/macro_data_platform/discovery/series_search.py), [`cli.py`](../src/macro_data_platform/cli.py), [`evaluation/cli.py`](../src/macro_data_platform/evaluation/cli.py): 로컬 catalog ranking CLI, 근거/상태/불확실성 보존, 제한·abstention 및 오프라인 평가 비교 | 실시간 전체 catalog 수집·다국어 의미 검색·LLM 질문 해석 없음. 검색 순위 자체는 채택 근거가 아니며 별도 수집 확인이 필요. |
| World Bank WDI collector | 확인된 미국 GDP current-dollar workflow와 `worldbank_series/1` exact country/source/indicator annual raw-only query. 둘 다 공통 EngineRegistry/Orchestrator, raw/manifest, 구조 검사 및 freshness를 사용한다. | General path는 1 series·최대 100 연속 연도·1 page·1 MiB다. metadata 검색, 단위·의미 검증 및 CSV/XLSX export는 없다. GDP 전용 품질 규칙은 일반 지표에 적용하지 않는다. |
| BOJ FX collector | FM08/FXERD01 one-month path와 boj_observations_range/1의 연속 1–120개월 path. metadata와 observations를 분리하고 변경 감지·freshness·재개 및 동일 series CSV 재검증을 지원한다. | 다른 DB/series, 120개월 초과, getDataLayer·탐색은 미지원. natural provider failure/revision은 여전히 미검증이다. |
| BLS collector | Public Data API v2, exact ID 지정 CLI/Python query, 1–20 series ID, 1–20년 구간, optional `BLS_API_KEY`, raw/manifest·parse·품질/freshness | CLI는 series catalogue를 검색하지 않는다. ID 의미/단위가 확인된 series만 안전하게 쓸 수 있다. 응답에 frequency/unit은 unknown. 장기·다수 series는 여러 요청 설계와 예산 검증이 필요. |
| Census collector | ACS1/ACS5 exact variable 지정 CLI/Python query, 한 해, 1–50 variable, 미국 전체 또는 단일 주 geography, 필수 Census key, raw/manifest·parse·품질/freshness | 임의 Census dataset·geography 조합·시간 범위·다중 지역 batching은 미지원. 변수 정의/단위 미확인 응답은 의미가 확정되지 않음. |
| Metadata engines | BLS 1 series metadata, Census ACS 1 variable metadata, 입력 SDMX 구조 및 제한 normalization/archive | provider 전체 메타데이터 수집·주기적 동기화·차원 간 자동 맵핑은 없음. 메타데이터 API 호출도 데이터 검색 전체를 대신하지 않음. |
| Non-API intake / deferral | 로컬 CSV/TSV/TXT, XLS/XLSX, HTML table, ZIP 내부 표를 제한 파싱·보존. Iteration 29에서 transport/parser/preflight가 typed `CapacityFinding`을 쓰고 구조화 deferral log를 남긴다. | 일반 파일의 열 이름·행은 보존해도 통계 의미·단위·날짜를 자동 확정하지 않는다. 고정폭 텍스트·미선언 구분자·대형 파일은 지원 범위 밖/검토 대기. |
| BIS GLI large-file | 보존된 BIS GLI flat ZIP의 Linux 전용 qualification 후 명시 승인 production, 문자열 JSONL chunk, checkpoint/resume | 단일 source/profile·artifact만 지원. 값의 의미 정규화/보편 CSV/XLSX·다른 ZIP/API의 대용량 처리로 확장되지 않음. |
| Feedback / Evaluation | [`feedback_cli.py`](../src/macro_data_platform/feedback_cli.py), [`storage/feedback.py`](../src/macro_data_platform/storage/feedback.py), [`evaluation/`](../src/macro_data_platform/evaluation/): append-only feedback, explicit review, 불완전 draft bridge, split/hash 검증, confirmation-boundary trace, 로컬 성능 예산, one-time holdout, D decision ledger | AI 권고는 별도 decision log에 남겼지만 실제 사람 결정은 미완료이며 promotion ledger는 비어 있다. 도구는 사람 신원을 인증하지 않는다. confirmation trace는 proposal-to-plan 경계까지이며 provider·raw-write·export 내부 호출을 검증하지 않는다. 통계적 동등성이나 analyst usability를 주장하지 않는다. |
| Performance | Orchestrator 전체 stage 시간 및 선택 network/raw/parse/quality/SQLite/export phase, privacy-safe 집계 | 세부 phase는 일부 겹친다. Discovery/general tabular/validator leaf timing은 제한적이며 표본이 적으면 p95를 주장하지 않는다. |

## 기관별 데이터 접근: API와 비API

다음 “할 수 없음”은 **현재 연결된 경로 또는 provider/API 계약에서 지원하지 않는다는 뜻**이다. 기관 웹사이트에
데이터가 없다는 일반 명제가 아니다. “가능하지만 미구현”은 별도 API·metadata endpoint·공개 파일을 더 연결하고,
검증/예산/권한을 정하면 구현할 수 있다는 뜻이다.

| 기관/방식 | 지금 가능한 범위 | 현재 경로에서 할 수 없는 것 | 가능한데 아직 미구현/미검증인 것 |
|---|---|---|---|
| World Bank API | 인증 없는 WDI Indicators API: 고정 미국 GDP와, 명시한 ISO3·indicator/source 2의 annual series; `1960..2100` 내 1–100년, JSON 1 page·최대 1 MiB | 현재 generic 경로는 여러 series·다중 page·비연간 series·자동 metadata 탐색을 처리하지 않음. 공식 응답에 없는 월별 값을 만들 수 없음. | pagination, metadata/indicator catalog, 검증된 단위·빈도 프로파일은 별도 어댑터 범위로 가능. 주기별 전수 지원은 아직 없음. |
| World Bank 비API | 일반 로컬 파일 intake는 형식/크기 한도 안에서 표를 보존 | 현재 파일 입력으로 World Bank 출처를 검증하거나 API series와 자동 결합하지 못함 | 명시 URL/공식 파일 허용목록, 출처 증거, 해당 schema adapter를 추가하면 지원 가능. 자동 웹 크롤링은 미구현. |
| BOJ API | 공식 통계 API의 FM08/FXERD01 metadata와 1–120개월 관측 query; 명시 실행, raw 보존, 범위별 변경 감지 | 다른 database/code, 120개월 초과, getDataLayer, 전체 series search는 현재 query contract로 불가 | 공식 API 문서의 60,000-point cap보다 보수적인 120개월 제한을 둔다. 다른 code·bulk metadata는 endpoint 계약과 의미 확인 후 별도 추가 가능. |
| BOJ 비API | 공통 local table parser로 지원 형식 내 파일을 제한 처리 | BOJ 파일임을 자동 식별·검증하거나 BOJ API와 동일 series로 간주하지 못함 | BOJ 공개 다운로드 파일별 schema/manifest adapter와 출처 검증을 추가하면 가능. |
| BLS API | Public Data API v2에서 명시 series ID 1–20개, 1900–2100 사이 1–20년(현재 query 검사는 최대 20년 미만 차이), API key 선택; 현재 결과의 구조 검증·raw 보존 | 자연어로 series ID를 찾거나 코드만으로 unit/frequency/economic concept를 확정하지 못함. 응답 페이지 밖/지원 범위 이상의 기간을 한 호출에 넣지 못함 | Series ID catalog/검색, 주기·단위 정의 연결, 요청 chunking/쿼터 정책, 검증된 장기 이력 workflow는 가능하지만 제품 경로로 미구현. API 한도·등록키에 따른 차등은 실제 계정/공식 문서 확인 필요. |
| BLS API 메타데이터 | 선택된 series의 API 응답과 metadata archive 연동 경로가 있음 | 전체 BLS catalog의 자동 동기화/semantic mapping은 안 됨 | 공식 전체 catalog/bulk metadata 다운로드와 증분 갱신을 별도 연결 가능. |
| BLS 비API | 로컬 표 파일 제한 intake; 안전하게 수집된 metadata archive는 catalog 후보로 쓸 수 있음 | BLS bulk 파일을 자동 다운로드·전체 파싱하거나 표의 경제적 의미를 추론하지 못함 | 공개 bulk series 파일 profile, manifest/hash/version, 대용량 예산·검증을 추가하면 가능. |
| Census API | ACS 1-year/5-year, 명시 연도, 최대 50 variable, `us:1` 또는 단일 `state:NN`, `CENSUS_API_KEY` 필수 | 다른 Census dataset, county/tract 등 현재 geography pattern 밖의 지리, 범위/다중 연도·지역 batch는 현재 adapter에서 불가. API 미제공 기간/추정치를 생성하지 못함 | geography hierarchy batching, 다양한 Census program, variable catalog 검색, estimate/MOE metadata·단위 결합은 별도 query와 검증을 추가하면 가능. 키·접근 권한 필요. |
| Census API metadata | ACS 선택 변수 하나의 metadata 요청 및 archive/normalization | 모든 변수/연도/프로그램을 다루는 동기화·비교·의미 동일성 검증은 안 됨 | 전체 ACS variable metadata catalog와 연도 간 schema diff를 연결 가능. |
| Census 비API | 공통 local table input만 가능 | 공식 bulk Census 파일의 자동 수집·코드북/추정치 매칭·API 결과와 조인은 미지원 | Census 공개 bulk dataset별 parser/geo-variable key·vintage·MOE 규칙을 정해 구현 가능. |
| BIS (비API) | BIS GLI flat ZIP 1건의 보존 artifact를 Linux에서 제한 시험/승인 후 구조 보존 JSONL 처리. 다른 파일은 로컬 preflight 및 deferral 기록 가능 | 현재 경로는 GLI 외 dataset/zip profile, Windows production, 표 의미 정규화·CSV/XLSX 연결을 지원하지 않음. GLI 관측 사례는 parser 셀 500,000 limit에 걸려 deferral됨 | typed schema와 chunk/예산 검증 후 GLI 확대 또는 다른 BIS 공개 파일 profile 구현 가능. 즉 원본 크기 자체가 불가능한 게 아니라, 현재 작은 표 parser 용량과 승인된 전용 profile 경계가 제한. |
| TIC (비API) | 목록/기록 도구는 deferred source seed를 조회할 수 있음. 일반 로컬 표는 parser 한도 내 처리 가능 | TIC 파일을 자동 감시·다운로드·해석·분석 데이터로 내보내는 실행 경로는 없음. 사용자가 Vantage를 필요로 하지 않는다고 정해 해당 경로도 범위 제외 | 명시 source/version/polling policy와 parser를 만들면 기술적으로 가능하지만 제품 계획에서는 우선순위/필요성이 낮아 제외. |
| 사용자 제공 로컬 파일 | CSV/TSV/TXT(UTF-8/UTF-16 BOM), XLS/XLSX, HTML table, ZIP의 단일 표 멤버를 제한 parse. 원본 형식은 provenance와 함께 보존할 수 있음 | 입력 기준 16 MiB 미만, ZIP 1000 entries 미만/압축해제 64 MiB 미만/ratio 200 미만, 최대 100,000행·1,000열·500,000 cells 및 field budget. 고정폭 TXT, 불명확한 delimiter, 안전하지 않은 archive, 셀 계산 초과는 자동 처리 안 됨 | 별도 large-file profile/worker에 schema·자원 상한·checkpoint를 더하면 기술적으로 가능. 형식 수용만으로 값의 단위/주기/출처가 검증되지는 않음. |

## 정확한 한계 분류

- **실제로 할 수 없는 것:** API/파일 자체가 제공하지 않는 주기·기간·단위·차원을 응답에서 복원하는 일, provider 인증이나
  접근권한 없이 보호된 endpoint를 호출하는 일, 원본에 없는 관측치를 사실로 만들어내는 일. 현재 WB/BOJ/BLS/Census query
  contract에 없는 조합은 해당 호출 경로에서 실행할 수 없다.
- **가능하지만 현재 연결되지 않은 것:** provider의 추가 공개 endpoint/bulk catalogue, 더 많은 BOJ/WDI series, BLS/Census
  전체 catalog·geography, 검증된 시간 범위 분할, provider별 bulk file, XLSX writer, 공통 typed series catalog,
  자동 분류 제안. 각각의 사용에는 별도 근거·권한·schema·품질·성능 검증이 필요하다.
- **기술적으로 가능해도 현재 정책상 하지 않는 것:** 피드백으로 prompt/규칙/code를 자동 변경하는 일, 자동으로 검색 후보를 확정해
  수집하는 일, 일괄 보간/forward-fill, 기관 자료를 근거 없이 동일 series로 합치는 일. 이는 안전 요구상 자동 동작이 아니다.
- **가능한지 아직 확인되지 않은 것:** 공급자별 상용/계정별 quota, 특정 계정의 접근 권한, 미검증 endpoint·다운로드 링크의 장기 안정성,
  실제 자연 요청의 latency. 문서화나 fixture 통과만으로 live 동작이라고 주장하지 않는다.

## 현재 상태/실행 안내의 기준 파일

상세 게이트·통과 판정: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). 데이터 제품 요구와 원칙: [`PROJECT_PLAN.md`](../PROJECT_PLAN.md).
공통 구조·CLI 및 성능 연결: [`ENGINE_CONNECTIONS.md`](ENGINE_CONNECTIONS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md).
기관별 검증 기록: [`connectors/WORLDBANK.md`](connectors/WORLDBANK.md), [추가 WDI series 경로](connectors/WORLDBANK_SERIES.md), [`connectors/BOJ.md`](connectors/BOJ.md),
[`LARGE_FILE_ENGINE.md`](LARGE_FILE_ENGINE.md). 실행 명령은 README와 각 provider 기록을 따른다.
