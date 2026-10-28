# Iteration 24 — 문서 확인 SDMX API raw-response adapter batch

**기준일:** 2026-10-25\
**Track:** C — 기관별 API connector\
**Gate:** O — PASS\
**시작 Git 기준점:** `778ab41` (`codex/iteration-07-08-discovery`). 시작 시 worktree에 여러 기존 변경이 있었으며 보존했다. 이번 작업은 stage/commit/merge하지 않았다.

## 목표와 경계

사용자가 API 문서 미확인 6개 기관은 우선 구현에서 제외하고, 공식 API 문서가 있는 기관의 adapter를 먼저 늘리도록 요청했다. 저장소 규칙의 one-High-iteration gate에 따라, 이번 회차는 같은 SDMX 계열 중 BIS, OECD, ECB, Eurostat, Deutsche Bundesbank, INSEE 6곳의 raw-response client까지 구현했다.

IMF도 API 상태는 `documented`다. 다만 IMF 공식 API 페이지는 상세 Swagger 탐색을 위해 beta portal account 로그인을 안내하고, 이번 작업에서 검토 가능한 공식 상세 경로/auth contract가 없었다. 따라서 endpoint를 추정해 client를 만들지 않고 다음 task의 공식 문서 gate로 남겼다. API가 없다고 분류한 것은 아니다.

## 구현 내용

- `src/macro_data_platform/connectors/sdmx.py`에 기관별 고정 root와 독립 route builder를 갖는 6개 client를 추가했다.
- 공통 전송은 HTTPS host/path allowlist, GET, 명시적 `MACROATLAS_NETWORK_ENABLED=true`, redirects 거부, `trust_env=False`, (5, 20)초 connect/read timeout, 최대 30초 elapsed bound, 8 MiB 응답 상한을 적용한다.
- 구조/데이터 응답은 기관이 제공한 response entity bytes로 반환한다. SDMX payload parsing, metadata normalization, observation validation, storage, workflow 연결은 포함하지 않았다.
- 데이터 query는 provider별 route의 차이를 유지한다. Eurostat의 무필터 전체 dataset 요청은 막았으며 INSEE IDBANK는 한 요청 1–100개로 제한했다.
- `tests/test_sdmx_connectors.py`에서 source별 URL, request options, 원 payload bytes, network-off, bad host/path, credential-like query, redirect/status, byte limit과 URL 입력 제한을 mock session으로 검사했다.
- source registry, 기관 상태표, 계획 문서에는 API client/fixture/workflow/live 상태를 분리해 반영했다.

공식 route 근거는 [BIS SDMX API v2](https://stats.bis.org/api-doc/v2/), [OECD SDMX REST v1](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1), [ECB Data API](https://data.ecb.europa.eu/help/api/data), [Eurostat SDMX 2.1 guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/sdmx2.1), [Bundesbank SDMX API](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448), [INSEE SDMX BDM service](https://www.insee.fr/en/information/2868055)에서 확인했다.

## 변경 파일

- `src/macro_data_platform/connectors/sdmx.py` — bounded transport와 6개 provider별 client.
- `src/macro_data_platform/discovery/source_registry.py` — 6개 source의 상태를 제한 raw-response client/mock route로 갱신.
- `tests/test_sdmx_connectors.py` — 기관별 request/transport mocked tests.
- `tests/test_source_registry.py` — client status와 no-live claim을 확인하는 registry tests.
- `docs/developer/connectors/SDMX_FAMILY.md`, `docs/developer/connectors/BIS.md`, `docs/developer/connectors/README.md` — route·한계·후속 gate.
- `docs/developer/ARCHITECTURE.md`, `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/EXECUTION_PLAN.md`, `docs/developer/testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md` — 현재 개발 상태와 다음 순서.
- `docs/operator/reference/INSTITUTION_API_AUDIT.md`, `docs/operator/reference/INSTITUTION_CATALOG.md`, `docs/operator/reference/INSTITUTION_IMPLEMENTATION_STATUS.md` — 운영자 상태표.
- `PROJECT_PLAN.md` — 현재 API client 구현 상태.
- `docs/developer/history/DECISION_LOG.md` — D-091 결정.
- `docs/developer/history/ITERATION_24_REPORT.md` — 이 회차 증거와 한계.

## 검증 결과

| 검사 | 결과 |
|---|---|
| 변경 전 관련 회귀 subset | 35 passed, 1 skipped |
| SDMX + 관련 subset | 58 passed, 1 skipped |
| 전체 offline pytest | **651 passed, 1 skipped, 0 failed**, exit 0 (35.13초) |
| Ruff (`--no-cache`, 변경 Python 파일) | **통과** |
| Live API/network | **실행하지 않음**; 모든 route 검증은 mock session |

첫 전체 suite 실행에서 registry 상태 설명의 문구만 과하게 고정한 assertion 1개가 실패했다. assertion을 실제 계약(“live” 표시 여부)에 맞게 고친 뒤 전체 suite를 다시 실행했고 통과했다. 최초 Ruff 실행은 `.ruff_cache` 임시 파일 생성이 Windows access denied로 실패했으며, cache를 사용하지 않은 재실행은 통과했다. 기존 한 건 skip은 Windows symlink 지원 제약이다.

## Gate O 판정과 한계

**PASS:** 6개 기관별 경로 builder와 제한 전송 동작을 offline mock으로 검증했다. 위험한 호스트/path, redirect, credential 이름 query parameter, network-off, 초과 body를 허용하지 않았다. 전체 회귀 suite와 변경 Python 파일 Ruff도 통과했다.

이번 gate는 **실 API endpoint가 연결되는지, 실제 provider 응답 형식·데이터 내용이 맞는지, 인증이 성공하는지 또는 전기관 수집이 동작하는지 증명하지 않는다.** live evidence는 계속 World Bank의 과거 고정 USA/WDI/GDP 경로뿐이다. 신규 6개는 source-specific raw request clients이며 공식 payload fixture parsing과 workflow integration은 후속이다.

## 다음 순서

1. IMF 공식 beta portal에서 API 상세 route/auth 문서를 확보할 수 있는지 조사한다. 근거를 얻지 못하면 `documented API / implementation pending specification`으로 유지한다.
2. 나머지 documented APIs (FRED/ALFRED·Board via FRED, BOJ, BLS, Census)용 adapter를 API family별 High iteration으로 추가한다.
3. 기존 World Bank·BEA·e-Stat 제한 API client를 요청된 dataset discovery, source metadata, workflow 단계로 확장한다.
4. source-specific payload fixture/parser와 workflow/storage/read-back/recovery를 별도 gate로 통과시킨다.
5. 이 작업이 완료되기 전까지 API 문서 미확인 6개는 endpoint를 추정하지 않고 표별 공식 조사 대상으로 둔다. 모든 live canary도 기관별 별도 readiness gate에 둔다.
