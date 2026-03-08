# Swift Pure DI Reference Guide

Swift Pure Dependency Injection 패턴, 구현 전략, 베스트 프랙티스 가이드입니다.

---

## Quick Index

- 핵심 개념
- 구현 패턴 (5가지)
- Pure DI vs DI Container 비교
- 아키텍처 패턴 통합
- Swift 6 Concurrency 통합
- Scope 관리
- 순환 의존성 해결
- 테스트 전략
- 안티패턴 체크리스트
- Quick Reference Card
- 리소스
- Modular DI Pattern

## 핵심 개념

### Pure DI란?

**Pure Dependency Injection**은 DI 컨테이너나 프레임워크 없이 생성자를 통해 의존성을 명시적으로 주입하는 방식입니다.

```swift
// ✅ Pure DI (명시적 주입)
class UserService {
    private let repository: UserRepository

    init(repository: UserRepository) {
        self.repository = repository
    }
}

// Composition Root에서 조립
func makeUserService() -> UserService {
    UserService(repository: APIUserRepository())
}
```

### 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **명시성** | 모든 의존성이 생성자에 드러남 |
| **컴파일 타임 안전성** | 타입 시스템이 의존성 계약 강제 |
| **Composition Root** | 객체 그래프가 단일 위치에서 구성 |
| **단순성** | 프레임워크 오버헤드 없음 |

---

## 구현 패턴 (5가지)

### 1. Composition Root 패턴 (권장 시작점)

```swift
@main
struct MyApp: App {
    private let dependencies = AppDependencies()

    var body: some Scene {
        WindowGroup {
            ContentView(viewModel: dependencies.makeContentViewModel())
        }
    }
}

final class AppDependencies {
    // Singleton 의존성
    lazy var networkService: NetworkService = URLSessionNetworkService()
    lazy var repository: Repository = RemoteRepository(networkService: networkService)

    // Factory 메서드
    func makeContentViewModel() -> ContentViewModel {
        ContentViewModel(useCase: GetItemsUseCase(repository: repository))
    }

    func makeDetailViewModel(itemId: String) -> DetailViewModel {
        DetailViewModel(itemId: itemId, repository: repository)
    }
}
```

**적합한 경우:** 소-중규모 앱, 신규 프로젝트 시작점

### 2. Factory 패턴

```swift
protocol ViewModelFactory {
    func makeUserViewModel(userId: String) -> UserViewModel
    func makeSettingsViewModel() -> SettingsViewModel
}

final class DefaultViewModelFactory: ViewModelFactory {
    private let userService: UserService
    private let settingsService: SettingsService

    init(userService: UserService, settingsService: SettingsService) {
        self.userService = userService
        self.settingsService = settingsService
    }

    func makeUserViewModel(userId: String) -> UserViewModel {
        UserViewModel(userId: userId, service: userService)
    }

    func makeSettingsViewModel() -> SettingsViewModel {
        SettingsViewModel(service: settingsService)
    }
}
```

**적합한 경우:** 대규모 앱, 복잡한 네비게이션

### 3. Protocol Witness 패턴 (테스트 최적)

```swift
struct UserClient {
    var fetch: (String) async throws -> User
    var save: (User) async throws -> Void
    var delete: (String) async throws -> Void
}

extension UserClient {
    static let live = UserClient(
        fetch: { id in try await API.fetchUser(id) },
        save: { user in try await API.saveUser(user) },
        delete: { id in try await API.deleteUser(id) }
    )

    static let mock = UserClient(
        fetch: { _ in User(id: "1", name: "Mock User") },
        save: { _ in },
        delete: { _ in }
    )

    static let failing = UserClient(
        fetch: { _ in throw TestError.intentional },
        save: { _ in throw TestError.intentional },
        delete: { _ in throw TestError.intentional }
    )
}

// 사용
final class UserViewModel {
    private let client: UserClient

    init(client: UserClient = .live) {
        self.client = client
    }
}

// 테스트
func testUserLoad() async {
    let viewModel = UserViewModel(client: .mock)
    // Mock 클래스 없이 즉시 테스트 가능
}
```

**적합한 경우:** 테스트 중심 개발, TDD

### 4. Environment 패턴 (SwiftUI)

```swift
// EnvironmentKey 정의
struct RepositoryKey: EnvironmentKey {
    static let defaultValue: Repository = InMemoryRepository()
}

extension EnvironmentValues {
    var repository: Repository {
        get { self[RepositoryKey.self] }
        set { self[RepositoryKey.self] = newValue }
    }
}

// App에서 주입
@main
struct MyApp: App {
    private let repository = RemoteRepository(
        networkService: URLSessionNetworkService()
    )

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.repository, repository)
        }
    }
}

// View에서 사용
struct ContentView: View {
    @Environment(\.repository) private var repository

    var body: some View {
        // repository 사용
    }
}

// Preview에서 Mock 주입
#Preview {
    ContentView()
        .environment(\.repository, MockRepository())
}
```

**적합한 경우:** SwiftUI 앱, Preview 지원 필요

### 5. Modular Assembly 패턴 (대규모)

```swift
// 코어 Assembly
final class CoreAssembly {
    lazy var networkClient: NetworkClient = URLSessionClient()
    lazy var database: Database = SQLiteDatabase()
    lazy var logger: Logger = ConsoleLogger()
}

// Feature Assembly
final class UserAssembly {
    private let core: CoreAssembly

    init(core: CoreAssembly) {
        self.core = core
    }

    lazy var userRepository: UserRepository = {
        RemoteUserRepository(client: core.networkClient)
    }()

    lazy var userService: UserService = {
        UserService(repository: userRepository, logger: core.logger)
    }()

    func makeUserViewModel(userId: String) -> UserViewModel {
        UserViewModel(userId: userId, service: userService)
    }
}

// 루트 Assembly
final class AppAssembly {
    let core = CoreAssembly()
    lazy var user = UserAssembly(core: core)
    lazy var order = OrderAssembly(core: core, user: user)
}
```

**적합한 경우:** 50+ 화면, 팀 분업

---

## Pure DI vs DI Container 비교

### 종합 비교표

| 측면 | Pure DI | Needle | Factory | Swinject |
|------|---------|--------|---------|----------|
| **컴파일 타임 안전성** | 10/10 | 10/10 | 8/10 | 3/10 |
| **런타임 오버헤드** | 0% | 0% | 3% | 15% |
| **메모리 영향** | 0 | 최소 | 최소 | 150KB |
| **학습 곡선** | 낮음 | 중간 | 낮음 | 중간 |
| **보일러플레이트** | 높음 (대규모) | 낮음 | 중간 | 낮음 |

### 프로젝트 규모별 권장

| 프로젝트 크기 | 권장 패턴 | 이유 |
|-------------|----------|------|
| 1-20 클래스 | **Pure DI** | 컨테이너 오버헤드 불필요 |
| 20-50 클래스 | **Factory** | 보일러플레이트 관리 |
| 50-100 클래스 | **Modular Assembly** | 구조화된 의존성 관리 |
| 100+ 클래스 | **Needle** | 코드 생성으로 정확성 보장 |

### Golden Rule

```
Start Simple (Pure DI) → Evolve as Needed (Factory) → Scale with Tooling (Needle)
```

---

## 아키텍처 패턴 통합

### MVVM + Pure DI

```swift
@Observable
@MainActor
final class UserViewModel {
    private let userService: UserServiceProtocol
    var user: User?
    var isLoading = false

    init(userService: UserServiceProtocol) {
        self.userService = userService
    }

    func loadUser(id: String) async {
        isLoading = true
        defer { isLoading = false }
        user = try? await userService.getUser(id: id)
    }
}

// SwiftUI View
struct UserView: View {
    @State private var viewModel: UserViewModel

    init(dependencies: AppDependencies, userId: String) {
        _viewModel = State(initialValue: dependencies.makeUserViewModel(userId: userId))
    }

    var body: some View {
        // ...
    }
}
```

### TCA + DependencyKey

```swift
// TCA의 내장 DI 시스템 활용
struct UserClient: DependencyKey {
    var fetch: @Sendable (String) async throws -> User
    var save: @Sendable (User) async throws -> Void

    static let liveValue = UserClient(
        fetch: { id in try await API.fetchUser(id) },
        save: { user in try await API.saveUser(user) }
    )

    static let testValue = UserClient(
        fetch: { _ in User(id: "test", name: "Test User") },
        save: { _ in }
    )
}

extension DependencyValues {
    var userClient: UserClient {
        get { self[UserClient.self] }
        set { self[UserClient.self] = newValue }
    }
}

@Reducer
struct UserFeature {
    @Dependency(\.userClient) var userClient

    // Reducer body...
}
```

### Clean Architecture + Pure DI

```swift
// Domain Layer
protocol UserRepository {
    func getUser(id: String) async throws -> User
    func saveUser(_ user: User) async throws
}

// Data Layer
final class RemoteUserRepository: UserRepository {
    private let client: NetworkClient

    init(client: NetworkClient) {
        self.client = client
    }

    func getUser(id: String) async throws -> User {
        try await client.request(UserEndpoint.get(id))
    }

    func saveUser(_ user: User) async throws {
        try await client.request(UserEndpoint.save(user))
    }
}

// Assembly
final class DataAssembly {
    private let coreAssembly: CoreAssembly

    init(coreAssembly: CoreAssembly) {
        self.coreAssembly = coreAssembly
    }

    lazy var userRepository: UserRepository = {
        RemoteUserRepository(client: coreAssembly.networkClient)
    }()
}
```

---

## Swift 6 Concurrency 통합

### Actor Isolation과 DI

```swift
actor DataStore {
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? { cache[key] }
    func set(_ key: String, data: Data) { cache[key] = data }
}

// Sendable 서비스
final class CachingService: Sendable {
    private let store: DataStore

    init(store: DataStore) {
        self.store = store
    }

    func fetchCached(_ key: String) async -> Data? {
        await store.get(key)
    }
}
```

### MainActor 바운드 의존성

```swift
@MainActor
final class AppContainer {
    private lazy var userService: UserServiceProtocol = {
        UserService(client: networkClient, store: dataStore)
    }()

    private let networkClient: NetworkClient
    private let dataStore: DataStore

    init(networkClient: NetworkClient, dataStore: DataStore) {
        self.networkClient = networkClient
        self.dataStore = dataStore
    }

    func makeUserViewModel() -> UserViewModel {
        UserViewModel(userService: userService)
    }
}
```

### Sendable 준수 전략

```swift
// ✅ Struct 사용 (권장 - 자동 Sendable)
struct UserData: Sendable {
    let id: String
    let name: String
}

// ✅ final + immutable
final class UserConfig: Sendable {
    let baseURL: URL
    let timeout: TimeInterval

    init(baseURL: URL, timeout: TimeInterval) {
        self.baseURL = baseURL
        self.timeout = timeout
    }
}

// ✅ @MainActor 격리
@MainActor
final class UIService: Sendable {
    var currentScreen: Screen?
}

// ⚠️ @unchecked Sendable (주의 - Lock 필수)
final class ThreadSafeCache: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String: Any] = [:]

    func get(_ key: String) -> Any? {
        lock.withLock { storage[key] }
    }
}
```

---

## Scope 관리

### Singleton Scope

```swift
final class CompositionRoot {
    // 앱 수명 동안 단일 인스턴스
    private lazy var _analyticsService: AnalyticsService = {
        AnalyticsService(tracker: tracker, logger: logger)
    }()

    var analyticsService: AnalyticsService { _analyticsService }
}
```

### Transient Scope

```swift
// 요청할 때마다 새 인스턴스
func makeImageLoader() -> ImageLoader {
    ImageLoader(cache: imageCache, downloader: makeDownloader())
}
```

### Session Scope

```swift
final class UserSessionScope {
    let user: AuthenticatedUser

    lazy var userPreferences: UserPreferences = {
        UserPreferences(userId: user.id)
    }()

    lazy var userAnalytics: UserAnalytics = {
        UserAnalytics(userId: user.id)
    }()

    init(user: AuthenticatedUser) {
        self.user = user
    }
}

final class SessionManager {
    private var currentSession: UserSessionScope?

    func login(user: AuthenticatedUser) {
        currentSession = UserSessionScope(user: user)
    }

    func logout() {
        currentSession = nil
    }
}
```

---

## 순환 의존성 해결

### Provider Pattern

```swift
final class OrderService {
    private let customerProvider: () -> CustomerService

    init(customerProvider: @escaping () -> CustomerService) {
        self.customerProvider = customerProvider
    }

    func processOrder(_ order: Order) {
        let customerService = customerProvider()
        let customer = customerService.getCustomer(order.customerId)
        // ...
    }
}

// Composition Root
final class CompositionRoot {
    private var _orderService: OrderService?
    private var _customerService: CustomerService?

    var orderService: OrderService {
        if let existing = _orderService { return existing }

        let service = OrderService(
            customerProvider: { [unowned self] in self.customerService }
        )
        _orderService = service
        return service
    }

    var customerService: CustomerService {
        if let existing = _customerService { return existing }

        let service = CustomerService(
            orderProvider: { [unowned self] in self.orderService }
        )
        _customerService = service
        return service
    }
}
```

### Mediator Pattern

```swift
protocol OrderCustomerMediator {
    func getCustomerForOrder(_ orderId: String) -> Customer?
    func getOrdersForCustomer(_ customerId: String) -> [Order]
}

// 서비스들이 서로 직접 참조하지 않고 Mediator 사용
final class OrderService {
    private let mediator: OrderCustomerMediator

    init(mediator: OrderCustomerMediator) {
        self.mediator = mediator
    }
}
```

---

## 테스트 전략

### Mock 생성

```swift
final class MockUserRepository: UserRepositoryProtocol {
    var users: [String: User] = [:]
    var findCallCount = 0
    var shouldThrowOnFind = false

    func find(_ id: String) async throws -> User? {
        findCallCount += 1
        if shouldThrowOnFind { throw TestError.findFailed }
        return users[id]
    }
}
```

### Test Container

```swift
final class TestContainer {
    let mockNetworkClient = MockNetworkClient()
    let mockDatabase = MockDatabase()
    let mockAnalytics = MockAnalytics()

    func makeUserService() -> UserService {
        UserService(client: mockNetworkClient)
    }
}

class IntegrationTestCase: XCTestCase {
    var container: TestContainer!

    override func setUp() {
        super.setUp()
        container = TestContainer()
    }
}
```

### Stub Builder

```swift
final class UserStubBuilder {
    private var id = "default-id"
    private var name = "Default User"
    private var email = "default@example.com"

    func with(id: String) -> Self { self.id = id; return self }
    func with(name: String) -> Self { self.name = name; return self }
    func with(email: String) -> Self { self.email = email; return self }

    func build() -> User {
        User(id: id, name: name, email: email)
    }

    static var admin: User {
        UserStubBuilder().with(name: "Admin").build()
    }
}
```

---

## 안티패턴 체크리스트

### CRITICAL (10개)

| # | 패턴 | 문제 | 해결책 |
|---|------|------|--------|
| DI1 | Service Locator | 의존성 숨김, 테스트 어려움 | Constructor Injection |
| DI2 | Ambient Context | 전역 상태, 예측 불가 | Explicit Dependencies |
| DI3 | Constructor Over-Injection | SRP 위반 (7+ 의존성) | Facade로 그룹화 |
| DI4 | Concrete Type Injection | 교체 불가, Mock 불가 | Protocol 사용 |
| DI5 | Optional Dependencies | nil 체크 필요 | Null Object Pattern |
| DI6 | Init에서 작업 수행 | 테스트 어려움, 사이드 이펙트 | Factory로 분리 |
| DI7 | God Object Container | 단일 책임 위반 | Modular Assembly |
| DI8 | 숨겨진 의존성 | Property Injection 남용 | Constructor 우선 |
| DI9 | 순환 의존성 방치 | 메모리 릭, 복잡도 | Provider/Mediator |
| DI10 | Non-Sendable across actors | 데이터 레이스 | Sendable 준수 |

### 탐지 패턴 (grep/검색용)

```
# Service Locator 안티패턴
Container\.shared\.resolve
ServiceLocator\.shared
Resolver\.resolve

# Ambient Context 안티패턴
static\s+var\s+current
static\s+let\s+shared.*=.*\(\)
AppContext\.\w+

# Constructor Over-Injection (7+ 파라미터)
init\([^)]*,[^)]*,[^)]*,[^)]*,[^)]*,[^)]*,[^)]*

# Optional Dependencies
init\(.*:\s*\w+\?\s*=\s*nil

# Concrete Type Injection
init\(.*:\s*(?!any\s+|some\s+)[A-Z]\w+(?!Protocol)\)
```

---

## Quick Reference Card

### 패턴 선택 플로우

```
프로젝트 시작?
├─ Yes → Composition Root
│        └─ 성장 시 Factory 추가
└─ No → 현재 규모?
         ├─ <50 클래스 → Pure DI 유지
         └─ >50 클래스 → Container 검토
                        └─ 타입 안전 필요? → Needle
                           └─ 아니면 → Factory/Resolver
```

### Injection 방식 비교

| 방식 | 권장도 | 사용 시점 |
|------|--------|----------|
| Constructor Injection | ⭐⭐⭐⭐⭐ | 기본 (95%) |
| Method Injection | ⭐⭐⭐ | 호출마다 다른 의존성 |
| Property Injection | ⭐⭐ | 순환 의존성 해결용 |

### 체크리스트

```
□ Constructor Injection 사용
□ 모든 의존성 Protocol 추상화
□ Composition Root 단일 위치
□ Service Locator 미사용
□ 전역 상태 최소화
□ 의존성 그래프 단방향
□ 클래스당 의존성 5개 이하
□ Swift 6 Sendable 준수
□ Preview용 Mock 준비
```

---

## 리소스

- **Dependency Injection Principles, Practices, and Patterns** - Mark Seemann
- **Swift 6 Concurrency Documentation** - Apple
- **TCA Dependencies Documentation** - Point-Free

---

## Modular DI Pattern (대규모 앱)

50+ 클래스 규모의 앱을 위한 Modular DI 아키텍처입니다. 위의 "Modular Assembly 패턴"의 확장판으로, Swift 6 Concurrency를 완벽히 지원합니다.

### Module Structure

```
App/
├── Core/                    # Protocol 정의만 (구현체 없음)
│   └── Protocols/
│       ├── NetworkServiceProtocol.swift
│       ├── SecureStorageProtocol.swift
│       └── UserIdProviding.swift   # 모듈 간 연결용 작은 Protocol
├── ServiceModules/
│   ├── AuthModule/
│   │   ├── Public/          # Interface + Assembly
│   │   └── Internal/        # 구현체 (외부 노출 X)
│   ├── PaymentModule/
│   └── AnalyticsModule/
└── App/                     # Composition Root
    ├── CompositionRoot/
    │   ├── AppDependencies.swift
    │   └── Adapters.swift   # 모듈 간 연결
    └── Infrastructure/      # Core Protocol 구현체
```

### 핵심 원칙

1. **Service 모듈은 서로 직접 의존하지 않음** - Core Protocol로만 연결
2. **모든 모듈은 Core만 의존**
3. **모든 Protocol은 `Sendable` 준수**
4. **App에서 Adapter로 모듈 간 연결**

### Assembly Pattern

```swift
// AuthModule/Public/AuthAssembly.swift
public struct AuthAssembly {
    public struct Dependencies {
        public let network: NetworkServiceProtocol
        public let secureStorage: SecureStorageProtocol
        public init(network: NetworkServiceProtocol, secureStorage: SecureStorageProtocol) { ... }
    }

    public init(dependencies: Dependencies) { ... }

    /// 모듈의 Public Interface 반환 (구현체 타입 노출 X)
    public func assemble() -> AuthManaging { AuthManager(...) }
}

// Internal 구현체 - Actor 기반
actor AuthManager: AuthManaging {
    private let network: NetworkServiceProtocol
    // ...
}
```

### Adapter로 모듈 연결

```swift
// App/CompositionRoot/Adapters.swift
struct AuthUserIdAdapter: UserIdProviding {
    let auth: AuthManaging
    var currentUserId: String? {
        get async { await auth.currentUser?.id }
    }
}

// PaymentModule은 Auth 직접 의존 없이 UserIdProviding으로 연결
```

### Composition Root

```swift
@MainActor
final class AppDependencies {
    // Infrastructure
    private let network: NetworkServiceProtocol
    private let secureStorage: SecureStorageProtocol

    // Public Services
    let auth: AuthManaging
    let payment: PaymentProcessing

    init() {
        // 1. Infrastructure 생성
        self.network = NetworkService(...)
        self.secureStorage = KeychainStorage()

        // 2. 독립 모듈 조립
        self.auth = AuthAssembly(dependencies: .init(...)).assemble()

        // 3. 의존 모듈 조립 (Adapter로 연결)
        self.payment = PaymentAssembly(
            dependencies: .init(
                network: network,
                userIdProvider: AuthUserIdAdapter(auth: auth)
            )
        ).assemble()
    }

    // ViewModel Factory
    func makeHomeViewModel() -> HomeViewModel { ... }
}
```

### SwiftUI Integration

```swift
// Environment 정의 (Swift 5.9+ @Entry 매크로)
extension EnvironmentValues {
    @Entry var dependencies: AppDependencies?
}

// App Entry Point
@main
struct MyApp: App {
    private let dependencies = AppDependencies()
    var body: some Scene {
        WindowGroup {
            RootView().environment(\.dependencies, dependencies)
        }
    }
}

// View에서 사용
struct ProfileView: View {
    @Environment(\.dependencies) private var dependencies
    // dependencies?.auth.signOut()
}
```

### Testing Strategy

```swift
// Mock: @unchecked Sendable + handler 패턴
final class MockNetworkService: NetworkServiceProtocol, @unchecked Sendable {
    var requestHandler: ((Endpoint) async throws -> Any)?
    func request<T: Decodable>(_ endpoint: Endpoint) async throws -> T {
        try await requestHandler?(endpoint) as! T
    }
}

// Assembly 단위 테스트
@MainActor
func testSignIn() async throws {
    let mockNetwork = MockNetworkService()
    mockNetwork.requestHandler = { _ in User(id: "1", ...) }

    let auth = AuthAssembly(dependencies: .init(
        network: mockNetwork,
        secureStorage: MockSecureStorage()
    )).assemble()

    let user = try await auth.signIn(email: "test@test.com", password: "1234")
    XCTAssertTrue(await auth.isAuthenticated)
}
```

### Checklist

```
새 Service 모듈:
□ Public Interface Protocol 생성 (Sendable 준수)
□ Assembly struct + Dependencies struct 정의
□ assemble()이 Public Interface 반환 (구현체 타입 X)
□ Internal 구현체는 Actor로 구현
□ 다른 모듈 필요시 Core에 작은 Protocol 추가

Composition Root:
□ Infrastructure 먼저 생성
□ 독립 모듈 → 의존 모듈 순서로 조립
□ 모듈 간 연결은 Adapter 사용
□ Testable init 제공

테스트:
□ Mock은 @unchecked Sendable + handler 패턴
□ Assembly 통해 모듈 단위 테스트
□ @MainActor 어노테이션 적용
```
