# codex-skills

개인 Codex 스킬 저장소입니다.

## 포함된 스킬

- `ios-multi-agent-dev`
  - iOS/Swift 작업을 여러 에이전트에 역할 분리해 진행하는 협업 개발 스킬
  - 정의 → 분석 → 구현 → 메인 검증 → 비판적 리뷰 → 반영 흐름 제공

- `swift-master`
  - Swift 6, SwiftUI, Swift Concurrency, SwiftData, Architecture, Pure DI, Combine 마이그레이션을 다루는 통합 Swift/iOS 스킬
  - 리뷰, 최적화, 마이그레이션, 가이드, 코드 생성 워크플로 제공

- `ios-swift-orchestrator`
  - iOS/Swift 작업의 상위 진입점으로, 협업 워크플로와 Swift 전문성을 라우팅하는 래퍼 스킬
  - `ios-multi-agent-dev`, `swift-master`, 또는 둘 다 선택해 오케스트레이션

## 사용 예시

```text
$ios-multi-agent-dev 실제 iOS/Swift 작업을 planner, builder, reviewer 역할로 나눠 진행해주세요.
$swift-master 이 SwiftUI 코드의 상태 관리와 동시성 문제를 리뷰해줘.
$ios-swift-orchestrator 이 iOS/Swift 작업을 어떤 하위 스킬로 진행할지 결정하고 실행 흐름을 잡아줘.
```
