# 개발자 문서

개발자 문서는 사용자 경험과 개입 경계를 먼저 확인한 뒤, 엔진·모듈 계약과 구현·검증 절차를 살펴보도록 구성합니다.

## 먼저 읽기

1. [사용자 아키텍처](../user/USER_ARCHITECTURE.md)
2. [개발자 아키텍처](ARCHITECTURE.md)
3. [개발 안내](DEVELOPMENT_GUIDE.md)
4. [구현 계획](IMPLEMENTATION_PLAN.md)

## 문서 영역

- [엔진 설계](engines/README.md)
- [사용자 Python 확장 설계](extensions/USER_PYTHON_EXTENSIONS.md) — 제안·미구현
- [기능 기획](planning/README.md)
- [기관 connector 명세](connectors/README.md)
- [테스트와 검증](testing/README.md)
- [성능 측정과 최적화](performance/README.md)
- [결정·회차별 개발 이력](history/README.md)

문서와 실행 코드는 별도로 관리합니다. 사용자별 Python 확장 코드는 사용자 데이터 영역에서 명시적으로 허용된 엔진 hook에만 연결하는 제안이며, 현재 구현되어 있지 않습니다.
