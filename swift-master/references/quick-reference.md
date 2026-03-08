# Swift Master Quick Reference

가장 먼저 읽는 진입용 문서입니다.
요청 유형별로 어떤 reference를 먼저 열지 빠르게 결정하기.

---

## Quick Index

- 리뷰 시작: `concurrency-reference.md`, `swiftui-reference.md`, `swiftdata-reference.md`
- 마이그레이션 시작: `swift6-reference.md`, `combine-migration.md`, `transformation-examples.md`
- 설계/가이드 시작: `architecture-reference.md`, `pure-di-reference.md`
- 팀 규칙 확인: `swift-conventions-reference.md`
- 예시/실전 패턴 확인: `swift-practices-reference.md`

## 작업 유형별 첫 진입점

### SwiftUI 리뷰

먼저 읽기:
- `swiftui-reference.md`
- 필요 시 `swift-conventions-reference.md`

주요 확인 항목:
- `@Observable` / `ObservableObject`
- `@State`, `@StateObject`, `@Bindable`
- `NavigationStack`
- 재렌더링과 source of truth

### Swift Concurrency 리뷰

먼저 읽기:
- `concurrency-reference.md`
- 필요 시 `swift6-reference.md`

주요 확인 항목:
- `Sendable`
- `@MainActor`
- `Task.detached`
- continuation resume 안전성
- cancellation

### SwiftData 리뷰

먼저 읽기:
- `swiftdata-reference.md`
- 필요 시 `concurrency-reference.md`

주요 확인 항목:
- `@Model` 설계
- 관계 모델링과 delete rule
- `ModelContext`
- 스레딩과 `PersistentIdentifier`

### 아키텍처 / DI 가이드

먼저 읽기:
- `architecture-reference.md`
- `pure-di-reference.md`
- 필요 시 `swift-conventions-reference.md`

주요 확인 항목:
- MVVM vs TCA
- Composition Root
- 생성자 주입
- Service Locator 회피

### Combine 마이그레이션

먼저 읽기:
- `combine-migration.md`
- `transformation-examples.md`
- 필요 시 `concurrency-reference.md`

주요 확인 항목:
- `Publisher` → `AsyncSequence`
- `sink` → `for await`
- `AnyCancellable` → `Task`
- callback/delegate → continuation / `AsyncStream`

## Mode별 읽기 순서

### REVIEW

1. `quick-reference.md`
2. 도메인 reference 1개
3. 필요 시 `swift-conventions-reference.md`

### OPTIMIZE

1. 도메인 reference 1개
2. `swift-practices-reference.md`

### MIGRATE

1. `swift6-reference.md` 또는 `combine-migration.md`
2. `transformation-examples.md`
3. 도메인 reference

### GUIDE

1. `architecture-reference.md` 또는 `pure-di-reference.md`
2. `swift-conventions-reference.md`

### GENERATE

1. 도메인 reference
2. `transformation-examples.md`
3. `swift-practices-reference.md`

## 자주 쓰는 검색어

- SwiftUI: `@StateObject`, `ObservableObject`, `NavigationView`, `.task`, `@Bindable`
- Concurrency: `Task.detached`, `DispatchQueue.main.sync`, `withCheckedContinuation`, `@unchecked Sendable`
- SwiftData: `@Model`, `ModelContext`, `@Relationship`, `FetchDescriptor`
- DI: `Factory`, `Injected`, `Container`, `protocol`
- Combine: `AnyCancellable`, `sink`, `Publisher`, `PassthroughSubject`

## 문서 역할 구분

- `swift-conventions-reference.md`: 짧고 강한 규칙, 팀 기본 정책, 빠른 체크리스트
- `swift-practices-reference.md`: 실전 예시, 문서화/에러 처리/타입 설계/테스트 패턴
- `transformation-examples.md`: Before/After 중심 변환 예시
