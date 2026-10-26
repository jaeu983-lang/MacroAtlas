# Gate C 증거 재검토 — 2026-10-26

11회차는 이후 사용자의 명시적 진행 지시에 따른 예외로 구현·검증했다. 해당 진행은 Gate C
통과 선언이 아니며, 이번 task에서 Gate C의 미완료 조건은 그대로 기록한다. 11회차 결과는
[`ITERATION_11_REPORT.md`](ITERATION_11_REPORT.md)를 참조한다.

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
| B BIS ZIP | live PASS, limited | raw/manifest/normalized hash 검증 완료. exact-scope 반복은 unchanged |
| C TIC 파일 | live PASS, limited | 기존 package `492bcc8a6a0e4892ac9c6a9377815aef`의 raw가 workspace에 존재하며 exact-scope hash 비교 완료 |
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
  실제 개정 비교와 기관별 durable resume는 여전히 NOT_RUN이므로 Gate C 미통과다.
- 다음 네트워크 작업은 위 실행 권한을 명시하고 제한된 요청 예산을 유지한다.
  접속 복구를 위해 환경 설정을 다시 게시하거나 키·도메인을 바꿀 필요는 확인되지 않았다.

## 기준본 보존·동일 범위 재수집 — revision 16

2026-10-26 09:16–09:19 UTC에 TIC/BIS 각 파일을 네트워크 권한이 지정된 실행에서 한 번씩 받고,
수 초 뒤 동일 URL·동일 parser scope로 다시 한 번 받았다. 매 요청 timeout은 30초,
redirect는 금지, 응답 상한은 16 MiB였다. `source_captured_at`, HTTP status, content type,
Last-Modified, 원본 hash 및 parser manifest를 저장했다. 따라서 다음 source revision을 비교할
검증된 baseline이 이제 현재 workspace에 있다.

| 출처/URL | 현재 baseline | 동일 scope 반복 | 판정 |
|---|---|---|---|
| TIC Table 5 `slt_table5.txt` | HTTP 200, 3,804 bytes, SHA256 `e5de973b1a6f13c8ec95707d665ce107f53f467db10d7a2d991677ee67d1de11`, Last-Modified `Fri, 16 Oct 2026 20:07:27 GMT`; TSV 36행 intake 및 raw/normalized hash PASS | 같은 bytes/hash, `unchanged` | 변경본은 아님 |
| BIS `WS_GLI_csv_col.zip` | HTTP 200, 104,833 bytes, SHA256 `aa52afce4e18214831cfa00d3cb5aef76db04c375dc6d3346e99f0568bdd9c1d`, Last-Modified `Wed, 21 Oct 2026 07:59:26 GMT`; 225×220 intake 및 raw/normalized hash PASS | 같은 bytes/hash, `unchanged` | 변경본은 아님 |

raw, request/manifest와 normalized 파일은 `.gitignore` 대상 `data/` 아래에 보존했다. 조회 요약은
`reports/gate_c_baselines_20261026T091628Z.json` 및 `reports/gate_c_same_scope_repeats.json`에 있다.
TIC의 첫 최신 capture는 delimiter를 TXT로 지정해 parser review로 남았고, 보존된 동일 raw를
TSV/header row 6으로 재처리해 정상 검증했다. 원본은 변형하지 않았다.

기존 package의 exact request scope를 적용해 과거 기준본과 비교했다. TIC package
`492bcc8a6a0e4892ac9c6a9377815aef`(format `txt`, delimiter tab, header row 6, agency/table title 포함),
BIS package `86a1923e3a2240dcbe8b1248b128443d`(format `zip`, agency `BIS`)에 대해 각각
`SUCCEEDED`, `source_change_status=unchanged`가 나왔고 raw와 normalized hashes도 확인했다.
요약은 `reports/gate_c_exact_scope_compare.json`이다. 두 기관 모두 exact-scope baseline을
검증했고 다음 실제 원자료 개정 시 비교할 준비가 됐다.

### BIS flat ZIP 응답 변화와 복구 한계

이전 10회차 보고에는 공식 BIS `WS_GLI_csv_flat.zip`의 HTTP 503 관측이 기록돼 있었다.
2026-10-26 09:18:10 UTC 새 요청은 동일 URL에서 HTTP 200, 256,334 bytes,
SHA256 `0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5`,
Last-Modified `Wed, 21 Oct 2026 07:59:26 GMT`를 받았다. ZIP 안 CSV는 9,403,437 uncompressed
bytes여서 현재 parser의 행/셀 한도 검토에 걸렸고, 원본·request.json은 저장했지만 intake task는
`NEEDS_REVIEW/SCHEMA_CHANGED`로 끝났다. task `bea335ad-1819-42cb-8acd-797c6a452255`의 첫
attempt와 stage 결과도 `data/catalog.sqlite`에 남았다. 이는 제공자의 503 이후 같은 경로가 다시
200을 반환한 실측이지만, 503 당시 attempt 자체가 영속 task로 저장돼 있지 않았다. 그러므로
durable resume 성공 증거로 승격하지 않는다.

### 남은 Gate C 차단 조건

1. 보존된 TIC/BIS baseline과 같은 URL·요청/parser 범위에서 **다음 실제 원본 개정**을 받아야 한다.
   이전·새 raw hash가 다르고, 엔진이 `changed`/`NEEDS_REVIEW`를 내며 두 raw를 보존하고
   새 normalized 파일 발행을 막는지 확인한다. 현재 반복 결과는 양쪽 모두 unchanged다.
2. 향후 자연 발생하는 429/5xx 또는 retryable transport failure를 실행 중인 Orchestrator task에
   저장하고, `Retry-After`를 지킨 뒤 process/store를 다시 열어 같은 task를 수동 resume해야 한다.
   같은 stage가 성공하고 attempt/event 기록이 유지될 때 완료로 본다. 실패를 인위적으로 만들거나
   반복 요청해 rate limit을 유발하지 않는다.

따라서 현재도 **Gate C 미통과**다. 11회차는 명시적 사용자 예외로 이미 완료했고 12회차는 미시작이다.
