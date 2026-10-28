# Iteration 23 — 전기관 검증 준비 상태와 Max 작업 묶음

**Date:** 2026-10-25\
**Result:** Gate N PASS\
**Track:** C — 전체 source readiness / offline test audit\
**Scope:** 사용자 지시에 따라 BIS 예시 하나가 아니라 21개 기관·서비스 전체를 live 검증 목표로 재정의했다. Luna Max 작업 크기에 맞춰 API 계열별 batch를 설계하고 현행 offline suite를 재실행했다.

## 현행 source 상태

레지스트리의 21개 profile을 읽어 확인한 상태는 다음과 같다.

| 상태 | 수 |
|---|---:|
| 공식 API 문서 확인 | 15 |
| 공식 API 문서 미확인 | 6 |
| 부분 구현/클라이언트 | 3 — World Bank, BEA, e-Stat |
| fixture 전용 | 8 |
| source adapter 미구현 | 10 |
| 과거에 live 일부 경로가 확인된 기관 | 1 — World Bank USA/WDI/GDP 고정 경로 |

전체 21개 source는 API·fixture·mock·adapter·live 증거를 독립적으로 기록해야 한다. `documented`는 API가 동작한다는 증거가 아니고 `unconfirmed`는 API 부재를 뜻하지 않는다. 기존 API 감사와 기관 구현 상태표를 근거로 두되, 현재 조사에서 live/API 세부를 새로 시험하지 않았다.

## 전체 offline suite 실행

정확한 현재 workspace source를 선택하도록 repository `.venv` Python과 `PYTHONPATH=C:\Projects\MacroAtlas\src`를 사용했다.

```powershell
$env:PYTHONPATH = 'C:\Projects\MacroAtlas\src'
& '.venv\Scripts\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider
```

**결과: 625 passed, 1 skipped, 0 failed; 33.99초; exit code 0.** Skip 하나는 Windows 환경에서 symlink를 만들 수 없어 symlink protection 검사를 건너뛴 것이다. 이 suite는 offline fixture/mock와 코드 계약을 검증했으며, 21개 API에 네트워크 호출은 하지 않았다.

실행 초기에 시스템 PATH에는 `pytest`/`python` 명령이 없었다. `.venv`로 실행했을 때 editable package 경로가 현재 checkout이 아닌 OneDrive checkout을 가리켜 collection 오류 12개가 났다. `PYTHONPATH`를 현재 repository의 `src`로 지정한 최종 실행에서 전체 suite가 통과했다. 처음의 오류는 테스트 본문 실패가 아니며, 최종 재현 명령에 이 경로 조건을 포함했다.

## Max 기준 작업 분할

Max는 한 번에 21개 provider를 임의로 묶어 성공 선언하는 기준이 아니라, 동일 API family의 공통 구현과 source별 판정을 함께 추론하는 작업 기준으로 쓴다.

1. Iteration 23: 모든 기관 readiness와 offline full suite 재확인 — 완료.
2. 다음 batch: 기존 request/metadata contracts를 전기관 audit하고 공통 conformance test record의 최소 추가 항목을 확정한다. 기존 필드를 새로 작성하지 않는다.
3. SDMX batch: IMF, BIS, OECD, ECB, Eurostat, Bundesbank, INSEE의 shared transport/parser를 개발하되 기관별 flow/DSD/code-list fixture와 판정은 독립 유지한다.
4. 개별 REST batch: World Bank, BEA, e-Stat, Board/FRED, FRED/ALFRED, BLS, Census, BOJ를 공통 transport/retry harness로 지원하되 인증·series·provider lineage는 source별 확인한다.
5. API 미확인 batch: TIC, Bank of England, Japan MOF, PBOC, SAFE, China NBS의 대상 표별 API 사양을 조사한다. API 미확인이 API 없음이나 파일 허용을 뜻한다고 가정하지 않는다.
6. 모든 준비 source의 source-specific offline E2E와 readiness가 통과된 뒤 기관별 bounded live canary를 시작한다. 기관별 성공, 실패, credential/network/terms block을 하나의 전체 성공으로 합치지 않는다.
7. seeded offline random/soak 후 source-specific budget을 가진 승인된 ready source에서만 live 2h/6h 시험을 검토한다.

세부 roster, gate, required fields 및 최종 완료 정의는 [전기관 검증 프로그램](../testing/ALL_INSTITUTION_VALIDATION_PROGRAM.md)에 둔다.

## 변경 범위와 미실행 항목

- 계획·검증 문서만 수정/추가했다. 기관 adapter, fixture, workflow, orchestration 및 production code는 변경하지 않았다.
- live API, API key 또는 `.env` 값은 확인/호출/기록하지 않았다.
- 현재 live scope는 과거 World Bank 고정 경로 외에 검증되지 않았다.
- Gate N은 전기관의 live 통과가 아니라, 전기관 테스트 목표·현재 readiness·offline 기준 결과를 근거 있게 정리했다는 뜻이다.
- 변경은 stage/commit하지 않았으며 사람 diff review가 남아 있다.

## 다음 제안

Iteration 24 후보는 전기관 request/metadata contract gap audit 및 공통 conformance result schema이다. 그 audit 뒤 단일 통합 계약이 정해질 때만 구현한다. 이후 API 계열 작업은 각 source gate를 유지하고, 대상 endpoint·series·credential 준비 전에 live 요청하지 않는다.
