# Iteration 30 — bounded live canary 상태

**현재 상태: NOT RUN — 명시적 network opt-in이 꺼져 있음.** `Settings.from_project_env()`를 통해 설정 상태만 읽었다. `MACROATLAS_NETWORK_ENABLED=false`; FRED와 Census 키는 configured, 값은 화면/파일에 출력하지 않았다. 실제 통계 API 또는 다운로드 경로 요청은 **0회**다. 이는 네트워크 장애나 권한 거부가 아니라 local opt-in gate다.

실제 preflight 기록: [network-off 결과 JSON](../../../reports/iteration_30_live_canary_d8a291e6301f4eb7a8be637f25a5d8b4.json) — 7개 전부 `not_run_network_disabled`, 요청 0회. `reports/`는 Git ignore 대상이라 본인 로컬에만 있다.

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

## 검사된 코드·절차

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.venv\Scripts\python.exe scripts/verify_dataset_paths.py --live
.venv\Scripts\python.exe -m pytest tests/test_live_canary.py -p no:cacheprovider -ra
```

위 live 명령은 지금 network-off 상태에서 실행해도 source request를 하지 않는다. 이후 설정을 바꾸면 같은 명령이 실제로 최대 7개 request를 만든다. `.env`의 network flag를 사람이 true로 바꾸고 확인한 뒤에만 실행한다. 이 준비 단계에서는 사용자의 명시적 opt-in을 임의로 변경하지 않았다.

현재 테스트는 network-off preflight에서 7개를 기록하고 실제 HTTP를 전혀 호출하지 않으며 credential 값을 보고서에 쓰지 않는 것을 검증한다. 이 offline test 통과는 live gate 완료가 아니다. 전체 결과는 모든 source가 성공하면 PASS, 그렇지 않으면 source별 실패 및 gate 미통과로 남겨야 한다. 상세 이용 조건은 [데이터셋 계약](../connectors/DATASET_CONTRACTS.md)에 있다.

준비 단계 검증: targeted `tests/test_live_canary.py tests/test_dataset_paths.py` **53 passed**; 최종 전체 offline suite **816 passed, 1 skipped, 0 failed (83.39초)**. Skip은 Windows symlink 생성 미지원이다. live 관련 변경 Python Ruff 통과, `git diff --check` exit 0. 위 통과는 network-off fail-closed와 synthetic regression만 의미한다.
