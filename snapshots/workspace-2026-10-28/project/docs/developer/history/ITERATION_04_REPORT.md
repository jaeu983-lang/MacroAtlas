# 04회차 완료 보고 — Gate A

기준일: 2026-10-25 (Asia/Seoul)

상태: **Gate A 통과 — World Bank USA GDP의 고정 경로**

## 구현한 사용자 가치

확정된 단일 World Bank 요청을 기존 작업 흐름에서 수집하고, 원본 무결성을 확인한 뒤 관측치를 검증·정규화해 SQLite 이력에 보존한다. 검증 결과, 실패 기록, 명시적 피드백도 해당 작업과 연결한다. 원본은 `data/raw/worldbank/<UUID>/response.json`, 요청 manifest는 같은 폴더의 `request.json`에 저장한다.

이 회차의 Gate A 경로는 기관·후보 자동 탐색이나 범용 수집 기능이 아니다. 검증 대상은 USA, WDI source 2, `NY.GDP.MKTP.CD` (GDP current US$), 2020~2022년, `raw_json` 한 건이다.

## 주요 구현·검증 파일

- `src/macro_data_platform/ingestion/worldbank_quality.py`: 원본·manifest SHA256 확인, 제한된 경로에서 재읽기, 최소 관측치 정규화·품질 검사, 검증 결과와 실패 incident 기록.
- `src/macro_data_platform/storage/audit.py`: 기존 SQLite schema version 2에 추가형 artifact·validation·incident·feedback 기록과 정규화 관측치를 저장한다. 과거 Task JSON을 다시 쓰지 않는다.
- `src/macro_data_platform/ingestion/worldbank_request.py`: Gate A 전용 수집·검증 단계를 기존 World Bank 요청에 연결한다.
- `scripts/verify_worldbank.py`: `--live --gate-a`를 모두 명시한 실측 검증 진입점.
- `tests/test_gate_a.py`: fixture 기반 정상·실패·무결성·재개·피드백 검증. 자동 fixture는 실제 HTTP 요청을 금지한다.

## 실측 및 저장 근거

저장된 실행 보고서: `reports/iteration_04_live_33263386304d44ee9ba174e0609d6cff.json`

Task ID: `19e26a12-7c35-4c1b-b759-2ec7a209f8a5`

실제 수집: 2026-10-24 15:29:32 UTC (2026-10-25 00:29:32 KST)

- 고정 World Bank API 요청이 HTTP 200으로 끝났다. 응답 본문은 724 bytes이고 세 관측 기간은 2020, 2021, 2022다.
- 원본 SHA256: `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1`. 보고서의 경로에 있는 파일과 해시가 일치한다.
- Manifest SHA256: `c41bd3f373fa80b624a47873ef8f399745f5453ffe4f968e4bf87b872890b5f8`. 보고서의 경로에 있는 파일과 해시가 일치한다.
- SQLite에는 artifact, validation, feedback 기록과 정규화 관측치 세 행이 남아 있다. 저장된 정규화 행의 재계산 해시가 validation 기록과 일치하며 schema version은 2다.
- 검증 상태는 `passed`, 이슈는 없고 요청 기간 세 개 모두 관측됐다. 저장 보고서의 `live_path_passed`는 `true`다.

데이터 원본에서 `unit`과 `frequency`를 확정할 근거는 없어서 정규화 값은 unknown으로 보존했다. `source_last_updated=2026-10-08`은 원본의 갱신 표기이며 불변 vintage가 아니다. 검증기는 경제적 이상치, 개정 이력, 다른 기관 시계열과의 동등성을 검사하지 않는다.

## 자동 검증 결과

2026-10-25 실행 결과:

- 전체 pytest: **433 passed in 19.95s**.
- Ruff: **All checks passed!**
- 전체 테스트는 로컬 검증이며 `test_gate_a.py` fixture 테스트는 실제 HTTP를 금지한다. 테스트 통과 자체를 live API 증거로 보지 않는다.

Gate A 실패·오염 안전성은 fixture에서 중복/누락 기간, 단위 불일치, schema/HTTP 오류, 파일 또는 관측치 변조, SQLite 원자성, 승인된 재개와 기존 원본 보존을 확인했다. 이는 해당 실패 조건을 이번 실측 API에서 유발했다는 뜻은 아니다.

## 범위와 남은 한계

- 실제 서비스 증거는 고정 World Bank USA GDP file 경로 1건뿐이다. 링크와 `both` 전달, 장애 분기는 fixture 증거다.
- 자동 검색, 다른 국가·지표·기관, CSV/XLSX 내보내기, 단위·주기 변환, 시계열 개정 비교와 전체 시나리오 H는 이 보고서의 검증 범위가 아니다.
- World Bank 개별 데이터셋 이용·재배포 조건의 전면 검토가 완료된 것은 아니다. Gate A 통과는 배포·재배포 승인이 아니다.

보안·데이터 무결성 측면에서 네트워크는 명시 설정을 요구하며 고정 HTTPS 경로·TLS 검증·리다이렉트 거부·호출/응답 크기 제한을 유지한다. raw와 manifest는 새 경로에 저장하고, 기존 SQLite schema 버전과 과거 Task JSON을 변경하지 않는다.

## 검토 및 체크포인트

Product Owner가 범위·검증 결과·이용 조건 한계를 검토해야 한다. 초기 프로젝트 체크포인트는 `2c4e11f`에 70개 파일로 기록했다. `.gitignore`에 따라 `data/catalog.sqlite`, `data/raw/**`, 생성된 live JSON은 커밋에서 제외되어 로컬에 남는다. 병합 전 사람 검토가 필요하다.
