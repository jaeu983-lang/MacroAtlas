# Iteration 30 — bounded live canary 상태

**현재 상태: PARTIAL — Gate U NOT PASSED.** 2026-10-25에 사용자가 요청한 live canary를 실행했다. 프로세스에서만 `MACROATLAS_NETWORK_ENABLED=true`를 설정했고 `.env`는 수정하지 않았다. 7개 경로를 각각 한 번 시도했으며 재시도는 0회다.

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

## 실제 실행 결과

| 경로 | 결과 | HTTP | 원본 저장/read-back | 비고 |
|---|---|---:|---|---|
| FRED GDP | `live_contract_validated` | 200 | 확인 | 7 observations, 명시 page만 검증 |
| Census ACS2023 population | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `LICENSE_SECURITY` / `NEEDS_REVIEW`; 상세 원인은 보고서에서 생략됨 |
| BLS unemployment | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `TRANSIENT` / `FAILED_RETRYABLE`; 재시도하지 않음 |
| BLS CPI | `live_request_failed` | 결과에 없음 | 보고서에 없음 | `TRANSIENT` / `FAILED_RETRYABLE`; 재시도하지 않음 |
| TIC MFH history | `live_needs_review` | 200 | 확인 | `dataset_contract_changed`; 원본은 보존했으나 validator 미통과 |
| TIC Table 3D 2023-01 | `live_needs_review` | 200 | 확인 | `dataset_contract_changed`; 원본은 보존했으나 validator 미통과 |
| BoE Bank Rate | `live_contract_validated` | 200 | 확인 | 7 native reporting dates |

Gate U는 7개 모두 `live_contract_validated`여야 통과한다. 현재 완전 검증은 2/7이므로 **다음 iteration을 시작하지 않는다**. Census 보안 분류와 TIC 원본 구조를 검토해야 한다. BLS 두 건은 일회성 예산을 이미 사용했고 자동 재시도 범위도 아니므로 다시 요청하지 않았다. 보고서는 실패 응답 본문이나 예외 문자열을 저장하지 않아 Census/BLS 세부 원인을 특정하지 않는다.

## 검사된 코드·절차

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:MACROATLAS_NETWORK_ENABLED = "true"
.venv\Scripts\python.exe -X utf8 scripts/verify_dataset_paths.py --live
.venv\Scripts\python.exe -m pytest tests/test_live_canary.py -p no:cacheprovider -ra
```

위 live 명령은 network opt-in이 true일 때 실제 요청을 보낸다. 이번 실행은 사용자 요청에 따라 프로세스에서만 임시로 opt-in했고 `.env`의 기존 `false` 값은 유지했다.

network-off 테스트와 synthetic regression 통과는 live gate 완료를 뜻하지 않는다. 이번 live run은 각 source의 실제 응답 범위만 증명하며, 실패나 `needs_review`를 성공으로 승격하지 않는다. 상세 이용 조건은 [데이터셋 계약](../connectors/DATASET_CONTRACTS.md)에 있다.

준비 단계 검증(이전 실행): targeted `tests/test_live_canary.py tests/test_dataset_paths.py` **53 passed**; 전체 offline suite **816 passed, 1 skipped, 0 failed (83.39초)**. Skip은 Windows symlink 생성 미지원이다. 이번 live 실행에서는 테스트를 돌리지 않았다. 준비 테스트 결과는 이번 source 응답 판정과 별도다.
