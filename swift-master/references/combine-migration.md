# Combine → AsyncSequence Migration Guide

Combine 코드를 Swift Concurrency의 AsyncSequence로 변환하는 가이드입니다.

---

## Quick Index

- 왜 AsyncSequence로 마이그레이션하는가?
- 기본 변환 패턴
- Operator 매핑 테이블
- 복잡한 패턴 변환
- 구독 생명주기 관리
- 에러 핸들링 변환
- 실전 변환 예시
- AsyncAlgorithms 패키지 사용

## 왜 AsyncSequence로 마이그레이션하는가?

| 측면 | Combine | AsyncSequence |
|------|---------|---------------|
| 메모리 관리 | AnyCancellable 수동 관리 | Task 생명주기로 자동 |
| 에러 처리 | Failure 타입 파라미터 | throws/rethrows |
| 취소 | cancel() 명시 호출 | Task 취소로 자동 |
| 백프레셔 | Demand 기반 | 자연스러운 await |
| 학습 곡선 | Operator 체인 복잡 | for-await 직관적 |

---

## 기본 변환 패턴

### 1. Publisher → AsyncSequence

**Before (Combine):**
```swift
let publisher = URLSession.shared.dataTaskPublisher(for: url)
    .map(\.data)
    .decode(type: User.self, decoder: JSONDecoder())

var cancellable: AnyCancellable?

cancellable = publisher
    .sink(
        receiveCompletion: { completion in
            switch completion {
            case .finished: break
            case .failure(let error):
                print("Error: \(error)")
            }
        },
        receiveValue: { user in
            print("User: \(user)")
        }
    )
```

**After (AsyncSequence):**
```swift
func fetchUser() async throws -> User {
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONDecoder().decode(User.self, from: data)
}

// 사용
Task {
    do {
        let user = try await fetchUser()
        print("User: \(user)")
    } catch {
        print("Error: \(error)")
    }
}
```

### 2. sink → for await

**Before:**
```swift
publisher
    .sink { value in
        process(value)
    }
    .store(in: &cancellables)
```

**After:**
```swift
Task {
    for await value in asyncSequence {
        process(value)
    }
}
```

---

## Operator 매핑 테이블

| Combine Operator | AsyncSequence 대응 |
|------------------|-------------------|
| `map` | `map` (AsyncMapSequence) |
| `compactMap` | `compactMap` |
| `filter` | `filter` |
| `flatMap` | `flatMap` (AsyncFlatMapSequence) |
| `first` | `first(where:)` 또는 직접 `break` |
| `prefix` | `prefix(_:)` |
| `drop` | `dropFirst(_:)` |
| `removeDuplicates` | 커스텀 구현 필요 |
| `debounce` | AsyncAlgorithms `debounce` |
| `throttle` | AsyncAlgorithms `throttle` |
| `merge` | AsyncAlgorithms `merge` |
| `combineLatest` | AsyncAlgorithms `combineLatest` |
| `zip` | AsyncAlgorithms `zip` |

### map 예시

**Before:**
```swift
publisher
    .map { $0.uppercased() }
    .sink { print($0) }
```

**After:**
```swift
for await value in asyncSequence.map({ $0.uppercased() }) {
    print(value)
}
```

### filter 예시

**Before:**
```swift
publisher
    .filter { $0 > 10 }
    .sink { print($0) }
```

**After:**
```swift
for await value in asyncSequence.filter({ $0 > 10 }) {
    print(value)
}
```

---

## 복잡한 패턴 변환

### 1. combineLatest

**Before:**
```swift
Publishers.CombineLatest(publisher1, publisher2)
    .sink { value1, value2 in
        process(value1, value2)
    }
```

**After (AsyncAlgorithms 사용):**
```swift
import AsyncAlgorithms

for await (value1, value2) in combineLatest(sequence1, sequence2) {
    process(value1, value2)
}
```

**After (수동 구현):**
```swift
actor CombineLatestState<A, B> {
    var latest: (A?, B?) = (nil, nil)

    func update(first: A) -> (A, B)? {
        latest.0 = first
        guard let second = latest.1 else { return nil }
        return (first, second)
    }

    func update(second: B) -> (A, B)? {
        latest.1 = second
        guard let first = latest.0 else { return nil }
        return (first, second)
    }
}
```

### 2. merge

**Before:**
```swift
Publishers.Merge(publisher1, publisher2)
    .sink { value in
        process(value)
    }
```

**After (AsyncAlgorithms):**
```swift
import AsyncAlgorithms

for await value in merge(sequence1, sequence2) {
    process(value)
}
```

**After (TaskGroup):**
```swift
func mergedSequence() -> AsyncStream<Value> {
    AsyncStream { continuation in
        Task {
            await withTaskGroup(of: Void.self) { group in
                group.addTask {
                    for await value in sequence1 {
                        continuation.yield(value)
                    }
                }
                group.addTask {
                    for await value in sequence2 {
                        continuation.yield(value)
                    }
                }
            }
            continuation.finish()
        }
    }
}
```

### 3. debounce

**Before:**
```swift
textPublisher
    .debounce(for: .milliseconds(300), scheduler: RunLoop.main)
    .sink { text in
        search(text)
    }
```

**After (AsyncAlgorithms):**
```swift
import AsyncAlgorithms

for await text in textSequence.debounce(for: .milliseconds(300)) {
    await search(text)
}
```

**After (수동 구현):**
```swift
func debounced<T>(_ sequence: some AsyncSequence<T, Never>,
                  interval: Duration) -> AsyncStream<T> {
    AsyncStream { continuation in
        Task {
            var task: Task<Void, Never>?

            for await value in sequence {
                task?.cancel()
                task = Task {
                    try? await Task.sleep(for: interval)
                    guard !Task.isCancelled else { return }
                    continuation.yield(value)
                }
            }
            continuation.finish()
        }
    }
}
```

---

## 구독 생명주기 관리

### AnyCancellable → Task

**Before:**
```swift
class ViewModel {
    private var cancellables = Set<AnyCancellable>()

    func subscribe() {
        publisher
            .sink { [weak self] value in
                self?.process(value)
            }
            .store(in: &cancellables)
    }

    deinit {
        // cancellables 자동 해제
    }
}
```

**After:**
```swift
class ViewModel {
    private var subscriptionTask: Task<Void, Never>?

    func subscribe() {
        subscriptionTask = Task { [weak self] in
            for await value in asyncSequence {
                self?.process(value)
            }
        }
    }

    deinit {
        subscriptionTask?.cancel()
    }
}

// 또는 @MainActor 사용
@MainActor
class ViewModel {
    private var subscriptionTask: Task<Void, Never>?

    func subscribe() {
        subscriptionTask = Task {
            for await value in asyncSequence {
                process(value)  // self 강한 참조 OK (Task가 관리)
            }
        }
    }

    func cleanup() {
        subscriptionTask?.cancel()
    }
}
```

### 여러 구독 관리

**Before:**
```swift
class ViewModel {
    private var cancellables = Set<AnyCancellable>()

    func setup() {
        subscription1().store(in: &cancellables)
        subscription2().store(in: &cancellables)
        subscription3().store(in: &cancellables)
    }
}
```

**After:**
```swift
class ViewModel {
    private var tasks: [Task<Void, Never>] = []

    func setup() {
        tasks = [
            Task { await subscription1() },
            Task { await subscription2() },
            Task { await subscription3() }
        ]
    }

    func cleanup() {
        tasks.forEach { $0.cancel() }
        tasks.removeAll()
    }
}

// 또는 TaskGroup 사용
func setupAll() async {
    await withTaskGroup(of: Void.self) { group in
        group.addTask { await subscription1() }
        group.addTask { await subscription2() }
        group.addTask { await subscription3() }
    }
}
```

---

## 에러 핸들링 변환

### Failure 타입 → throws

**Before:**
```swift
let publisher: AnyPublisher<Data, NetworkError>

publisher
    .sink(
        receiveCompletion: { completion in
            if case .failure(let error) = completion {
                handleError(error)
            }
        },
        receiveValue: { data in
            process(data)
        }
    )
```

**After:**
```swift
func fetchData() async throws -> Data {
    // NetworkError를 throw
}

Task {
    do {
        let data = try await fetchData()
        process(data)
    } catch let error as NetworkError {
        handleError(error)
    } catch {
        handleUnknownError(error)
    }
}
```

### replaceError → 기본값

**Before:**
```swift
publisher
    .replaceError(with: defaultValue)
    .sink { value in
        process(value)
    }
```

**After:**
```swift
let value = (try? await fetchValue()) ?? defaultValue
process(value)
```

---

## 실전 변환 예시

### 1. 네트워크 요청

**Before (Combine):**
```swift
class NetworkManager {
    func fetch<T: Decodable>(_ type: T.Type, from url: URL) -> AnyPublisher<T, Error> {
        URLSession.shared.dataTaskPublisher(for: url)
            .map(\.data)
            .decode(type: T.self, decoder: JSONDecoder())
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
}
```

**After (AsyncSequence):**
```swift
class NetworkManager {
    func fetch<T: Decodable>(_ type: T.Type, from url: URL) async throws -> T {
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(T.self, from: data)
    }
}
```

### 2. 타이머

**Before (Combine):**
```swift
Timer.publish(every: 1, on: .main, in: .common)
    .autoconnect()
    .sink { _ in
        updateClock()
    }
    .store(in: &cancellables)
```

**After (AsyncSequence):**
```swift
// Swift 5.9+
Task {
    for await _ in AsyncTimerSequence.repeating(every: .seconds(1)) {
        await updateClock()
    }
}

// 또는 수동 구현
func timerSequence(interval: Duration) -> AsyncStream<Date> {
    AsyncStream { continuation in
        let task = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: interval)
                continuation.yield(Date())
            }
        }
        continuation.onTermination = { _ in task.cancel() }
    }
}
```

### 3. NotificationCenter

**Before (Combine):**
```swift
NotificationCenter.default
    .publisher(for: UIApplication.didBecomeActiveNotification)
    .sink { _ in
        refreshData()
    }
    .store(in: &cancellables)
```

**After (AsyncSequence):**
```swift
Task {
    for await _ in NotificationCenter.default.notifications(named: UIApplication.didBecomeActiveNotification) {
        await refreshData()
    }
}
```

### 4. @Published 프로퍼티

**Before (Combine):**
```swift
class ViewModel: ObservableObject {
    @Published var searchText = ""

    init() {
        $searchText
            .debounce(for: .milliseconds(300), scheduler: RunLoop.main)
            .removeDuplicates()
            .sink { [weak self] text in
                self?.search(text)
            }
            .store(in: &cancellables)
    }
}
```

**After (AsyncSequence + @Observable):**
```swift
import Observation

@Observable
class ViewModel {
    var searchText = ""
    private var searchTask: Task<Void, Never>?

    func startObserving() {
        searchTask = Task {
            var lastText = ""
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(100))

                let currentText = searchText
                if currentText != lastText {
                    // debounce 대기
                    try? await Task.sleep(for: .milliseconds(300))
                    if searchText == currentText {
                        await search(currentText)
                        lastText = currentText
                    }
                }
            }
        }
    }
}
```

---

## AsyncAlgorithms 패키지 사용

많은 Combine operator에 대응하는 기능을 제공합니다:

```swift
// Package.swift
dependencies: [
    .package(url: "https://github.com/apple/swift-async-algorithms", from: "1.0.0")
]

// 사용
import AsyncAlgorithms

// merge
for await value in merge(sequence1, sequence2) { }

// combineLatest
for await (a, b) in combineLatest(seqA, seqB) { }

// zip
for await (a, b) in zip(seqA, seqB) { }

// debounce
for await value in sequence.debounce(for: .seconds(0.3)) { }

// throttle
for await value in sequence.throttle(for: .seconds(1)) { }

// chunks
for await chunk in sequence.chunks(ofCount: 10) { }
```
