# 공통 HTTP 전송층과 API 계열 어댑터

**목적:** 반복되는 안전한 HTTP 실행 규칙은 공통층에서 유지하고, API별 route·의미·parser는 adapter에 둔다. GET과 명시적으로 제한된 JSON POST를 지원한다.

## 왜 World Bank와 SDMX가 따로 있었나

두 경로는 모두 HTTPS GET을 하지만 데이터 계약이 다르다.

| 구분 | World Bank WDI 제한 client | SDMX clients |
|---|---|---|
| API 계약 | WDI Indicators의 country/indicator/date/source query | provider별 data·structure resource와 flow/agency/version/dimension key |
| 응답 | World Bank JSON page envelope 및 관측 행 | SDMX-ML/CSV/JSON 등 원 payload bytes; provider마다 형식 차이 |
| 규칙 | WDI 지표·국가·기간·페이지 검증, 오류 본문 raw 보존, Retry-After 처리 | provider root/path, 구조·데이터 작업, 식별자 인코딩, query 및 content negotiation |
| 현재 제한 | USA GDP 고정 경로 하나 | BIS/OECD/ECB/Eurostat/Bundesbank/INSEE route client; payload parser는 미구현 |

따라서 **기관/API 요청·응답 adapter는 분리**하는 것이 맞다. 다만 두 구현에 세션 생성, 암묵 설정 차단, timeout, byte streaming, redirect 거부가 반복되어 있으므로 **HTTP 실행 기초는 공유**한다.

## 목표 계층

```text
기관 client
  ├─ 공식 route와 source ID·query·credential 규칙
  ├─ API 계열의 오류 의미와 response type
  └─ API 계열 transport wrapper
       ├─ WorldBankTransport → bounded HTTP GET
       ├─ JsonApiTransport   → bounded GET / BLS v1 POST → JSON parse/redaction
       └─ SdmxApiTransport   → bounded HTTP GET → raw SDMX bytes
                              └─ 공통 bounded HTTP primitive
```

`connectors/http_transport.py`는 네트워크 opt-in, reviewed HTTPS host/path, `trust_env=False`, TLS 기본 검증, `(5,20)`초 timeout, redirect 거부, Content-Length/streaming byte 상한, elapsed budget, 완료 시각·content type·Retry-After와 raw entity bytes를 맡는다. Source route 자체는 구성하지 않는다. Iteration 28의 `post_json()`은 16 KiB JSON body 상한을 추가하고 동일한 수신 안전 규칙을 공유한다. JSON family wrapper는 POST를 고정된 BLS v1 endpoint와 세 요청 field에만 허용하며, 기존 WB/SDMX/BEA/e-Stat GET 계약은 유지한다.

API 계열 wrapper는 현행 공개 class와 메서드, 기관별 URL/query/credential 처리, 상태 코드의 의미, 크기 제한, parser/redaction, 최종 오류 메시지와 response model을 보유한다. 공통층의 transport 오류를 기존 계열의 `ConnectorFailure` 상태·코드로 매핑한다. 사용자 입력 또는 credential이 포함될 수 있는 URL/예외 상세는 오류 메시지로 내보내지 않는다.

HTTP response의 redirect `Location`은 후속 요청 없이 wrapper의 source 오류 분류에만 일시 전달하며 dataclass repr에서 제외한다. query에 credential이 있을 수 있어 이 header를 archive/report에 serialize하지 않는다. Census의 공식 key-error host/path 판단은 JSON family wrapper가 맡는다. 실패 응답의 media type은 report에 `json`·`html`·`other` 고정 category로만 기록한다.

## 경계 및 보존 계약

- 이 작업은 **전송 중복 제거**이지 source adapter 통합이나 새 API 구현이 아니다.
- World Bank의 실패 HTTP 응답 body와 `Retry-After` 보존을 유지한다. JSON/SDMX wrapper는 현재대로 성공 상태 응답 body만 해석/반환하고, 비-200의 status 판정은 family wrapper에서 한다.
- 응답 제한은 World Bank/JSON 각 1 MiB, SDMX 8 MiB로 유지한다. timeout 및 byte-bound 실패 응답을 완전한 raw 성공으로 저장하지 않는다.
- BEA/e-Stat JSON credential parameter redaction, SDMX credential-like query 차단, source-specific allowlist, HTTP status 분류는 해당 wrapper에 남긴다.
- 통제 테스트는 mock HTTP만 사용한다. official payload fixture, auth, external endpoint reachability, live ingestion은 검증하지 않는다.

## 코드와 테스트

- 공통: `src/macro_data_platform/connectors/http_transport.py`, `tests/test_http_transport.py`
- 계열 wrappers: `connectors/worldbank.py`, `connectors/official_api.py`, `connectors/sdmx.py`
- 기존 source contract: `tests/test_worldbank.py`, `tests/test_official_api_credentials.py`, `tests/test_sdmx_connectors.py`
- HTTP transport pass는 route, schema parsing, 기관 API 성공, 저장 workflow, live 검증을 대신하지 않는다.

GET 구조 정리 결과는 [Iteration 26 report](../history/ITERATION_26_REPORT.md), 제한 POST와 추가 REST clients는 [Iteration 28 report](../history/ITERATION_28_REPORT.md)에 기록한다.
