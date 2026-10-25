# MacroAtlas

API와 공식 파일의 데이터셋별 실행·검증·저장 범위는 [데이터셋 계약](docs/developer/connectors/DATASET_CONTRACTS.md)을 참고하세요. FRED/Census/BLS v1 API 4개와 TIC/BoE CSV 3개 선택 경로의 synthetic fixture 검증이며 전체 기관 live 지원이 아닙니다.

MacroAtlas는 국제금융·거시경제 통계를 공식 출처에서 찾아, 의미와 접근 경로를 확인한 뒤 원자료와 실행 근거를 보존하며 수집하는 로컬 우선 데이터 플랫폼입니다.

## 현재 상태

- 기관 목록에는 21개 출처가 있습니다. 공식 API 문서를 확인한 곳은 15개, 이번 조사에서 명세를 확인하지 못한 곳은 6개입니다. unconfirmed는 API가 없다는 뜻이 아닙니다.
- API 문서 확인, 어댑터 구현, fixture 검증, 실 API 성공은 서로 다른 상태입니다.
- 현재 확인된 live 수집은 World Bank의 미국 GDP 고정 경로 하나입니다.
- BEA와 e-Stat에는 제한된 JSON 클라이언트와 mock 검사가 있지만, 전체 작업 흐름과 실기관 호출은 아직 검증되지 않았습니다.
- FRED·Census·BLS v1에는 기관별 JSON client와 synthetic fixture의 파일 저장·재조회 검사가 있습니다. BLS는 키 없는 1.0 전용입니다. [예시 파일 테스트](docs/developer/history/ITERATION_28_REPORT.md)는 실제 기관 데이터와 구분합니다.
- 자연어 사용자 에이전트 UI는 목표 구조입니다. 현재 저장소에는 일반 대화형 제품 UI가 없습니다.

## 운영 기준과 구조

- [제품 범위와 품질 기준](PROJECT_PLAN.md)
- [문서 시작점](docs/README.md)
- [사용자 문서](docs/user/README.md) · [운영자 문서](docs/operator/README.md) · [개발자 문서](docs/developer/README.md)
- [사용자 중심 흐름](docs/user/USER_ARCHITECTURE.md)과 [개발자 아키텍처](docs/developer/ARCHITECTURE.md)
- [기관 상태와 공식 API 조사](docs/operator/reference/README.md)
- [개발·성능·회차별 기록](docs/developer/README.md)

## 개발 시작

Windows PowerShell에서 프로젝트 루트에 가상환경을 만들고 개발 패키지를 설치합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

로컬 검사는 네트워크 없이 fixture/mock을 기본으로 사용합니다. 로컬 검사 절차는 [개발자 안내](docs/developer/DEVELOPMENT_GUIDE.md), live 호출과 운영 예산은 [운영자 runbook](docs/operator/OPERATOR_RUNBOOK.md)을 따르세요. 실기관 호출은 해당 기관의 준비 게이트, 인증, 약관, 호출 예산을 확인한 뒤에만 진행합니다.

## 운영 원칙

오류와 사람의 피드백은 매주 검토하고, 메모리/성능은 2주마다 측정 근거를 보고 개선합니다. 기관 추가는 수요가 생길 때마다 별도로 추진합니다. 서로 독립된 offline 작업은 나란히 진행할 수 있지만, 실기관 시험은 공통 엔진과 해당 기관의 준비 조건을 모두 통과한 뒤 기관별로 엽니다. 상세 일정은 [운영 계획](docs/operator/OPERATING_PLAN.md)을 기준으로 합니다.
