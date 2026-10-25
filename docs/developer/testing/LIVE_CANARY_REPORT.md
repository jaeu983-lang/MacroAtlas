# Iteration 30 — bounded live canary 상태

**현재 상태: PARTIAL — Gate U NOT PASSED.** 마지막 전체 canary는 4/7 통과였다. 이후 새 제한 진단에서 Census 302 목적지가 공식 `invalid_key.html`임을 확인했다. BLS는 기존 POST 두 경로와 공식 GET·예제 POST 비교까지 모두 503 HTML을 반환했다. Akamai·JavaScript 표식은 앞단 오류/접근 페이지 가능성의 근거이며 차단 정책은 확정되지 않았다. [원인·코드 수정·재개 조건](CENSUS_BLS_GATE_U_DIAGNOSIS.md)을 따른다. 기존 전체 run [JSON](../../../reports/iteration_30_live_canary_02afcdd6b6254239adf01af824df4e64.json)은 변경하지 않는다.

이번 추가 진단은 5회(Census 1, BLS 4), 자동 재시도 0회였다. 이전 전체 canary 14회와 합쳐 저장소가 기록한 source 요청은 19회이며, 추가 5회는 7개 전체 gate run이 아니다. 코드에는 Census 인증 오류 분류, 고정 media category, `--profile` 선택과 부분 실행의 `not_assessed_partial_scope` 판정을 추가했다. 새 분류 자체는 offline 회귀로 검증했으며 추가 live 요청은 하지 않았다.

## 후속 live run — 2026-10-25 (7회, 재시도 0회)

| 경로 | 최신 결과 | HTTP | raw/hash read-back | 판정 근거 |
|---|---|---:|---|---|
| FRED GDP | `live_contract_validated` | 200 | 969 bytes, 확인 | 7개 observation이 있는 명시 page만 검사; 전체 dataset이 아니며 정규화 observation은 게시하지 않음 |
| Census ACS2023 population | `live_request_failed` — `LICENSE_SECURITY` / `NEEDS_REVIEW` | 302 | 저장 안 함 | `redirect_refused`; 목적지 host/path와 응답 본문은 기록되지 않아 redirect 원인은 더 세분할 수 없음 |
| BLS unemployment | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE` | 503 | 저장 안 함 | `http_transient_status`; 서버/게이트웨이가 일시 오류를 반환했으나 구체 사유는 확인 불가 |
| BLS CPI | `live_request_failed` — `TRANSIENT` / `FAILED_RETRYABLE` | 503 | 저장 안 함 | `http_transient_status`; 서버/게이트웨이가 일시 오류를 반환했으나 구체 사유는 확인 불가 |
| TIC MFH history | `live_contract_validated` | 200 | 98,124 bytes, 확인 | 955개 자료 행과 26개 header block, source 계약만 검증 |
| TIC Table 3D 2023-01 | `live_contract_validated` | 200 | 5,982 bytes, 확인 | 127개 자료 행; 고정 2023-01 snapshot이며 최신 표가 아님 |
| BoE Bank Rate | `live_contract_validated` | 200 | 140 bytes, 확인 | 7개 native reporting date; 날짜 보간·월말 정렬 없음 |

이 후속 실행 자체의 통과는 **4/7**이며 Gate U는 7/7 조건을 만족하지 못해 **NOT PASSED**다. `live_contract_validated`는 해당 고정 source contract와 저장 무결성만 의미한다. 완전한 데이터셋, 정규화된 observation 수용, 다기관 전체 지원을 뜻하지 않는다. 이전 실행 결과와 receipt는 이 후속 실행으로 소급 변경하지 않는다.

### 두 번째 전체 run 당시의 후속 조치 (이력)

- **Census:** 현재 redirect 거부 정책을 유지하고 자동으로 따라가지 않는다. 기존 실행에는 `Location`이 보존되지 않아 목적지를 추정하지 않는다. 새 요청 예산을 정한 뒤에만 한 번의 안전한 진단으로 redirect의 scheme/host/path를 query 값 없이 기록하고, 그 host가 공식 허용 경로인지 확인한다. 그 전에는 endpoint·키·네트워크 우회 변경을 하지 않는다.
- **BLS:** 503은 실제 HTTP 응답이지만 장애 원인이 점검/과부하/중간 게이트웨이 중 무엇인지는 확인되지 않았다. 이미 두 v1 요청을 보냈으므로 이번 예산에서 재시도하지 않는다. 별도 예산을 정한 뒤 공식 v1 endpoint 상태와 새 단발 응답을 재확인한다. v2 전환이나 임의 재시도는 하지 않는다.
- **Gate:** Census와 BLS 두 profile의 source contract 및 저장/read-back 검증이 각각 완료되어야 다시 Gate U를 판정한다. 현재 결과로 Iteration 31이나 soak 단계로 넘어가지 않는다.

실제 결과: [live run JSON](../../../reports/iteration_30_live_canary_ffc0fe15c3b440a28c65b64aa9b5bb81.json). 이전 [network-off preflight JSON](../../../reports/iteration_30_live_canary_d8a291e6301f4eb7a8be637f25a5d8b4.json)은 7개 전부 `not_run_network_disabled`, 요청 0회였다. 결과 파일과 raw는 Git ignore 대상이라 로컬에만 있다.

## 계획된 단발 요청 범위

| Profile | 요청 예산 |
|---|---|
| FRED GDP | 2024-01-01–2025-12-31, 최대 8 observations, FRED key |
| Census ACS2023 population | California (`state:06`) 한 geographic row, Census key |
| BLS unemployment | 무키 v1 POST 1회, 2024 |
| BLS CPI | 무키 v1 POST 1회, 2024 |
| TIC MFH history | 등록 CSV GET 1회, 전체 공식 파일, 8 MiB cap |
| TIC Table 3D 2023-01 | 등록 CSV GET 1회, 8 MiB cap |
| BoE Bank Rate | IUDBEDR CSV GET 1회, 10일 |

총 최대 7 요청, 재시도 0회, BLS v1 POST 2회다. `--live` 실행기는 network opt-in이 false일 때 위 7개 모두 `not_run_network_disabled`로 보고하고 요청을 하지 않는다. true일 때만 요청하며 누락된 FRED/Census key는 해당 경로를 생략한다. 각 source 결과는 별개로 기록하고, 응답 contract 검증 뒤 raw·manifest·profile receipt를 저장해 hash read-back한다. 원본이 바뀌거나 client 검증에 실패하면 해당 source는 실패/검토로 남는다.

## 첫 live run — 원 실행 결과와 원 receipt

| 경로 | 결과 | HTTP | 원본 저장/read-back | 비고 |
|---|---|---:|---|---|
| FRED GDP | `live_contract_validated` | 200 | 확인 | 7 observations, 명시 page만 검증 |
| Census ACS2023 population | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `LICENSE_SECURITY` / `NEEDS_REVIEW`; 상세 원인은 보고서에서 생략됨 |
| BLS unemployment | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `TRANSIENT` / `FAILED_RETRYABLE`; 재시도하지 않음 |
| BLS CPI | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `TRANSIENT` / `FAILED_RETRYABLE`; 재시도하지 않음 |
| TIC MFH history | `live_needs_review` | 200 | 확인 | `dataset_contract_changed`; 원본은 보존했으나 validator 미통과 |
| TIC Table 3D 2023-01 | `live_needs_review` | 200 | 확인 | `dataset_contract_changed`; 원본은 보존했으나 validator 미통과 |
| BoE Bank Rate | `live_contract_validated` | 200 | 확인 | 7 native reporting dates |

Gate U는 7개 모두 canary 실행 중 `live_contract_validated`여야 통과한다. 첫 실행 판정 2/7(FRED·BoE)은 그 run의 원 receipt 기준으로 유지한다. 그 당시 저장된 TIC 응답 2개를 오프라인에서 재검증했을 때, 첫 실행과 사후 검증을 합친 source-response 근거는 4/7이었다. 이는 첫 run 결과이며, 이후 후속 live run은 별도 표에 기록한다. 첫 실행의 Census/BLS 상세 원인은 그 report에서 복구할 수 없지만, 후속 run은 각각 302와 503을 새 receipt에 기록했다. Gate U는 **NOT PASSED**이며 다음 iteration은 시작하지 않는다.

## 저장된 원본의 후속 오프라인 재검증

원래 canary 이후, 기존 TIC 원본 bytes에 현재 validator만 오프라인으로 다시 적용했다. HTTP를 호출하지 않았고 기존 원본·manifest·write-once receipt도 수정하지 않았다.

- **TIC Table 3D:** SHA-256은 canary 결과와 일치한다. 원본의 161행에 단독 `"Notes:"` 각주 경계가 있고, 그 앞 160개 표 행은 strict CSV 및 고정 2023-01 구조를 통과했다(자료 행 127개). 이후의 잘못된 형식 각주는 raw에 그대로 남는다. 이것은 원래 실행 시점의 `live_needs_review` receipt를 소급 수정하지 않는다.
- **TIC MFH:** SHA-256은 canary 결과와 일치한다. 현재 validator는 26개 header block과 955개 자료 행을 확인했다. 연월 중복 11쌍은 Series 식별자가 다르게 명시된 공식 series break로 판정되어 `contract_validated`다: 2000-03 II/I와 2002-06부터 2011-06까지의 각 June break. Treasury는 이전 series 경계 월 값을 비교용이라고 각주에 명시한다. 두 값을 병합·삭제하지 않았고 저장 원본도 바꾸지 않았다. [공식 MFH 표와 각주](https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfhhis01.html).
- **첫 실행의 Census 및 BLS:** 그 run에서는 실패 raw/HTTP status가 보존되지 않아 상세 원인을 소급 판별할 수 없다. 후속 canary는 별도 새 receipt로 Census 302와 BLS 503을 기록했으며, 이 결과가 첫 실행의 receipt를 바꾸지는 않는다.

첫 실행의 Gate U 판정 **2/7, NOT PASSED**는 이력으로 유지한다. 후속 canary 실행의 live source-contract pass는 4/7이며 Gate U는 현재도 미통과다. 후속 TIC 성공은 최신 실행에서 live로 확인되었으며, 앞선 실행의 `live_needs_review` receipt는 그대로 둔다. 이후 canary 실행기는 키·응답·예외 문구를 남기지 않고 고정 `failure_reason`과 가능한 경우 `failure_http_status`를 기록한다.

원래 canary JSON과 TIC 원본은 `reports/` 및 `data/raw/`의 local-only 파일로 읽혔고 hash가 일치했다. 기본 샌드박스에서는 `reports/` 새 파일 쓰기가 `PermissionError`로 거부됐다. 2026-10-25 현재 `.env` 네트워크 허용이 false임을 확인한 뒤, network-off `--live` preflight를 승인된 elevated shell로 재실행해 [최신 preflight JSON](../../../reports/iteration_30_live_canary_c1fa08b936df44869eebefc81e34ca42.json)을 저장했다. 보고서는 `not_run_network_disabled` 7건, 요청 0회, retry 0회다. 따라서 저장 경로는 승인된 실행 컨텍스트에서 확인됐지만, 새 live canary나 Gate U 증거는 아니다. 기존 canary raw·receipt는 바꾸지 않았다.

## 검사된 코드·절차

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:MACROATLAS_NETWORK_ENABLED = "true"
.venv\Scripts\python.exe -X utf8 scripts/verify_dataset_paths.py --live
.venv\Scripts\python.exe -m pytest tests/test_live_canary.py -p no:cacheprovider -ra
```

위 live 명령은 network opt-in이 true일 때 실제 요청을 보낸다. 이번 실행은 사용자 요청에 따라 프로세스에서만 임시로 opt-in했고 `.env`의 기존 `false` 값은 유지했다.

network-off 테스트와 synthetic regression 통과는 live gate 완료를 뜻하지 않는다. 이번 live run은 각 source의 실제 응답 범위만 증명하며, 실패나 `needs_review`를 성공으로 승격하지 않는다. 상세 이용 조건은 [데이터셋 계약](../connectors/DATASET_CONTRACTS.md)에 있다.

준비 단계 검증(원래 실행 전): targeted `tests/test_live_canary.py tests/test_dataset_paths.py` **53 passed**; 전체 offline suite **816 passed, 1 skipped, 0 failed (83.39초)**. 저장 TIC 응답 검토와 MFH Series-break validator를 포함한 최신 후속 검증은 targeted `tests/test_dataset_paths.py tests/test_official_api_credentials.py tests/test_live_canary.py` **85 passed, 1 skipped**, 전체 offline suite **822 passed, 1 skipped, 0 failed (82.45초)**, 변경 Python Ruff passed다. Skip은 Windows symlink 생성 미지원이다. 이 테스트는 네트워크 요청을 보내지 않았으며 live gate 증거와 별개다.
