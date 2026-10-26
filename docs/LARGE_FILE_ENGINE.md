# 대용량 엔진 설정·시험·미실행 정책

2026-10-26. 범위: **비API 로컬 파일의 qualification과 제한된 BIS flat 구조 보존 production 경로**.
일반 대용량 수집·정규화는 지원하지 않는다. 이 문서는 qualification 정책을 기록한다. BIS handoff의
지원 범위와 현재 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 목표 경계는
[제품 아키텍처](PRODUCT_ARCHITECTURE.md)를 따른다.

## 공식 사례 조사와 선택

| 사례 | 공식 자료에서 확인한 방식·주의점 | 이번 적용 |
|---|---|---|
| DuckDB | out-of-core spill, temp_directory와 임시 디스크 제한. 일부 연산의 할당은 buffer manager memory_limit 밖에서 발생 가능 | 메모리 설정 하나를 전체 제한으로 보지 않고 프로세스·시간·출력 예산을 함께 적용 |
| Apache Arrow | open_csv 배치 읽기, 초기 block에서 타입 추론 후 고정. string 명시로 leading zero 같은 표현 보존 가능 | 작은 배치로 읽고 관측값을 문자열로 보존. 자동 숫자·결측 변환을 하지 않음 |
| Polars | lazy streaming·sink 지원. 일부 연산은 in-memory 처리로 fallback 가능 | 숨은 전체 메모리 fallback을 허용하지 않고 지원 형식만 시험. 미지원 형식은 미실행 |

공식 출처: [DuckDB OOM](https://duckdb.org/docs/current/guides/performance/oom),
[DuckDB workload tuning](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads),
[Arrow CSV](https://arrow.apache.org/docs/python/csv.html#incremental-reading),
[Polars streaming](https://docs.pola.rs/user-guide/concepts/streaming/).
조사는 공식 문서 기반이며 세 제품의 실행 성능을 비교 측정한 것은 아니다. 현재 환경에 이 세 제품은 설치되지 않았다.
이번 시험 worker는 Python 표준 csv/zipfile의 제한된 streaming 구현을 사용해 추가 의존성을 도입하지 않았다.

## 설정과 실행 흐름

```mermaid
flowchart LR
    A[인계 후보 / 애매한 후보] --> B[명시 large-check]
    B --> C[불변 판정 event + 원본 stat + 코드/예산 고정]
    C --> D[부모 참조를 가진 시험 task 저장]
    D --> E[동일 저장소 worker 1개 / 격리 프로세스]
    E --> F{시험 결과}
    F -->|통과| G[TRIAL_PASSED / 본 실행 승인 대기]
    F -->|예산·형식·환경 실패| H[NOT_EXECUTED / 미실행 사유]
    G --> I[시험 임시 산출물 폐기 / 원본·결과 이력 보존]
    H --> I
```

- 기본 시험 예산: **입력 128 MiB 미만, 출력 합계 192 MiB 미만, 가상 주소 공간 384 MiB,
  CPU 15초, wall time 20초**, 한 저장소에서 동시에 worker 1개.
- worker는 Linux의 RLIMIT_AS/CPU/FSIZE와 부모 프로세스 timeout을 함께 사용한다. RSS는 별도로 측정한다.
  이 프로세스 분리는 자원 제한이며 임의 코드의 보안 sandbox를 제공하지 않는다. worker는 고정된 로컬 파일 처리만 수행한다.
- CSV/TSV/TXT·ZIP 내 단일 표만 시험한다. UTF-8, 최대 4,096열·2,000,000행,
  필드 1 MiB·물리적 한 줄 2 MiB 제한이 있다. ZIP 경로·암호화·중복·200배 압축 비율 등 보안 제한을 유지한다.
- ZIP 전체 해제량 256 MiB 미만, 선택 표 128 MiB 미만. 실제 읽은 decoded bytes에도 상한을 적용한다.
- 행을 10,000개씩 임시 JSONL chunk로 쓰고 전체 표를 메모리에 쌓지 않는다. 작은 파일 엔진에 재진입하지 않는다.
- 원본 경로는 configured inbox/raw 내부로 제한하고 symlink를 거부한다. 선택 당시 inode/크기/mtime를 고정하고
  처리 전후 raw hash를 대조한다. 선택 당시 hash가 없으면 소급 원본 버전 검증을 주장하지 않는다.
- event ID+scope+예산+실행 코드 fingerprint로 중복 시험을 막는다. 원본 stat이 바뀌면 이전 결과를 새 시험으로 재사용하지 않는다.
- 시험 task 생성과 부모/event 연결은 같은 HistoryStore transaction에서 저장한다. 원래 인계 task의 상태는 유지한다.

## 애매한 자료와 실패 응답

애매한 자료는 인계 목록의 inspection_required 후보로 남겨 시험할 수 있다. 구분자를 지정하지 않은 TXT는 현재 파일 intake에서 자동으로 delimiter_unknown 후보를 등록한다. TXT 구분자는 한정된 후보에서
제한된 header sample로 추정하며, `delimiter_inferred=true`를 남긴다. 추정 성공을 본 실행 승인으로 승격하지 않는다.
여러 ZIP 표 중 선택 불명, 지원하지 않는 XLS/XLSX/PDF/encoding 등은 reason과 함께 미실행한다.
보안 검토 대상은 용량 시험으로 우회하지 않는다. 원격 URL만 있고 로컬 raw가 없으면 no_local_artifact로 미실행한다.

| 상황 | 응답 / 처리 |
|---|---|
| 용량 시험 통과 | TRIAL_PASSED, production_execution=NOT_EXECUTED, eligible_for_production=false |
| 입력/출력/메모리/CPU·wall 예산 도달 또는 worker 종료 | NOT_EXECUTED, reason·trial_attempted 기록, 원본 보존·시험 임시 산출물 제거 |
| 자원 격리를 제공하지 않는 OS | NOT_EXECUTED: resource_isolation_unavailable. 무제한 실행으로 fallback하지 않음 |
| 같은 저장소 worker 사용 중 | NOT_EXECUTED: engine_busy. 자동 재시도 없음 |
| 원본 교체·변경 / 실행 코드 변경 | NOT_EXECUTED: source_changed_since_binding / engine_version_changed |
| SQLite 이력 저장소 사용 불가 | NOT_EXECUTED: trial_storage_unavailable. trial_state=UNKNOWN으로 시험 여부를 단정하지 않음 |
| 같은 후보·코드·예산 재요청 | 저장된 결과 반환. 실패한 시험을 몰래 다시 실행하지 않음 |
| 부모 프로세스 강제 종료 | worker가 상속한 workspace lock이 child 종료까지 유지됨. lock 사용 중 resume은 worker_still_active로 멈춤. lock 해제 뒤 `resume`은 marked scratch를 정리하고 `NEEDS_REVIEW`, `execution_state=NOT_EXECUTED`, `trial_state=UNKNOWN`을 저장하며 worker를 다시 실행하지 않음 |

사용자 표시 예: `미실행: wall_time_budget`. `trial_attempted=true`이면 예산 제한 아래 시험이 시작됐다는
뜻이며, 본 수집/정규화가 실행 완료됐다는 뜻이 아니다. 강제 종료로 worker 결과가 task에 저장되지 않은 경우
`trial_attempted=null`, `trial_state=UNKNOWN`을 사용한다. “버림”은 시험 scratch의 폐기와 본 실행 포기를 뜻한다.
원본과 판정 이력·부모 task를 삭제하지 않는다. 검증된 실행 범위 확대에는 별도 명시적 검토와 새 증거가 필요하다.

## 사용과 재현

```text
macroatlas deferred
macroatlas large-check <DEFERRAL_ID>
macroatlas large-check <DEFERRAL_ID> --event-seq <SEQ>
macroatlas status <TRIAL_TASK_ID>
macroatlas resume <TRIAL_TASK_ID> --live
python scripts/benchmark_large_file_trials.py
```

large-check는 네트워크 요청을 하지 않는다. 응답의 parent_task_id/deferral_event_seq로 인계 원인을 추적한다.
시험 task의 resume는 일반 workflow 재시도와 다르다. `RUNNING` 상태에서 시작하면 worker lock을 확인하고
중단 결과를 미확정으로 기록한다. 성공 결과가 저장되지 않은 qualification을 같은 task에서 다시 실행하지 않는다.
합성 benchmark는 별도 `data/qualification_benchmark/` 저장소를 쓰며 실제 기관 인계 목록과 분리한다.
benchmark가 생성한 합성 입력·시험 chunk만 정리하고 보고서/이력은 보존한다.
결과는 `reports/large_file_qualification.json`, 검토용 사본은 LARGE_FILE_QUALIFICATION_RESULTS.json에 둔다.

## 19회차 제한 production 경로

17회차 시험 결과는 계속 `trial_only`이며 자동 승격되지 않는다. 19회차는 별도 approval과 같은 event/hash의
성공 trial을 요구하는 BIS GLI flat ZIP production child task를 추가했다. flow는 다음과 같다.

```text
macroatlas deferred <ID> --events
macroatlas large-run <ID> --event-seq <SEQ> --approve-production
macroatlas status <CHILD_TASK_ID>
macroatlas large-resume <CHILD_TASK_ID>
```

지원 범위는 `https://data.bis.org/static/bulk/WS_GLI_csv_flat.zip`의 이미 보존된 raw 한 건,
ZIP 내부 단일 UTF-8 CSV로 한정한다. 새 네트워크 요청은 보내지 않는다. `large-run`은 불변 deferral event,
origin task, inbox/raw SHA-256, 기존 request manifest/hash, 일치하는 `TRIAL_PASSED` task를 검증한 뒤
child task와 `handed_off` event를 같은 SQLite transaction에서 저장한다. 중복 호출은 같은 child를 돌려준다.

Linux에서 입력 128 MiB, 출력 192 MiB, RLIMIT_AS 384 MiB, CPU 30초, wall 60초를 제한한다.
최대 2,000,000 data rows / 20,000,000 cells를 처리하며 10,000행마다 JSONL chunk와 SHA-256 checkpoint를
원자적으로 기록한다. Worker는 SQLite cancel flag를 확인한다. resume는 source, request manifest, checkpoint,
완료 chunk를 다시 검증하고 같은 task에서 이어간다. parent 종료 후에는 worker가 물려받은 lock이 풀린 뒤
`large-resume`으로 중단 task를 복구한다. 다른 OS에서는 제한 없는 fallback 없이 `NOT_EXECUTED`다.

완료 output manifest는 source URL·기관·capture metadata·raw/request hash·zip member·headers·counts·chunk hashes를
기록한다. null/empty와 `0` 표현을 그대로 보존하며 모든 원본 필드를 문자열로 둔다. 검증 범위는 CSV 구조와 파일
무결성뿐이다. 단위·빈도·경제 의미를 정규화하지 않고 Gate C natural revision/recovery 증거로 사용하지 않는다.
시험 chunk와 production artifact는 별도 경로다. 범용 대용량 export, 다른 provider/format, GB/TB, Windows
resource worker는 미지원이다.

### 보존 원본 실행 기록

2026-10-26에 통합 HEAD `dfdfa307534c504f8c740fe1a154a7ba47945e10`에서 기존 deferral event seq `1`을
child task `c244a486-17e5-4b60-a82b-287f8a37bbe7`로 한 번 처리했다. task는 1 attempt에서 완료됐고,
24,378행·21열을 세 JSONL chunk로 기록했다. output manifest SHA-256은
`bc0e7434765b03aa0dc78e9bae684abd02cfd5e083387ba950697b4a91151e88`이며 raw·request manifest 원본 해시와
각 chunk 해시를 재검증했다. deferral 상태는 `handed_off`와 `resolved` 이력을 보존한다. 전체 근거와 식별자는
[19회차 보고서](ITERATION_19_REPORT.md)에 있다. 이는 로컬 보존본의 구조 처리이며 Gate C natural change/recovery 증거가 아니다.

## 한계와 다음 연결

특정 크기의 합성 CSV 통과를 동일 크기의 모든 ZIP/XLSX 또는 GB/TB 파일 지원으로 확대하지 않는다.
이 child output을 검증된 World Bank/BOJ observation CSV exporter에 연결하지 않는다. provider task exporter는
[CSV 후속 계획](CSV_EXPORT_FOLLOWUP_PLAN.md)의 별도 artifact/provenance 계약을 따른다.
