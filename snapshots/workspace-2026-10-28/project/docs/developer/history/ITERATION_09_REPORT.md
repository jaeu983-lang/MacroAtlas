# 09회차 완료 보고 — 파일 파서·대량 수집 계획

일자: 2026-10-25\
상태: 구현 및 로컬 검증 완료, 사람 diff 검토 대기\
기준 브랜치: `codex/iteration-07-08-discovery`\
커밋: 만들지 않음

## 구현한 사용자 가치

- 명시된 기관 접근 경로에서 CSV, TSV, 구분자를 지정한 TXT, ZIP 내 단일/선택 파일, HTML 표, XLSX, XLS를 안전 경계 안에서 파싱할 수 있는 경로를 추가했다.
- HTTP/API 원본 bytes는 그대로 보존하고 SHA-256, 수집 시각, 상태, metadata revision, 선택한 멤버·시트·구분자·HTML 표 번호를 manifest에 기록한다.
- ZIP 경로를 디스크에 추출하지 않는다. 입력 크기, 구성원 수, 압축 해제량·압축 비율, 행·열·셀 수를 제한한다. 모호한 표나 지원되지 않는 파일은 추측해 읽지 않고 검토가 필요하다고 처리한다.
- 대량 요청은 샘플 또는 전체 범위를 명시한 뒤 시리즈·국가·기간 블록으로 계획한다. 요청·관측치 예산을 강제하고, byte/시간 추정치는 근거가 없으면 미상으로 남긴다. 계획은 실행하지 않으며 확인 전 수집하지 않는다.

## 주요 변경 파일

- `src/macro_data_platform/ingestion/formats.py`: 경계가 있는 비실행형 표 파서와 원본 중복 보존 경고.
- `src/macro_data_platform/ingestion/bulk.py`: 명시적 샘플/전체 및 예산 제한 계획기.
- `src/macro_data_platform/ingestion/discovered.py`: 선언된 포맷 route, 원본·manifest 보존과 최소 파싱 연결.
- `src/macro_data_platform/metadata/models.py`, `src/macro_data_platform/discovery/series.py`: 파일 접근 선택 항목과 지원 포맷 route 연결.
- `tests/test_ingestion_formats.py`, `tests/test_ingestion_bulk.py`, `tests/test_series_discovery.py`: fixture 기반 파서·예산·route 검증.
- `pyproject.toml`: XLS BIFF reader 의존성 `xlrd>=2.0.1,<3` 선언.
- `docs/developer/IMPLEMENTATION_PLAN.md`, `docs/developer/history/DECISION_LOG.md`: 회차 상태·결정·검증 범위 기록.

## 테스트와 실제 결과

- 집중 parser/bulk/route 테스트: **72 passed in 7.79s**.
- 전체 pytest: **559 passed in 33.24s**.
- `ruff check .`: 통과.
- `git diff --check`: 통과. Git이 기존 LF 문서 파일의 다음 갱신 시 CRLF 변환을 알리는 경고는 출력했지만 whitespace 오류는 없었다.
- 모든 데이터 경로 확인은 로컬 fixture/mock이다. 공식 사이트 조사 및 live API/ingestion은 수행하지 않았다.

## 미검증 가정과 한계

- 프로젝트 venv에 `xlrd`가 없고 네트워크 접근이 허용되지 않아 실제 XLS BIFF workbook의 파싱은 실행하지 못했다. XLS 요청은 의존성이 없는 환경에서 unsupported로 표시되어 수집 전 차단된다. 배포/설치 환경에서 `pyproject.toml` 의존성 설치 후 별도 XLS fixture 검증이 필요하다.
- PDF 수치 추출, 범용 API 포맷 확장, XLSX 수식 계산, 파일 변환·분할 저장은 이 회차에서 구현하지 않았다. XLSX 수식은 계산하지 않고 거부한다.
- 대량 계획기는 실행되지 않는 계획 API다. 관측치 외의 byte/시간 예상치는 호출자가 단위 관측치 크기와 요청 시간 근거를 제공하지 않으면 미상이다.
- 실제 기관별 이용약관·자료 스키마·접근 가능성은 검증되지 않았다.

## 보안·데이터 무결성 영향

- 원본은 별도 raw 경로에 create-exclusive로 보존하고 파싱 과정에서 중복 행이나 중복 헤더를 제거하지 않는다.
- 결측을 0으로 바꾸지 않는다. XLSX 수식·오류, 외부 관계, 매크로, 비정상 ZIP/XML, 모호한 HTML 레이아웃은 임의 해석하지 않는다.
- 대량 계획 API는 어떤 네트워크 요청도 실행하지 않는다. 실제 수집 경로는 기존 명시 metadata 확인·사용자 확인·네트워크 설정 경계를 유지한다.

## 선행 조건과 사람 검토

- 09회차 로컬 검증 기준은 충족했다. 10회차 Gate C의 검증을 시작할 수 있다.
- Gate C 통과 전에는 11회차로 진행하지 않는다.
- 사람이 diff를 검토한 뒤 체크포인트/커밋 여부를 결정해야 한다. 이 보고 단계에서는 stage, commit, merge를 하지 않았다.
