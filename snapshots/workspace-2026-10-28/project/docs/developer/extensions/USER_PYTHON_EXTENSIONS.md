# 사용자별 Python 확장 설계 제안

**상태:** 설계 제안, 실행기·hook registry 미구현

## 목적

사용자가 필요로 하는 특정 처리를 공통 엔진 전체를 복사하거나 수정하지 않고 추가합니다. 사용자는 지원되는 엔진 경계에 extension을 연결하고, 나머지 엔진은 기존 계약대로 유지합니다. 이 방식은 엔진의 임의 내부 코드를 대체하는 기능이 아니라, 문서화된 hook 단계에 제한된 코드를 끼우는 방식입니다.

## Python과 Markdown의 역할

실행 로직은 Markdown에 넣지 않습니다. Markdown은 설명, 예시, 입력·출력 계약과 사용법을 작성하는 문서입니다. JSON 또는 YAML manifest는 extension ID, 버전, 대상 hook, 입력·출력 schema, 필요한 capability, 제한된 자원 값을 선언합니다. 실제 기능은 Python package로 작성하고 테스트합니다.

Python의 문법·import·타입·계약·runtime 오류는 실행 오류로 다룹니다. Markdown의 링크·표·문법 문제는 lint나 문서 검토로 고칠 수 있지만, 문서에 기술한 methodology, 통계 정의, 단위 의미를 바꾸는 일은 문장 교정으로 취급하지 않고 사람이 검토합니다.

## 지원할 hook 후보

Hook는 안정된 공개 경계에만 둡니다. 1차 후보는 다음과 같습니다.

| Hook | 입력 | 허용 결과 예 | 하지 않는 일 |
|---|---|---|---|
| 후보 선택/필터 | 공식 discovery 후보와 요청 조건 | 후보 제외 사유, 정렬·필터 선택 | 공식 식별자나 출처를 증거 없이 만들기 |
| Metadata 보강 | 보존된 원문 metadata와 출처 | 추가 설명·사용자 annotation | 원문을 덮어쓰거나 원문과 번역을 혼합 |
| 수집 후 가공 | 검증된 입력 series와 사용자가 승인한 정책 | 별도 파생 series와 provenance | 원자료 수정, 결측을 0으로 대체, 미승인 interpolation |
| 출력 layout | 검증된 원자료/파생 자료와 output specification | 허용된 열·시트 구성 제안 | 원자료·계산 결과 값 변경, 승인된 형식 밖의 내보내기 |

Hook가 없는 엔진 부분은 확장할 수 없습니다. 자격 증명, 네트워크 전송, raw 저장, SQLite 쓰기, 권한·정책 판정은 사용자 extension에 넘기지 않습니다. 필요성이 확인되면 별도 권한 설계와 사람의 승인이 필요합니다.

## 폴더 구조 제안

개발·검토용 extension source는 core의 `src/macro_data_platform/`와 분리된 저장소 루트 `extensions/`에 둡니다. 사용자가 extension을 선택·활성화하는 상태는 사용자별 데이터 디렉터리에서 관리합니다.

```text
extensions/
  example_country_filter/
    pyproject.toml
    manifest.json
    README.md
    src/example_country_filter/
      __init__.py
      plugin.py
    tests/
      test_plugin.py

MACROATLAS_DATA_DIR/
  extensions/<user_id>/<extension_id>/<version>/
  extension_registry.json
```

위 구조는 제안이며 어떤 폴더나 loader도 아직 생성·구현하지 않았습니다. 설치본은 읽기 전용, 버전 고정, hash 기록을 고려합니다. 사용자별 registry에는 사용자가 승인한 extension ID/version과 hook 선택을 기록하고 비밀값은 두지 않습니다. package source, dependency lock, test fixture는 `docs/`에 넣지 않습니다.

## 실행·오류 처리 원칙

1. Hook ID와 version을 core contract에 등록하고 입력/출력 타입 및 허용 가능한 크기·행 수를 정합니다.
2. manifest 형식, package 설치, Python 버전, syntax, contract와 fixture를 offline에서 검사합니다. Python import 자체도 top-level 코드를 실행할 수 있으므로 신뢰되지 않은 package를 main process에서 미리 import하지 않습니다.
3. 사용자에게 extension, version, hook, 권한·제한, 예상 출력 차이를 보여주고 활성화를 명시적으로 확인받습니다.
4. 작업 시작 때 package hash와 configuration snapshot을 고정합니다. 실행 도중 파일 교체(hot-swap)는 허용하지 않습니다.
5. 격리된 실행 경계와 capability 제한을 확인한 뒤 실행합니다. 별도 프로세스만으로 임의 Python의 파일·네트워크 권한이 격리된다고 간주하지 않습니다. Windows에서 검증 가능한 격리를 확보하지 못하면 기능을 비활성으로 둡니다.
6. 실행은 timeout, memory, CPU, output size, filesystem/network 접근을 제한합니다. core 데이터와 credentials를 extension worker에 직접 노출하지 않고 필요한 입력만 전달합니다.
7. 실패는 `manifest_error`, `syntax_error`, `import_error`, `contract_error`, `runtime_error`, `timeout`, `resource_limit`, `permission_denied`처럼 분류하고 extension ID/version, hook, 오류 위치, 정리된 원인을 남깁니다. secret과 원자료 일부가 로그로 새지 않도록 합니다.
8. 실패 시 해당 hook 및 의존 결과만 실패 상태로 표시하고 raw와 앞 단계 산출물을 보존합니다. 사전에 사용자가 승인한 fallback이 없으면 기본 동작으로 몰래 대체하지 않습니다.

안전한 OS 격리 기술, package 설치 정책, 서명·hash 신뢰 절차, extension 삭제/rollback 기준은 구현 전에 조사·승인할 미결정 사항입니다. 현재 코드는 이러한 제한을 집행하지 않습니다.

## 검토 기준

- 좁은 hook 계약으로 엔진 전체를 갈아끼우지 않고 요청된 일부 동작만 바뀌는가?
- 원자료, 출처, 단위, 빈도, 결측/0, revision, provenance를 보존하는가?
- fixture로 성공·빈 입력·잘못된 출력·예외·timeout·권한 실패를 재현하는가?
- 사용자가 버전·hash·정책을 확인하고 다시 같은 실행을 재현할 수 있는가?
- 일반 실행에서 extension 미사용 상태가 기존 결과와 완전히 같은가?
- 격리 경계를 실제 Windows 환경에서 확인했는가? 확인 전에는 live 사용자 코드를 실행하지 않는가?

기능 구현은 이 설계 검토와 별도 iteration이며, 현재 문서는 Python runner, plugin API, sandbox 또는 user-specific code execution이 이미 지원된다고 주장하지 않습니다.
