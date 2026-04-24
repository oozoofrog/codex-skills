# Swift 6 Migration Reference Guide

Swift 6 마이그레이션, Strict Concurrency, Typed Throws 가이드입니다.

---

## Swift 6 핵심 변경사항

### 1. 완전한 동시성 검사 (Complete Concurrency Checking)

Swift 6는 컴파일 타임에 데이터 레이스를 감지합니다.

```swift
// ❌ Swift 6에서 컴파일 에러
var globalState = 0 // 전역 가변 상태

func increment() {
    globalState += 1 // 데이터 레이스 가능성
}

// ✅ Swift 6 호환
actor GlobalState {
    static let shared = GlobalState()
    private(set) var value = 0

    func increment() {
        value += 1
    }
}
```

### 2. Typed Throws (SE-0413)

```swift
// 에러 타입 명시 가능
enum FileError: Error {
    case notFound
    case permissionDenied
}

func readFile(at path: String) throws(FileError) -> String {
    guard FileManager.default.fileExists(atPath: path) else {
        throw .notFound
    }
    // ...
}

// 타입 추론 가능한 catch
do throws(FileError) {
    let content = try readFile(at: "test.txt")
} catch .notFound {
    print("File not found")
} catch .permissionDenied {
    print("Permission denied")
}
// 모든 케이스 처리됨 - 추가 catch 불필요
```

### 3. Swift 6.2+ Isolation 변경사항

```swift
// 순수 sync helper는 actor state에 접근하지 않도록 nonisolated로 분리할 수 있습니다.
nonisolated func pureHelper() -> Int {
    1
}

// actor를 벗어나 concurrent executor에서 실행하려는 의도는 명시합니다.
@concurrent
func heavyWork() async -> Int {
    // caller actor를 점유하지 않는 CPU-heavy 작업
    return expensiveCalculation()
}

// UI 상태는 MainActor에 둡니다.
@MainActor
func updateUI() {
    // UI 업데이트
}
```

판단 순서:
- 현재 toolchain과 빌드 설정(`SWIFT_DEFAULT_ACTOR_ISOLATION`, `NonisolatedNonsendingByDefault`) 확인
- UI 상태/화면 컴포넌트는 `@MainActor`
- 순수 sync helper만 `nonisolated` 후보
- CPU-heavy async 작업은 `@concurrent` 후보
- `nonisolated async`를 백그라운드 실행 escape hatch로 사용하지 않기

---

## 마이그레이션 단계

### Step 1: Strict Concurrency Checking 점진적 활성화

```
Build Settings → Swift Compiler → Strict Concurrency Checking

1. Minimal (기본) - 기본 검사만
2. Targeted - 명시적 async 코드 검사
3. Complete - 모든 동시성 검사 (Swift 5에서는 warning, Swift 6에서는 error)
```

권장 마이그레이션 순서:
1. Swift 5 language mode에서 대상 모듈만 `Complete`로 경고를 먼저 본다.
2. 경고를 “현재 코드의 실제 isolation/Sendable 계약”으로 해소한다.
3. 경고가 사라진 모듈만 `Swift Language Version = 6`으로 고정한다.
4. 큰 구조 리팩터와 Swift 6 전환을 한 커밋에 섞지 않는다.

### Step 2: 경고를 에러로 처리

```
Build Settings → Swift Compiler → Treat Warnings as Errors = Yes
```

### Step 3: 모듈별 점진적 마이그레이션

```swift
// Package.swift
.target(
    name: "MyModule",
    swiftSettings: [
        .enableExperimentalFeature("StrictConcurrency")
    ]
)
```

---

## 주요 마이그레이션 패턴

### 1. 전역 가변 상태 제거

```swift
// ❌ Swift 6 에러
var cache: [String: Data] = [:]

// ✅ 방법 1: Actor
actor CacheManager {
    static let shared = CacheManager()
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? {
        cache[key]
    }

    func set(_ key: String, data: Data) {
        cache[key] = data
    }
}

// ✅ 방법 2: TaskLocal
enum CacheKey {
    @TaskLocal static var current: [String: Data]?
}

// ✅ 방법 3: immutable snapshot 또는 computed constant로 변경
let emptyCache: [String: Data] = [:]
```

`nonisolated(unsafe)`는 컴파일러 검사를 끄는 escape hatch입니다. 새 마이그레이션의 기본 해결책으로 제안하지 말고, repo/user가 금지하면 사용하지 마세요.

### 2. Sendable 준수

```swift
// ❌ Swift 6 에러 - class는 기본적으로 non-Sendable
class UserData {
    var name: String
}

// ✅ 방법 1: Struct 사용 (권장)
struct UserData: Sendable {
    let name: String
}

// ✅ 방법 2: final + immutable
final class UserData: Sendable {
    let name: String

    init(name: String) {
        self.name = name
    }
}

// ✅ 방법 3: @MainActor 격리
@MainActor
final class UserData: Sendable {
    var name: String // mutable OK - MainActor에서만 접근
}

// ✅ 방법 4: non-Sendable 객체 대신 필요한 값만 snapshot으로 전달
struct UserDataSnapshot: Sendable {
    let name: String
}
```

`@unchecked Sendable`은 “스레드 안전함을 사람이 보증한다”는 unsafe opt-out입니다. 기본 수정안으로 제시하지 말고, 값 타입 snapshot/actor isolation/API isolation 정정을 먼저 검토하세요.

### 3. Closure의 Sendable

```swift
// ❌ Swift 6 에러
func performAsync(completion: @escaping () -> Void) {
    Task {
        completion() // non-Sendable closure
    }
}

// ✅ @Sendable 명시
func performAsync(completion: @escaping @Sendable () -> Void) {
    Task {
        completion()
    }
}

// ✅ async 함수로 변환
func performAsync() async {
    // 작업
}
```

### 4. Legacy API와의 호환

```swift
// 외부 라이브러리가 Sendable 준수 안함
import LegacyLibrary

// @preconcurrency로 경고 억제
@preconcurrency import LegacyLibrary

// 또는 concurrency boundary에서 필요한 값만 추출
struct LegacySnapshot: Sendable {
    let id: String
    let title: String
}
```

`@preconcurrency import`는 점진 전환용 임시 장치입니다. 사용한 import는 추적하고, 의존 모듈이 Swift Concurrency annotation을 갖추면 제거하세요.

### 5. Callback → Continuation 패턴

```swift
// Legacy API
func legacyFetch(completion: @escaping (Data?, Error?) -> Void) {
    // ...
}

// Swift 6 호환 래퍼
func modernFetch() async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        legacyFetch { data, error in
            if let error = error {
                continuation.resume(throwing: error)
            } else if let data = data {
                continuation.resume(returning: data)
            } else {
                continuation.resume(throwing: FetchError.unknown)
            }
        }
    }
}
```

---

## MainActor 패턴

### UI 클래스 격리

```swift
// ❌ Swift 6에서 경고/에러
class ViewModel: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() async {
        let data = await fetchItems()
        items = data // 어느 스레드에서 실행될지 불명확
    }
}

// ✅ MainActor 격리
@MainActor
class ViewModel: ObservableObject {
    @Published var items: [Item] = []
    @Published private(set) var thumbnails: [Thumbnail] = []
    private let service: ItemService

    init(service: ItemService) {
        self.service = service
    }

    func loadItems() async throws {
        let data = try await service.fetchItems()
        items = data

        // CPU-heavy 후처리만 actor 밖으로 명시적으로 분리
        thumbnails = try await Self.decodeThumbnails(from: data)
    }

    @concurrent
    private static func decodeThumbnails(from items: [Item]) async throws -> [Thumbnail] {
        try items.map { try Thumbnail(item: $0) }
    }
}
```

### nonisolated 활용

```swift
@MainActor
class ViewModel {
    var displayName: String = ""

    // 계산만 하는 함수는 nonisolated 가능
    nonisolated func formatDate(_ date: Date) -> String {
        DateFormatter.localizedString(from: date, dateStyle: .short, timeStyle: .short)
    }

    // async 작업을 actor 밖에서 병렬 실행하려면 @concurrent로 의도를 명시
    @concurrent
    static func decode(_ data: Data) async throws -> Model {
        try JSONDecoder().decode(Model.self, from: data)
    }
}
```

주의:
- `nonisolated`는 actor-isolated state에 접근하지 않는 선언이라는 의미입니다.
- Swift 6.2+에서는 `nonisolated async`를 백그라운드 실행으로 가정하지 마세요.
- instance `nonisolated` 메서드는 `@MainActor` 저장 프로퍼티나 non-Sendable dependency에 접근할 수 없습니다.
- `@concurrent` 인자/반환값은 actor 경계를 넘으므로 `Sendable` value 또는 안전한 transfer 형태여야 합니다.

### MainActor.assumeIsolated

```swift
// 이미 MainActor에서 실행 중임을 알 때
func updateFromCallback() {
    // Legacy callback - 스레드 보장 없음
    MainActor.assumeIsolated {
        // MainActor에서 실행 중이라고 가정
        // 아니면 런타임 에러
        updateUI()
    }
}

// 더 안전한 방법
func updateFromCallback() async {
    await MainActor.run {
        updateUI()
    }
}
```

---

## 안티패턴 체크리스트

| # | 패턴 | 탐지 | 수정 |
|---|------|------|------|
| S61 | Non-Sendable Closure Capture | `@escaping () ->` | `@Sendable` 추가 |
| S62 | Global Mutable State | `var \w+ =` (전역) | Actor/TaskLocal |
| S63 | Protocol Sync Requirements | `protocol.*func \w+\(\)` | `async` 추가 |
| S64 | Unsafe Sendable Opt-out | `@unchecked Sendable` | value snapshot/actor/API isolation 먼저 검토 |
| S65 | Missing @MainActor | UI class 격리 없음 | `@MainActor` |
| S66 | Typed Throws Nesting | 중첩된 typed throws | 레이어별 에러 |
| S67 | Legacy Callback Isolation | callback executor 불일치 | static annotation, `MainActor.run`, 보장된 경우만 `assumeIsolated` |
| S68 | Non-Sendable Default | 기본값이 non-Sendable | Sendable 타입 |
| S69 | Isolated Parameter Misuse | `isolated` 파라미터 오용 | isolation 명시 |
| S610 | Task.detached Overuse | `Task.detached` 남용 | `async let`/`TaskGroup` 또는 owner-managed `Task` |

---

## Typed Throws 가이드

### 언제 사용?

```swift
// ✅ 사용하면 좋은 경우
// - 명확한 에러 타입이 있을 때
// - 에러 처리가 exhaustive해야 할 때
// - API 명세가 중요할 때

enum ValidationError: Error {
    case invalidEmail
    case passwordTooShort
    case usernameTaken
}

func validateUser(_ user: User) throws(ValidationError) {
    // ...
}

// ❌ 피해야 할 경우
// - 여러 레이어를 거치는 경우 (nesting hell)
// - 에러 타입이 자주 변경될 수 있는 경우
// - 외부 라이브러리 에러를 포함해야 할 때
```

### Typed Throws 변환

```swift
// Before
func fetchUser() throws -> User {
    // URLError, DecodingError, CustomError 등 다양한 에러
}

// After - 명확한 도메인 에러로 래핑
enum UserFetchError: Error {
    case networkError(underlying: Error)
    case invalidResponse
    case userNotFound
}

func fetchUser() throws(UserFetchError) -> User {
    do {
        let data = try await network.fetch(url)
        return try decoder.decode(User.self, from: data)
    } catch let error as URLError {
        throw .networkError(underlying: error)
    } catch is DecodingError {
        throw .invalidResponse
    }
}
```

---

## 마이그레이션 체크리스트

### Phase 1: 준비

- [ ] Xcode 16+ 업그레이드
- [ ] 대상 모듈의 Swift version/build settings 확인
- [ ] 빌드 성공 확인

### Phase 2: 점진적 마이그레이션

- [ ] Swift 5 language mode에서 Strict Concurrency = Complete 설정
- [ ] 경고 수정
  - [ ] UI 상태와 화면 컴포넌트 `@MainActor` 격리
  - [ ] boundary를 넘는 값은 `Sendable` snapshot/DTO로 축소
  - [ ] 전역 상태는 immutable, global actor, actor owner 중 하나로 정리
  - [ ] `@unchecked Sendable` / `nonisolated(unsafe)`는 repo/user가 명시 허용한 경우만 임시 사용 여부 추적

### Phase 3: Complete 모드

- [ ] Strict Concurrency = Complete 설정
- [ ] 모든 경고/에러 수정
- [ ] `@preconcurrency import` 최소화 및 제거 계획 기록
- [ ] `nonisolated async` / `@concurrent` 의미가 Swift 6.2+ 설정과 맞는지 재확인

### Phase 4: Swift 6 모드

- [ ] Swift Language Version = 6 설정
- [ ] 모든 에러 수정
- [ ] 테스트 통과 확인

---

## 주요 날짜

| 날짜 | 이벤트 |
|------|--------|
| 2024 가을 | Swift 6 출시 (Xcode 16) |
| 2025년 4월 | App Store 제출 시 iOS 18 SDK 필수 |
| 2025년 9월 15일 | Swift 6.2 출시, Approachable Concurrency / `@concurrent` |
| 2026년 3월 24일 | Swift 6.3 출시 |

---

## 리소스

- [Swift 6 Migration Guide](https://www.swift.org/migration/documentation/migrationguide/)
- [WWDC 2024: Migrate to Swift 6](https://developer.apple.com/videos/play/wwdc2024/10169/)
- [WWDC 2025: Embracing Swift concurrency](https://developer.apple.com/videos/play/wwdc2025/268/)
- [Swift 6.2 Released](https://www.swift.org/blog/swift-6.2-released/)
- [Swift 6.3 Released](https://www.swift.org/blog/swift-6.3-released/)
- [SE-0413: Typed Throws](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0413-typed-throws.md)
- [SE-0461: Run nonisolated async functions on the caller's actor by default](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0461-async-function-isolation.md)
- [SE-0466: Control default actor isolation inference](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0466-control-default-actor-isolation.md)
