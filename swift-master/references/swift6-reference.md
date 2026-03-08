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

### 3. Swift 6.2 변경사항

```swift
// 기본값: Main Thread 실행
// @concurrent 명시로 백그라운드 실행
@concurrent
func heavyWork() async -> Int {
    // 백그라운드에서 실행
    return expensiveCalculation()
}

// MainActor 코드는 그대로
@MainActor
func updateUI() {
    // UI 업데이트
}
```

---

## 마이그레이션 단계

### Step 1: Strict Concurrency Checking 점진적 활성화

```
Build Settings → Swift Compiler → Strict Concurrency Checking

1. Minimal (기본) - 기본 검사만
2. Targeted - 명시적 async 코드 검사
3. Complete - 모든 코드 검사 (Swift 6 모드)
```

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

// ✅ 방법 3: nonisolated(unsafe) - 최후의 수단
// 반드시 외부에서 동기화 보장 필요
nonisolated(unsafe) var legacyCache: [String: Data] = [:]
```

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

// ✅ 방법 4: @unchecked Sendable (주의)
final class ThreadSafeUserData: @unchecked Sendable {
    private let lock = NSLock()
    private var _name: String

    var name: String {
        lock.withLock { _name }
    }
}
```

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

// 또는 wrapper 생성
struct LegacyWrapper: @unchecked Sendable {
    let legacy: LegacyObject
}
```

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

    func loadItems() async {
        let data = await fetchItems() // 백그라운드
        items = data // MainActor 보장
    }

    nonisolated func fetchItems() async -> [Item] {
        // 백그라운드에서 실행
        return await networkService.fetch()
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

    // 네트워크 요청도 nonisolated
    nonisolated func fetchData() async throws -> Data {
        try await URLSession.shared.data(from: url).0
    }
}
```

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
| S64 | @unchecked without Sync | `@unchecked Sendable` | Lock 추가 확인 |
| S65 | Missing @MainActor | UI class 격리 없음 | `@MainActor` |
| S66 | Typed Throws Nesting | 중첩된 typed throws | 레이어별 에러 |
| S67 | Legacy Callback Isolation | callback executor 불일치 | `assumeIsolated` |
| S68 | Non-Sendable Default | 기본값이 non-Sendable | Sendable 타입 |
| S69 | Isolated Parameter Misuse | `isolated` 파라미터 오용 | isolation 명시 |
| S610 | Task.detached Overuse | `Task.detached` 남용 | `Task` 사용 |

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
- [ ] Strict Concurrency = Minimal 설정
- [ ] 빌드 성공 확인

### Phase 2: 점진적 마이그레이션

- [ ] Strict Concurrency = Targeted 설정
- [ ] 경고 수정
  - [ ] Sendable 준수 추가
  - [ ] @MainActor 격리
  - [ ] 전역 상태 Actor로 변환

### Phase 3: Complete 모드

- [ ] Strict Concurrency = Complete 설정
- [ ] 모든 경고/에러 수정
- [ ] @preconcurrency import 최소화

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
| 2025년 9월 | Swift 6.2 출시 예정 |

---

## 리소스

- [Swift 6 Migration Guide](https://www.swift.org/migration/documentation/migrationguide/)
- [WWDC 2024: Migrate to Swift 6](https://developer.apple.com/videos/play/wwdc2024/10169/)
- [SE-0413: Typed Throws](https://github.com/apple/swift-evolution/blob/main/proposals/0413-typed-throws.md)
