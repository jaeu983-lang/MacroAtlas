# Gate C 증거 재검토 — 2026-10-26

최신 정정: **revision 10에서 실행 네트워크 권한을 지정하자 BIS 실측과 Git push가 성공했다.**
아래 ProxyError 기록은 당시 기본 실행 권한의 결과이며 프록시 서버 장애로 확정할 수 없다.
최신 원인·복구 증거는 문서 마지막 절을 따른다. Gate C 자체는 아직 미통과다.

판정: **미통과**. 11회차는 시작하지 않았다. 오류 분기 fixture 통과와 실제 기관의
변경·복구 검증을 구분하며, 남은 live 검증을 fixture로 대체하지 않는다.

## 실행 기준

- 코드 HEAD: `aabdc59bb53788f73ff1610be4bef5457ab0440f`.
- 작업 브랜치: `codex/gate-c-evidence-review`. 최초 검토 시 commit/push는 수행하지 않았다.
  이후 사용자 지시로 검토 문서와 commit/push 기본 규칙을 커밋·푸시하는 후속 작업을 진행한다.
  publish는 수행하지 않는다.
- 활성 인스턴스: `ccarenv_b64_Y2NhcmVudl9mNTI0Zjc5ZTc5YjA4MTkxODQ5YzJiZTM0NTUxZTkwMw`.
- 환경 조회: running/connected, spec/observed revision `6`, observations current.
  네트워크 정책 enforced, 설정된 다섯 secret 및 network runtime variable ready.
  이 관측은 실제 외부 연결 성공을 보장하지 않는다. 게시 설정의 repository ref는 여전히 조회되지 않았다.
- 이전 문서의 기준 HEAD `781827…`, revision 5, local-only 변경 기록은 당시 이력이다.
  이번 checkout은 위 최신 HEAD이고 작업 시작 시 clean이었다.

## 검증 결과와 증거 종류

`python -m pytest -q`: exit 0, 전체 **556개 통과**. 별도 collect-only로 556개를 확인했다.
`python -m ruff check .`: 통과. `git diff --check`: 통과.

| 조건 | 이번 검증 | 증거와 제한 |
|---|---|---|
| X01 429/503 | fixture PASS | `test_http_status_classification_is_safe_and_retains_status`, `test_retry_after_seconds_are_retained_without_an_automatic_request`; 실제 429를 유발하지 않음 |
| X02 403 | fixture PASS | `test_403_requires_review_and_never_becomes_retryable`; 인증 우회·자동 재시도 없음 |
| X03 schema drift | fixture PASS | `test_schema_drift_retains_new_raw_response_for_diagnosis`; 새 raw 보존 |
| X04 의미 불일치 | PARTIAL | 후보의 기관/국가 불일치 차단과 unknown 단위·빈도·vintage 경고 통과. 잔액/거래액의 일반 의미 판별 완료를 뜻하지 않음 |
| X07 durable resume | fixture PASS | `test_429_failure_remains_retryable_across_process_restart`, `test_resume_reuses_valid_prefix_and_only_retries_failed_stage_after_restart`; 실제 기관 장애 후 복구는 NOT_RUN |
| X08 source revision | fixture PASS / live NOT_RUN | `test_live_source_change_is_preserved_and_requires_review_before_normalization`는 이름과 달리 합성 bytes를 사용하는 fixture. 양쪽 raw 보존·정규화 중단은 검증했으나 실제 개정 관측 없음 |
| B BIS ZIP | live BLOCKED | 아래 제한 재수집이 ProxyError로 중단됨 |
| C TIC 파일 | 이전 보고서만 존재 | 이번 checkout에는 이전 raw가 없어 기존 hash를 재검증할 수 없음. 새 TIC 요청은 보내지 않음 |
| F BOJ | BLOCKED 유지 | 이전 manual 403 기록. 이번 작업에서 문서·API를 재요청하지 않음 |

각 테스트의 경로는 `tests/test_statistical_quality.py`, `tests/test_orchestration.py`,
`tests/test_tabular_files.py`, `tests/test_series_search.py`다. 기존 live 성공 보고서는
`ITERATION_10_REPORT.md`의 이력으로 보존하되 이번 실행의 성공으로 재사용하지 않는다.

## 제한 live 재수집

2026-10-26 08:52:53 UTC (17:52:53 KST)에 기존 공식 URL
`https://data.bis.org/static/bulk/WS_GLI_csv_col.zip`을 요청했다.
계획 상한은 GET 두 번, 요청별 timeout 30초, 응답 16 MiB이며 redirect·자동 재시도는 금지했다.
첫 요청에서 `ProxyError`가 발생해 HTTP status, 원본 bytes, hash를 확보하지 못했다.
두 번째 요청은 실행하지 않았다. 이는 BIS 서버의 HTTP 오류나 기관의 접근 거부로 판정할 수 없다.
상세 예외 문자열과 자격증명은 출력·저장하지 않았다.

로컬 실행 기록: `reports/gate_c_review_20261026T085253Z.json` (gitignore 대상).
이 문서에도 판정에 필요한 관측을 남겨 로컬 보고서 부재 시 성공으로 오인하지 않도록 한다.
새 raw/normalized 데이터는 생성되지 않았다.

## 남은 종료 조건

1. 지원되는 실행 경로에서 프록시 연결 문제를 해결한 뒤 공식 TIC/BIS 원본·manifest·정규화 hash 재검증.
2. 같은 URL/요청 범위의 실제 개정 원본 쌍 확보 및 X08 변경 감지·양쪽 raw 보존 확인.
   같은 bytes를 재수집한 결과나 합성 수정 bytes를 live revision으로 표시하지 않는다.
3. 기관별 실패 후 durable resume 증거와 X04 잔액/거래액 후보 불일치 증거 보완.
4. BOJ BLOCKED와 지원 범위를 명시한 최종 Gate C 검토. 종료 조건 충족 전 11회차 보류.

관측치·기관 정의·자격증명·게시 설정을 변경하지 않았다. 이번 작업에 코드 동작 변경은 없다.

## 후속 보완 — revision 9 (2026-10-26)

- 기준 HEAD `5e93c89`, 작업 시작 시 clean. 환경 상태를 재조회하니 revision 9,
  running/connected, 정책 enforced, observations current, 키·runtime variable ready였다.
- 08:59:53 UTC (17:59:53 KST)에 위 BIS URL을 GET 1회/timeout 20초/redirect 금지로
  재확인했다. `ProxyError`로 HTTP 응답 전 차단됐다. 서버 403/503, 실제 개정 또는 복구
  성공으로 해석할 수 없다. 로컬 기록은 `reports/gate_c_followup_network.json`이다.
- `git push -u origin codex/gate-c-evidence-review`도 프록시 port 8080 연결 실패로 차단됐다.
  로컬 커밋 `5e93c89`는 보존돼 있다. proxy 우회나 자격증명 변경은 하지 않았다.
- X04 fixture를 구체화했다. `tests/test_series_search.py`의
  `test_holdings_request_cannot_confirm_transaction_or_unknown_measure` 두 경우는 동일한
  holdings label을 가진 후보라도 명시 차원이 transactions이면 순위에서 제외하고,
  차원이 unknown이면 review_required로 표시하며, 두 경우 모두 선택 확정을 거부함을 확인한다.
  올바른 holdings 차원 후보는 확정 가능하다. 이는 명시된 fixture 차원의 검증이며,
  공식 TIC metadata 발견·자연어 통계 의미 추론이나 live 검증을 주장하지 않는다.
- `python -m pytest -o addopts='' -q`: **558 passed in 4.20s**.
  `python -m ruff check .`와 `git diff --check` 통과.
- 남은 종료 조건 중 X04의 제한 구조화 fixture 증거만 보완됐다. 실제 개정 원본 쌍과
  기관별 장애 복구 증거는 여전히 없다. **Gate C 미통과, 11회차 미시작**이다.
  11회차를 시작하라는 지시는 Gate C 보완·통과 후 진행 순서로 적용하며, 통과를 가정하지 않는다.
  다음 선행 작업은 지원되는 환경 설정/복구 경로를 통한 실행 프록시 연결 복구다.

## 원인 확인·접속 복구 — revision 10

- 환경은 running/connected, revision 10, unrestricted/enforced였다. HTTP(S) proxy는
  정책과 런타임 변수 모두 `http://proxy:8080`으로 일치했고 Git 전용 proxy override는 없었다.
- 기본 sandbox에서 `proxy`는 `172.31.0.237`로 해석됐지만 8080/8088 TCP 연결은
  `PermissionError`, errno 1이었다. DNS 실패나 BIS의 HTTP 거부가 아니다.
- 실행 도구의 지원 옵션 `sandbox_permissions=with_additional_permissions`,
  `additional_permissions.network.enabled=true`를 지정한 요청은 동일 proxy에 연결됐고
  BIS GET도 HTTP 200이었다. proxy/TLS/키/환경 URL 변경이나 우회는 하지 않았다.
  따라서 관측된 실패 원인은 기본 명령 실행의 네트워크 권한 제한이었다. 과거 개별 실행의
  다른 장애 가능성까지 소급 부정하지 않지만, 프록시 서비스가 고장났다는 기존 설명은 정정한다.
- 최초 권한 요청에 포함한 push는 자동 검토에서 외부 대상/전송 범위 미확인을 이유로 거절됐다.
  기존 origin이 `https://github.com/jaeu983-lang/MacroAtlas.git`이고 기존 작업 브랜치도 origin을
  추적하며, 전송 차이가 문서/테스트 5개뿐임을 확인한 후 동일 명령 재검토가 승인돼 push 성공했다.
  `35efa62`까지 `origin/codex/gate-c-evidence-review`에 반영됐다.
- 2026-10-26 09:02:43 UTC (18:02:43 KST) BIS 재수집·intake 성공:
  HTTP 200, 104,833 bytes, SHA256
  `aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d`.
  package `86a1923e3a2240dcbe8b1248b128443d`, 225행/220열, raw/normalized hash 모두 일치.
  로컬 보고서는 `reports/gate_c_network_recovery.json`; raw/normalized는 gitignore 대상이다.
- `source_change_status=first_observation`. 과거 보고서의 BIS hash와 같으며, 실제 개정된
  원본 쌍을 확보한 것은 아니다. Git push 성공도 데이터 품질 게이트 조건이 아니다.
  실제 개정 비교와 기관별 durable resume는 여전히 NOT_RUN이므로 Gate C 미통과·11회차 보류다.
- 다음 네트워크 작업은 위 실행 권한을 명시하고 제한된 요청 예산을 유지한다.
  접속 복구를 위해 환경 설정을 다시 게시하거나 키·도메인을 바꿀 필요는 확인되지 않았다.
