# Iteration 29 — API·공식 파일 데이터셋 계약 (Gate T)

**결과:** PASS, 2026-10-25. API와 비API를 데이터셋별로 준비하는 한 회차를 수행했다. 전체 기관 live 완료를 뜻하지 않는다. Git 기준 HEAD `778ab412d3076aad4a37d6f3140b6ced54b56d26`, 기존 `codex/iteration-07-08-discovery` branch의 사용자 변경을 보존했다. stage·commit·merge·publish하지 않았다.

## 변경 파일과 목적

| 위치 | 변경 목적 |
|---|---|
| `discovery/datasets.py` | 공식 문서·고정 source/dataset·adapter/validator·결측 규칙·version/hash의 immutable registry 7개. |
| `connectors/dataset_bindings.py` | FRED GDP / Census ACS 2023 population / BLS v1 unemployment·CPI API 4개, TIC 2개·BoE 1개 파일 선택 연결. |
| `connectors/official_files.py` | TIC exact CSV 2개와 BoE IUDBEDR CSVF=TN 다운로드. 공통 bounded HTTP와 허용 query·날짜·크기·media 검사. |
| `connectors/http_transport.py` | 기존 보안·한도를 유지하며 선택 ETag/Last-Modified 반환. |
| `ingestion/datasets.py`, `ingestion/dataset_validators.py` | 공통 실행과 source별 검증 분리. CSV 변경은 원본 보존·needs_review, 관측치 정규화/수락 없음. |
| `storage/api_responses.py`, `storage/datasets.py` | CSV entity bytes·file provider·revision 보존, source 일치 검사, profile snapshot/hash와 검증 receipt 배타 저장·pinned read-back. |
| `discovery/source_registry.py` | TIC·BoE 부분 구현·기관별 fixture 표시. API unconfirmed/인증 unknown/live 미검증 유지. |
| `tests/test_dataset_paths.py`, `tests/fixtures/rest_api/*.csv` | 신규 52개 검사, 공식 구조를 참고한 명시적 합성 fixture 3개. |
| `scripts/verify_dataset_paths.py` | 실제 HTTP 차단·합성 설정만으로 7개 artifact 생성·검증·보고. |
| 제품·실행·아키텍처·기관 상태·archive 문서 | 현재 범위, 사용 방법, 미검증 경계 갱신. [실행 계약](../connectors/DATASET_CONTRACTS.md) 참조. |

API clients는 기존 12곳, 공식 파일 client 2곳을 별도로 추가했다. 21기관 상태는 제한 live 1 + API 부분 11 + 공식 파일 부분 2 + fixture 4 + 미구현 3이다. API 문서는 15 documented / 6 unconfirmed / 0 not_offered 그대로다.

## 검증

- 초기 dataset/archive/HTTP 회귀: **84 passed in 3.53s**. 이후 보안·날짜 회귀 5개 추가.
- 최종 전체: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -ra` — **815 passed, 1 skipped, 0 failed, 76.67초**. skip은 기존 `tests/test_official_api_credentials.py:155`, Windows symlink 생성 미지원. 성능 개선율은 측정하지 않았다.
- 변경 Python 11개 Ruff `--no-cache` 통과. `git diff --check` exit 0; 기존 파일 LF→CRLF 안내만 있었다.
- fixture script: **7/7 contract_validated**, 각 mock request 1회. raw·manifest·receipt 생성 후 read-back, 최종 코드로 저장된 7개를 다시 hash 검증. [원시 보고서](../../../reports/iteration_29_offline_777d9f70f81c4d58b501201deeabdb0f.json).
- 선택 override·unknown route·network off·HTTP 3xx/401/403/404/429/500·TLS/timeout·크기/media 제한, 키 비노출·fixture 증거 불일치·raw/manifest/receipt 변조·덮어쓰기·경로/profile pin 검사 포함.
- BoE 중복/범위 밖 날짜·잘못된 열·NaN·2자리 연도 leap day, TIC 반복 연도 block·단위·결측/0·집계 보존·다른 월 snapshot 변경 확인.

일반 sandbox의 프로젝트 raw 하위폴더 생성은 Windows WinError 5로 거부됐다. 저장소 내부의 합성 파일만 만드는 동일 스크립트의 한정 승인 실행으로 완료했다. 전역 권한·sandbox 설정은 변경하지 않았다. pytest는 일반 실행으로 완료했다.

## 사람이 열어볼 파일

모든 숫자는 합성 테스트 값이다. 같은 폴더의 `request.json`과 `dataset_validation.json`에 출처·요청·profile·검증 범위를 기록했다.

| Profile | Raw 예시 |
|---|---|
| FRED GDP | [JSON](../../../data/raw/api/US-02/483ded2b23fc4e2fa1781603c16ccea3/response.json) |
| Census population | [JSON](../../../data/raw/api/US-06/7d9ba97ccb484c5e80f205e5e57c9d10/response.json) |
| BLS unemployment | [JSON](../../../data/raw/api/US-05/30ffd13d105b486f965d5eb40931699c/response.json) |
| BLS CPI | [JSON](../../../data/raw/api/US-05/7dcf79a97a65400085d05076d26d9760/response.json) |
| TIC MFH history | [CSV](../../../data/raw/api/US-03/f029acc9f4774bd4a5c6e48b7aaf6376/response.csv) |
| TIC Table 3D Jan 2023 | [CSV](../../../data/raw/api/US-03/5e192b8cbe5a4d76b0875dfb6015ece9/response.csv) |
| BoE Bank Rate | [CSV](../../../data/raw/api/EU-04/2928521f4cf7474faf2ecd4a7c21c0ff/response.csv) |

## 한계와 다음 작업

공식 Treasury CSV의 canonical URL·표 구조 및 BoE download help/시리즈 식별은 웹 조사로 확인했다. [dataset 명세](../connectors/DATASET_CONTRACTS.md)에 공식 링크를 보존했다. 공식 파일 웹 열람과 repository live 수집은 다른 증거다. 이번 repository live 통계 요청 **0회**, 실제 `.env`/키 읽기·변경 없음. BLS는 무키 v1만 사용한다.

일반 대화 workflow·전체 데이터셋 discovery·정규화 DB·계산/XLSX·월말 정렬·국가 코드 매핑·자동 페이지 수집/재시도·일일 budget scheduler·장시간 live 시험은 제외했다. CSV 계약 통과는 통계 의미·방법론·전국가 완전성 검증이 아니다. TIC 보유액은 국가 총부채가 아니다. 등록 Table 3D는 2023-01 snapshot으로 최신을 보장하지 않는다. 알려진 키가 raw에 있으면 변형 저장 대신 거부한다. JSON은 sanitized canonical serialization이다. HTTP/JSON client가 반환 전 거부한 응답 raw는 이 collector가 보존하지 못한다.

새 dataset은 profile과 source validator/fixture를 함께 추가한다. API 우선은 유지하고 API 오류를 파일 경로로 자동 전환하지 않는다. 다음 후보는 Iteration 30 IMF 상세 route/auth 문서 gate이며 시작하지 않았다. 코드 통합·live 범위 확대에는 사람의 검토가 남는다.
