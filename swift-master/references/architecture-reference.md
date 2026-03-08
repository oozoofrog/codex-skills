# iOS Architecture Patterns Reference Guide

MVVM과 TCA 아키텍처 패턴 비교 및 선택 가이드입니다.

---

## 패턴 비교 요약

| 측면 | MVVM | TCA |
|------|------|-----|
| **기원** | Microsoft (2005) | Point-Free (2019) |
| **핵심 철학** | 데이터 바인딩 | 단방향 + 함수형 |
| **컴포넌트 수** | 3개 | 4개 |
| **데이터 흐름** | 양방향 | 엄격한 단방향 |
| **SwiftUI 친화도** | 높음 | 매우 높음 |
| **UIKit 친화도** | 높음 | 중간 |
| **테스트 용이성** | 중간 | 매우 높음 |
| **학습 곡선** | 낮음 | 중간 |
| **보일러플레이트** | 낮음 | 중간 |

---

## 아키텍처 다이어그램

### MVVM

```
┌─────────┐      ┌─────────────┐      ┌─────────┐
│  View   │◄────►│  ViewModel  │◄────►│  Model  │
└─────────┘      └─────────────┘      └─────────┘
      │                  │
      └──────────────────┘
        양방향 바인딩
```

### TCA

```
                    ┌─────────────┐
                    │    Store    │
                    │  ┌───────┐  │
┌────────┐  Action  │  │ State │  │   ┌─────────────┐
│  View  │─────────►│  └───────┘  │◄──│ Dependency  │
└────────┘          │      │      │   └─────────────┘
     ▲              │      ▼      │
     │    State     │  ┌───────┐  │
     └──────────────│  │Reducer│  │
                    │  └───────┘  │
                    └─────────────┘
           단방향 (Unidirectional)
```

---

## MVVM (Model-View-ViewModel)

### 구조

```swift
// Model
struct User: Codable {
    let id: UUID
    var name: String
    var email: String
}

// ViewModel (iOS 17+)
@Observable
@MainActor
final class UserViewModel {
    var user: User?
    var isLoading = false
    var errorMessage: String?

    private let service: UserService

    init(service: UserService = .shared) {
        self.service = service
    }

    func loadUser(id: UUID) async {
        isLoading = true
        defer { isLoading = false }

        do {
            user = try await service.fetchUser(id: id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// View
struct UserView: View {
    @State private var viewModel = UserViewModel()
    let userId: UUID

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView()
            } else if let user = viewModel.user {
                UserDetailView(user: user)
            } else if let error = viewModel.errorMessage {
                ErrorView(message: error)
            }
        }
        .task {
            await viewModel.loadUser(id: userId)
        }
    }
}
```

### 폴더 구조

```
Features/
└── User/
    ├── Models/
    │   └── User.swift
    ├── ViewModels/
    │   └── UserViewModel.swift
    └── Views/
        ├── UserView.swift
        └── UserDetailView.swift
```

### 장점

- 학습 곡선 낮음
- 빠른 개발 속도
- Apple의 SwiftUI 패턴과 유사
- 소규모 프로젝트에 최적
- 외부 의존성 없음

### 단점

- 대규모에서 ViewModel 비대화 (Massive ViewModel)
- 팀 간 일관성 유지 어려움
- 네비게이션 로직 처리 모호
- 테스트 작성이 TCA보다 번거로움

### 적합한 프로젝트

- 소규모~중규모 (5-20화면)
- 1-4명 팀
- 빠른 MVP 개발
- SwiftUI 또는 UIKit

---

## TCA (The Composable Architecture)

### 구조

```swift
import ComposableArchitecture

@Reducer
struct UserFeature {
    @ObservableState
    struct State: Equatable {
        var user: User?
        var isLoading = false
        var errorMessage: String?
    }

    enum Action {
        case onAppear
        case userResponse(Result<User, Error>)
        case editButtonTapped
        case delegate(Delegate)

        enum Delegate {
            case navigateToEdit(User)
        }
    }

    @Dependency(\.userClient) var userClient

    var body: some ReducerOf<Self> {
        Reduce { state, action in
            switch action {
            case .onAppear:
                state.isLoading = true
                return .run { send in
                    await send(.userResponse(
                        Result { try await userClient.fetch() }
                    ))
                }

            case .userResponse(.success(let user)):
                state.isLoading = false
                state.user = user
                return .none

            case .userResponse(.failure(let error)):
                state.isLoading = false
                state.errorMessage = error.localizedDescription
                return .none

            case .editButtonTapped:
                guard let user = state.user else { return .none }
                return .send(.delegate(.navigateToEdit(user)))

            case .delegate:
                return .none
            }
        }
    }
}

// View
struct UserView: View {
    @Bindable var store: StoreOf<UserFeature>

    var body: some View {
        Group {
            if store.isLoading {
                ProgressView()
            } else if let user = store.user {
                VStack {
                    Text(user.name)
                    Text(user.email)
                    Button("Edit") {
                        store.send(.editButtonTapped)
                    }
                }
            } else if let error = store.errorMessage {
                Text(error).foregroundStyle(.red)
            }
        }
        .onAppear { store.send(.onAppear) }
    }
}

// Dependency
struct UserClient {
    var fetch: @Sendable () async throws -> User
}

extension UserClient: DependencyKey {
    static var liveValue: UserClient {
        UserClient {
            try await URLSession.shared.decode(User.self, from: userURL)
        }
    }

    static var testValue: UserClient {
        UserClient {
            User(id: UUID(), name: "Test", email: "test@test.com")
        }
    }
}

extension DependencyValues {
    var userClient: UserClient {
        get { self[UserClient.self] }
        set { self[UserClient.self] = newValue }
    }
}
```

### 폴더 구조

```
Features/
└── User/
    ├── UserFeature.swift      # State, Action, Reducer
    ├── UserView.swift         # SwiftUI View
    └── UserClient.swift       # Dependency

// 또는 단일 파일
Features/
└── UserFeature.swift          # 모든 것 포함
```

### 장점

- 단방향 데이터 흐름 (예측 가능)
- 최고의 테스트 지원
- SwiftUI와 완벽한 통합
- Dependency Injection 내장
- 상태 복원/시간 여행 디버깅
- 명확한 규칙으로 팀 일관성

### 단점

- 학습 곡선 (함수형 개념)
- 외부 의존성 필수 (swift-composable-architecture)
- 빌드 시간 증가 (매크로)
- UIKit 통합 복잡

### 적합한 프로젝트

- SwiftUI 중/대규모
- 테스트 중심 개발
- 복잡한 상태 관리
- 4명+ 팀

### TCA 테스트 예시

```swift
@MainActor
func testUserLoad() async {
    let store = TestStore(
        initialState: UserFeature.State()
    ) {
        UserFeature()
    } withDependencies: {
        $0.userClient.fetch = {
            User(id: UUID(), name: "Test", email: "test@test.com")
        }
    }

    await store.send(.onAppear) {
        $0.isLoading = true
    }

    await store.receive(\.userResponse.success) {
        $0.isLoading = false
        $0.user = User(id: UUID(), name: "Test", email: "test@test.com")
    }
}
```

---

## 선택 가이드

### 의사결정 플로우

```
프로젝트 시작
    │
    ▼
┌─────────────────┐
│ UI 프레임워크?  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
SwiftUI     UIKit
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│규모?  │ │규모?  │
└───┬───┘ └───┬───┘
    │         │
┌───┼───┐ ┌───┼───┐
▼   ▼   ▼ ▼   ▼   ▼
소 중 대 소 중  대
│   │   │ │   │   │
▼   ▼   ▼ ▼   ▼   ▼
MVVM TCA TCA MVVM MVVM MVVM+
                      Coord
```

### 상황별 권장

| 상황 | 권장 패턴 |
|------|----------|
| SwiftUI + 소규모 + 빠른 개발 | **MVVM** |
| SwiftUI + 중/대규모 + 테스트 중요 | **TCA** |
| UIKit + 모든 규모 | **MVVM + Coordinator** |
| 스타트업 MVP | **MVVM** |
| 엔터프라이즈 신규 SwiftUI | **TCA** |
| 레거시 UIKit 유지보수 | 기존 패턴 유지 |

### 팀 규모별 권장

| 팀 규모 | SwiftUI | UIKit |
|---------|---------|-------|
| 1-3명 | MVVM | MVVM |
| 4-10명 | TCA | MVVM+Coordinator |
| 10명+ | TCA | MVVM+Coordinator |

---

## 안티패턴 체크리스트

### MVVM 안티패턴

| # | 패턴 | 문제 | 해결 |
|---|------|------|------|
| M1 | Massive ViewModel | 500+ LOC ViewModel | Feature 분리 |
| M2 | View에서 비즈니스 로직 | 테스트 불가 | ViewModel로 이동 |
| M3 | ViewModel 간 직접 통신 | 결합도 증가 | Coordinator/Delegate |
| M4 | 네비게이션 로직 in ViewModel | SwiftUI 호환 문제 | Router 패턴 추가 |
| M5 | @State로 ViewModel 생성 in View | 상태 손실 | App 레벨에서 생성 |

### TCA 안티패턴

| # | 패턴 | 문제 | 해결 |
|---|------|------|------|
| T1 | View에서 직접 상태 변경 | 단방향 위반 | Action으로 전달 |
| T2 | Effect에서 State 접근 | 데이터 레이스 | 파라미터로 전달 |
| T3 | 과도한 Action 세분화 | 복잡도 증가 | 논리적 그룹화 |
| T4 | Dependency 없이 네트워크 | 테스트 불가 | Dependency 사용 |
| T5 | Reducer에서 UI 로직 | 역할 혼란 | View로 이동 |

---

## 마이그레이션 가이드

### MVVM → TCA

```swift
// Before: MVVM ViewModel
@Observable
class UserViewModel {
    var user: User?
    var isLoading = false

    func loadUser() async {
        isLoading = true
        user = try? await service.fetch()
        isLoading = false
    }
}

// After: TCA Reducer
@Reducer
struct UserFeature {
    @ObservableState
    struct State: Equatable {
        var user: User?
        var isLoading = false
    }

    enum Action {
        case loadUser
        case userLoaded(User?)
    }

    @Dependency(\.userService) var userService

    var body: some ReducerOf<Self> {
        Reduce { state, action in
            switch action {
            case .loadUser:
                state.isLoading = true
                return .run { send in
                    let user = try? await userService.fetch()
                    await send(.userLoaded(user))
                }
            case .userLoaded(let user):
                state.isLoading = false
                state.user = user
                return .none
            }
        }
    }
}
```

### 점진적 마이그레이션 전략

```
Phase 1: 새 기능 → TCA
Phase 2: 공유 상태 통합
Phase 3: 화면 단위 전환
Phase 4: 완전 전환
```

---

## 2025년 트렌드

```
채택률 (SwiftUI 프로젝트)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MVVM   ████████████████████  55%
TCA    ██████████████        40%
기타   ██                    5%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**전망:**
- TCA: SwiftUI 성장과 함께 급상승
- MVVM: 진입장벽 낮아 여전히 인기
- 순수 SwiftUI (@Observable 활용): 증가 추세

---

## Quick Reference Card

### MVVM vs TCA 선택

```
┌─────────────────────────────────────────────────────────────┐
│                    어떤 패턴을 선택할까?                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  테스트가 매우 중요? ───────────────────► TCA              │
│                                                             │
│  빠른 MVP 개발? ────────────────────────► MVVM             │
│                                                             │
│  팀원 4명 이상? ────────────────────────► TCA              │
│                                                             │
│  함수형 프로그래밍 경험? ───────────────► TCA              │
│                                                             │
│  외부 의존성 최소화? ───────────────────► MVVM             │
│                                                             │
│  복잡한 상태 관리? ─────────────────────► TCA              │
│                                                             │
│  UIKit 프로젝트? ───────────────────────► MVVM + Coord     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
