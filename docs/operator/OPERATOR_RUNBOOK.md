# MacroAtlas 운영자 runbook

**대상:** 로컬 설정, API credential, 요청 예산, 실기관 호출, 결과 저장과 장애 처리를 담당하는 운영자
**주의:** 이 문서는 명령과 credential 절차를 담습니다. API key 값을 대화·소스·로그·보고서·XLSX에 붙여 넣지 않습니다.

## 현재 운영 가능 범위

- 기관 목록: 21개 profile. 공식 API 문서 확인 15개, 문서 명세 미확인 6개, 공식 no-API 확인 0개로 기록돼 있습니다. 미확인은 API 부재가 아닙니다.
- MacroAtlas live ingestion 확인: World Bank Indicators API의 USA/WDI/GDP 고정 요청 경로.
- BEA/e-Stat: 제한된 JSON client와 mock 검증. 실제 workflow 연결과 실기관 인증·수집은 미검증.
- FRED·Census·BLS v1: 기관별 요청·응답 계약 및 synthetic fixture 파일 저장·read-back 검증. BLS는 무키 v1만 사용하며 실기관 호출·일반 workflow는 미검증.
- MacroAtlas 일반 자연어 UI와 XLSX exporter: 아직 제공되지 않습니다.

기관별 근거는 [기관 카탈로그](reference/INSTITUTION_CATALOG.md)와 [API 조사](reference/INSTITUTION_API_AUDIT.md), 실행·승인 주기는 [OPERATING_PLAN.md](OPERATING_PLAN.md)를 봅니다.

## 로컬 API key 설정

저장소 루트의 .env는 일반 텍스트입니다. Git 제외 여부를 확인하고 PC 안에서만 관리하세요. .env.example, 코드, fixture, 대화, terminal transcript에 실제 키를 넣지 않습니다.

```ini
BEA_API_KEY=<발급받은 BEA UserID>
ESTAT_APP_ID=<발급받은 e-Stat Application ID>
FRED_API_KEY=
CENSUS_API_KEY=
BLS_API_KEY=
MACROATLAS_NETWORK_ENABLED=false
```

현재 설정 로더는 .env와 프로세스 환경변수를 읽으며 프로세스 환경변수가 우선합니다. key는 repr/log에서 숨기고 네트워크 기본값은 false입니다. 값을 설정해도 connector의 live 지원이 생기지 않습니다. BEA/e-Stat client의 현 상태에서 실기관 요청은 검증된 사용 경로가 아닙니다.

추가 키의 공식 발급 링크와 21개 source별 필요성은 [API_KEYS.md](API_KEYS.md)를 따릅니다. FRED/Census는 Settings의 키를 사용하며 BLS v1은 키를 사용하지 않습니다. 세 client의 파일 저장은 공통 helper를 명시적으로 호출하는 방식이며 live·일반 workflow 검증은 별도입니다. [합성 예시 생성](../developer/history/ITERATION_28_REPORT.md)은 `python scripts/verify_rest_adapters.py --fixture`로 실행합니다.

## 확인된 World Bank live canary

아래 스크립트는 외부 HTTPS 요청을 실제로 보냅니다. 기관 약관, 네트워크 상태, 사용자 승인, 공통 platform gate와 해당 source gate를 확인한 뒤 고정된 범위로만 실행합니다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\verify_worldbank.py --live
```

Gate A 저장·hash·검증까지 확인하는 모드도 외부 요청을 합니다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\verify_worldbank.py --live --gate-a
```

기간·지표·국가를 임의로 확장하지 않습니다. 요청 전 예산, 이용 약관, source gate를 확인합니다. 2시간/6시간 시험은 canary, 저장/read-back, 중단·재개가 검증된 다음 별도 운영 승인을 받습니다.

## 결과와 증거 확인

기본 data 경로에는 raw 응답, 요청 manifest, SQLite 작업 카탈로그가 저장됩니다.

- raw: data/raw/worldbank/<작업 ID>/response.json
- manifest: 같은 디렉터리의 request.json
- SQLite: data/catalog.sqlite
- 실검증 결과: reports/ 아래 iteration/alignment live JSON

보고서의 기관·지표·기간, 성공/실패, raw size/hash, 저장 위치, validator 결과를 manifest와 비교합니다. 새 실행은 기존 raw를 조용히 덮어쓰면 안 됩니다. 결측을 0으로 해석하지 않습니다. 재배포 권한은 source 이용 약관과 attribution을 따릅니다.

## 장애 대응

| 상황 | 운영자 조치 |
|---|---|
| 401/403/auth | 호출을 멈추고 API key 설정 위치와 공식 권한 안내를 확인. key 값을 복사해 보내지 않음 |
| 429/rate limit | 재시도 폭주를 멈추고 provider limit과 요청 예산을 확인 |
| timeout/일시 실패 | 설정된 재시도 횟수와 retryable 상태를 확인하고 중단/재개 |
| schema drift | raw 응답을 보존하고 connector 담당자에게 fixture 재현 자료 제공 |
| quality failure | 결과를 분석에 제공하지 말고 source metadata와 검증 사유 검토 |
| provenance/hash/저장 무결성 이상 | 영향받은 run과 export를 멈추고 raw·manifest·상태를 보존. 복구 검증 전 재개하지 않음 |
| API docs 미확인 | endpoint를 추측하거나 scraping으로 우회하지 말고 조사 task로 돌림 |

네트워크·키 범위를 바꾸거나 새로운 source를 live 실행하기 전에는 해당 기관 gate 및 [운영 계획](OPERATING_PLAN.md)을 확인하세요. 장시간 시험은 중단 조건, 요청 cap, 재개 기준과 보고 위치를 미리 기록합니다.

## 사용자 확장 모듈 오류 — 향후 설계, 현재 미지원

사용자가 제공한 Python 확장을 실행하는 기능은 아직 없습니다. 이 기능이 구현되기 전에는 사용자 코드를 MacroAtlas workflow에 끼워 넣거나 main process에서 `import`/실행하지 않습니다.

향후 확장 기능이 준비되면 운영자는 다음 원칙을 적용합니다.

1. run에 고정된 extension ID/version/hash와 hook을 확인합니다.
2. syntax·contract·fixture 오류는 extension stage에서 멈추고 입력·raw evidence를 보존합니다. 사용자가 수정한 새 version은 새 실행 또는 검증된 checkpoint 재개로만 적용합니다.
3. 사전 동의된 fallback이 없으면 extension 오류 뒤 core 동작으로 조용히 전환하지 않습니다.
4. extension이 raw, provenance, permission boundary를 훼손할 가능성이 있으면 export와 계산을 막고 운영자/개발자에게 넘깁니다.
5. Python execution isolation, resource limit, per-user permissions이 실제 Windows 환경에서 검증되지 않으면 사용자 extension 실행을 켜지 않습니다.

Markdown의 link/format 오류는 자동검사와 편집 제안으로 처리할 수 있지만, 통계 정의·단위·기관 정책을 바꾸는 문구는 실행 권한처럼 취급하지 않고 개발자/통계 담당자 검토를 받습니다.
