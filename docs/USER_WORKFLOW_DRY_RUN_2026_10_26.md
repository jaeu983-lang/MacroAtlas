# 사용자 업무 흐름 내부 dry run — 2026-10-26

## 범위와 판정

로드맵의 다음 단계인 “완료 자료 확인 → CSV 전달” 경로를 저장된 실제 task로 한 번 따라갔다. 이는
작성자가 수행한 오프라인 desk review이며, 독립적인 목표 사용자 사용성 조사나 Gate C 실측이 아니다.
실제 사용자 조사 없이 사용성 통과를 선언하지 않는다.

## 실행한 경로

네트워크 요청 없이 기존 task를 대상으로 아래 절차를 실행했다.

1. `macroatlas --help`, `collect --help`, `export --help`에서 지원 경로와 필수 인자를 확인했다.
2. World Bank task `0f968a54-9855-439c-aaf2-bb7022fb5c8c`의 저장 상태를 조회했다. `COMPLETED`,
   collect/validate 성공, 품질 통과, 2020–2022년 3행, 결측 0, 원본 변경 없음과 단위·주기 미상 경고를 확인했다.
3. BOJ task `96f82a80-e84b-4b34-b282-204fb642afae`의 저장 상태를 조회했다. `COMPLETED`,
   metadata/collect 성공, 품질 통과, 30행·결측 11, 원본 변경 없음을 확인했다.
4. 각 task를 새 `data/exports/iteration-21-walkthrough-*.csv` 경로로 export했다. 기존 파일을 덮어쓰지 않았고,
   생성한 CSV의 hash가 20회차에서 검증한 CSV hash와 각각 일치했다. Catalog DB와 원본을 수정하지 않았다.

| Provider | CSV 행 / 결측 | CSV SHA-256 | Provenance SHA-256 |
|---|---:|---|---|
| World Bank USA GDP | 3 / 0 | `2fdc918d810cd676eeb5ca0ea106fc991c461e8d37c4953e43442ed3c838f942` | `63ce35c271d3a09a86fb372f465fcd1e2716a7dd2da7590fe7c9223ffcdd984c` |
| BOJ FM08/FXERD01 | 30 / 11 | `e5021e8d8e6009ae2ecfcecdc74e0d4aaa940b78da42a6328864ee512abd1ee8` | `abd5aaebf7d76e599edaf09489c57bd2bc46890bbdc3cb5ad233d31dc17f3564` |

실행은 `python -m macro_data_platform.cli --project-root . status <TASK_ID>`와
`python -m macro_data_platform.cli --project-root . export <TASK_ID> --format csv --output <PATH>`로 했다.
실행 산출물은 Git에서 제외되는 `data/exports/`에 있다.

## 관찰과 한계

- 시작 명령, 상태 조회, 결과 저장은 사용자 안내서의 예시와 일치하며 고정 지원 경로 안에서는 오류 없이 끝났다.
- CLI는 상세 JSON을 출력한다. 분석가나 개발자는 task ID, 상태, 품질 경고, 결과 경로를 확인할 수 있지만,
  처음 쓰는 사람이 JSON만으로 다음 행동을 찾을 수 있는지는 독립적인 관찰이 필요하다.
- World Bank의 단위·주기 미상 경고와 BOJ의 11개 결측은 결과에 남았다. CSV에는 결측 상태가 분리되어 있다.
- 기존 성공 task만 재사용했으므로 새 수집, 자연 장애, 재개 동작을 시험하지 않았다. 합성 장애도 만들지 않았다.
- `data/catalog.sqlite`에는 63개 task가 있었다. 저장된 retryable stage는 한 건으로, 과거 World Bank task
  `84a1afd9-4b56-454f-96ea-f6e59f245afc`의 기록이었다(부모 task `FAILED`, collect stage
  `FAILED_RETRYABLE`, 1회 task attempt, `Retry-After` 없음). TIC/BIS watch task가 아니므로 재개하지 않았다.
  현재 catalog에 재개할 Gate C watch 실패는 없었다.

## 다음 단계

실제 수요를 바탕으로 UI·provider·자연어 범위를 고르기 전, 프로젝트 작성자가 아닌 분석가 1–2명과 짧은
관찰 세션을 한다. 참가자에게 “미국 GDP 2020–2022 결과를 확인하고 CSV로 저장해 결측과 통계 단위 정보를
설명해 달라”고 요청하고, 도움 없이 첫 명령을 찾는 시간, task ID 복사, 상태·경고 해석, 올바른 CSV 저장,
결측과 0의 구분, 재실행 경로 이해를 기록한다. 참가자가 사용할 환경에서 외부 요청이 허용되지 않으면 보존된
task로 결과 확인·전달만 평가한다. 자연 오류는 만들지 않는다.

참가자가 없으므로 위 관찰 세션과 다음 제품 범위 결정은 보류한다. Gate C의 natural source revision과
같은 task/stage의 natural retry/resume도 별도 자연 이벤트가 생길 때까지 대기한다. 이 둘은 현재 제품
사용성 dry run의 완료 조건에 포함하지 않는다.
