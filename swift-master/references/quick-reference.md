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
- actor-isolated 타입이 non-Sendable 서비스/protocol existential을 보관한 채 async 호출하는지
- `async func`가 실제 완료를 기다리지 않고 내부 `Task`만 시작하는지
- 취소된 이전 요청이 최신 `loading/error/result` 상태를 덮어쓰는지
- 최신 요청만 상태를 반영하는 `requestID`/token gate가 필요한지

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

## 검증 기준 올리기

다음이 보이면 `typecheck`만으로 끝내지 말기.
- `@MainActor`
- `Sendable`
- actor/service 경계
- `.task`와 lifecycle 연동
- cancellation

우선 검토할 명령:
- `swift test`
- `swift build`
- `xcodebuild test`
- strict concurrency 옵션이 포함된 build/test

문제를 찾았으면 진단으로 끝내지 말고 바로 다음 수정안을 함께 쓰기.

## 비동기 의미 불일치

다음을 위험 신호로 보기.
- `async func generate()`가 내부에서 `Task { ... }`만 만들고 바로 반환
- 메서드 이름은 `load()/generate()/save()`인데 실제 의미는 `startLoad()/startGenerate()/startSave()`
- 이전 task의 취소/실패가 최신 요청의 `isLoading` / `error` / `result`를 덮어씀

우선 읽기:
- `concurrency-reference.md`

우선 검색:
- `Task {`
- `currentTask`
- `isLoading`
- `errorMessage`
- `requestID`
- `token`

## 자주 쓰는 검색어

- SwiftUI: `@StateObject`, `ObservableObject`, `NavigationView`, `.task`, `@Bindable`
- Concurrency: `Task.detached`, `DispatchQueue.main.sync`, `withCheckedContinuation`, `@unchecked Sendable`, `@MainActor`, `Sendable`
- Async semantics: `Task {`, `currentTask`, `requestID`, `generationID`, `isLoading`, `errorMessage`
- SwiftData: `@Model`, `ModelContext`, `@Relationship`, `FetchDescriptor`
- DI: `Factory`, `Injected`, `Container`, `protocol`
- Combine: `AnyCancellable`, `sink`, `Publisher`, `PassthroughSubject`

## 문서 역할 구분

- `swift-conventions-reference.md`: 짧고 강한 규칙, 팀 기본 정책, 빠른 체크리스트
- `swift-practices-reference.md`: 실전 예시, 문서화/에러 처리/타입 설계/테스트 패턴
- `transformation-examples.md`: Before/After 중심 변환 예시
