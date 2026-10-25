# API·공식 파일의 데이터셋 실행 계약

Iteration 29는 기관 client를 공통 데이터셋 선택·실행·원본 보존·검증 read-back 계약으로 연결한다. 일반 자연어 workflow와 정규화 관측치 DB는 아직 연결하지 않았다. 아래 7개 profile만 지원하며 전체 기관·전체 데이터셋 지원을 뜻하지 않는다.

| Profile ID | 기관 / 방식 | 선택 범위와 검증 |
|---|---|---|
| `fred.gdp` | FRED / API v1 | GDP의 명시적 관측치 한 page. start/end, limit/offset, 선택 real-time 기간. 전체 이력·원 통계기관·단위는 별도 metadata 확인 필요. |
| `census.acs2023.population` | Census / API | `2023/acs/acs5`, NAME·B01001_001E 고정, geography 등 predicates는 기존 client가 검증. null·음수 sentinel·문자열 보존. |
| `bls.unemployment` | BLS / API v1 | LNS14000000, 요청 연도 범위. 무키 v1만 사용. |
| `bls.cpi` | BLS / API v1 | CUUR0000SA0, 요청 연도 범위. M13 Annual을 월로 바꾸지 않음. |
| `tic.mfh.history` | Treasury TIC / 공식 CSV | MFH 역사 파일 전체. 반복 month/year header block·집계·각주 보존. 단위 billions of dollars. |
| `tic.treasury_holdings.2023_01` | Treasury TIC / 공식 CSV | 확인한 Table 3D January 2023 snapshot. 최신자료 보장 아님. 단위 Millions of dollars, 지역·합계·memo 보존. |
| `boe.bank_rate` | Bank of England / 공식 CSV | IUDBEDR, CSVF=TN, 최대 366 inclusive days, 원 보고 날짜만 검증. 단위·주기 미확정, 달력 채움·월말 정렬 없음. |

## 구성요소와 확장 위치

`discovery/datasets.py`는 version·SHA-256·공식 문서·고정 식별자·결측 token을 가진 immutable profile registry다. 사용자 요청이 endpoint, series, parser를 교체할 수 없다. 새 데이터셋은 profile 및 해당 family의 fixture/validator를 함께 추가한다. API가 먼저인 원칙을 유지하되, API 문서 미확인을 API 부재로 해석하지 않는다. 파일 경로는 별도 명시 선택이며 API 실패를 파일 다운로드로 자동 전환하지 않는다.

`connectors/dataset_bindings.py`는 고정 선택을 각 기관 client 요청으로 변환한다. `connectors/official_files.py`는 검토된 exact host/path/query의 TIC 2개·BoE 1개 CSV만 허용한다. 공통 `BoundedHttpTransport`의 network opt-in, TLS, redirects 금지, trust_env=False, 5/20초 timeout, stream 경과시간 30초·8 MiB 제한을 재사용한다. 자동 재시도·일일 호출량 scheduler는 없다. BoE 범위 제한은 프로젝트 예산이며 기관 최대 한도 주장도 아니다.

`ingestion/datasets.py`는 profile→binding→archive→validator→receipt를 연결한다. `ingestion/dataset_validators.py`에 출처별 구조 검사를 둔다. 기존 API clients가 JSON envelope·선택·기간을 먼저 검증하며 파일은 완료된 raw를 먼저 저장한다. 파일 구조 변화는 `needs_review`로 남기고 관측치 수집 성공으로 승격하지 않는다. JSON client가 반환 전에 거부한 잘못된 HTTP/envelope는 이 collector가 raw 보존하지 못한다. HTTP 실패·HTML 로그인 페이지·크기 초과도 완성 파일로 저장하지 않는다.

`storage/api_responses.py`는 파일 bytes와 request manifest를 기관별 write-once 폴더에 보존한다. 함수 이름은 기존 호환성을 위해 유지했다. JSON은 redacted payload의 canonical UTF-8이며 원 HTTP bytes가 아니다. CSV는 Requests content decoding 이후 entity bytes이며 원 행·결측을 수정하지 않는다. CSV revision header ETag/Last-Modified는 제공될 때만 남긴다. 헤더만으로 immutable vintage를 보장하지 않는다. API provider와 file provider를 구분한다.

`storage/datasets.py`는 같은 폴더에 `dataset_validation.json`을 배타 생성한다. 전체 profile snapshot·version/hash, safe 요청 조건, raw/manifest 경로와 hash, 검증 결과·범위·fixture 증거를 남긴다. `SavedDatasetArtifact`의 pinned hash로 세 파일을 read-back한다. 이후 registry가 바뀌어도 저장한 snapshot을 조용히 재해석하지 않는다. Hash는 우발적 변경 검출용이며 외부 서명이나 악의적인 전면 교체 방지를 뜻하지 않는다. pin 참조는 호출자가 보존해야 한다. 알려진 키가 파일 본문에 나타나면 원본을 수정하는 대신 보존을 거부한다. 실제 `.env`는 이 검증에서 읽지 않는다.

## 실행 예

```python
from pathlib import Path
from macro_data_platform.config import Settings
from macro_data_platform.ingestion.datasets import DatasetCollector
from macro_data_platform.storage.datasets import read_dataset_artifact

# 실제 호출은 별도의 live 준비·budget/권한 검토 후에만 network_enabled=True로 설정.
settings = Settings(Path.cwd())
collector = DatasetCollector(settings)
# saved = collector.collect("tic.mfh.history", {})
# receipt, raw = read_dataset_artifact(settings, saved)
```

재현 가능한 offline 실행:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.venv\Scripts\python.exe scripts/verify_dataset_paths.py --fixture
.venv\Scripts\python.exe -m pytest tests/test_dataset_paths.py -p no:cacheprovider -ra
```

스크립트는 실제 HTTP를 차단하고 synthetic key·합성 fixture만 사용한다. 프로젝트 `data/raw/api/<institution>/<uuid>/`에 원본·manifest·receipt를 만들고 `reports/iteration_29_offline_*.json`에 검증 참조를 기록한다. `contract_validated`는 이 source 구조 검사 통과만 뜻하며 live·통계 의미·정규화·전국가 완전성 검증이 아니다.

## 공식 파일 조사 근거와 해석

- [Treasury 공식 securities 배포 목록](https://home.treasury.gov/data/treasury-international-capital-tic-system-home-page/tic-forms-instructions/securities-b-portfolio-holdings-of-us-and-foreign-securities)의 링크와 redirect 목적지를 확인해 [MFH history CSV](https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfhhis01.csv), [Table 3D CSV](https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt3d.csv)를 등록했다. 표 구조 열람은 공식 문서/파일 조사이며 repository live ingestion이 아니다. TIC 보유액은 한 국가의 총부채나 민간부채와 동의어가 아니다.
- [BoE database help](https://www.bankofengland.co.uk/boeapps/database/help.asp)는 CSV download query·CSVF=TN·날짜/SeriesCodes 사용을 설명한다. 공식 DB의 IUDBEDR 식별을 조사했다. 2자리 연도는 요청 기간 안의 세기로만 해석하며 현재 시스템 연도의 pivot을 쓰지 않는다. 날짜가 없다고 0·이전값·월말로 채우지 않는다.
- TIC·BoE의 일반 API 상태는 계속 unconfirmed, registry authentication은 unknown으로 둔다. 파일 링크 공개만으로 전 기관 라이선스·재배포 권한이나 무제한 수집을 보장하지 않는다. 실제 수집 전 통계별 이용 조건을 확인한다.

원 API 문서는 [FRED](FRED.md), [Census](CENSUS.md), [BLS v1](BLS.md), 보존 계약은 [archive 명세](API_RESPONSE_STORAGE.md), 결과는 [Iteration 29](../history/ITERATION_29_REPORT.md)를 따른다.
