# START HERE

이 저장소는 기획 문서만 담은 템플릿이 아니라 Python 코드와 테스트가 들어 있는 MacroAtlas
작업 저장소입니다. 처음 확인할 때 아래 순서를 따르세요.

1. 제품이 만들 범위는 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)에서 확인합니다.
2. 지금 구현된 범위, 미통과 게이트, 다음 허용 작업은
   [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)에서 확인합니다.
3. 모듈 경계는 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), 기관별 확인 사실은
   [`docs/INSTITUTION_CATALOG.md`](docs/INSTITUTION_CATALOG.md)에서 확인합니다.
4. 코드를 바꾸기 전 [`AGENTS.md`](AGENTS.md)와 [`GUIDELINES.md`](GUIDELINES.md)를 읽습니다.
5. 설치와 검사는 [`docs/INSTALLATION.md`](docs/INSTALLATION.md)를 따릅니다.

현재 검수 상태는 Gate A 통과, Gate B는 engine/API 제한 범위 통과, Gate C 미통과,
Gate D/E 미실행입니다. Gate B 제한 통과는 전체 기관 검색, CLI 또는 자연어 대화 기능을 뜻하지
않습니다. 실패한 게이트를 통과한 것으로 가정해 다음 의존 회차로 이동하지 않습니다.

Git branch/commit 정보는 `git status -sb`, `git log -1 --oneline`,
`git rev-parse HEAD`로 확인합니다. 원격 branch가 가리키는 commit과 작업 트리 commit이
다르면, local 수정은 새 checkout에 포함되지 않습니다. 키나 실제 수집 원본은 커밋하지 않습니다.

자동 스케줄러는 제품의 승인 기반 개선 흐름이 검증되기 전에는 설치하지 않습니다.
