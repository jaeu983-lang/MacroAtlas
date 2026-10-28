# 운영자 문서

운영자는 로컬 설정과 비밀값을 관리하고, 승인된 실행을 감독하며, 부분 실패나 데이터 무결성 문제를 분류합니다.

1. [운영 흐름과 유지보수 주기](OPERATING_PLAN.md)
2. [설치·로컬 설정](INSTALLATION.md)
   - [API 키 발급·입력 안내](API_KEYS.md) — FRED/Census, 기존 BEA/e-Stat, 현재 무키 BLS v1과 21개 source 판단
3. [실행·장애 대응 runbook](OPERATOR_RUNBOOK.md)
4. [기관 reference](reference/README.md)
5. [기존 운영·개발 PowerPoint 참고본](reference/MacroAtlas_운영_개발_개정.pptx)

API 문서 확인, adapter 구현, fixture 검사, 실 API 호출, 저장 후 재조회는 각각 다른 준비 상태로 기록합니다. live 작업은 기관별 한도와 별도 승인 게이트를 따릅니다.
