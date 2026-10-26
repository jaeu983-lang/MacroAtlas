# 16회차 — 비API 대용량 분류·인계

구현: 원본 stat/제한 읽기, ZIP directory 및 member 크기·비율·개수, CSV 행·열·셀·필드,
스프레드시트 dimensions 사전 검사를 추가했다. HTML/기타 parser 한도는 bounded parser가 멈춘 시점에
inspection_required로 영속 등록한다. 모든 검사가 metadata만으로 완료되는 것은 아니다.
HTTP Content-Length와 stream 용량 경계는 현재 공식 TIC/BIS transport에 연결했다. 임의 URL download 기능은 없다.

SQLite deferred_non_api와 append-only event 목록은 scope/policy로 중복을 묶고 task/stage와 측정값을 보존한다.
`macroatlas deferred`는 최대 100개 최신 레코드를, `macroatlas deferred ID`는 해당 ID의 최근 100개 이력을 조회한다.
한도에서 NEEDS_REVIEW로 중단하며 정상 수집·Gate C 통과로 승격하지 않는다. API 엔진은 이 정책 적용 대상이 아니다.

별도 대용량 엔진·자동 인계 실행·목록 상태 변경은 구현하지 않았다. 원본 hash는 크기 확인을 위해 새로 계산하지 않는다.
이미 받은 파일은 inbox/raw에 보존한다. 보안 검토 대상은 자동 해제하지 않는다.

검증: 전체 pytest 612개, Ruff 통과. 로컬 oversized stat은 파일을 열지 않는지, 정확한 열 경계,
정상 소형 파일, SQLite 재시작 후 중복 제거·이력 보존을 검증했다. Windows CI 결과는 이 로컬 검증에 포함하지 않는다.

향후: 제한된 목록 pagination·상태 변경 및 별도 엔진의 명시적 인계 계약을 별도 회차에서 구현한다.
