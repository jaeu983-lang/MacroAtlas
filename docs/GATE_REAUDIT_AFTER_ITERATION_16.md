# 16회차 이후 Gate A–E 현행 재검증

기준일: 2026-10-26. 이 문서는 과거 실패를 재사용하지 않고 현재 checkout의 테스트·실측·코드 연결 여부를 기준으로 판정한다.
기준 구현은 0cf72a3에 이번 재점검 수정분을 적용한 상태다. 과거 회차 보고서는 당시 기록으로 보존한다.

## 판정

| Gate | 현재 확인 | 판정 및 범위 |
|---|---|---|
| A | World Bank USA GDP 2020–2022 CLI live task가 collect/validate 완료, 3 observations, quality passed. raw hash 대조 성공 | 기존 고정 경로 통과 재확인 |
| B | 전체 회귀에 후보 순위·불일치 차원 차단·명시 선택·workflow 계약 검증 포함. World Bank CLI가 confirmed workflow를 거쳐 live 완료 | 제한 범위 통과 재확인. 일반 자연어·전체 기관 검색의 구현 증거는 없음 |
| C | TIC/BIS column ZIP live 완료·unchanged·raw/normalized hash 확인. BOJ 단일 월 live 30행·11 null. BIS flat 보존 원본은 capacity 인계 성공 | 제한 범위 통과 재확인. flat의 처리 결과는 정상 deferral로 갱신. 자연 source revision/자연 transient→same-task resume은 이번에도 관측되지 않음 |
| D | 현재 test_knowledge_orchestration/knowledge/feedback 회귀에서 기관·범위 분리, 명시 선택에 따른 stage reuse와 충돌·stale 차단 통과 | 기존 제한 workflow에서 통과 재확인. 새 provider 전체에 일반화하지 않음 |
| E | 현재 구조화 CLI와 위 네 live 경로, capacity 목록·오류 가드 및 전체 회귀 검증 | 제한 범위 로컬 v1 판정 재확인. Windows 결과는 PR의 현재 커밋 CI로 별도 확인 |

## 현행 실측 증거

| 경로 | task | 결과 |
|---|---|---|
| World Bank GDP | 0f968a54-9855-439c-aaf2-bb7022fb5c8c | COMPLETED, 3행, quality passed, unchanged |
| BOJ FM08/FXERD01/202609 | 96f82a80-e84b-4b34-b282-204fb642afae | COMPLETED, 30행, 11 null, unchanged |
| TIC Table 5 | 2720605a-199c-4355-ab2c-d18a8cfa27a3 | COMPLETED, unchanged |
| BIS column ZIP | e8a57a1a-b24e-4c5f-a4e7-ea557cc6a762 | COMPLETED, unchanged |
| BIS flat ZIP 보존 원본 재처리 | 2797e6d0-a8ac-40e5-aca4-066991a7c2e1 | NEEDS_REVIEW + deferred, reason=cells, observed=500010, threshold=500000 |

네 live 실행 모두 저장된 raw hash와 실제 파일 hash를 대조했고, TIC/BIS 두 normalized hash도 일치했다.
World Bank hash는 SQLite collect stage에 보존된 digest를 사용했다. request.json에 hash가 있다고 가정하지 않았다.
BIS flat은 이번 네트워크 수집이 아니라 SHA256
`0ff64677d00c4c1a880816e401d0ea0802cb5924cab24b4987373320b95b0bb5` 보존 원본의 재처리다.
새 normalized 파일을 만들지 않고 원본 inbox 참조와 task/stage를 SQLite 목록에 보존했다.
상세 실행 산출물은 gitignored `reports/gate_reaudit_20261026.json`과 로컬 SQLite에 있다.

## 재점검 중 발견·수정한 결함

- CSV 한 개와 README가 함께 들어 있는 정상 ZIP을 preflight가 다중 자료로 오인했다. parser와 같은 supported-member 선택으로 수정했다.
- 손상된 XLS의 라이브러리 예외가 preflight 밖으로 나올 수 있었다. inspection_required로 안전하게 중단한다.
- deferred CLI가 읽기 전에 DB/tables를 생성했다. read-only 연결로 바꾸고 새 저장소에서 파일을 생성하지 않는지 확인했다.
- task CLI 요약에 non_api_deferral이 빠졌다. 인계 ID·이유·측정값을 표시한다.
- HTTP 크기 초과가 오류 문자열에 의존했다. FileCapacityFailure 타입으로 분리해 header/stream 중단 지점과 측정값을 기록한다.
- 파일 검사 후 다시 읽을 때 무제한 read_bytes를 사용했다. 두 번째 읽기도 상한을 두고 파일이 커지면 중단한다.
- 스프레드시트 sheet 선택을 기존 parser 기준과 맞추고 external links를 읽지 않도록 했다.
- 인계 URL을 저장소에서도 검증하고 목록은 최근 관측순으로 정렬한다. 로컬 symlink 입력은 거부한다.

전체 pytest **626 passed**, Ruff와 diff 검사 통과. 이번 추가 14개 회귀 사례는 ZIP 선택,
행·열·셀 경계, 압축 metadata 단계 중단, 손상 workbook, read-only CLI, 비밀 URL 거부,
영속 목록 정렬·이력, HTTP header/stream 한계와 인계 task·CLI 연결을 검증한다.
수정 전 612개 전체 시험도 통과했으므로 전체 시험 개수만으로 새 경로의 완전성을 주장하지 않는다.

## 남는 항목의 현행 분류

- BIS flat은 대용량 엔진 대기 대상이다. 현재 엔진의 파싱 오류를 계속 해결해야 하는 항목으로 취급하지 않는다.
- 자연 revision과 자연 장애 재개는 현재 live 결과에서 미관측이다. fixture 변경/503 시험과 별도로 남긴다.
- IMF·BEA·ECB/Eurostat·중국 기관의 광범위 수집은 현재 connectors/ 및 CLI에 해당 observation 경로가 없다.
  따라서 기관 서버가 여전히 차단했다고 주장하지 않고 현재 제품의 미구현 범위로 표시한다.
- BOJ는 이번 성공한 series/month로 지원한다. MOF/e-Stat·다른 BOJ series로 확대할 근거는 없다.
- 별도 대용량 엔진·CSV export는 현재 구현 목록에 없다. 이 항목들은 새 scope의 개발 작업이다.
