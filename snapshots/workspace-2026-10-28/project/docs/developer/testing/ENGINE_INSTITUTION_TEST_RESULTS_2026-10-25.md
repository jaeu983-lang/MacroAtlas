# 엔진·기관별 오프라인 테스트 결과

**실행일:** 2026-10-25\
**목적:** 후속 작업에서 엔진별·기관별로 무엇이 통과했고 무엇을 추가 구현해야 하는지 확인할 수 있도록 결과를 고정한다.\
**범위:** 기존 로컬 pytest fixture/mock 실행과 현재 기관 레지스트리 상태 확인. 코드 변경, API live 호출, `.env` 값 확인은 하지 않았다.

## 요약

- 전체 suite: **626 collected, 625 passed, 1 skipped, 0 failed**, exit code 0.
- 네트워크: **미사용**. 따라서 이번 실행은 기관 API 연결 성공을 뜻하지 않는다.
- 기관 레지스트리: **21/21 프로필 로드 및 레지스트리 테스트 통과**.
- API 문서 상태: `documented` **15**, `unconfirmed` **6**, `not_offered` **0**.
- 실제 소스별 어댑터/fixture 검증이 있는 범위는 World Bank, BEA, e-Stat의 제한된 경로 등 일부다. 나머지 기관은 레지스트리/공통 파서 fixture 통과를 source API 성공으로 해석하지 않는다.
- 대화형 GPT 엔진: 저장소에 자연어 LLM 대화 엔진이 없으므로 **미실행**.

## 엔진별 실행 결과

분류는 pytest 모듈별 실행 수를 역할 기준으로 묶은 것이다. 모든 묶음은 같은 전체 suite 실행에서 나왔다.

| 엔진 묶음 | 포함 모듈 | 수집 | 통과 | skip | 실패 | 대표 결과 |
|---|---|---:|---:|---:|---:|---|
| 기관·사이트·메타데이터·시계열 발견 | `test_institution_site_discovery`, `test_source_guides`, `test_source_registry`, `test_metadata_discovery`, `test_series_discovery` | 86 | 86 | 0 | 0 | 기관 후보·가이드·메타데이터·시계열 검색 및 레지스트리 계약 검증 |
| 매핑·지식·개선 제안 | `test_concept_search`, `test_feedback_knowledge`, `test_knowledge_reuse`, `test_improvement_patterns` | 42 | 42 | 0 | 0 | concept 검색, 범위 있는 지식 재사용, feedback 및 read-only 개선 후보 검사 |
| 수집·커넥터·원본 보존 | `test_ingestion_bulk`, `test_ingestion_formats`, `test_official_api_credentials`, `test_worldbank_request`, `test_worldbank`, `test_gate_a` | 190 | 189 | 1 | 0 | mock 응답·오류·인증 경계·저장/read-back 및 World Bank 고정 경로 |
| workflow·orchestration·계약 | `test_orchestration`, `test_workflow`, `test_workflow_contracts`, `test_workflow_extensions` | 292 | 292 | 0 | 0 | 단계 실행, 오류 분류, 재시도/복구, 계약 직렬화 검증 |
| 기반·상태 점검 | `test_foundations`, `test_health` | 16 | 16 | 0 | 0 | 기본 모델 및 상태 진단 검증 |
| **합계** | 21개 테스트 모듈 | **626** | **625** | **1** | **0** | **exit code 0** |

### 출력·데이터 무결성 예시

- 기존 World Bank 고정 fixture E2E 기록(Iteration 18/20): 30회 반복에서 **30/30 완료**, raw hash와 SQLite read-back 확인.
- 대표 저장 결과: 값 `[123.5, null, 0]`, 상태 `[reported, missing, reported]`. 결측과 0을 구별했다.
- Iteration 20 재측정: 같은 고정 fixture 2회 실행, 각각 **30/30 완료**, hash·missing/zero invariant 통과.
- 이 결과들은 fixture/mock 응답이다. live 기관 자료를 확인한 결과가 아니다.

## 기관별 결과

이번 전체 pytest 실행은 네트워크를 사용하지 않았다. 아래의 `레지스트리 테스트` 통과는 기관 프로필의 분류/불변식 테스트를 뜻하며, 해당 기관 API를 호출했다는 뜻이 아니다.

| 기관 ID | 기관 | API 상태 | 오프라인 구현·fixture 상태 | 이번 live 결과 |
|---|---|---|---|---|
| INT-01 | IMF | 문서 확인 | 합성 IMF형 SDMX/메타데이터 fixture; 기관 API adapter 아님 | 미실행 |
| INT-02 | BIS | 문서 확인 | 사이트·형식 탐색 fixture; BIS API adapter 없음 | 미실행 |
| US-03 | Treasury TIC | 미확인 | 합성 TIC codebook/파일 해석 fixture; 공식 endpoint 호출 없음 | 미실행 |
| US-04 | BEA | 문서 확인 | BEA JSON GET client와 mock 응답 테스트; workflow 미연결 | 미실행 |
| EU-01 | ECB | 문서 확인 | 일반 SDMX fixture; ECB 전용 adapter 없음 | 미실행 |
| EU-02 | Eurostat | 문서 확인 | 일반 catalogue/SDMX fixture; Eurostat 전용 adapter 없음 | 미실행 |
| JP-02 | Japan MOF | 미확인 | adapter/기관 fixture 미구현; 공식 파일은 표별 검토 필요 | 미실행 |
| JP-01 | Bank of Japan | 문서 확인 | adapter/기관 fixture 미구현 | 미실행 |
| JP-03 | e-Stat | 문서 확인 | e-Stat JSON GET client와 mock 응답 테스트; workflow 미연결 | 미실행 |
| CN-01 | PBOC | 미확인 | 사이트 시나리오 fixture만 있음; 수집 adapter 없음 | 미실행 |
| CN-02 | SAFE | 미확인 | 사이트 시나리오 fixture만 있음; SAFE 자료 수집 adapter 아님 | 미실행 |
| CN-03 | NBS China | 미확인 | 사이트 시나리오 fixture만 있음; 수집 adapter 없음 | 미실행 |
| INT-03 | OECD | 문서 확인 | adapter/fixture 미구현 | 미실행 |
| INT-04 | World Bank | 문서 확인 | 고정 WDI GDP 경로 일부에 source fixture/adapter 존재 | 이번 실행에서는 미호출; 과거 USA/WDI/`NY.GDP.MKTP.CD` 단일 경로만 제한 live 근거 있음 |
| US-01 | Federal Reserve Board | 문서 확인 | adapter/fixture 미구현; FRED 제공 주체와 DDP crosswalk 확인 필요 | 미실행 |
| US-02 | St. Louis Fed FRED/ALFRED | 문서 확인 | adapter/fixture 미구현 | 미실행 |
| US-05 | Bureau of Labor Statistics | 문서 확인 | adapter/fixture 미구현 | 미실행 |
| US-06 | U.S. Census Bureau | 문서 확인 | adapter/fixture 미구현 | 미실행 |
| EU-03 | Deutsche Bundesbank | 문서 확인 | adapter/기관 fixture 미구현 | 미실행 |
| EU-04 | Bank of England | 미확인 | adapter/fixture 미구현; 공식 다운로드와 API 상태는 별도 | 미실행 |
| EU-05 | INSEE | 문서 확인 | adapter/기관 fixture 미구현 | 미실행 |

## 전체 실행의 한계와 판정

- `documented`는 공식 API 문서 상태이며 데이터 요청 성공이나 수집 가능 상태가 아니다.
- `unconfirmed`는 API가 없다는 뜻이 아니다. 공식 문서 확인 없이 endpoint를 추정해 호출하지 않았다.
- BEA/e-Stat은 mock 클라이언트 경로만 검증됐고 workflow 통합 및 실제 키 인증은 미검증이다.
- World Bank의 과거 제한 live 근거는 단일 USA/WDI/GDP 고정 경로뿐이다. 다른 지표/국가 또는 다른 기관에 일반화하지 않는다.
- 전체 suite에서 유일한 skip은 Windows에서 symlink를 만들 수 없는 환경에서 symlink 보호 테스트를 실행하지 못한 건이다.
- 8개 사람용 대화 시나리오는 기대 동작 문서다. 자연어 GPT UI/LLM은 저장소에 없어서 실제 프로그램 대화 출력은 생성되지 않았다.

## Iteration 23 이후 이어갈 전기관 우선순위

1. BIS 하나를 우선 고정하지 않고 21개 source를 모두 대상으로 API 문서→기관 fixture→mock ingestion→offline E2E→bounded live 순서를 적용한다.
2. Luna Max batch는 공통 SDMX(7개)와 개별 REST(8개), API 미확인 6개로 묶을 수 있다. 기관별 dataset/인증/coverage/live 판정은 각각 기록한다.
3. 전체 offline suite의 625 passed, 1 skipped는 live 통과가 아니다. 현재 코드로 전기관 관측치를 가져올 수 있는 상태가 아니므로 connector·fixture 없는 source를 먼저 준비한다.
4. [전기관 검증 프로그램](ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 공식 API가 확인된 15곳과 API 미확인 6곳의 진행 gate 및 최종 상태값을 둔다. API가 해당 표에 없다고 공식 확인된 경우에만 허용된 공식 파일 경로를 검토한다.
5. 이 report의 full-suite run은 network를 사용하지 않았다. API key, credential 값, live 요청은 확인하거나 실행하지 않았다.

## 재현 명령

```powershell
.\.venv\Scripts\python.exe scripts/measure_test_suite.py
```

실행 환경: Windows 11, repository `.venv` Python 3.12.14. 이번 실행의 `network_used` 값은 `false`였다.
