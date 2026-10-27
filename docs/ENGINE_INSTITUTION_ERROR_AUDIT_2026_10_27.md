# 전체 이력 engine×institution 오류 감사

**감사일:** 2026-10-27
**범위:** `data/catalog.sqlite` 전체 저장 이력, read-only
**목적:** 최근 PatternAnalyzer 표본을 넘어 현재 catalog의 기관·engine별 오류와 scope 식별 공백을 확인한다.

## 방법과 범위

SQLite를 `mode=ro`와 `query_only`로 열어 69개 task 문서, 330개 task event, 전체 저장 stage 기록을 상한 없이 조회했다. 외부 요청은 하지 않았다. 기존 raw나 manifest도 변경하지 않았다. BIS flat capture는 기존 provenance 검증기를 이용해 exact URL, request manifest, raw SHA, ZIP member profile을 다시 확인했다. 합성/qualification task는 저장된 trial marker와 deferral event가 연결될 때만 운영 기록에서 제외했다.

Task 상태는 `COMPLETED` 42개, `NEEDS_REVIEW` 7개, `CREATED` 20개다. 저장 stage는 총 57개로 `SUCCEEDED` 49개, `NEEDS_REVIEW` 7개, `FAILED_RETRYABLE` 1개다. 20개 `CREATED` task에는 저장 stage가 없었다. 57개 stage 중 검증된 합성 fixture 15개와 보존 파일 qualification trial 5개를 제외하면 운영 stage는 37개다.

## 오류 결과

전체 catalog에서 운영 오류 3건을 확인했다. 세 건 모두 institution과 dataset이 식별되며, 이 snapshot에는 기관/dataset 미상인 오류 stage가 없다.

| Engine/version | Institution / dataset | Stage / error | 실패 task 수 | 같은 scope 성공 근거 |
|---|---|---|---:|---|
| `tabular_file/1` | `bis` / `WS_GLI_csv_flat` | `inspect / SCHEMA_CHANGED` | 1 | 같은 engine/stage의 운영 성공 없음 |
| `bis_flat_probe/1` | `bis` / `WS_GLI_csv_flat` | `capture / SCHEMA_CHANGED` | 1 | 같은 engine/stage의 운영 성공 없음 |
| `worldbank_collect_audit/1` | `worldbank` / `2` | `collect / TRANSIENT` | 1 | 같은 task `84a1afd9…`에서 같은 collect stage가 실패 후 성공. 같은 scope의 성공 task는 총 5개이며, 이 중 4개는 별도 task |

World Bank task는 attempt 1에서 `FAILED_RETRYABLE/TRANSIENT`, attempt 2에서 같은 collect stage가 `SUCCEEDED`로 끝났다. 그 task의 16개 append-only event도 남아 있다. 따라서 **BIS 오류 두 건이 전체 기관 오류의 전부는 아니다.** 현재 full-catalog snapshot에는 추가로 World Bank 오류 한 건이 있으며, 저장된 attempt 이력에서 복구도 확인된다. 다만 실패는 World Bank task 한 건이라 반복 오류로 승격할 근거는 없다. BIS 두 오류도 각각 다른 engine/stage의 단발 사례다. qualification trial 결과는 운영 성공 counterexample로 세지 않았다.

## Engine별 운영 scope coverage

| Engine/version | Operational stages | 오류 stage | Unknown institution | Unknown dataset | 확인 |
|---|---:|---:|---:|---:|---|
| `bis_flat_probe/1` | 1 | 1 | 0 | 0 | BIS exact URL와 저장 raw/manifest 검증 |
| `bls/1` | 2 | 0 | 2 | 2 | payload에 BLS agency와 공식 API URL은 있으나 analyzer projection은 unknown. payload의 `dataset_id`도 명시적으로 null |
| `boj_metadata/1` | 2 | 0 | 0 | 0 | BOJ / `FM08` |
| `boj_observations/1` | 2 | 0 | 0 | 0 | BOJ / `FM08` |
| `census/1` | 2 | 0 | 2 | 2 | payload에 Census agency, `acs/acs1` dataset, 공식 URL이 있으나 analyzer projection은 unknown |
| `gate_c_file_watch/1` | 15 | 0 | 0 | 0 | TIC 7, BIS column 8로 식별 |
| `large_file_production/1` | 1 | 0 | 1 | 1 | 성공 task plan에 BIS source, raw/manifest path·hash가 있으나 analyzer가 해당 input fields를 projection에 연결하지 않음 |
| `tabular_file/1` | 1 | 1 | 0 | 0 | BIS flat scope 복구 |
| `worldbank_collect_audit/1` | 6 | 1 | 0 | 0 | World Bank / dataset `2`; transient 이후 같은 task 재개 성공 |
| `worldbank_validate/1` | 5 | 0 | 0 | 0 | World Bank / dataset `2` |
| **합계** | **37** | **3** | **5** | **5** | Unknown 5건은 모두 성공 stage이며 오류 scope에는 없음 |

BLS·Census·`large_file_production`의 5개 unknown은 **오류 누락이 아니라 analyzer scope projection 공백**이다. 저장된 BLS payload는 dataset ID가 null이므로 이를 만들어 내지 않는다. Census payload에는 `acs/acs1`이 있고 production plan에는 BIS provenance가 있으나, 각각의 기관/범위를 현재 projection이 연결하지 않는다.

## 다음 우선 작업

1. 성공 stage의 검증된 scope projection을 확장한다. Census는 저장된 dataset과 provider metadata를 확인하고, `large_file_production`은 BIS helper에 plan의 raw/manifest 경로를 연결해 기존 검증을 재사용한다.
2. BLS agency identity는 보존 request manifest와 공식 endpoint metadata를 확인한 뒤 adapter 여부를 정한다. dataset ID는 현재 응답의 null을 유지하고, BLS series 범위가 명확해지기 전에는 오류들을 하나의 dataset scope로 합치지 않는다.
3. 변경 후 전체 catalog를 다시 읽어 같은 69 task/57 stage 범위에서 identity coverage를 비교한다. 운영 오류 수와 Gate C 판정은 별도 집계로 유지한다.

이 결과는 2026-10-27 당시 local catalog 전체의 감사다. 다른 catalog, 이후 task, 또는 모든 기관이 오류가 없다는 뜻은 아니다. TIC/BIS Gate C의 자연 변경과 해당 watch scope의 자연 장애 후 재개 조건도 별도로 남아 있다.
