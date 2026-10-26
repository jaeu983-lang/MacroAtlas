# Gate C 증거 재검토 — 2026-10-26

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
