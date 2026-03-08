# Swift Coding Conventions Reference

Swift/SwiftUI 프로젝트에서 일관된 코드 품질을 유지하기 위한 짧은 규칙 중심 레퍼런스입니다.

> 이 문서는 기존 `swift-conventions` 플러그인의 핵심 규칙을 통합한 것입니다.

---

## 이 문서의 역할

- 빠르게 확인하는 팀 기본 규칙과 체크리스트를 제공하기
- 답변, 리뷰, 패치에서 바로 적용할 짧은 정책을 모아두기
- 자세한 예시와 실전 패턴은 `swift-practices-reference.md`에서 확인하기

## Quick Index

- Target Versions
- Formatting & Naming
- Architecture
- Dependency Injection
- Concurrency
- Testing

## Formatting & Naming

- 들여쓰기: 4-space, 탭 사용 금지
- 줄 끝 공백 제거
- 타입 이름: `UpperCamelCase`
- 멤버/함수/변수: `camelCase`
- 열거형 케이스: `camelCase`
- Protocol 이름:
  - 동작/능력: `-able`
  - 책임/역할: `-er`
  - 특성: 형용사
- Magic number는 상수로 이름 붙이기
- 복잡한 로직은 “무엇”보다 “왜”를 설명하는 주석을 우선하기

## Target Versions

- **Swift**: 6.0+
- **iOS**: 18.0+ (또는 프로젝트 요구사항에 맞춤)
- **Xcode**: 16.0+

---

## Architecture (MVVM)

### View Layer
- SwiftUI Views는 **thin**하게 유지
- 비즈니스 로직 없이 렌더링에만 집중
- 복잡한 뷰는 작은 컴포넌트로 분해

### ViewModel Layer
- 상태(State)와 비즈니스 로직 담당
- `@Observable` 또는 `ObservableObject` 사용
- View와 1:1 또는 N:1 관계

### Model Layer
- 순수 데이터 구조
- Value types 선호 (struct/enum)

---

## Dependency Injection (PureDI + Composition Root)

- **모듈은 Factory import 금지**: 모듈은 순수하게 유지
- **생성자 주입만 사용**: 모든 의존성은 `init`을 통해 주입
- **프로토콜 의존**: 구체 타입이 아닌 프로토콜에 의존
- **Composition Root**: 모든 의존성 조립은 App Target에서만 수행

```swift
// ✅ 모듈 내부 - Pure Swift (Factory import 없음)
public protocol UserRepository {
    func fetchUser() async throws -> User
}

@MainActor
public final class ProfileViewModel: ObservableObject {
    private let repository: UserRepository

    public init(repository: UserRepository) {  // 생성자 주입
        self.repository = repository
    }
}

// ✅ App Target - Composition Root
import Factory
extension Container {
    var profileViewModel: Factory<ProfileViewModel> {
        self { ProfileViewModel(repository: self.userRepository()) }
    }
}

// ❌ 금지 - 모듈 내부에서 Factory 사용
import Factory  // 절대 금지
@Injected(\.service) var service  // 절대 금지
```

---

## Concurrency (Swift 6)

### Strict Concurrency
- Swift 6의 **complete strict concurrency checking** 활성화 권장
- `Sendable` 준수 필수 (데이터 레이스 방지)
- Actor isolation 명확히 정의

### MainActor 규칙
- UI 상태 변경은 반드시 `@MainActor`에서 실행
- ViewModel은 `@MainActor` 또는 `@Observable` 사용
- 비동기 작업은 격리하고 취소 가능하게

### Task 관리
- 뷰 생명주기에 맞춰 Task 취소
- `task(id:)` 또는 `@State private var task: Task<Void, Never>?` 활용
- `withTaskCancellationHandler`로 취소 처리

### Actor 사용
- 공유 mutable 상태는 Actor로 보호
- `nonisolated` 키워드로 필요시 격리 해제

```swift
actor DataCache {
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? {
        cache[key]
    }

    func set(_ key: String, data: Data) {
        cache[key] = data
    }
}
```

---

## Testing Conventions

- 테스트하기 어려우면 설계 변경 (seams 도입)
- Test doubles: Fake/Spy 선호 (heavy mocking 회피)
- 시간 의존 코드는 Clock 프로토콜 주입
- Swift Testing framework 사용 권장 (`@Test`, `#expect`)
- **PureDI 테스트**: 모듈 테스트는 Mock을 생성자에 직접 주입 (Container 불필요)
- **App 통합 테스트**: `@Suite(.container)` trait + FactoryTesting 사용
- **XCTest**: `Container.Registrations.push()/pop()` 패턴 사용
