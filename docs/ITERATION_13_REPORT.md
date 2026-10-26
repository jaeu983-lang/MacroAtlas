# 13회차 보고서 — 반복 패턴 분석과 검토용 제안

> 이 문서는 작성 당시 계획 또는 검증 결과를 보존하는 스냅샷입니다. 현재 구현 상태는 [구현 상태](IMPLEMENTATION_PLAN.md), 다음 순서는 [제품 로드맵](ROADMAP_2026_10_26.md), 현재 지원 경로는 [사용자 안내서](USER_GUIDE.md)를 확인하세요. 아래의 당시 판정·수치는 수정하지 않습니다.

## 상태와 범위

13회차 로컬 구현·검증을 완료했다. Gate D 이후의 반복 오류·명시 피드백을 읽기 전용으로 분석해
범위별 `draft` 제안을 만든다. Gate C의 D-067 제한 범위 통과 판정은 변경하지 않았다. 실제 원자료
개정 및 자연 provider failure→resume 증거는 더 넓은 검증 범위에서 계속 `NOT_RUN`이다.
이 보고서 작성 시점에는 14회차/Gate E가 시작되지 않았다. 이후 Gate E 제한 범위 검수는
[`ITERATION_14_REPORT.md`](ITERATION_14_REPORT.md)에 기록했다.

`PatternAnalyzer`는 완료·실패·부분 완료·검토 필요 상태의 task에서 stage 상태, 오류 코드, 기관·엔진·
stage와 명시된 dataset/concept 범위만 읽는다. 조회는 SQLite read-only 연결이며, raw provider payload,
task 요청 원문, 성공 결과 payload, 비밀 필드는 결과 행으로 가져오지 않는다. 사용자 피드백은
`accepted` 상태의 `user_instruction`만 사용한다. 내용은 NFKC·공백 정규화 후 SHA-256 지문으로만 비교하고
보고서에는 원문을 포함하지 않는다. 일반적인 키·토큰·개인키 형태가 검출된 피드백은 제외한다.

오류·피드백은 기관, 엔진/버전, stage, 오류 코드/피드백 종류, dataset/concept 범위가 일치하고 서로 다른
task ID가 3개 이상일 때만 반복 후보가 된다. 한 task의 재시도는 독립 사례가 아니다. 모르는 범위 차원은
task별로 분리해 `insufficient evidence`로 센다. 서로 다른 승인 피드백 문구가 같은 명시 범위와 종류에
나타나면 자동 제안 대신 사람 검토가 필요한 충돌 후보로 보고한다. 반환 제안은 항상 `draft`이며 지식 승격,
task/feedback 변경, 코드 수정은 하지 않는다.

실행 예:

```sh
macro-patterns --project-root /path/to/MacroAtlas
```

저장소에 DB가 아직 없으면 DB 파일이나 스키마를 만들지 않고 빈 분석 결과를 반환한다. 한 번에 최대 500개
terminal task, 2,500개 stage/feedback record를 분석하고, 제안 20개 및 제안당 근거 10개를 반환한다.
상한 뒤의 결과가 있으면 `partial`과 truncation 표시를 낸다.

## 검증

- `tests/test_patterns.py`의 11개 결정적 fixture 검사가 서로 다른 3 task 반복, 단일 task 재시도,
  기관·dataset·engine 분리, unknown 범위, 선택된 workflow 범위 추출, accepted feedback 경계, 충돌,
  성공 반례, 비밀 형태 제외, 500/2,500/20/10 상한과 빈 DB CLI를 확인한다.
- 전체 `python -m pytest -o addopts='' -q`: **591 passed**.
- `python -m ruff check .`: 통과.
- `git diff --check`: 통과.
- 외부 네트워크와 실제 provider를 사용하지 않았다.

## 합성 규모 측정

Linux x86_64 (`Linux-6.18.55-x86_64-with-glibc2.41`), Python 3.12.14, SQLite 3.53.1에서
`scripts/benchmark_iteration_13.py --repeats 30`을 실행했다. 자료는 같은 fingerprint를 반복하는
합성 stage 결과이며, 각 입력 크기에서 warm local SQLite latency 30회와 Python allocation 측정 5회를
별도로 수행했다. 논리 바이트는 조회해 온 메타데이터 field의 UTF-8 크기 합으로 실제 디스크 I/O나 RSS가
아니다.

| 입력 stage records | 상태 | 읽은 task / record | 논리 bytes | p50 / p95 | 최대 Python allocation | 범위 적합 후보 |
|---:|---|---:|---:|---:|---:|---:|
| 100 | complete | 10 / 100 | 22,100 | 5.113 / 5.448 ms | 215,561 bytes | 1 / 1 |
| 1,000 | complete | 100 / 1,000 | 221,000 | 45.653 / 51.023 ms | 2,110,619 bytes | 1 / 1 |
| 5,000 | partial | 500 / 2,500 | 565,000 | 125.960 / 134.287 ms | 5,484,768 bytes | 1 / 1 |

5,000건의 부분 결과는 설정된 2,500 record 상한에서 의도한 동작이다. 이 기준 환경의 bounded run에 대한
참조 예산을 warm p95 150 ms, 최대 traced Python allocation 8 MiB로 정했다. 이는 측정 환경의 회귀 기준이며
다른 기기나 실제 기관 workload의 성능 보증은 아니다. X09는 synthetic fixture 범위에서 PASS이며 실제
운영 이력의 반복 패턴이나 provider 장애를 검증한 것으로 해석하지 않는다.

## 한계와 후속

- 사용자 교정은 의미 유사도를 추론하지 않고 정규화된 문구가 같은 경우만 묶는다. 누락된 scope는 합치지
  않으므로 충분히 구조화되지 않은 피드백은 반복 제안이 되지 않는다.
- 비밀값 감지는 흔한 키·토큰 형식에 대한 보수적 필터다. 분석기는 원문을 반환하지 않지만, 알려지지 않은
  형식까지 완벽히 식별하는 비밀 탐지기로 간주해서는 안 된다.
- 반복 후보는 원인·위험의 확정이 아니다. 실제 변경 코드는 다음 회차에서 별도 회귀 검증과 인간 승인 없이
  생성·승격되지 않는다.
- Gate C는 검증된 경로에 한해 **제한 범위 통과** 상태다. 자연 원자료 개정 및 자연 장애 후 재개라는
  미해결 증거 범위는 그대로 `NOT_RUN`이며, 본 회차의 합성 검증은 이를 대체하거나 Gate C 범위를
  확대하지 않는다. 상세 원인은 `docs/GATE_C_REVIEW_2026_10_26.md`의 현행 판정을 따른다.
