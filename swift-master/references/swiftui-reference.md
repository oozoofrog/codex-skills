# SwiftUI Reference Guide (iOS 17-18)

SwiftUI 베스트 프랙티스, 안티패턴, 마이그레이션 가이드입니다.

---

## Quick Index

- `@Observable` 마이그레이션
- 상태 관리 Property Wrappers
- `@Bindable` 사용법
- Navigation (`NavigationStack`)
- 안티패턴 체크리스트
- 성능 최적화
- 마이그레이션 가이드
- Thread Safety
- Design System

## @Observable 마이그레이션 (iOS 17+)

### Before (ObservableObject)

```swift
class ViewModel: ObservableObject {
    @Published var username: String = ""
    @Published var isLoading: Bool = false
}

struct ContentView: View {
    @StateObject private var viewModel = ViewModel()

    var body: some View {
        TextField("Username", text: $viewModel.username)
    }
}
```

### After (@Observable)

```swift
@Observable
final class ViewModel {
    var username: String = ""
    var isLoading: Bool = false
    // @Published 필요 없음 - 모든 프로퍼티 자동 관찰
}

struct ContentView: View {
    @State private var viewModel = ViewModel()

    var body: some View {
        TextField("Username", text: $viewModel.username)
    }
}
```

### @Observable 장점

| 기능 | ObservableObject | @Observable |
|------|------------------|-------------|
| 옵셔널 추적 | ❌ | ✅ |
| 컬렉션 요소 추적 | ❌ | ✅ |
| 세밀한 뷰 업데이트 | ❌ (전체 갱신) | ✅ (변경된 것만) |
| 보일러플레이트 | @Published 필요 | 없음 |

---

## 상태 관리 Property Wrappers

### iOS 17+ 권장 패턴

| 상황 | Property Wrapper | 설명 |
|------|------------------|------|
| 값 타입 소유 | `@State` | View가 소유하는 값 타입 |
| 값 타입 바인딩 | `@Binding` | 부모로부터 전달받은 값 타입 |
| @Observable 소유 | `@State` | View가 생성하는 @Observable 객체 |
| @Observable 바인딩 | `@Bindable` | 전달받은 @Observable 객체의 바인딩 생성 |
| 환경 객체 | `@Environment` | DI로 주입받는 객체 |

### CRITICAL: @State는 App 레벨에서 선언

```swift
// ❌ WRONG: View에서 @State로 클래스 인스턴스 생성
struct ContentView: View {
    @State private var viewModel = ViewModel() // View 재생성 시 문제!
}

// ✅ CORRECT: App 레벨에서 생성, 환경으로 주입
@main
struct MyApp: App {
    @State private var appState = AppState() // App 수명과 동일

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(appState)
        }
    }
}

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        // appState 사용
    }
}
```

---

## @Bindable 사용법

```swift
@Observable
final class User {
    var name: String = ""
    var email: String = ""
}

// 부모 View
struct ParentView: View {
    @State private var user = User()

    var body: some View {
        // @Bindable 없이 직접 $user 사용 가능
        ChildView(user: user)
    }
}

// 자식 View - @Bindable 필요
struct ChildView: View {
    @Bindable var user: User // @Observable 객체의 바인딩 생성

    var body: some View {
        Form {
            TextField("Name", text: $user.name)   // $user.name 사용 가능
            TextField("Email", text: $user.email)
        }
    }
}
```

### @Binding vs @Bindable

| | @Binding | @Bindable |
|---|----------|-----------|
| 대상 | 값 타입 | @Observable 참조 타입 |
| 소유권 | 부모가 소유 | 객체 자체는 다른 곳에서 소유 |
| 사용 | `$property` 전달 | 객체 직접 전달 후 `$` 사용 |

---

## Navigation (iOS 16+)

### NavigationStack 기본

```swift
struct ContentView: View {
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            List {
                NavigationLink("Go to Detail", value: "detail")
            }
            .navigationDestination(for: String.self) { value in
                DetailView(id: value)
            }
        }
    }
}
```

### Type-Safe Routing (권장)

```swift
enum Route: Hashable {
    case detail(id: String)
    case settings
    case profile(user: User)
}

struct ContentView: View {
    @State private var path: [Route] = []

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Button("Go to Settings") {
                    path.append(.settings)
                }
                Button("Go to Detail") {
                    path.append(.detail(id: "123"))
                }
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .detail(let id):
                    DetailView(id: id)
                case .settings:
                    SettingsView()
                case .profile(let user):
                    ProfileView(user: user)
                }
            }
        }
    }
}

// 프로그래매틱 네비게이션
extension ContentView {
    func navigateToDetail(_ id: String) {
        path.append(.detail(id: id))
    }

    func popToRoot() {
        path.removeAll()
    }

    func pop() {
        path.removeLast()
    }
}
```

### Router Pattern (대규모 앱)

```swift
@Observable
final class Router {
    var path = NavigationPath()

    func navigate<T: Hashable>(to route: T) {
        path.append(route)
    }

    func pop() {
        guard !path.isEmpty else { return }
        path.removeLast()
    }

    func popToRoot() {
        path.removeLast(path.count)
    }
}

// App에서 환경으로 주입
@main
struct MyApp: App {
    @State private var router = Router()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(router)
        }
    }
}
```

---

## 안티패턴 체크리스트 (20개)

### CRITICAL (10개)

| # | 패턴 | 탐지 | 수정 |
|---|------|------|------|
| SC1 | @State with Reference Type | `@State.*= \w+\(` | App 레벨 또는 @Observable |
| SC2 | @Published in @Observable | `@Published.*@Observable` | @Published 제거 |
| SC3 | @StateObject with @Observable | `@StateObject` + `@Observable` | @State 사용 |
| SC4 | Force Unwrap | `\.self!`, `as!` | Optional binding |
| SC5 | Heavy body Computation | body 내 복잡한 로직 | .task 또는 computed property |
| SC6 | ViewModel SwiftUI API | ViewModel에서 withAnimation 등 | View 내에서 처리 |
| SC7 | Deprecated NavigationLink | `NavigationLink(destination:` | NavigationStack |
| SC8 | Missing @Environment | @Environment nil 접근 | 주입 확인 |
| SC9 | View State in ViewModel | ViewModel에 isPresented 등 | View @State |
| SC10 | ObservableObject in iOS 17+ | class: ObservableObject | @Observable |

### WARNING (10개)

| # | 패턴 | 탐지 | 권장 |
|---|------|------|------|
| SW1 | Large View body | body 100줄 이상 | 하위 View 추출 |
| SW2 | Inline Closures | 복잡한 inline closure | 메서드 추출 |
| SW3 | Magic Numbers | 하드코딩된 수치 | 상수 또는 환경값 |
| SW4 | Missing Accessibility | accessibilityLabel 없음 | 접근성 추가 |
| SW5 | Hardcoded Colors | Color(.red) 직접 사용 | Asset Catalog 또는 semantic |
| SW6 | Excessive Modifiers | 10개 이상 modifier 체인 | ViewModifier 추출 |
| SW7 | onAppear Heavy Work | onAppear에서 동기 작업 | .task 사용 |
| SW8 | GeometryReader Overuse | 불필요한 GeometryReader | 레이아웃 시스템 활용 |
| SW9 | AnyView Usage | 타입 소거로 성능 저하 | @ViewBuilder 또는 조건부 |
| SW10 | Missing Preview | #Preview 없음 | Preview 추가 |

---

## 성능 최적화

### View 재렌더링 최소화

```swift
// ❌ BAD: body에서 무거운 계산
var body: some View {
    let processed = items.filter { $0.isValid }.sorted() // 매번 실행
    List(processed) { item in
        ItemRow(item: item)
    }
}

// ✅ GOOD: 캐싱
@State private var processedItems: [Item] = []

var body: some View {
    List(processedItems) { item in
        ItemRow(item: item)
    }
    .task {
        processedItems = items.filter { $0.isValid }.sorted()
    }
}
```

### 불필요한 의존성 제거

```swift
// ❌ BAD: 전체 객체 전달
struct ItemRow: View {
    @Bindable var viewModel: ViewModel // 전체 VM 변경 시 재렌더링

    var body: some View {
        Text(viewModel.items[index].name)
    }
}

// ✅ GOOD: 필요한 데이터만 전달
struct ItemRow: View {
    let item: Item // 해당 item만 변경 시 재렌더링

    var body: some View {
        Text(item.name)
    }
}
```

### Equatable 최적화

```swift
struct ExpensiveView: View, Equatable {
    let data: ComplexData

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.data.id == rhs.data.id // 빠른 비교
    }

    var body: some View {
        // 복잡한 뷰 구조
    }
}

// 사용
ExpensiveView(data: data)
    .equatable() // Equatable 비교로 재렌더링 방지
```

---

## 마이그레이션 가이드

### ObservableObject → @Observable

```swift
// Step 1: class에 @Observable 매크로 추가
// Step 2: @Published 제거
// Step 3: @StateObject → @State
// Step 4: @ObservedObject → 일반 프로퍼티 또는 @Bindable

// Before
class UserViewModel: ObservableObject {
    @Published var name: String = ""
    @Published var age: Int = 0
}

struct UserView: View {
    @StateObject var viewModel = UserViewModel()
}

// After
@Observable
final class UserViewModel {
    var name: String = ""
    var age: Int = 0
}

struct UserView: View {
    @State var viewModel = UserViewModel()
}
```

### NavigationView → NavigationStack

```swift
// Before
NavigationView {
    List {
        NavigationLink(destination: DetailView()) {
            Text("Go to Detail")
        }
    }
}

// After
NavigationStack {
    List {
        NavigationLink(value: "detail") {
            Text("Go to Detail")
        }
    }
    .navigationDestination(for: String.self) { value in
        DetailView()
    }
}
```

### List Selection → Modern Pattern

```swift
// Before (iOS 15)
@State private var selection: Item?
List(items, selection: $selection) { item in
    Text(item.name)
}

// After (iOS 17+) - 더 유연한 패턴
@State private var selectedItem: Item?
List(items, selection: $selectedItem) { item in
    Text(item.name)
}
.onChange(of: selectedItem) { _, newValue in
    // 선택 처리
}
```

---

## Thread Safety

### @Observable과 MainActor

```swift
// UI 바운드 객체는 MainActor 격리 권장
@MainActor
@Observable
final class ViewModel {
    var items: [Item] = []

    func loadItems() async {
        // 백그라운드 작업은 nonisolated로
        let data = await fetchData()
        items = data // MainActor에서 안전하게 업데이트
    }

    nonisolated func fetchData() async -> [Item] {
        // 네트워크 요청 등
    }
}
```

### 주의: @Observable 자체는 Thread-Safe하지 않음

```swift
// ❌ DANGEROUS: 여러 스레드에서 동시 접근
@Observable
class SharedState {
    var count = 0
}

// ✅ SAFE: MainActor로 격리
@MainActor
@Observable
class SharedState {
    var count = 0
}

// 또는 Actor 사용
actor SharedStateActor {
    var count = 0
}
```

---

## Design System

### Design Principles

#### 1. Information Hierarchy First
- 사용자가 **먼저 보는 것** → **읽는 것** → **행동하는 것** 순서 고려
- 시각적 무게로 중요도 표현 (크기, 색상, 대비)

#### 2. Consistency via System Thinking
- 간격, 타이포그래피, 색상, 모서리 반경은 일관된 스케일 사용
- 매직 넘버 대신 시맨틱 토큰 활용

#### 3. States are Part of Design
- 모든 상태를 디자인해야 함:
  - `loading` (로딩 중)
  - `empty` (데이터 없음)
  - `error` (오류 발생)
  - `disabled` (비활성화)
  - `permission denied` (권한 거부)

#### 4. Responsive by Default
- Dynamic Type 지원 필수
- 다양한 화면 크기 대응
- 긴 텍스트/다국어 고려
- RTL (오른쪽→왼쪽) 언어 인식

#### 5. Platform Conventions
- 네이티브 패턴 우선 사용
- 커스터마이징은 목적이 있을 때만

### Design Tokens

#### Spacing Scale (pt)
| Token | Value | Usage |
|-------|-------|-------|
| xs | 4 | 아이콘-텍스트 간격 |
| s | 8 | 관련 요소 간 간격 |
| m | 12 | 그룹 내 요소 간격 |
| l | 16 | 섹션 내 간격 |
| xl | 24 | 섹션 간 간격 |
| xxl | 32 | 주요 영역 구분 |
| xxxl | 40 | 최대 간격 |

#### Corner Radius Scale (pt)
| Token | Value | Usage |
|-------|-------|-------|
| s | 8 | 작은 요소 (버튼, 뱃지) |
| m | 12 | 중간 요소 (카드) |
| l | 16 | 큰 컨테이너 |
| xl | 20 | 모달, 시트 |

#### Typography
Dynamic Type semantic styles 우선 사용:
- `.largeTitle`, `.title`, `.title2`, `.title3`
- `.headline`, `.subheadline`
- `.body`, `.callout`
- `.caption`, `.caption2`
- `.footnote`

#### Semantic Colors
| Token | Purpose |
|-------|---------|
| textPrimary | 주요 텍스트 |
| textSecondary | 보조 텍스트 |
| background | 배경 |
| surface | 카드/컨테이너 배경 |
| surfaceElevated | 높은 elevation 배경 |
| accent | 강조색 (브랜드) |
| destructive | 삭제/위험 액션 |
| border | 테두리 |
| separator | 구분선 |

### Existing System Detection

프로젝트에 기존 디자인 시스템이 있는지 확인하는 패턴:

#### Token 패턴
- `Spacing.*`, `Radius.*`, `Typography.*`, `ColorToken.*`
- `Theme.*`, `DesignTokens.*`, `UIConstants.*`
- `AppColor.*`, `AppFont.*`, `AppSpacing.*`

#### ViewModifier/Style 패턴
- `.cardStyle()`, `.primaryButtonStyle()`
- Custom `ButtonStyle`, `LabelStyle`

#### Component 패턴
- `CardView`, `SectionHeader`, `SettingsRow`
- `Chip`, `Badge`, `EmptyStateView`

**규칙**: 기존 시스템이 있으면 **채택하고 확장**. 새 시스템 도입 금지.

### Accessibility Checklist

#### Touch Targets
- 최소 터치 영역: **44pt x 44pt**
- 작은 요소는 `.contentShape()` 또는 패딩으로 확장

#### Contrast
- 텍스트 대비 비율 준수 (WCAG AA 기준)
- 고대비 모드 지원 고려

#### VoiceOver
- 모든 인터랙티브 요소에 적절한 레이블
- `.accessibilityLabel()`, `.accessibilityHint()`
- 장식용 이미지는 `.accessibilityHidden(true)`

#### Reduce Motion
- `@Environment(\.accessibilityReduceMotion)` 확인
- 필수 아닌 애니메이션 비활성화 옵션

#### Dynamic Type
- 최대 글씨 크기에서 레이아웃 테스트
- 잘림 없이 표시되는지 확인
- `@ScaledMetric` 활용

#### Focus Order
- 논리적 탭 순서 유지
- 커스텀 컨트롤의 포커스 처리

### Component Breakdown

재사용 가능한 컴포넌트 분해 패턴:

| Component | Purpose |
|-----------|---------|
| Card | 관련 정보 그룹 |
| Row | 리스트 아이템 |
| SectionHeader | 섹션 제목 |
| Chip/Badge | 태그, 상태 표시 |
| CTA (Call-to-Action) | 주요 액션 버튼 |
| EmptyState | 데이터 없음 상태 |
| Skeleton | 로딩 플레이스홀더 |

### UI Verification Checklist

UI 코드 작성 후 확인 사항:

- [ ] Dynamic Type 최대 글씨 크기에서 테스트
- [ ] 긴 텍스트/다국어에서 레이아웃 확인
- [ ] 다크 모드에서 확인
- [ ] VoiceOver 라벨 및 탭 순서 확인
- [ ] 모든 터치 타겟 44pt 이상
- [ ] Reduce Motion 설정 시 동작 확인
- [ ] 작은 화면/큰 화면에서 레이아웃 확인
```
