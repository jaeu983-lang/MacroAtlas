# 14회차 보고서 — Gate E 최종 검수와 제한 범위 v1 안내

기준일: 2026-10-26  
판정: **Gate E 통과 — 제한 범위 로컬 v1 검토**. 이 판정은 현재 문서화한 지원 범위와 실행 환경에 한정한다.
일반 기관 지원, 서비스 publish, main 병합 또는 배포 승인을 뜻하지 않는다.

## 실행 및 수정

`python scripts/verify_worldbank.py --live --gate-a`로 사용자 안내의 대표 절차를 재현했다. 첫 시도
task `84a1afd9-4b56-454f-96ea-f6e59f245afc`는 `TRANSIENT`로 끝났다. 네트워크 정책은
`http://proxy:8080` sidecar를 요구하지만 `WorldBankTransport`가 `Session.trust_env=False`로 직접 연결을
시도해 설정된 프록시를 사용하지 않은 것이 원인이었다. HTTP/API 응답 본문은 저장되지 않았다.

커넥터가 `.netrc`와 암묵 자격증명 검색을 계속 끄면서 `HTTP_PROXY`/`HTTPS_PROXY` 및 소문자 fallback을
요청별로 전달하고 `REQUESTS_CA_BUNDLE`/`CURL_CA_BUNDLE`을 TLS `verify` 설정으로 전달하도록 고쳤다.
redirect 거부, TLS 검증, timeout, 크기 상한, 자동 재시도 없음은 유지했다. 환경 변수 경로 선택과
자격증명 비사용을 mocked test로 검증했다.

같은 명령의 두 번째 실행 task `4e2650a0-de72-4e6a-99a8-7b38f7dd7e8a`는
2026-10-26 13:01:50 UTC에 완료됐고 `live_path_passed=true`다. 고정 요청은 World Bank WDI source 2,
USA, `NY.GDP.MKTP.CD`, 2020–2022였다. HTTP 200 응답에서 3개 연도 관측치를 받아 raw 724 bytes,
SHA256 `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1`을 저장했다. 해시는
Gate A의 이전 capture와 같아 실제 원본 변경은 관측되지 않았다. 이번 task의 비교 필드는
`first_observation`이므로 이를 엔진의 cross-run revision 판정으로 해석하지 않는다. 품질 검증은
`passed`, issue 0, 누락 기간 0이었다. 원문에서 단위·주기를 확정할 수 없어 `null`/unknown 경고를
유지했고 경제 이상치, revision history, cross-source equivalence는 검사하지 않았다.

새 응답은 `data/raw/`와 실행 JSON 보고서 `reports/iteration_04_live_ea9e089c2a014c178e8f2f9be69f5749.json`
아래에 있다. 이 로컬 산출물은 `.gitignore` 대상이다. BOJ D-072/D-073 실측은 metadata/data 응답
smoke 증거에만 추가되며 Gate C 범위·판정은 바꾸지 않는다.

## Gate E 대표 시나리오 결과

전체 A–H 및 X01–X09 결과는 [`REFERENCE_SCENARIOS.md`](REFERENCE_SCENARIOS.md)의 Gate E matrix에
기록했다. World Bank 고정 경로의 live 정상 실행, simulated 503의 durable resume, source change의
controlled-copy 분기, 명시 피드백·반복 제안의 인간 검토 경계를 재확인했다. IMF, BEA, ECB/Eurostat,
중국 기관과 여러 부분 경로는 `BLOCKED`/`PARTIAL`로 명시했다. 제한 경로의 성공을 기관 전체 지원으로
확대하지 않는다.

## 사용자 산출물

- [`USER_GUIDE.md`](USER_GUIDE.md): 설치, 고정 수집 명령, 결과 경로, 키 정책, 오류·resume 및 부분 지원
  경계를 작성했다. Codex 실행 요청과 제품 자체 채팅 UI를 구분했다.
- [`MacroAtlas_User_Guide.pptx`](MacroAtlas_User_Guide.pptx): 같은 명령·경로·기관 상태를 반영한 10장 안내.
  LibreOffice로 10페이지 PDF 변환을 확인하고 모든 슬라이드 렌더를 육안 검토했다.
- 대표 절차 live 실행과 `feedback_cli --help`, read-only `pattern_cli` 실행을 현재 Linux managed
  환경에서 재현했다. Windows 설치 단계는 이 Linux 환경에서 실행하지 않았으므로 Windows 전용
  설치·실행을 실측했다고 주장하지 않는다.

## 검증

- `python -m pytest -o addopts='' -q`: **592 passed**.
- `python -m ruff check .`: 통과.
- `git diff --check`: 통과.
- `tests/test_worldbank.py`: **58 passed**. 명시 프록시·CA 사용, `trust_env=False`, TLS 검증,
  1회 요청 및 안전한 오류 경계를 fixture로 확인했다.
- 설치 안내의 CLI 모듈 도움말과 실제 live 검증 명령을 실행했다. PPTX는 10 slide package로 열리고
  렌더됐다.

## 보안·비용·복구 검토

Gate E live 재현은 두 번 시도됐다. 첫 시도는 프록시 미사용으로 HTTP 응답 전에 끝나 raw를 남기지
않았고, 수정 후 같은 단일 요청 하나가 성공했다. 성공 요청은 비밀키가 필요 없는 공개 World Bank
경로를 사용했다. 커넥터는 TLS를 검증하고 redirect를 거부하며 5/20초 timeout, 1 MiB 상한,
요청당 자동 retry 0회를 유지한다. 저장소 내 `.env`를 읽지 않고 키 또는 proxy 값을 출력하지 않았다.
기관별 과금이나 자료별 재배포 권한은 이 검토에서 확인하지 않았으므로 각 기관 약관·호출 한도를 따른다.

503 복구 증거는 simulated HTTP fixture이며, 자연 발생한 provider failure→resume은 여전히
`NOT_RUN`이다. TIC/BIS의 다음 실제 source revision도 미관측이다. 이 미해결 항목은 Gate C의 제한
범위 판정 안에서 제외됐고 그대로 공개한다.

## 종료 및 통합 경계

Gate E는 문서화된 제한 범위의 로컬 검토로 통과했다. 이 Linux 실행 환경에서 World Bank 고정 경로와
설명서 절차가 재현됐고, 지원 경계·오류·변경·피드백 evidence가 명시됐다. 일반 Windows 배포, 비지원
기관의 end-to-end 실행, 자연 live revision/recovery는 이번 판정 밖이다. main 병합 전 사람의 검토가
필요하며 실행 환경 publish는 하지 않았다. 이 회차 변경은 task branch commit으로 보존되고,
검토 후 되돌릴 때는 해당 task commit을 `git revert`할 수 있다.

## 통합 및 병합 후 재검증 — 2026-10-26

후속 검토 PR [#1](https://github.com/jaeu983-lang/MacroAtlas/pull/1)은 기본 브랜치에 병합됐다.
merge commit은 `9986472f983a70aacc86209ee54883cca558c5e9`다. 병합된 checkout에서
`python -m pytest -o addopts='' -q` 592개, `python -m ruff check .`, `git diff --check`가 통과했다.

`python scripts/verify_worldbank.py --live --gate-a`도 다시 완료됐다. HTTP 200과 3 observations,
quality `passed`, `source_change_status=unchanged`를 확인했다. 이 검증은 기존 Gate A 경로 재실행이며
TIC/BIS natural revision이나 provider failure→resume을 뜻하지 않는다. 병합 후 검증으로 Gate C의
제한 범위와 Gate E의 문서화된 제품 범위는 바뀌지 않았다. 실행 환경 publish는 수행하지 않았다.
