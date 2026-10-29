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
| `bls/1` | 2 | 0 | 0 | 2 | 두 보존 response/manifest가 BLS endpoint와 요청 series를 확인. provider 결과의 `dataset_id`는 명시적으로 null |
| `boj_metadata/1` | 2 | 0 | 0 | 0 | BOJ / `FM08` |
| `boj_observations/1` | 2 | 0 | 0 | 0 | BOJ / `FM08` |
| `census/1` | 2 | 0 | 0 | 0 | 보존 response/manifest, 요청, 공식 URL이 Census / `acs/acs1`과 일치 |
| `gate_c_file_watch/1` | 15 | 0 | 0 | 0 | TIC 7, BIS column 8로 식별 |
| `large_file_production/1` | 1 | 0 | 0 | 0 | 성공 plan의 raw/manifest 경로와 SHA가 BIS flat capture 검증 결과와 일치 |
| `tabular_file/1` | 1 | 1 | 0 | 0 | BIS flat scope 복구 |
| `worldbank_collect_audit/1` | 6 | 1 | 0 | 0 | World Bank / dataset `2`; transient 이후 같은 task 재개 성공 |
| `worldbank_validate/1` | 5 | 0 | 0 | 0 | World Bank / dataset `2` |
| **합계** | **37** | **3** | **0** | **2** | Unknown dataset 2건은 BLS success stage이며 오류 scope에는 없음 |

초기 감사 시에는 BLS·Census·`large_file_production` 성공 stage 5건이 analyzer projection에서 unknown이었다. 2026-10-27 후속으로 exact API URL, saved request, manifest, raw digest와 응답 구조를 검증하는 BLS/Census adapter를 연결하고, large-file production plan hash를 기존 BIS 검증기 결과와 대조했다. 이어 전체 analyzer 범위를 다시 읽어 terminal task 49개와 stage 57개 모두를 검사했다. truncation은 없었고 verified scope resolution 7건, operational stage 37건, 오류 3건, unknown institution 0건, unknown dataset 2건이었다. 나머지 unknown dataset 두 건은 BLS 성공 응답의 `dataset_id=null`을 그대로 보존한 결과다. series ID만으로 경제 dataset을 만들어 내지 않았다.

## 다음 우선 작업

1. BLS 문서 검토 결과, registered API v2는 series description을 제공하지만 complete series catalogue는 없고 `catalog`도 일부 survey만 지원한다. CPI 공식 code 표의 `CU`는 CPI-U를 뜻하지만 이는 series type이고 MacroAtlas `dataset_id`라고 단정할 근거는 아니다. 보존 task는 `dataset_id=null`로 유지한다. 이후 등록 metadata가 자연 수집 응답에 저장되면 다시 매핑을 검토한다. ([BLS API FAQ](https://www.bls.gov/developers/api_FAQs.htm), [API v2 signature](https://www.bls.gov/developers/api_signature_v2.htm), [CPI series ID codes](https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm))
2. 새 운영 이력이 쌓일 때 같은 full-catalog 방식으로 기관·dataset·engine/version·stage·error category를 재감사한다. 운영 오류 수와 Gate C 자연 증거 판정은 계속 분리한다.

이 결과는 2026-10-27 당시 local catalog 전체의 감사다. 다른 catalog, 이후 task, 또는 모든 기관이 오류가 없다는 뜻은 아니다. TIC/BIS Gate C의 자연 변경과 해당 watch scope의 자연 장애 후 재개 조건도 별도로 남아 있다.

### 후속 확인 — 2026-10-29

Iteration 42에서 등록키를 사용하는 BLS 요청에 `catalog=true`를 설정하고 CPI-U와 실업률 series 두 건의 선택 metadata를 실제로 보존했다. 제목과 일부 survey/seasonality 속성이 확인됐으나 두 응답 모두 `dataset_id=null`로 유지했다. 이 후속 표본은 위 2026-10-27 catalog snapshot이나 전체 series coverage를 바꾸지 않는다. value-free 근거와 한계는 [Iteration 42 report](ITERATION_42_REPORT.md)에 기록했다.
