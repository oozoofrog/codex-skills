# Swift Intelligence 전역 도입 계획

## 사실 검증

- `anvyxhq/swift-mcp-server`는 SourceKit-LSP를 MCP로 감싸 symbols, references, definition, implementations, hover, diagnostics, hierarchy, rename, code actions를 제공한다. Xcode 프로젝트의 build settings 연결은 별도 문제다. <https://github.com/anvyxhq/swift-mcp-server>
- `Block/xcode-index-mcp`는 DerivedData의 IndexStoreDB를 읽어 USR 기반 occurrence를 조회한다. 편집 기능은 없으며 별·포크·커밋 수는 변동값이므로 선택 근거에서 제외한다. <https://github.com/block/xcode-index-mcp>
- `leftspin/mcp-sourcekit-lsp`는 SourceKit-LSP 기반의 작은 TypeScript 구현이다. npm 안내에 미출시 표현이 남아 있어 커밋 수만으로 성숙도를 단정할 수 없다. <https://github.com/leftspin/mcp-sourcekit-lsp>
- XcodeBuildMCP는 빌드·테스트·시뮬레이터·기기·로그 작업 중심의 보완재다. 공식 저장소는 Sentry 프로젝트다. <https://github.com/getsentry/XcodeBuildMCP>
- SourceKit-LSP 공식 문서는 SwiftPM과 `compile_commands.json`을 명시하며, 전역 인덱스 결과는 빌드 또는 background indexing 상태에 좌우된다. <https://github.com/swiftlang/sourcekit-lsp>
- `sourcekit-xcode-bsp`는 Xcode 26+ build engine을 BSP로 연결하지만 early-stage다. 필수 런타임으로 채택하지 않는다. <https://github.com/slime-studio/sourcekit-xcode-bsp>
- SwiftSyntax는 source-accurate syntax tree 계층이며 SourceKit 의미론과 다르다. deterministic AST query/rewrite 수요가 확인될 때 별도 추가한다. <https://github.com/swiftlang/swift-syntax>

## 채택 구조

1. Codex 전역 개인 플러그인에 MCP 소스, 스킬, 벤치마크를 함께 둔다.
2. 외부 MCP 바이너리를 설치하지 않고 `/usr/bin/xcrun sourcekit-lsp`를 실행한다.
3. 읽기 전용 의미론 도구 7개와 Xcode 스킴 선택 조회 도구 1개만 노출한다.
4. 각 호출이 `workspace_path`를 받아 어떤 Codex 프로젝트에서도 사용되게 한다.
5. SwiftPM 모노레포에서는 대상 파일과 가장 가까운 `Package.swift`를 자동 선택한다.
6. 루트의 단일 `.xcworkspace` 또는 `.xcodeproj`를 자동 감지하고 `xcodebuild -showBuildSettingsForIndex`의 파일별 앱·테스트 타깃 설정을 임시 BSP 서버로 전달한다.
7. BSP가 제공한 DerivedData index store는 SourceKit-LSP 내장 IndexStoreDB가 읽는다. 별도 IndexStoreDB 래퍼나 외부 MCP 바이너리는 추가하지 않는다.
8. Xcode 컨테이너 중복, 공유 스킴 선택 필요·누락, build settings 누락, 미생성 index store, 타깃에 속하지 않는 파일은 명시적 오류로 반환한다.

## 판정 기준

- semantic 모드 정확도가 baseline 이상이어야 한다.
- 참조·구현 과제의 누락 여부를 별도로 비교한다.
- MCP 오류와 인덱스 미준비를 빈 성공으로 처리하지 않는다.
- 모든 의미론 도구는 읽기 전용으로 선언한다.
