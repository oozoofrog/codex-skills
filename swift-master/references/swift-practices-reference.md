# Swift Practices Reference Guide

Swift 코드 품질을 높이기 위한 예시 중심 실전 가이드입니다. 짧은 규칙보다 실제 적용 패턴, 문서화, 에러 처리, 타입 설계, 테스트 패턴을 코드 예시와 함께 다룹니다.

---

## 이 문서의 역할

- `swift-conventions-reference.md`의 규칙을 실제 코드에 적용하는 예시를 제공하기
- 문서화, 에러 처리, 타입 설계, 테스트 전략처럼 설명이 필요한 주제를 다루기
- 짧은 규칙 확인이 목적이면 `swift-conventions-reference.md`를 먼저 읽기

## Quick Index

- Documentation Standards
- Error Handling Patterns
- Type Design Principles
- Testing Considerations

---

## Documentation Standards

### DocC Comments
```swift
/// 공개 API에 한 줄 요약
///
/// 더 자세한 설명이 필요하면 빈 줄 후 작성
/// - Parameters:
///   - param1: 파라미터 설명
///   - param2: 파라미터 설명
/// - Returns: 반환값 설명
/// - Throws: 발생 가능한 에러
///
/// ```swift
/// // 사용 예시
/// let result = try await method(param1, param2)
/// ```
public func method(_ param1: String, _ param2: Int) async throws -> Result
```

### Inline Comments
```swift
// 복잡한 로직 설명: "왜 이렇게 했는가?"
// ❌ // i는 인덱스
// ✅ // 역순으로 처리하여 삭제 중 인덱스 변경 방지
for i in (0..<items.count).reversed() {
    items.remove(at: i)
}
```

### Magic Numbers 피하기
```swift
// ❌
if retries > 3 {
    // ...
}

// ✅
let maxRetryCount = 3
if retries > maxRetryCount {
    // ...
}
```

---

## Error Handling Patterns

### Custom Error Types
```swift
enum NetworkError: LocalizedError {
    case invalidURL
    case noResponse
    case decodingError(DecodingError)
    case serverError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "URL이 유효하지 않습니다"
        case .noResponse:
            return "서버 응답이 없습니다"
        case .decodingError:
            return "응답 파싱에 실패했습니다"
        case .serverError(let code):
            return "서버 오류: \(code)"
        }
    }
}
```

### Recovery Strategies
```swift
// 복구 가능한 에러
do {
    let data = try await fetch()
} catch NetworkError.noResponse {
    // 재시도 또는 캐시 사용
    return try await fetchFromCache()
} catch NetworkError.decodingError {
    // 스키마 변경 감지 - 사용자 안내
    logger.warning("API 스키마 변경됨")
}

// 복구 불가능한 에러
catch let error as DecodingError {
    // 로깅 후 사용자 알림
    logger.error("프로그래밍 오류", error: error)
    throw FatalError.invalidSchema
}
```

### Error Propagation
```swift
// async/throws 일관되게 사용
func load() async throws {
    let data = try await repository.fetch()  // ✅
    workouts = try parse(data)
}

// Result 타입도 일관되게 사용
func loadWithResult() -> Result<[Workout], Error> {
    // ...
}
```

---

## Type Design Principles

### Value Types Preference
```swift
// ✅ Struct (Value type) - 대부분의 모델
struct Workout {
    var id: UUID
    var name: String
    var duration: TimeInterval
}

// ✅ Enum (Value type) - 상태/선택
enum LoadState {
    case idle
    case loading
    case success([Workout])
    case failure(Error)
}

// ⚠️ Class (Reference type) - 꼭 필요한 경우만
class WorkoutRepository {
    // 디스크/네트워크 접근 등 부작용이 있는 경우
}
```

### Singleton Minimization
```swift
// ❌ 싱글톤 - 테스트 어려움
class UserManager {
    static let shared = UserManager()
}

// ✅ Protocol로 추상화 + DI
protocol UserProvider {
    func getCurrentUser() async throws -> User
}

class ViewController {
    init(userProvider: UserProvider) {
        self.userProvider = userProvider
    }
}
```

### Global State Avoidance
```swift
// ❌ 전역 상태
var currentUser: User?
var appConfig: AppConfiguration?

// ✅ 명시적 의존성
@MainActor
@Observable
class AppState {
    var currentUser: User?
    var config: AppConfiguration

    init(config: AppConfiguration) {
        self.config = config
    }
}

struct ContentView {
    @State private var appState: AppState
}
```

### Immutability Preference
```swift
// ✅ let 우선
let user = User(id: 1, name: "John")
let items = loadItems()

// var는 필요할 때만
var counter = 0
counter += 1

// 컬렉션 수정 필요시 함수형
let filtered = items.filter { $0.isActive }
let mapped = filtered.map { $0.name }
```

---

## Testing Considerations

### Test Doubles Strategy
```swift
// ✅ Fake - 실제 구현의 간단한 버전
class FakeUserRepository: UserRepository {
    var users: [User] = []

    func fetch() async throws -> [User] {
        users
    }

    func save(_ user: User) async throws {
        users.append(user)
    }
}

// ✅ Spy - 호출 기록
class SpyAnalytics: Analytics {
    var loggedEvents: [String] = []

    func log(_ event: String) {
        loggedEvents.append(event)
    }
}

// ⚠️ Mock - 복잡한 기대값 설정 (신중하게 사용)
let mock = Mock<UserRepository>()
mock.expect.fetch().andReturn([testUser])
```

### Time-Dependent Code
```swift
// ❌ 시간 의존 - 테스트 불가능
func isExpired(_ date: Date) -> Bool {
    Date.now > date.addingTimeInterval(3600)
}

// ✅ Clock protocol 주입
protocol Clock {
    func now() -> Date
}

func isExpired(_ date: Date, clock: Clock) -> Bool {
    clock.now() > date.addingTimeInterval(3600)
}

// 테스트
let fixedClock = FixedClock(now: Date(timeIntervalSince1970: 1000))
XCTAssertTrue(isExpired(Date(timeIntervalSince1970: 0), clock: fixedClock))
```

### Swift Testing Framework (권장)
```swift
import Testing

@Test
func testWorkoutLoad() async {
    let repository = FakeWorkoutRepository(workouts: [.mock])
    let viewModel = WorkoutViewModel(repository: repository)

    await viewModel.load()

    #expect(viewModel.workouts.count == 1)
    #expect(viewModel.isLoading == false)
}

@Test("음수 개수 입력 실패", .tags(.validation))
func testNegativeCountFails() {
    let result = calculateCalories(count: -5)

    #expect(throws: ValidationError.self) {
        try result.get()
    }
}
```
