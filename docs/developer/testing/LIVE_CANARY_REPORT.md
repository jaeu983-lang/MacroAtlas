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

Gate U는 7개 모두 `live_contract_validated`여야 통과한다. 원래 실행 보고서는 2/7을 기록했다. 후속 오프라인 재검증에서 저장된 Table 3D 응답이 현재 validator를 통과해, 기존 live 증거까지 합친 최신 source-response contract 근거는 3/7(FRED·BoE·Table 3D)이다. Gate U는 **NOT PASSED**이며 다음 iteration은 시작하지 않는다. MFH는 여전히 검토 대상이고 Census/BLS 원인은 당시 상세 reason이 저장되지 않아 소급 복원할 수 없다. 재요청은 하지 않았다.

## 저장된 원본의 후속 오프라인 재검증

원래 canary 이후, 기존 TIC 원본 bytes에 현재 validator만 오프라인으로 다시 적용했다. HTTP를 호출하지 않았고 기존 원본·manifest·write-once receipt도 수정하지 않았다.

- **TIC Table 3D:** SHA-256은 canary 결과와 일치한다. 원본의 161행에 단독 `"Notes:"` 각주 경계가 있고, 그 앞 160개 표 행은 strict CSV 및 고정 2023-01 구조를 통과했다(자료 행 127개). 이후의 잘못된 형식 각주는 raw에 그대로 남는다. 이것은 원래 실행 시점의 `live_needs_review` receipt를 소급 수정하지 않는다.
- **TIC MFH:** SHA-256은 canary 결과와 일치한다. 일부 연도 블록에 13개 기간 열과 중복 `(연도, Jun)`이 관측돼 계속 `needs_review`다. 값이나 기간을 합치거나 버리지 않았다.
- **Census 및 BLS:** 실패 raw/HTTP status가 저장되지 않았고 이전 보고서에도 고정 reason 세부정보가 없어 원인을 소급 판별할 수 없다. 재요청하지 않았다.

Gate U 원판정은 **2/7, NOT PASSED**로 유지한다. 이후 canary 실행기는 키·응답·예외 문구를 남기지 않고 고정 `failure_reason`과 가능한 경우 `failure_http_status`를 기록한다. 이 개선은 새 요청 결과가 있어야만 진단에 도움이 되며 현재 실패를 변경하지 않는다.

원래 canary JSON과 TIC 원본은 `reports/` 및 `data/raw/`의 local-only 파일로 읽혔고 hash가 일치했다. 이 Codex shell에서는 `reports/`에 새 후속 JSON을 만드는 작업이 `PermissionError`로 거부되어 새 기계 판독 JSON은 만들지 않았다. 기존 파일은 수정하지 않았고 후속 판정은 이 문서에 남겼다. 사용자가 앞서 regular PowerShell에서 canary 보고서를 저장한 결과와는 별개의 현재 shell write 제한이다.

## 검사된 코드·절차

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:MACROATLAS_NETWORK_ENABLED = "true"
.venv\Scripts\python.exe -X utf8 scripts/verify_dataset_paths.py --live
.venv\Scripts\python.exe -m pytest tests/test_live_canary.py -p no:cacheprovider -ra
```

위 live 명령은 network opt-in이 true일 때 실제 요청을 보낸다. 이번 실행은 사용자 요청에 따라 프로세스에서만 임시로 opt-in했고 `.env`의 기존 `false` 값은 유지했다.

network-off 테스트와 synthetic regression 통과는 live gate 완료를 뜻하지 않는다. 이번 live run은 각 source의 실제 응답 범위만 증명하며, 실패나 `needs_review`를 성공으로 승격하지 않는다. 상세 이용 조건은 [데이터셋 계약](../connectors/DATASET_CONTRACTS.md)에 있다.

준비 단계 검증(원래 실행 전): targeted `tests/test_live_canary.py tests/test_dataset_paths.py` **53 passed**; 전체 offline suite **816 passed, 1 skipped, 0 failed (83.39초)**. 이번 후속 변경은 targeted **84 passed, 1 skipped**, 전체 offline suite **821 passed, 1 skipped, 0 failed (74.11초)**, 변경 Python Ruff passed, `git diff --check` passed다. Skip은 Windows symlink 생성 미지원이다. 네트워크 시험 결과와 offline 테스트 결과는 별도 증거다.
