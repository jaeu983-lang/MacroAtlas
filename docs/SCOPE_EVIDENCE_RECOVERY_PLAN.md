# 분석기 근거 부족 사례 재검토와 후속 계획

2026-10-27. 보존 catalog를 읽기 전용으로 분석했다. 과거 실행은 `insufficient_evidence_count=7`을 반환했지만, 이는 합성 용량 시험과 운영 수집 오류를 한 목록에 섞고 BIS 파일의 보존 manifest 경로를 읽지 못한 결과였다. 이 문서는 기존 task·event·원본을 수정하지 않고 분석 projection만 개선한 후속 결과를 기록한다.

## 구현 결과

현재 보존 catalog를 다시 분석한 결과는 task 49개, stage 57개이며 task/record 상한에 걸리지 않았다.

| Evidence domain | Stage 수 | 처리 |
|---|---:|---|
| 검증된 합성 qualification fixture | 15 | `trial_only`, `large_file_trial`, 미실행 production 상태, deferral ID/sequence/origin 및 저장 event/scope가 모두 일치하는 경우에만 운영 집계에서 분리한다. |
| 저장된 실제 파일을 대상으로 한 qualification trial | 5 | 동일한 task/event 연결과 `production_execution=NOT_EXECUTED`를 검증해 qualification 집계에 둔다. 운영 장애 건수에는 포함하지 않는다. |
| Operational stage history | 37 | 일반 오류·성공 이력으로 분석한다. |

이전 `insufficient_evidence_count=7`의 다섯 오류 fixture는 현재 15건의 합성 시험 이력 중 일부로 확인됐다. 저장 event가 없거나 plan/stage/event의 출처 연결이 맞지 않는 `trial_only` task는 시험으로 추측 분류하지 않고 운영 집계에 남긴다.

두 BIS 운영 오류는 각각 `tabular_file` inbox raw와 `bis_flat_probe`가 가리키는 보존 raw/manifest를 검증해 `institution_id=bis`, `dataset_id=WS_GLI_csv_flat`으로 분석 projection에서 복구했다. 두 경로 모두 다음 증거와 일치한다.

- 공식 source URL: `https://data.bis.org/static/bulk/WS_GLI_csv_flat.zip`
- 원본 SHA-256: `0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5`
- 보존 manifest: `data/raw/tabular/9594fab099de46d89bac7ba97a26b8e1/request.json`
- manifest SHA-256: `ca5ccd38d6856aa8c832db9d6b45351b8bf12a352435e725401aa791eb3c243e`
- manifest HTTP status 200, BIS 기관, UTC retrieval time, ZIP format, raw byte 수·해시, 실제 단일 CSV member와 CRC를 확인했다.

복구는 read-only scope projection으로만 이뤄진다. task 문서, failure 상태, raw, manifest를 수정하지 않는다. 파일 ID 복구는 경제 concept을 제공하지 않으며 결과에 `concept=null`, `unknown_not_inferred_from_file_identity`를 남긴다.

기술 오류 분석에서는 `TRANSIENT`, `AUTH_ACCESS`, `SITE_CHANGED`, `SCHEMA_CHANGED`, `LICENSE_SECURITY`, `INTERNAL_BUG`에 institution, engine/version, stage, dataset, error category를 요구하고 concept은 요구하지 않는다. `SEMANTIC_AMBIGUITY`, `QUALITY_FAILURE`, 미분류 오류와 accepted feedback는 concept을 계속 요구한다. 따라서 서로 다른 dataset이나 engine은 같은 기술 오류 코드라는 이유만으로 합쳐지지 않는다.

현 로컬 snapshot 결과는 operational stage 37건, technical error 3건, 그중 concept 미상 2건(BIS 두 오류), insufficient-evidence 0건, recurring proposal 0건이다. BIS 두 stage는 서로 다른 engine/stage의 단발 이력이므로 반복 개선 제안이 되지 않는다. `insufficient_evidence_count=0`은 이 보존 snapshot과 analyzer 상한 안에서만 성립하며 Gate C 통과나 모든 engine/provider의 오류 완결성을 뜻하지 않는다.

## 회귀 검증과 완료 기준

이번 변경에서 검증하는 계약은 다음과 같다.

1. 합성 시험은 task의 `trial_only` 표시만으로 분류하지 않는다. 저장된 deferral event의 ID, sequence, origin task, scope 경로·format과 stage 결과가 모두 맞아야 별도 qualification domain으로 집계한다.
2. BIS 기관/dataset은 exact URL, 보존 manifest의 기관·HTTP status·UTC capture time·ZIP 경로/크기/hash, 보존 raw SHA 및 단일 CSV ZIP 구조가 일치할 때만 복구한다. 불일치·누락·안전하지 않은 경로는 unknown으로 남긴다.
3. 기술 오류는 concept 미상이어도 동일한 institution/dataset/engine/version/stage/error에 한해 검토할 수 있다. 경제 의미·품질 분석은 concept 미상일 때 제안하지 않는다.
4. 원본 보존, 출력의 민감 정보 비노출, 기존 3개 distinct task 기준, reader-only 동작을 회귀 검증한다.

## 완료된 후속: engine별 기관 오류 전체 목록

전체 69개 task와 저장 stage 57개를 상한 없이 읽은 [full-catalog 감사 보고서](ENGINE_INSTITUTION_ERROR_AUDIT_2026_10_27.md)를 작성했다. 운영 오류는 3건이며 모두 기관/dataset을 식별했다: BIS `SCHEMA_CHANGED` 2건과 World Bank `TRANSIENT` 1건. World Bank 오류는 같은 task/stage에서 실패 후 성공한 기록을 보존한다. 이 catalog snapshot의 현재 운영 오류에 기관/dataset unknown은 없다.

다만 `bls`, `census`, `large_file_production` 성공 stage 5건은 analyzer scope projection에서 기관/dataset이 unknown이다. 보존 payload/plan에는 BLS·Census source metadata와 BIS production raw/manifest reference가 있으므로, 다음 작업은 이 세 engine의 근거 경로와 scope adapter를 별도로 검증·보완하는 것이다. BLS `dataset_id=null`은 유지하고, 미상 identity를 가진 오류처럼 취급하거나 추정하지 않는다. 해당 scope projection 보완 뒤 전체 audit를 다시 실행해 범위를 확인한다.

이 audit과 adapter 후속은 Gate C 자연 원본 변경·자연 장애 증거 및 사용자 사용성 시험과 별도 트랙으로 관리한다.
