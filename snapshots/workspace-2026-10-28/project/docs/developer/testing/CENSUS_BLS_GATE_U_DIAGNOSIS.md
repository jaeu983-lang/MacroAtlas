# Gate U — Census 키 오류와 BLS 503 진단

**현재 지시(D-101):** Census·BLS는 보류 상태다. 아래 재개 절차는 이력/참고이며 사용자의 명시적인 재개 전에는 키 입력 요청이나 외부 호출을 진행하지 않는다. 다른 기관 API는 독립 source gate로 진행한다.

**일자:** 2026-10-25

**회차:** Iteration 30 후속 수정. Gate U는 **NOT PASSED**이며 Iteration 31은 시작하지 않는다.

## 현재 결론

- Census의 ACS 2023 고정 요청은 HTTP 302로 공식 `/data/invalid_key.html`을 가리켰다. 현재 설정한 키를 Census가 거부한다는 실제 응답 근거다. `Location`을 따라가지 않았고 키와 원 URL query를 출력·저장하지 않았다.
- BLS unemployment·CPI의 기존 v1 POST는 각각 HTTP 503, `text/html`을 반환했다. 공식 single-series GET과 공식 Python 예제 방식의 기간 지정 POST도 각각 503이었다. 두 비교 응답의 제한된 표본에는 `akamai`, `javascript`, `error` 문자열이 있었다. 이는 서비스 앞단의 접근/오류 페이지일 가능성과 일치하지만, 차단 정책·IP 상태·점검 여부는 확인되지 않았다.
- 새 성공 artifact는 없다. 이전 7개 전체 canary의 4/7 성공 근거는 유지하지만 이번 부분 진단을 전체 gate 통과로 합산하지 않는다.

## 요청 예산과 실제 실행

| 진단 | 실제 요청 | 결과 | 증거 범위 |
|---|---:|---|---|
| 기존 collector의 Census 고정 ACS query | GET 1회 | 302, `invalid_api_key` 목적지 | 공식 host/path만 비교해 고정 오류 종류를 남김 |
| 기존 collector의 BLS unemployment 2024 | POST 1회 | 503 HTML | 실패 응답 종류만 진단; 자료 저장 없음 |
| 기존 collector의 BLS CPI 2024 | POST 1회 | 503 HTML | 실패 응답 종류만 진단; 자료 저장 없음 |
| BLS 공식 single-series 방식 | GET 1회 | 503 HTML | `/publicAPI/v1/timeseries/data/LNS14000000`; GET의 기본 기간은 고정 2024 계약과 다르며 대체 수집으로 취급하지 않음 |
| BLS 공식 Python 방식 | POST 1회 | 503 HTML | 2024, `LNS14000000`·`CUUR0000SA0`를 함께 요청; 기본 requests header와 JSON Content-Type으로 비교 |

**이 작업의 합계는 5회(Census 1, BLS 4), 자동 재시도 0회다.** 마지막 BLS POST는 요청 방식 비교를 위한 의도된 별도 진단이다. v2, BLS key, pagination, proxy 변경, JavaScript challenge 처리나 자동 파일 fallback은 사용하지 않았다. 이후 추가 API 요청은 하지 않았다.

로컬 원시 진단 기록:

- [3개 기존 경로 진단](../../../reports/iteration_30_failure_diagnostic_a6d09a0acb16403ab92e1479119a706d.json)
- [BLS GET/POST 비교](../../../reports/iteration_30_bls_method_diagnostic_d438672dd46241748189470943325c50.json)

비교 기록에는 status, 고정 media category, 표본 bytes/hash와 사전에 정한 문자열 표식만 보존했다. 오류 HTML 원문·redirect query·credential·서버가 반환할 수 있는 IP나 지원 식별자는 저장하지 않았다. 이 진단은 source payload fixture나 정상 수집 결과가 아니다.

## 수정한 동작

1. 공통 HTTP 응답은 `Location`을 일시적으로 wrapper에 전달하되 `repr`에 표시하지 않는다. 원 header를 archive·실패 report로 보내지 않는다.
2. JSON wrapper는 Census data 요청에 한해 공식 HTTPS `api.census.gov`의 정확한 `/data/invalid_key.html`·`/data/missing_key.html`을 인증 오류(`AUTH_ACCESS`, `invalid_api_key`·`missing_api_key`)로 분류한다. 다른 host, port, userinfo, fragment, 알 수 없는 경로는 기존처럼 redirect 거부다. 자동 follow 요청은 없다.
3. HTTP 오류 응답의 종류는 `json`·`html`·`other` 고정값으로만 report에 기록한다. BLS HTML 503은 `http_transient_status`로 유지하고 HTML 표식만으로 보안 차단을 확정하지 않는다. 오류 body를 자료 artifact로 저장하지 않는다.
4. canary 실행기에 반복 가능한 `--profile` 옵션을 추가했다. 등록된 고정 profile만 고를 수 있고 알 수 없는 ID·중복·빈 목록은 요청 전에 거부한다. 전체 7개 기본 실행 계약은 유지한다.
5. 부분 실행은 모두 성공해도 `gate_u_assessment=not_assessed_partial_scope`다. 전체 7개가 같은 canary에서 모두 통과한 경우에만 `passed`를 기록한다. profile별 최대 요청 수와 BLS budget도 선택 범위로 계산한다.

키 값, endpoint 설정, 통계 값, 단위, 기간 및 raw 보존 계약은 변경하지 않았다. 이번 코드 변경의 검증은 합성 HTTP 응답으로 수행했다. 새 오류 분류 코드 자체의 추가 live 검증은 아직 하지 않았다.

## Census 재개 조건

사용자는 활성화 링크를 완료했다고 답했다. 로컬 확인에서는 프로세스 key override가 없고, 실제 설정값과 프로젝트 파일의 설정값이 일치했다. 바깥 따옴표·명백한 placeholder·다른 기관 key와의 동일 값은 발견되지 않았다. 이 확인은 키 유효성을 보증하지 않는다.

운영자는 발급 메일의 키를 로컬 `.env`의 `CENSUS_API_KEY`에 다시 입력하고, 필요하면 공식 발급/활성화 절차로 재발급한다. 실제 값을 대화·소스·보고서에 보내지 않는다. 키를 수정한 뒤 아래 명령은 Census 한 profile만 한 번 요청한다.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.venv\Scripts\python.exe -X utf8 scripts/verify_dataset_paths.py --live --profile census.acs2023.population
```

이 명령에는 네트워크 opt-in과 새 1회 요청 예산이 필요하다. 현재 프로젝트의 network opt-in은 앞선 사용자 지시로 켜졌으며 이 API 진단 작업에서는 `.env`나 credential을 변경하지 않았다.

## BLS 재개 조건과 문의 자료

현재 로컬 자료만으로 503을 해결하는 endpoint/header 변경 근거는 없다. 기관이 정상 JSON 응답을 제공할 수 있는지 확인한 뒤, 새 제한 예산에서 필요한 profile만 단발 재확인한다. HTML 보안/오류 페이지를 통과하려고 브라우저를 위장하거나 요청 경로를 우회하지 않는다.

운영자가 공식 API 문의 창구로 전달할 수 있는 내용은 다음과 같다. 이번 작업에서 문의를 발송하지는 않았다.

> BLS Public Data API v1에서 GET `/publicAPI/v1/timeseries/data/LNS14000000` 및 POST `/publicAPI/v1/timeseries/data/`가 HTTP 503과 text/html을 반환했습니다. POST는 JSON Content-Type, seriesid LNS14000000/CUUR0000SA0, startyear/endyear 2024를 사용했습니다. 무등록 v1이며 key·v2·자동 재시도는 사용하지 않았습니다. API JSON 응답을 받을 수 있는 공식 접근 조건과 현재 장애 여부를 확인 부탁드립니다. 요청 시각은 첨부할 로컬 진단 JSON의 UTC 시각을 사용합니다.

권한·장애 문제가 확인되기 전까지 BLS live 성공으로 기록하지 않는다. Census와 BLS가 준비된 뒤 전체 7개 gate canary는 별도 예산으로 실행한다.

## 검증과 환경 한계

- 관련 테스트: **146 passed, 1 skipped**. Skip은 이 Windows 환경의 symlink 생성 미지원이다. 변경 Python Ruff 통과.
- 기본 pytest 임시 경로에서 `WinError 5`가 발생했다. `-x` 재현은 fixture setup 1 error였다. 권한 문제가 있던 기존 사용자 Temp를 수정하지 않고, 저장소 `reports/pytest_<고유 ID>`를 `--basetemp`로 지정해 관련 테스트를 통과시켰다.
- 전체 offline suite: **846 passed, 1 skipped, 0 failed (72.70초)**. 같은 symlink 제한 1건이 제외됐다. 변경 Python Ruff와 `git diff --check`를 최종 확인한다.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$taskTestRoot = Join-Path (Get-Location) ('reports\pytest_' + [guid]::NewGuid().ToString('N'))
.venv\Scripts\python.exe -m pytest --basetemp $taskTestRoot -p no:cacheprovider -ra
```

고유 경로를 사용해 기존 시험 자료를 덮어쓰지 않는다. API 자격증명 변경은 사용자가 처리해야 하며, BLS 외부 접근 문제는 기관/네트워크 확인이 남아 있다. 코드 변경은 branch에서 검토하고 main 통합 전에 사람의 diff 검토가 필요하다.

## 공식 근거

- [Census Invalid Key](https://api.census.gov/data/invalid_key.html), [키 발급·활성화 안내](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html)
- [BLS v1 signatures](https://www.bls.gov/developers/api_signature.htm), [공식 v1 Python 예제](https://www.bls.gov/developers/api_python.htm), [API FAQ](https://www.bls.gov/developers/api_faqs.htm)
- [BLS API 이용 조건](https://www.bls.gov/developers/termsOfService.htm), [자동 수집 이용 안내](https://www.bls.gov/bls/blsterms.htm)
