# Swift Intelligence 설치 및 사용

Swift Intelligence는 Xcode에 포함된 SourceKit-LSP를 사용해 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 조회하는 읽기 전용 Codex 플러그인입니다.

## 요구 사항

- macOS
- Xcode와 Command Line Tools
- Python 3

다음 명령이 모두 성공해야 합니다.

```bash
xcrun --find sourcekit-lsp
xcodebuild -version
python3 --version
```

별도 Python 패키지나 외부 바이너리는 필요하지 않습니다.

## 설치

1. GitHub marketplace를 등록합니다.
2. Swift Intelligence Plugin을 설치합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add swift-intelligence@codex-skills
codex plugin list
```

`codex plugin list`에 `swift-intelligence@codex-skills`가 `installed, enabled`로 표시되어야 합니다. 설치 후 Codex 데스크톱 앱을 다시 시작하고 새 작업을 여십시오.

동일한 marketplace 이름이 이미 등록되어 오류가 발생하면 기존 등록을 제거한 뒤 GitHub marketplace를 다시 등록합니다.

```bash
codex plugin marketplace remove codex-skills
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add swift-intelligence@codex-skills
```

## 사용

Swift 코드의 의미론적 관계가 필요한 요청을 자연어로 작성하면 스킬이 자동으로 선택됩니다. 명시적으로 선택하려면 프롬프트에서 `$swift-intelligence:swift-intelligence`를 사용합니다.

예시:

```text
$swift-intelligence:swift-intelligence 이 Swift 프로토콜 요구사항의 정의, 구현, 참조를 찾아주세요.
```

```text
$swift-intelligence:swift-intelligence 이 타입의 컴파일러 해석 타입과 현재 진단을 확인해주세요.
```

제공되는 MCP 도구:

- `swift_xcode_schemes`: 공유 Xcode 스킴 목록과 사용자 선택 필요 여부
- `swift_definition`: 사용 위치가 가리키는 정의
- `swift_references`: 심볼 기준 참조
- `swift_implementations`: 프로토콜 또는 메서드 구현
- `swift_hover`: 컴파일러 해석 타입과 문서
- `swift_symbols`: 파일 내 선언
- `swift_workspace_symbols`: 워크스페이스 심볼 검색
- `swift_diagnostics`: 파일 진단

## 프로젝트 준비

교차 파일 결과를 조회하기 전에 관련 타깃을 한 번 빌드하십시오.

SwiftPM:

```bash
swift build
```

Xcode 프로젝트:

```bash
xcodebuild -project Example.xcodeproj -scheme Example build-for-testing
```

먼저 `swift_xcode_schemes`로 공유 스킴을 조회합니다. 컨테이너와 같은 이름의 공유 스킴이 있으면 자동 선택되고, 없으면 스킬이 목록을 제시해 사용자에게 묻습니다. 선택한 값은 의미론 도구의 `xcode_scheme` 인자로 전달됩니다. 고정 자동화에서는 MCP 서버 환경변수 `SWIFT_INTELLIGENCE_XCODE_SCHEME`을 기본값으로 사용할 수 있으며, 호출별 `xcode_scheme`이 우선합니다. 둘 다 쉼표로 여러 스킴을 나열할 수 있습니다. 선택한 스킴의 build action이 필요한 프레임워크와 테스트 타깃을 이미 포함한다면 모듈 스킴을 추가할 필요가 없습니다. 포함하지 않는 타깃만 별도 스킴으로 추가합니다. 목록에 없는 파일이라도 경로 구성요소 중 공유 스킴 이름과 같은 것이 있으면(예: `Projects/TalkMediaKit/...` → `TalkMediaKit`) 그 스킴을 같은 세션에 자동 병합하며, 그 첫 호출은 sourcekit-lsp 재기동으로 약 1분 걸립니다. 일치하는 스킴이 없는 파일은 여전히 `build settings do not include` 오류가 납니다. 스킴당 약 1분이 처음 한 번 들고, 빌드 설정은 `~/Library/Caches/swift-intelligence/`에 캐시되어 워크스페이스의 `project.pbxproj`가 바뀌면 갱신됩니다. 인덱스 DB(IndexStoreDB)도 같은 곳에 인덱스 스토어별로 하나씩 두어 서버를 재시작해도 바뀐 유닛만 증분으로 읽습니다. 같은 스토어를 쓰는 서버가 이미 떠 있으면 두 번째 서버는 임시 DB를 씁니다. `SWIFT_INTELLIGENCE_EXPLICIT_UNITS=1`을 주면 인덱스를 로드한 타깃의 파일 유닛으로만 한정합니다. 다른 configuration(Sandbox, SampleApp)으로 빌드된 낡은 유닛이 내는 옛 줄 위치가 사라지지만, 선택한 스킴에 없는 모듈 안의 참조도 함께 사라지므로 조회 대상 모듈을 모두 나열한 경우에만 켭니다. `xcodebuild -showBuildSettingsForIndex`는 `-configuration`을 무시하고 한 configuration의 산출물 경로만 돌려주므로, 서버는 우선 명시적인 `SWIFT_INTELLIGENCE_XCODE_CONFIGURATION`, 그다음 스킴의 TestAction configuration을 사용해 `<config>-<sdk>` 경로를 보정합니다.

새 Xcode 세션에서는 기존 IndexStore를 SourceKit-LSP 데이터베이스로 가져오는 동안 참조·구현 결과가 점진적으로 증가할 수 있습니다. 서버는 첫 non-empty 결과를 즉시 확정하지 않고 결과가 일정 시간 안정될 때까지 기다립니다. `swift_workspace_symbols`는 정확 일치를 우선 정렬하고 동일 위치를 중복 제거하며 최대 200개를 반환합니다.

`swift_diagnostics`는 SourceKit-LSP가 pull diagnostics를 광고하면 `textDocument/diagnostic`을 사용하고, 그렇지 않으면 version이 일치하는 `publishDiagnostics` 알림을 사용합니다. timeout은 빈 진단 배열로 바꾸지 않습니다.

## 문제 진단

`No language service` 또는 반복 timeout을 조사할 때 MCP 서버 환경변수에 다음 값을 추가하고 Codex를 다시 시작합니다.

```text
SWIFT_INTELLIGENCE_TRACE=1
```

세션별 임시 trace 디렉터리에 SourceKit-LSP 표준 오류, LSP 입출력 mirror 및 BSP 요청 요약이 저장됩니다. 일반 실행에서는 trace 파일을 생성하지 않습니다. 문서 언어 서비스가 `-32001`로 실패하거나 SourceKit-LSP 프로세스가 종료되면 서버는 문서 상태를 초기화하고 한 번만 자동 재시도합니다.

저장소 루트에는 `.xcworkspace` 또는 `.xcodeproj`가 하나만 있어야 합니다. 여러 Xcode 컨테이너가 있으면 서버가 임의 선택하지 않고 오류를 반환합니다. 빈 참조 결과는 인덱스나 빌드 설정이 준비되지 않은 상태일 수 있으므로 완전한 결과로 단정하지 마십시오.

## 제거

```bash
codex plugin remove swift-intelligence@codex-skills
codex plugin marketplace remove codex-skills
```

공식 참고 문서: [Package your plugin](https://developers.openai.com/plugins/build/plugins)
