# SwiftData Reference Guide

SwiftData 베스트 프랙티스, 안티패턴, 스레딩 가이드입니다.

---

## CRITICAL 안티패턴

### 1. 모델 상속 금지

```swift
// ❌ CRITICAL: 절대 하지 마세요 - 크래시 발생
class BaseModel {
    var id: UUID
}

@Model
class MyModel: BaseModel { // ❌ 상속 금지!
    var name: String
}

// ✅ CORRECT: final class 사용
@Model
final class MyModel {
    var id: UUID
    var name: String
}
```

### 2. 배열 대신 관계 사용

```swift
// ❌ WRONG: 쿼리 불가, Codable blob으로 저장
@Model
final class Author {
    var bookTitles: [String] = [] // ❌ 검색/필터 불가
}

// ✅ CORRECT: @Relationship 사용
@Model
final class Author {
    @Relationship(deleteRule: .cascade)
    var books: [Book] = []
}

@Model
final class Book {
    var title: String

    @Relationship(inverse: \Author.books)
    var author: Author?
}
```

### 3. 중복 삽입 금지

```swift
// ❌ FATAL ERROR: 이미 삽입된 객체 재삽입
let author = Author(name: "John")
let book = Book(title: "Swift Guide")
author.books.append(book)

modelContext.insert(author)
modelContext.insert(book) // ❌ Fatal error!

// ✅ CORRECT: 루트 객체만 삽입
let author = Author(name: "John")
let book = Book(title: "Swift Guide")
author.books.append(book)

modelContext.insert(author) // book도 자동으로 삽입됨
```

### 4. Delete Rule과 Optional 매칭

```swift
// ❌ DANGEROUS: nullify인데 non-optional
@Model
final class Order {
    @Relationship(deleteRule: .nullify)
    var customer: Customer // ❌ 삭제 후 nil 되면 크래시
}

// ✅ CORRECT: 매칭되게 설정
@Model
final class Order {
    // cascade: 주문 삭제 시 항목도 삭제
    @Relationship(deleteRule: .cascade)
    var items: [OrderItem] = []

    // nullify: 고객 삭제 시 nil로 설정 (optional)
    @Relationship(deleteRule: .nullify)
    var customer: Customer?

    // deny: 활성 주문 있으면 삭제 거부
    @Relationship(deleteRule: .deny)
    var activeDelivery: Delivery?
}
```

### 5. 배열 순서 보장 안됨

```swift
// ⚠️ WARNING: SwiftData가 순서를 임의로 변경함
@Model
final class Playlist {
    var songs: [Song] = [] // 순서 보장 안됨!
}

// ✅ WORKAROUND: 명시적 순서 필드
@Model
final class Song {
    var title: String
    var orderIndex: Int // 순서 명시
}

// 정렬된 접근
extension Playlist {
    var orderedSongs: [Song] {
        songs.sorted { $0.orderIndex < $1.orderIndex }
    }
}
```

---

## 스레딩 & 동시성

### Sendable 여부

| 타입 | Sendable | 설명 |
|------|----------|------|
| ModelContainer | ✅ | Actor 간 공유 가능 |
| PersistentIdentifier | ✅ | 모델 참조로 사용 |
| @Model 인스턴스 | ❌ | Context에 종속 |
| ModelContext | ❌ | 스레드 종속 |

### Background 작업 패턴

```swift
// ✅ CORRECT: @ModelActor 사용
@ModelActor
actor DatabaseManager {
    func fetchUsers() -> [UserDTO] {
        let descriptor = FetchDescriptor<User>()
        let users = (try? modelContext.fetch(descriptor)) ?? []

        // DTO로 변환하여 반환 (Sendable)
        return users.map { UserDTO(id: $0.persistentModelID, name: $0.name) }
    }

    func createUser(name: String) {
        let user = User(name: name)
        modelContext.insert(user)
        try? modelContext.save()
    }
}

// Sendable DTO
struct UserDTO: Sendable {
    let id: PersistentIdentifier
    let name: String
}
```

### PersistentIdentifier로 모델 전달

```swift
// ❌ WRONG: 모델 직접 전달
@MainActor
func displayUser(_ user: User) { // User는 Sendable 아님!
    print(user.name)
}

// ✅ CORRECT: ID 전달 후 재조회
@MainActor
func displayUser(id: PersistentIdentifier, container: ModelContainer) {
    let context = ModelContext(container)
    guard let user = context.model(for: id) as? User else { return }
    print(user.name)
}

// 호출
let userId = user.persistentModelID
await displayUser(id: userId, container: container)
```

### ModelContext 생성 규칙

```swift
// ✅ CORRECT: 각 Actor에서 Context 생성
actor BackgroundProcessor {
    let container: ModelContainer

    func process() async {
        // Actor 스레드에서 Context 생성
        let context = ModelContext(container)

        let descriptor = FetchDescriptor<Item>()
        let items = try? context.fetch(descriptor)
        // 처리...
    }
}

// ✅ CORRECT: MainActor에서 메인 Context
@MainActor
class ViewModel {
    let container: ModelContainer
    private var context: ModelContext!

    init(container: ModelContainer) {
        self.container = container
        self.context = ModelContext(container)
    }
}
```

---

## 쿼리 패턴

### FetchDescriptor 사용

```swift
// 기본 fetch
var descriptor = FetchDescriptor<User>()
let users = try modelContext.fetch(descriptor)

// Predicate 사용
let predicate = #Predicate<User> { user in
    user.age > 18 && user.isActive
}
descriptor = FetchDescriptor<User>(predicate: predicate)

// 정렬
descriptor.sortBy = [
    SortDescriptor(\.createdAt, order: .reverse)
]

// 제한
descriptor.fetchLimit = 20
descriptor.fetchOffset = 0
```

### 복잡한 쿼리

```swift
// AND 조건
let predicate = #Predicate<User> { user in
    user.name.contains("John") && user.age >= 18
}

// OR 조건
let predicate = #Predicate<User> { user in
    user.role == "admin" || user.role == "moderator"
}

// 관계 쿼리
let predicate = #Predicate<Author> { author in
    author.books.count > 5
}

// 옵셔널 처리
let predicate = #Predicate<User> { user in
    if let email = user.email {
        email.contains("@company.com")
    } else {
        false
    }
}
```

### @Query in SwiftUI

```swift
struct UserListView: View {
    @Query(
        filter: #Predicate<User> { $0.isActive },
        sort: \.createdAt,
        order: .reverse
    )
    private var users: [User]

    var body: some View {
        List(users) { user in
            UserRow(user: user)
        }
    }
}

// 동적 필터링
struct SearchableUserList: View {
    @State private var searchText = ""

    var body: some View {
        UserListView(searchText: searchText)
    }
}

struct UserListView: View {
    let searchText: String

    @Query private var users: [User]

    init(searchText: String) {
        self.searchText = searchText
        let predicate = #Predicate<User> { user in
            searchText.isEmpty || user.name.localizedStandardContains(searchText)
        }
        _users = Query(filter: predicate, sort: \.name)
    }

    var body: some View {
        List(users) { user in
            Text(user.name)
        }
    }
}
```

---

## 모델 설계 베스트 프랙티스

### 기본 모델 구조

```swift
@Model
final class User {
    // 필수: 고유 식별자
    @Attribute(.unique)
    var id: UUID

    // 일반 프로퍼티
    var name: String
    var email: String
    var createdAt: Date

    // 옵셔널
    var avatarURL: URL?

    // Computed (저장 안됨)
    var displayName: String {
        email.isEmpty ? name : "\(name) (\(email))"
    }

    // 관계
    @Relationship(deleteRule: .cascade, inverse: \Post.author)
    var posts: [Post] = []

    init(name: String, email: String) {
        self.id = UUID()
        self.name = name
        self.email = email
        self.createdAt = Date()
    }
}
```

### 관계 설정

```swift
// 일대다 (One-to-Many)
@Model
final class Author {
    @Relationship(deleteRule: .cascade, inverse: \Book.author)
    var books: [Book] = []
}

@Model
final class Book {
    var author: Author?
}

// 다대다 (Many-to-Many)
@Model
final class Student {
    @Relationship(inverse: \Course.students)
    var courses: [Course] = []
}

@Model
final class Course {
    @Relationship(inverse: \Student.courses)
    var students: [Student] = []
}

// 자기 참조 (Self-referential)
@Model
final class Category {
    var name: String

    @Relationship(inverse: \Category.children)
    var parent: Category?

    @Relationship(deleteRule: .cascade, inverse: \Category.parent)
    var children: [Category] = []
}
```

### Delete Rules 가이드

| Rule | 효과 | 사용 시점 |
|------|------|-----------|
| `.cascade` | 관련 객체도 삭제 | 부모-자식 관계 |
| `.nullify` | 관계를 nil로 설정 | 선택적 관계 |
| `.deny` | 관계 있으면 삭제 거부 | 참조 무결성 |
| `.noAction` | 아무것도 안함 | 수동 관리 |

---

## Preview & Testing

### Preview용 In-Memory Container

```swift
struct SampleDataPreview: PreviewModifier {
    static func makeSharedContext() throws -> ModelContainer {
        let schema = Schema([User.self, Post.self])
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: schema, configurations: [config])

        // 샘플 데이터 삽입
        let user = User(name: "Sample User", email: "sample@test.com")
        container.mainContext.insert(user)

        let post = Post(title: "Hello World", content: "...")
        post.author = user
        container.mainContext.insert(post)

        return container
    }

    func body(content: Content, context: ModelContainer) -> some View {
        content.modelContainer(context)
    }
}

#Preview(traits: .modifier(SampleDataPreview())) {
    ContentView()
}
```

### Unit Testing

```swift
@MainActor
final class UserTests: XCTestCase {
    var container: ModelContainer!
    var context: ModelContext!

    override func setUp() async throws {
        let schema = Schema([User.self])
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try ModelContainer(for: schema, configurations: [config])
        context = container.mainContext
    }

    func testCreateUser() throws {
        let user = User(name: "Test", email: "test@test.com")
        context.insert(user)
        try context.save()

        let descriptor = FetchDescriptor<User>()
        let users = try context.fetch(descriptor)

        XCTAssertEqual(users.count, 1)
        XCTAssertEqual(users.first?.name, "Test")
    }
}
```

---

## 안티패턴 체크리스트

| # | 패턴 | 증상 | 수정 |
|---|------|------|------|
| SD1 | Model Subclassing | 크래시 | final class |
| SD2 | Array of Primitives | 쿼리 불가 | @Relationship |
| SD3 | Duplicate Insert | Fatal Error | 루트만 insert |
| SD4 | Wrong Delete Rule | 데이터 불일치 | optionality 매칭 |
| SD5 | Cross-Actor Model | 크래시 | PersistentIdentifier |
| SD6 | Shared ModelContext | 스레드 위반 | Actor당 생성 |
| SD7 | Array Order Assumption | 순서 변경 | orderIndex |
| SD8 | No @ModelActor | 스레드 위반 | @ModelActor |
| SD9 | Access After Delete | 크래시 | 삭제 전 검증 |
| SD10 | Missing Inverse | 데이터 불일치 | inverse 명시 |
| SD11 | Large Blob Storage | 성능 저하 | 외부 파일 참조 |
| SD12 | No Index | 느린 쿼리 | @Attribute(.unique) |
| SD13 | Lazy Load Assumption | 예상외 로드 | 명시적 fetch |
| SD14 | Context.rollback Misuse | 상태 불일치 | 새 Context 생성 |
| SD15 | Missing save() | 데이터 손실 | 명시적 save |

---

## 마이그레이션

### 스키마 버전 관리

```swift
enum SchemaV1: VersionedSchema {
    static var versionIdentifier = Schema.Version(1, 0, 0)
    static var models: [any PersistentModel.Type] = [UserV1.self]

    @Model
    final class UserV1 {
        var name: String
    }
}

enum SchemaV2: VersionedSchema {
    static var versionIdentifier = Schema.Version(2, 0, 0)
    static var models: [any PersistentModel.Type] = [User.self]

    @Model
    final class User {
        var name: String
        var email: String = "" // 새 필드
    }
}

enum UserMigrationPlan: SchemaMigrationPlan {
    static var schemas: [any VersionedSchema.Type] = [SchemaV1.self, SchemaV2.self]

    static var stages: [MigrationStage] = [
        .lightweight(fromVersion: SchemaV1.self, toVersion: SchemaV2.self)
    ]
}

// Container 설정
let container = try ModelContainer(
    for: User.self,
    migrationPlan: UserMigrationPlan.self
)
```

### 커스텀 마이그레이션

```swift
static var stages: [MigrationStage] = [
    .custom(
        fromVersion: SchemaV1.self,
        toVersion: SchemaV2.self
    ) { context in
        let users = try context.fetch(FetchDescriptor<SchemaV1.UserV1>())
        for user in users {
            // 데이터 변환 로직
            user.email = "\(user.name.lowercased())@legacy.com"
        }
        try context.save()
    }
]
```
