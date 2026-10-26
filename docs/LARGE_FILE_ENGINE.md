# 대용량 엔진 설정·시험·미실행 정책

2026-10-26. 범위: **비API 로컬 파일의 용량·형식 qualification**. 정식 대용량 수집/정규화 승인은 후속이다.

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

사용자 표시 예: `미실행: wall_time_budget`. trial_attempted=true이면 시험 중 중단된 것이며,
본 수집/정규화가 실행 완료됐다는 뜻이 아니다. “버림”은 시험 scratch의 폐기와 본 실행 포기를 뜻한다.
원본과 판정 이력·부모 task를 삭제하지 않는다. 검증된 실행 범위 확대에는 별도 명시적 검토와 새 증거가 필요하다.

## 사용과 재현

```text
macroatlas deferred
macroatlas large-check <DEFERRAL_ID>
macroatlas large-check <DEFERRAL_ID> --event-seq <SEQ>
macroatlas status <TRIAL_TASK_ID>
python scripts/benchmark_large_file_trials.py
```

large-check는 네트워크 요청을 하지 않는다. 응답의 parent_task_id/deferral_event_seq로 인계 원인을 추적한다.
합성 benchmark는 별도 `data/qualification_benchmark/` 저장소를 쓰며 실제 기관 인계 목록과 분리한다.
benchmark가 생성한 합성 입력·시험 chunk만 정리하고 보고서/이력은 보존한다.
결과는 `reports/large_file_qualification.json`, 검토용 사본은 LARGE_FILE_QUALIFICATION_RESULTS.json에 둔다.

## 정식 실행 전 남은 연결

이 단계는 용량·형식 시험이다. 경제 의미·단위·개정 비교·normalized 품질·출력 승인까지 수행하는 정식 엔진은 아니다.
정식 대용량 엔진은 검증된 schema와 resource profile, immutable artifact manifest, checkpoint/resume,
source-change guard와 품질 검증을 추가한 뒤 연결한다. 시험 통과 파일의 임시 chunk를 그대로 export하지 않는다.
특정 크기의 합성 CSV 통과를 동일 크기의 모든 ZIP/XLSX 또는 GB/TB 파일 지원으로 확대하지 않는다.
