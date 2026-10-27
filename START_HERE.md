# START HERE

이 저장소는 Python 코드와 테스트가 있는 MacroAtlas 작업 저장소입니다. 읽는 목적에 맞춰 문서를 고르세요.

1. 사용자는 [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)부터 읽습니다.
2. 개발자는 [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md),
   [`AGENTS.md`](AGENTS.md), [`GUIDELINES.md`](GUIDELINES.md)를 읽습니다.
3. 통합 기준인 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)에서 현재 제품 범위·우선순위·완료 조건을 확인합니다.
   [`docs/ROADMAP_2026_10_26.md`](docs/ROADMAP_2026_10_26.md)는 짧은 실행 요약입니다.
4. 현재 구현·Gate 증거는 [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md),
   남은 문제의 종류는 [`docs/UNRESOLVED_ITEMS.md`](docs/UNRESOLVED_ITEMS.md)에서 확인합니다.
5. 사용자·개발자 관점의 목표 시스템은 [`docs/PRODUCT_ARCHITECTURE.md`](docs/PRODUCT_ARCHITECTURE.md),
   현재 함수·엔진 호출 경로는 [`docs/ENGINE_CONNECTIONS.md`](docs/ENGINE_CONNECTIONS.md)를 봅니다.
6. 설치와 로컬 검사는 [`docs/INSTALLATION.md`](docs/INSTALLATION.md)를 따릅니다.
7. 문서 역할과 날짜가 붙은 역사 보고서의 의미는 [`docs/README.md`](docs/README.md)에 있습니다.

현재 검수 상태는 Gate A/D 통과, Gate B/C와 E 제한 범위 판정입니다. 이 결과는 전체 기관 검색이나
모든 기관의 정상·실패 흐름이 제공됨을 뜻하지 않습니다. 자연 TIC/BIS source revision과 자연 provider
failure→durable resume은 실측되지 않았습니다. BOJ는 FM08/FXERD01 한 달 경로만 연결됐으며 다른
series는 지원하지 않습니다. 현행 범위는 [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md), A–H/X01–X09
세부 증거는 [`docs/REFERENCE_SCENARIOS.md`](docs/REFERENCE_SCENARIOS.md)를 확인합니다.

구현 증거는 [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)를 따릅니다. 현재 TIC/BIS 변경 감시
자동화는 중지됐으며 사용자가 필요할 때 요청하는 단발 명령만 남습니다. `macroatlas --help`로
지원되는 고정 수집·감시 명령을 볼 수 있습니다.

Git branch/commit 정보는 `git status -sb`, `git log -1 --oneline`,
`git rev-parse HEAD`로 확인합니다. 원격 branch가 가리키는 commit과 작업 트리 commit이
다르면, local 수정은 새 checkout에 포함되지 않습니다. 키나 실제 수집 원본은 커밋하지 않습니다.

자동 스케줄러는 제품의 승인 기반 개선 흐름이 검증되기 전에는 설치하지 않습니다.
