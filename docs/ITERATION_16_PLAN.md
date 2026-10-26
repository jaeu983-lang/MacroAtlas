# 16회차 기획안 — 비API 대용량 자료 분류·인계

상태: 제한 범위 구현·로컬 검증 완료. 실제 구현 경계는 ITERATION_16_REPORT.md 참조. 사용자 추가 지시로 CSV 출력보다 우선한다.

## 동작 원칙

비API 파일이 아래 조건 중 하나에 해당하면 현재 엔진은 본문 다운로드·압축 해제·전체 parsing·
정규화를 진행하지 않고 별도 대용량 엔진 인계 대상으로 영속 등록한다. 발견 가능한 시점부터 중단한다.
HTTP로 받는 TXT/CSV/ZIP도 비API 파일에 포함한다. API pagination·query chunking은 별도 정책이다.
이미 받은 원본은 삭제·변형하지 않고 참조로 남긴다. 별도 엔진은 아직 없으므로 등록 후 자동 실행하지 않는다.

## 초기 분류 기준

현재 parser 상한을 기준으로 구현한 정책이다. 사용자 표현인 ‘이상’을 적용해 경계값도 인계한다.
이전 코드의 일부 초과(>) 조건도 경계값 포함(>=)으로 변경했다. 실제 검증과 후속 보완은 Gate 재검증 보고서를 따른다.

| 측정 항목 | 인계 기준 | 확인 시점 |
|---|---|---|
| 다운로드/로컬 원본/선택 ZIP member 크기 | 16 MiB 이상 | Content-Length·stat·ZIP directory, 미상일 때 bounded stream |
| ZIP 전체 압축 해제량 | 64 MiB 이상 | directory 검사, 실제 해제 시에도 한도 유지 |
| ZIP member 개수 | 1,000개 이상 | directory |
| ZIP 압축 해제 비율 | 200배 이상 | member별 크기 정보 |
| 데이터 행 | 100,000행 이상 | 신뢰할 수 있는 metadata 또는 제한된 탐색 |
| 열 | 1,000열 이상 | header/worksheet dimensions |
| 전체 셀(헤더 포함) | 500,000개 이상 | dimensions 또는 제한된 탐색 |
| 필드 길이 | 1,000,000 문자 이상 | 제한된 탐색 |

metadata가 없거나 부정확하면 전체 로딩으로 크기를 알아내지 않는다. bounded 탐색으로만 판단하고
판정 불가는 `inspection_required`로 보류한다. ZIP 경로 탈출·암호화·손상·의심스러운 압축 비율은
security review도 필요하며 대용량 엔진으로 보내도 자동 해제하지 않는다. XLSX 내부 ZIP에도 압축 가드를 적용한다.

## 영속 인계 목록 계약

현재 엔진이 SQLite에 `deferred_non_api` 목록과 append-only 판정 이력을 저장한다.
기관·dataset/table·credential-free URL·local raw/manifest 참조·task/stage ID·발견 시각·측정값·
단위·판정 기준 버전·reason code·검사 중단 지점·원본 hash(이미 계산된 경우)·상태를 보존한다.
미측정값은 null이며 hash를 얻으려고 큰 파일 전체를 읽지 않는다. URL query의 토큰은 저장하지 않는다.
중복 키는 source identity+request/parser scope+정책 버전이며 새 관측은 이력으로 추가한다.
상태는 deferred/inspection_required/security_review/handed_off/resolved. 이 상태들은 source change 판정과 분리한다.
등록은 수집 성공이나 Gate C 통과가 아니다. 원자료 변경 가드를 우회하지 않는다.

## 대상 목록

초기 확인 대상은 `NON_API_DEFERRED_CATALOG.json`에 기록한다. 현재 실제 확인된 것은 BIS GLI flat ZIP 한 건이다.
다른 기관은 크기 증거 확보 전 대상이라고 추정해 등록하지 않는다. URL 발견 단계에서도 크기가 확인되면
본문 요청 없이 등록한다. 현재 엔진의 용량 차단 시 SQLite 자동 등록을 구현했다. 이 JSON은 초기 문서 목록이며 runtime DB로 자동 이관하지 않는다.

## 수용 조건

1. 각 기준 직전/정확한 경계/초과에서 실행·인계가 정책과 일치한다.
2. 큰 Content-Length는 본문 요청/읽기 없이, 큰 로컬 stat은 read_bytes 없이 등록된다.
3. 미상·허위 크기와 ZIP metadata가 실제 상한을 우회하지 못한다.
4. 재시작 후 같은 인계 목록·판정 이력이 유지되고 중복 수집·자동 resume가 없다.
5. 읽기 전용 목록/상세 CLI로 이유·측정값·원본 위치·인계 상태를 확인한다.
6. 대용량 엔진 실행은 별도 명시적 인계 단계로 남긴다. 작은 정상 파일과 API 수집 경로의 회귀를 검증한다.

구현 순서: 정책·typed reason → preflight/stream 가드 → SQLite 목록·이력 → 엔진/transport 연결 →
목록 CLI → 경계·무실행·재시작 검증 → 보고서·문서·commit/push.

후속 CSV 계획은 `CSV_EXPORT_FOLLOWUP_PLAN.md`에 보존했다.

## 후속 엔진 인계 연결

ENGINE_CONNECTIONS.md의 실제 연결표와 미구현 bridge를 기준으로 후속 작업을 한다.
현재 deferred record를 자동 실행 queue로 해석하지 않으며 불변 event/version·원본 snapshot·부모/자식 task
연결·중복 방지 transaction을 먼저 구현한다.
