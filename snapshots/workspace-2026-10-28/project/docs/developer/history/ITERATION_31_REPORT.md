# Iteration 31 — BEA·e-Stat metadata API와 저장 검증

**일자:** 2026-10-25

**범위:** Census·BLS 보류 후 다른 기관의 독립 API 검증(D-101). BEA GetDataSetList와 e-Stat getStatsList(lang=E, limit=1)만 사용했다. 기존 Gate U는 NOT PASSED 이력으로 유지한다.

## 실제 결과

| 기관 | 고정 요청 | HTTP | metadata 계약 | 저장 bytes | hash read-back |
|---|---|---:|---|---:|---|
| BEA / US-04 | GetDataSetList | 200 | Dataset 13개, 이름·설명·중복 검사 통과 | 1,302 | 통과 |
| e-Stat / JP-03 | getStatsList, lang=E, limit=1 | 200 | STATUS=0, LANG/LIMIT 및 표 1건 ID·제목 검사 통과 | 1,285 | 통과 |

실제 외부 요청은 **기관당 1회, 합계 2회, 재시도 0회**다. Census·BLS 호출은 0회다. 기존 프로젝트 network opt-in과 키를 사용했으며 `.env`나 credential을 변경하지 않았다. 이 요청 범위에서 API 인증과 metadata 응답·파일 재조회는 확인됐다. 관측값, 단위, 빈도, 개정판, 전체 데이터셋 coverage, 일반 discovery/ingestion workflow는 검증하지 않았다.

실행 증거:

- [live report JSON](../../../reports/iteration_31_api_metadata_2aad8102015e41b2a39fd2f310ce11f1.json)
- [synthetic fixture report](../../../reports/iteration_31_api_metadata_d4eb8047e97b4685b5e749ce8caf9379.json), 실제 HTTP 0회
- BEA [response](../../../data/raw/api/US-04/8d936bcf38234aa8b86581fa3bde44a6/response.json), [manifest](../../../data/raw/api/US-04/8d936bcf38234aa8b86581fa3bde44a6/request.json)
- e-Stat [response](../../../data/raw/api/JP-03/eb488978a4b2422e9088be120eb03bdc/response.json), [manifest](../../../data/raw/api/JP-03/eb488978a4b2422e9088be120eb03bdc/request.json)

저장 응답은 credential을 제거한 canonical JSON이다. 원 HTTP bytes와 동일하다고 주장하지 않는다. BEA SHA-256은 `56da2d2691d5d69da1f1c86864298b0922cd1838290fdaca91335be0a9db4204`, e-Stat은 `cc9dad50cde5cd746837181efe6de158bdd773dcfd541835fd0c9ce2283de209`다.

## 변경한 파일과 이유

- `discovery/api_catalogue_validation.py`: HTTP 200, source API 성공, metadata 존재를 분리하는 순수 검사. BEA Error envelope, e-Stat 오류/빈 결과·LANG/LIMIT 불일치는 성공으로 처리하지 않는다. 통계 값 변환은 없다.
- `scripts/verify_api_metadata.py`: 선택 가능한 기관을 BEA·e-Stat으로 고정하고 source당 요청 1회, 키/네트워크 확인, source별 결과와 archive/read-back을 기록한다. report를 exclusive 생성해 쓰기를 확인한 뒤 HTTP를 시작하고 기관 결과마다 flush한다. 한 기관 실패가 다른 기관의 결과를 숨기지 않는다.
- `discovery/source_registry.py`: 두 기관을 metadata-only PARTIAL live 근거로 갱신했다. adapter는 PARTIAL이며 일반 관측치 수집 지원으로 승격하지 않는다.
- `tests/test_api_metadata_checks.py`, `tests/test_source_registry.py`: 정상/오류/빈 목록/키 redaction/고정 선택/실패 분리/report 사전 쓰기와 실제 recorded fixture의 hash·계약을 검증한다.
- `bea_catalogue.json`, `estat_catalogue.json`: 합성 fixture. `recorded_bea_catalogue.json`, `recorded_estat_catalogue.json` 및 provenance JSON은 이번 live 저장 응답을 키 비노출 확인 후 복사한 source fixture다. 두 증거 유형을 혼합하지 않는다.
- 운영·실행 문서와 AGENTS.md: 사용자 지시인 Census·BLS 보류, Gate U 이력 보존, 독립 source gate와 다음 API 큐를 반영했다.

## 재현

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.venv\Scripts\python.exe -X utf8 scripts/verify_api_metadata.py --fixture
```

실기관 요청은 network opt-in과 source 키가 준비됐을 때만 실행한다. 다음 명령은 BEA 한 기관에 1회 요청하며 반복 실행은 별도 요청 예산에 포함한다.

```powershell
.venv\Scripts\python.exe -X utf8 scripts/verify_api_metadata.py --live --source bea
```

`--source estat`은 e-Stat만 선택하며 생략하면 두 기관을 한 번씩 실행한다. `census`·`bls` 또는 임의 endpoint는 이 실행기가 받지 않는다. 오류 설명이나 credential을 report에 복사하지 않고 고정 상태·이유만 기록한다.

## Gate V와 검증

Gate V는 metadata 검사·안전한 저장/재조회 구현을 검증하는 engineering gate다. 실제 기관 상태는 위 두 source별 metadata sub-gate로 따로 판정한다. 전체 ingestion gate나 보류된 Gate U 성공을 뜻하지 않는다.

- 초기 관련 검사: `test_api_metadata_checks.py`·`test_api_response_storage.py` **51 passed**.
- Recorded fixture와 registry 갱신 후 최종 전체 offline suite: **884 passed, 1 skipped, 0 failed (66.66초)**. Skip은 Windows symlink 생성 미지원이다.
- 합성 runner: 두 source 모두 `fixture_metadata_validated`, live HTTP 0회.
- 실제 runner: 두 source 모두 `live_metadata_validated`, source 요청 2회, retry 0회.
- 변경 Python Ruff와 `git diff --check` 통과. 변경 파일·신규 fixture·live/fixture reports·저장 응답/manifest 등 41개 파일의 실제 configured credential 비노출 검사도 통과했다. **Engineering Gate V PASS, BEA/e-Stat metadata live sub-gate PASS**다. 관측치 ingestion과 Gate U는 이 판정 범위 밖이다.

Windows 기본 pytest Temp의 접근 거부를 피하도록 저장소 내부의 고유 `reports/pytest_<id>`를 basetemp로 사용했다. 전체 검사에서 symlink를 만들 수 없는 경우 해당 테스트는 skip으로 기록한다. 기존 사용자 Temp나 Windows ACL을 바꾸지 않았다.

## 공식 근거와 한계

- [BEA GetDataSetList 및 API guide](https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf): 데이터셋 이름·설명 계약, 문서상 분당 요청 100회/100 MB/오류 30회 및 변경 가능한 제한. 이번 요청은 1회이며 자동 retry를 하지 않았다.
- [e-Stat v3.0 명세](https://www.e-stat.go.jp/api/node/166): getStatsList, lang/limit, RESULT.STATUS와 목록 구조. STATUS=1은 빈 결과 정상 종료여서 오류와 구분하지만 이 회차의 metadata 존재 검증에는 통과시키지 않는다. 별도 일일/초당 quota는 이 문서 조사에서 확정하지 않았으며 1회로 제한했다.

e-Stat은 영어를 요청하고 echo를 확인했다. 모든 자유 텍스트가 영어로 제공되는지, 미제공 항목을 어떻게 번역할지는 평가하지 않았다. 원문은 archive에 보존한다. 키 값은 출력하지 않았고 source 오류 설명도 새 report에 복사하지 않는다.

다음 독립 회차 후보는 SDMX 6곳의 source payload·metadata 검사다. IMF·BOJ는 정확한 route/auth 근거와 구현이 별도로 필요하다. 이번 작업 이후 추가 번호 회차나 main 병합은 수행하지 않는다.
