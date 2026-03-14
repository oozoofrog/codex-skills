# SourceKit-LSP / Swift code intelligence guide

`swift-lsp` Claude plugin은 사실상 `sourcekit-lsp` 등록 정보입니다.
Codex에서는 이를 독립 skill로 두기보다 Swift 진단 reference로 흡수합니다.

## 언제 읽을까
- `sourcekit-lsp` 가 안 잡힌다
- Swift symbol/diagnostic/completion이 깨진다
- Xcode toolchain과 Swift toolchain 충돌이 의심된다
- Swift 프로젝트의 code intelligence/LSP 문제를 디버깅해야 한다

## 먼저 확인할 것
```bash
command -v sourcekit-lsp
xcode-select -p
swift --version
```

## 보통 원인
- Xcode/Swift toolchain PATH 문제
- `xcode-select` 가 기대한 Developer dir를 가리키지 않음
- 프로젝트 root가 잘못되어 package/xcodeproj 컨텍스트를 못 잡음
- DerivedData 또는 build artifact와 편집 대상이 어긋남

## 점검 순서
1. `sourcekit-lsp` 존재 확인
2. 현재 toolchain/Xcode 선택 상태 확인
3. SwiftPM 프로젝트인지, Xcode project/workspace인지 구분
4. 프로젝트 root에서 build/typecheck가 실제 되는지 확인
5. LSP 문제를 편집기 문제와 빌드 문제로 분리

## 실용 명령
```bash
command -v sourcekit-lsp
xcode-select -p
swift build
swift test
```

Xcode 기반이면 필요 시 build setting/source of truth도 확인합니다.

## 판단 원칙
- build 자체가 실패하면 LSP만 따로 고치려 하지 말고 빌드 오류부터 해결
- toolchain 경로 문제면 editor 설정보다 `xcode-select`/PATH/sourcekit-lsp 존재를 먼저 확인
- SwiftUI/Swift Concurrency 이슈와 섞이면 `concurrency-reference.md`, `swiftui-reference.md`도 같이 읽기
