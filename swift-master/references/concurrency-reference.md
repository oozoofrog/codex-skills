# Swift Concurrency Reference Guide

Swift Concurrency 안티패턴, 변환 규칙, 베스트 프랙티스입니다.

---

## Quick Index

- 안티패턴 체크리스트
- 변환 규칙
- Sendable 전략
- Actor 재진입 패턴
- 취소 처리
- 동시성 결정 트리
- Quick Reference
- 레거시 이벤트 → `AsyncStream`
- Swift 6 Concurrency 리팩토링 가이드

## 안티패턴 체크리스트 (28개)

### CRITICAL (10개) - 런타임 크래시/데드락

| # | 패턴 | 탐지 규칙 | 수정 방법 |
|---|------|-----------|-----------|
| C1 | Blocking in Async | `semaphore.wait()`, `DispatchQueue.sync`, `Thread.sleep` in async | Actor 또는 AsyncSemaphore |
| C2 | Continuation Double Resume | `continuation.resume` 2회 이상 | 한 번만 호출, flag 체크 |
| C3 | Missing Continuation Resume | 모든 경로에서 resume 없음 | guard + defer 패턴 |
| C4 | Sendable Violation | non-Sendable을 actor 경계 넘김 | Struct 또는 @unchecked Sendable |
| C5 | Actor Reentrancy Race | await 후 상태 가정 | 트랜잭션 패턴 |
| C6 | Core Data Thread Violation | viewContext를 Task 내 직접 사용 | perform 또는 @MainActor |
| C7 | Realm Thread Violation | Realm 객체를 다른 Task에서 접근 | ThreadSafeReference |
| C8 | Unsafe Task Detachment | Task.detached로 취소 단절 | Task 사용 |
| C9 | MainActor Blocking | @MainActor에서 무거운 async 작업 | nonisolated로 분리 |
| C10 | Swift 6 Isolation Crash | Legacy callback executor 불일치 | @preconcurrency, assumeIsolated |

### WARNING (10개) - 성능/유지보수 문제

| # | 패턴 | 탐지 규칙 | 수정 방법 |
|---|------|-----------|-----------|
| W1 | Excessive Unstructured Tasks | Task { } 남용 | 구조적 동시성 (async let, TaskGroup) |
| W2 | DispatchGroup in Async | DispatchGroup.wait() | TaskGroup |
| W3 | Missing Cancellation Check | 긴 루프에 checkCancellation 없음 | try Task.checkCancellation() |
| W4 | Unbounded Task Creation | 무제한 Task 생성 | TaskGroup + 제한 |
| W5 | Ignoring Task Result | Task { } 결과 무시 | Task<Void, Never> 명시 |
| W6 | GlobalActor Overuse | @MainActor 과다 사용 | 필요한 부분만 격리 |
| W7 | AsyncSequence Retain Cycle | for await에서 self 강한 참조 | [weak self] |
| W8 | Missing Task Priority | 기본 우선순위만 사용 | Task(priority:) 명시 |
| W9 | Synchronous Property Access | Actor 동기 프로퍼티 접근 시도 | nonisolated 또는 async |
| W10 | withTaskGroup Missing throws | 에러 가능한데 non-throwing | withThrowingTaskGroup |

### INFO (8개) - 베스트 프랙티스

| # | 패턴 | 탐지 규칙 | 권장 사항 |
|---|------|-----------|-----------|
| I1 | Class Instead of Struct | Sendable 필요한 곳에 class | Struct 사용 |
| I2 | Missing autoreleasepool | 대량 객체 생성 루프 | autoreleasepool 추가 |
| I3 | XCTest async | async 테스트에 XCTest | Swift Testing (@Test) |
| I4 | Completion Handler Retained | completion에서 self 캡처 | async/await 변환 |
| I5 | NotificationCenter Callback | addObserver with selector | AsyncSequence |
| I6 | Timer Without AsyncSequence | Timer.scheduledTimer | AsyncTimerSequence |
| I7 | URLSession Delegate | delegate 기반 네트워킹 | async URLSession API |
| I8 | Manual Thread Management | Thread() 직접 생성 | Task 사용 |

---

## 변환 규칙 (10가지)

### 1. Completion Handler → async/await

```swift
// Before
func fetchData(completion: @escaping (Result<Data, Error>) -> Void) {
    URLSession.shared.dataTask(with: url) { data, _, error in
        if let error = error {
            completion(.failure(error))
        } else {
            completion(.success(data ?? Data()))
        }
    }.resume()
}

// After
func fetchData() async throws -> Data {
    let (data, _) = try await URLSession.shared.data(from: url)
    return data
}
```

### 2. DispatchGroup → TaskGroup

```swift
// Before
func processAll(items: [Item], completion: @escaping ([Result]) -> Void) {
    let group = DispatchGroup()
    var results = [Result]()
    let lock = NSLock()

    for item in items {
        group.enter()
        process(item) { result in
            lock.withLock { results.append(result) }
            group.leave()
        }
    }

    group.notify(queue: .main) { completion(results) }
}

// After
func processAll(items: [Item]) async -> [Result] {
    await withTaskGroup(of: Result.self) { group in
        for item in items {
            group.addTask { await process(item) }
        }

        var results = [Result]()
        for await result in group {
            results.append(result)
        }
        return results
    }
}
```

### 3. DispatchSemaphore → Actor

```swift
// Before
class ResourcePool {
    private let semaphore = DispatchSemaphore(value: 3)
    private var resources: [Resource] = []

    func acquire() -> Resource {
        semaphore.wait()
        return resources.removeLast()
    }
}

// After
actor ResourcePool {
    private var available: [Resource] = []
    private var waiters: [CheckedContinuation<Resource, Never>] = []

    func acquire() async -> Resource {
        if let resource = available.popLast() {
            return resource
        }
        return await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release(_ resource: Resource) {
        if let waiter = waiters.first {
            waiters.removeFirst()
            waiter.resume(returning: resource)
        } else {
            available.append(resource)
        }
    }
}
```

### 4. DispatchQueue.main.async → @MainActor

```swift
// Before
func updateUI(with data: Data) {
    DispatchQueue.main.async {
        self.label.text = String(data: data, encoding: .utf8)
    }
}

// After
@MainActor
func updateUI(with data: Data) {
    label.text = String(data: data, encoding: .utf8)
}

// 호출: await updateUI(with: data)
```

### 5. NSOperationQueue → Task 구조

```swift
// Before
let queue = OperationQueue()
queue.maxConcurrentOperationCount = 4

let op1 = BlockOperation { /* work 1 */ }
let op2 = BlockOperation { /* work 2 */ }
op2.addDependency(op1)

queue.addOperations([op1, op2], waitUntilFinished: false)

// After
Task {
    let result1 = await work1()  // op1
    await work2(using: result1)  // op2 (의존성)
}

// 병렬 작업
await withTaskGroup(of: Void.self) { group in
    for _ in 0..<4 {
        group.addTask { await work() }
    }
}
```

### 6. Legacy Callback → Continuation

```swift
// Before
func legacyAPI(completion: @escaping (String) -> Void)

// After
func modernAPI() async -> String {
    await withCheckedContinuation { continuation in
        legacyAPI { result in
            continuation.resume(returning: result)
        }
    }
}

// 에러 가능한 경우
func modernAPIThrowing() async throws -> String {
    try await withCheckedThrowingContinuation { continuation in
        legacyAPI { result, error in
            if let error = error {
                continuation.resume(throwing: error)
            } else {
                continuation.resume(returning: result)
            }
        }
    }
}
```

### 7. 안전한 Continuation 패턴

```swift
func safeModernAPI() async -> String {
    await withCheckedContinuation { continuation in
        var resumed = false

        legacyAPI { result in
            guard !resumed else { return }
            resumed = true
            continuation.resume(returning: result)
        }

        // 타임아웃
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
            guard !resumed else { return }
            resumed = true
            continuation.resume(returning: "timeout")
        }
    }
}
```

### 8. NotificationCenter → AsyncSequence

```swift
// Before
NotificationCenter.default.addObserver(
    self,
    selector: #selector(handleNotification),
    name: .didUpdate,
    object: nil
)

// After
Task {
    for await _ in NotificationCenter.default.notifications(named: .didUpdate) {
        handleUpdate()
    }
}
```

### 9. Timer → AsyncTimerSequence

```swift
// Before
Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
    self.tick()
}

// After (iOS 16+)
Task {
    for await _ in AsyncTimerSequence.repeating(every: .seconds(1)) {
        tick()
    }
}
```

### 10. URLSession Delegate → async API

```swift
// Before
class Downloader: NSObject, URLSessionDownloadDelegate {
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        // 처리
    }
}

// After
func download(from url: URL) async throws -> URL {
    let (localURL, _) = try await URLSession.shared.download(from: url)
    return localURL
}

// Progress 필요 시
func downloadWithProgress(from url: URL) async throws -> URL {
    let (bytes, response) = try await URLSession.shared.bytes(from: url)
    let total = response.expectedContentLength

    var data = Data()
    for try await byte in bytes {
        data.append(byte)
        let progress = Double(data.count) / Double(total)
        await updateProgress(progress)
    }

    let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try data.write(to: tempURL)
    return tempURL
}
```

---

## Sendable 전략

### Struct 우선 (암묵적 Sendable)

```swift
// Good
struct UserData: Codable {
    let id: UUID
    let name: String
}

// Bad - 명시적 Sendable 필요
class UserData: Sendable {
    let id: UUID
    let name: String
}
```

### Actor 경계에서 값 복사

```swift
actor DataManager {
    private var cache: [String: Data] = [:]

    // Good: 값 타입 반환
    func getData(for key: String) -> Data? {
        cache[key]
    }

    // Bad: 참조 타입 노출
    // func getCache() -> [String: SomeClass]
}
```

### @unchecked Sendable 최소화

```swift
// 정말 필요한 경우만
final class ThreadSafeCache: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String: Any] = [:]

    func get(_ key: String) -> Any? {
        lock.withLock { storage[key] }
    }
}
```

### Actor-isolated dependency contract 점검

다음 패턴을 우선 의심하기.

```swift
@MainActor
final class ViewModel {
    private let service: ArticleService

    func load() async throws {
        _ = try await service.fetch()
    }
}
```

위 구조는 `service`가 non-Sendable이거나 protocol existential의 격리 계약이 불명확하면 Swift 6 strict concurrency에서 깨질 수 있습니다.

우선 검토하기.
- protocol에 `Sendable` 부여
- 저장 프로퍼티를 `any ServiceProtocol & Sendable`로 명시
- 서비스 구현을 actor 또는 안전한 value type으로 설계
- 서비스가 실제로 main actor에 묶여야 하면 protocol 또는 메서드에 `@MainActor` 부여

리뷰에서 이 패턴을 찾으면 진단만 하지 말고 위 네 방향 중 최소 하나를 즉시 수정안으로 제시하기.

---

## Async semantic mismatch와 최신 요청 보호

다음 패턴을 위험 신호로 보기.

```swift
@MainActor
final class ViewModel {
    func generate() async {
        Task {
            self.result = try await service.generate()
        }
    }
}
```

위 코드는 함수 시그니처는 `async`지만, 호출자는 실제 생성 완료를 기다리지 못합니다. 테스트는 `await viewModel.generate()` 뒤 최종 상태를 기대하지만, 구현은 사실상 `startGenerate()`처럼 동작해 실패하기 쉽습니다.

추가 위험:
- 이전 task 취소가 최신 요청의 `isLoading = false`를 덮어씀
- 오래된 task가 늦게 끝나며 최신 `result`/`error`를 덮어씀

우선 검토하기.
- 반환된 `Task`를 실제로 `await value`하는지
- API 이름과 실제 의미가 일치하는지 (`generate` vs `startGenerate`)
- 최신 요청만 상태를 반영하는 `requestID`/token gate가 있는지
- 취소 후 `Task.checkCancellation()`로 stale 결과 반영을 막는지

자주 쓰는 수정 방향:
- `async func`라면 내부 spawned task를 `await`해 실제 완료까지 기다리기
- fire-and-forget 의도라면 메서드 이름을 `start...`로 바꾸고 호출부/테스트 기대를 맞추기
- `requestID` 또는 token을 두고 최신 요청만 `result`/`error`/`isLoading` 반영하기
- 취소된 이전 task가 최신 상태를 덮어쓰지 않도록 guard 추가

---

## Actor 재진입 패턴

### 문제

```swift
actor BankAccount {
    var balance: Int = 100

    func transfer(amount: Int, to other: BankAccount) async {
        guard balance >= amount else { return }
        balance -= amount           // 1
        await other.deposit(amount) // 2 - 재진입 가능!
        // balance가 다른 transfer에 의해 변경될 수 있음
    }
}
```

### 해결: 트랜잭션 패턴

```swift
actor BankAccount {
    var balance: Int = 100
    private var pending: [UUID: Int] = [:]

    func beginTransfer(amount: Int) -> UUID? {
        guard balance >= amount else { return nil }
        let id = UUID()
        balance -= amount
        pending[id] = amount
        return id
    }

    func commit(id: UUID) {
        pending.removeValue(forKey: id)
    }

    func rollback(id: UUID) {
        if let amount = pending.removeValue(forKey: id) {
            balance += amount
        }
    }
}
```

---

## 취소 처리

### 루프에서 취소 체크

```swift
func processLargeDataset(_ items: [Item]) async throws {
    for item in items {
        try Task.checkCancellation()
        await process(item)
    }
}
```

### withTaskCancellationHandler

```swift
func fetchWithCancellation() async throws -> Data {
    let task = URLSession.shared.dataTask(with: url)

    return try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation { continuation in
            task.completionHandler = { data, _, error in
                if let error = error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume(returning: data ?? Data())
                }
            }
            task.resume()
        }
    } onCancel: {
        task.cancel()
    }
}
```

---

## 동시성 결정 트리

```
데이터 공유 필요?
├─ No → 일반 async/await
└─ Yes → 여러 Task에서 접근?
         ├─ No → 단일 Task 내 처리
         └─ Yes → 가변 상태?
                  ├─ No → Struct (자동 Sendable)
                  └─ Yes → Actor 사용
                           └─ UI 관련? → @MainActor
```

---

## Quick Reference

### async let vs TaskGroup

| | async let | TaskGroup |
|---|-----------|-----------|
| 작업 수 | 고정 | 동적 |
| 타입 | 동일하지 않아도 됨 | 동일해야 함 |
| 사용 | 2-3개 병렬 작업 | N개 병렬 작업 |

```swift
// async let - 고정된 병렬 작업
async let user = fetchUser()
async let posts = fetchPosts()
async let comments = fetchComments()
let data = await (user, posts, comments)

// TaskGroup - 동적 병렬 작업
await withTaskGroup(of: Image.self) { group in
    for url in urls {
        group.addTask { await downloadImage(url) }
    }
    // ...
}
```

### Task vs Task.detached

| | Task | Task.detached |
|---|------|---------------|
| Actor 상속 | ✅ | ❌ |
| 우선순위 상속 | ✅ | ❌ |
| TaskLocal 상속 | ✅ | ❌ |
| 취소 전파 | ✅ | ❌ |

**규칙:** `Task.detached`는 거의 사용하지 마세요.

---

## AsyncStream을 활용한 레거시 이벤트 패턴 변환

여러 번 반복해서 이벤트를 전달하는 레거시 패턴(Delegate, Observer, 다중 호출 Callback 등)을 Swift의 `AsyncSequence`로 변환하기 위한 범용 표준 패턴은 **`AsyncStream`**을 사용하는 것입니다.

단발성 비동기 작업에는 `withCheckedContinuation`을 사용하지만, 이벤트처럼 데이터가 지속적으로 들어오는 경우에는 `AsyncStream`이 필요합니다.

### Step 1: Sendable 데이터 모델 정의

레거시 객체(참조 타입)를 그대로 스트림으로 방출하면 Swift 6의 엄격한 동시성 검사에서 `Sendable` 에러가 발생합니다. 레거시 객체에서 실제로 필요한 데이터만 추출하여 `Sendable`을 준수하는 값 타입(`struct`)으로 정의합니다.

```swift
// 이벤트 발생 시 방출할 안전한 데이터 구조체
struct EventResult: Sendable {
    let id: String
    let value: Int
}
```

### Step 2: Delegate/Callback Proxy 객체 생성

기존 시스템의 이벤트를 수신하여 `AsyncStream.Continuation`으로 전달(yield)하는 중간자(Proxy) 역할의 클래스를 만듭니다.

```swift
final class EventStreamProxy: LegacySystemDelegate, @unchecked Sendable {
    private let continuation: AsyncStream<EventResult>.Continuation

    init(continuation: AsyncStream<EventResult>.Continuation) {
        self.continuation = continuation
    }

    // 레거시 델리게이트나 콜백 메서드
    func system(_ system: LegacySystem, didProduceEvent data: LegacyData) {
        // 1. 필요한 데이터만 Sendable Struct로 변환
        let safeData = EventResult(id: data.id, value: data.value)

        // 2. 스트림으로 데이터 방출 (await 없이 동기적으로 호출 가능)
        continuation.yield(safeData)
    }

    func systemDidFinish(_ system: LegacySystem) {
        // 스트림의 끝을 알림
        continuation.finish()
    }
}
```

### Step 3: AsyncStream 생성 및 수명 관리

외부에서 호출할 팩토리 메서드를 만들고, 그 내부에서 `AsyncStream`을 생성합니다. **등록(Register)**과 **해제(Unregister)** 로직이 반드시 포함되어야 합니다.

```swift
func observeEvents(from system: LegacySystem) -> AsyncStream<EventResult> {
    return AsyncStream { continuation in
        // 1. 프록시 객체 생성 및 레거시 시스템에 등록
        let proxy = EventStreamProxy(continuation: continuation)
        system.delegate = proxy
        // 옵저버 패턴이라면 system.addObserver(proxy)

        // 2. 스트림 종료 또는 Task 취소 시 메모리 정리 (Cleanup)
        continuation.onTermination = { @Sendable _ in
            // 메모리 누수 방지를 위해 반드시 등록을 해제해야 함
            system.delegate = nil
            // 옵저버 패턴이라면 system.removeObserver(proxy)
        }
    }
}
```

### Step 4: 핵심 주의사항

| 항목 | 설명 |
|------|------|
| **yield는 동기 함수** | `AsyncStream.Continuation`의 `yield`는 `await`를 요구하지 않습니다. 어떤 레거시 델리게이트/콜백 내부에서도 스레드 블로킹 없이 즉시 호출하여 스트림에 데이터를 밀어 넣을 수 있습니다. |
| **수명(Lifetime) 관리** | 스트림을 소비하는 `Task`가 취소되거나 `for-await` 루프를 빠져나오면 `onTermination` 클로저가 호출됩니다. 이 블록 내에서 기존 델리게이트나 옵저버를 해제하지 않으면 레거시 시스템이 프록시를 계속 강하게 참조하여 **영구적인 메모리 누수(Retain Cycle)**가 발생합니다. |
| **단방향 데이터 흐름** | `for await event in observeEvents(from: system)` 형태로 소비하면 데이터 경쟁 없이 안전하게 데이터를 수신할 수 있습니다. |

---

## Swift 6 Concurrency 리팩토링 아키텍처 가이드

Swift 6의 핵심은 컴파일 타임에 데이터 레이스(Data Race)를 원천 차단하는 '엄격한 동시성(Strict Concurrency)' 모델의 안착에 있습니다. 시스템 안정성과 성능 최적화를 동시에 달성하기 위한 전략적 리팩토링 로드맵입니다.

### 1. GCD에서 협력적 멀티태스킹으로의 전환

기존 GCD(Grand Central Dispatch) 기반 모델은 **선점형 멀티태스킹(Preemptive Multitasking)**에 의존합니다. OS 커널이 스레드 실행을 임의로 중단하고 컨텍스트 스위칭을 강제하며, 개발자가 시리얼 큐나 Lock을 통해 수동으로 상태를 보호해야 합니다. **스레드 폭발(Thread Explosion)** 현상은 과도한 컨텍스트 스위칭 비용을 발생시켜 시스템 전체의 전진 보장(Forward Progress)을 저해합니다.

Swift 6의 동시성 모델은 **협력적 멀티태스킹(Cooperative Multitasking)**을 지향합니다:
- 작업(Task)은 오직 `await`로 표시된 일시 중단 지점(Suspension Point)에서만 제어권을 런타임에 양도
- 시스템은 기기의 CPU 코어 수에 맞춘 **고정 폭 스레드 풀(Fixed-width thread pool)**을 관리하여 리소스 고갈 방지
- 시스템 전체의 **예측 가능성** 확보가 목적

### 2. 컴플리션 핸들러 단계적 리팩토링 ('Crunchy Bagel' 전략)

대규모 코드베이스에서 모든 콜백 기반 코드를 한 번에 바꾸는 것은 불가능합니다. 하위 호환성을 유지하면서 안전하게 마이그레이션하는 4단계 전략:

| 단계 | 활동 | 설명 |
|------|------|------|
| **1. Async Wrapper** | `withCheckedThrowingContinuation`으로 래핑 | 기존 콜백 API를 비동기 함수로 감쌈 |
| **2. Deprecation** | `@available(*, deprecated, renamed: "...")` | 컴파일러가 새 API로의 전환을 유도 |
| **3. 로직 분리** | 프라이빗 메서드(`_fetchData`)로 이동 | 콜백 API와 async API가 동일 로직 공유 |
| **4. 최종 전환** | Continuation 래퍼 제거 | 순수 async 방식으로 완전 전환 |

### 3. Continuation 브리징 기술

시스템 프레임워크나 SDK의 콜백 API를 현대적 동시성 도메인으로 통합할 때 Continuation은 브릿지 역할을 수행합니다.

| 타입 | 특성 | 사용 시점 |
|------|------|----------|
| **CheckedContinuation** | 재개가 정확히 한 번 발생하는지 런타임 검증. 두 번 재개 시 크래시, 미재개 시 메모리 누수 | 원칙적으로 항상 사용 |
| **UnsafeContinuation** | 런타임 검증 생략. 오버헤드 적음 | 성능 임계 영역으로 검증된 경우에만 |

**표준 패턴**: `Result` 타입을 직접 수용하여 실수 방지

```swift
func fetchData() async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        legacyAPI.load { result in
            // Result 타입을 그대로 resume에 전달하여 '정확히 한 번' 원칙 준수
            continuation.resume(with: result)
        }
    }
}
```

### 4. Actor 재진입성과 Task 캐싱 전략

Actor의 `await` 호출 시 **재진입성(Reentrancy)** 문제가 발생합니다. Actor는 비동기 작업 중 `await` 지점에서 일시 중단되면, 메일박스의 다른 메시지를 처리하기 시작합니다. '중복 네트워크 요청'과 같은 논리적 오류를 방지하기 위해 **Task 캐싱 전략**을 도입해야 합니다.

```swift
actor DataCache {
    private enum CacheEntry {
        case inProgress(Task<Data, Error>)
        case ready(Data)
    }
    private var cache: [UUID: CacheEntry] = [:]

    func fetch(id: UUID) async throws -> Data {
        // 1. 이미 진행 중인 Task가 있다면 해당 Task에 Join하여 중복 요청 방지
        if let entry = cache[id] {
            switch entry {
            case .ready(let data): return data
            case .inProgress(let task): return try await task.value
            }
        }

        // 2. 새로운 Task 생성 및 캐싱
        let task = Task { try await download(id) }
        cache[id] = .inProgress(task)

        do {
            let data = try await task.value
            // [주의]: await 이후에는 Actor의 상태가 변경되었을 수 있음
            // 반드시 상태 가정을 재검증(Re-verify state assumptions)해야 함
            cache[id] = .ready(data)
            return data
        } catch {
            cache[id] = nil
            throw error
        }
    }
}
```

### 5. Sendability 보장 전략 심화

| 타입 | Sendable 조건 | 비고 |
|------|-------------|------|
| **Value Types** | `struct`/`enum`의 모든 속성이 Sendable이면 자동 준수 | 가장 안전한 선택 |
| **Reference Types** | `final` 클래스 + 불변(`let`) 속성만 가질 때 | 제한적 |
| **Manual Sync** | `NSLock` 등으로 스레드 안전성 수동 확보 → `@unchecked Sendable` | 기술 부채로 추적 관리 |
| **프로토콜 합성** | `P & Sendable` 문법으로 격리 경계 보증 | 추상화된 프로토콜 전달 시 사용 |

**핵심**: `P & Sendable` 합성 문법은 해당 프로토콜을 준수하는 구체적 인스턴스가 동시성 안전성을 갖추었음을 보장하는 격리 경계의 보증수표입니다.

### 6. 협력적 스레드 풀 최적화 및 데드락 방지

Swift Concurrency는 CPU 코어 수에 맞춘 **고정 폭 협력적 스레드 풀**을 사용합니다. 불투명한 하위 시스템(예: Vision.framework)이 내부적으로 `DispatchGroup.wait()` 같은 동기식 차단 작업을 수행하면, 협력적 풀의 스레드가 완전히 점유됩니다. 풀의 모든 스레드가 차단되면 **순환 종속성(Circular Dependency)에 의한 데드락**이 발생합니다.

**해결**: 블로킹 API는 `DispatchQueue`로 작업을 오프로딩하고 Continuation으로 브리징

```swift
func heavyProcessingBridge() async throws -> ResultData {
    try await withCheckedThrowingContinuation { continuation in
        // 고정 폭 스레드 풀을 점유하지 않도록 별도 큐로 오프로딩
        DispatchQueue.global(qos: .userInitiated).async {
            let result = callOpaqueBlockingAPI()
            continuation.resume(returning: result)
        }
    }
}
```

### 7. 대규모 프로젝트 마이그레이션 로드맵

| 단계 | 주요 활동 | Build Setting & Tech Debt |
|------|----------|--------------------------|
| **Phase 1: 진단** | 경고 분석 및 데이터 격리 경계 파악 | `targeted`, IUO 및 legacy `@objc` 패턴 오딧 |
| **Phase 2: 기반** | UI `@MainActor` 격리, 값 타입 Sendable 최적화 | `targeted`, Obj-C 인터롭 경계 설정 |
| **Phase 3: Actor 전환** | 공유 싱글톤/매니저 객체를 Actor로 리팩토링 | `complete`, `@preconcurrency import` 활용 |
| **Phase 4: 엄격화** | 모든 모듈의 경고 해결 및 브릿징 코드 최적화 | `complete`, `@unchecked Sendable` 정당화 문서화 |
| **Phase 5: 완료** | Swift 6 언어 모드 활성화 (Warnings → Errors) | `SWIFT_VERSION=6`, 기술 부채 청산 완료 |

**Objective-C Interop**: `@preconcurrency import`를 사용하여 레거시 모듈의 경계를 관리하고 점진적으로 제거합니다.

### 8. Swift Testing과 동시성 통합

기존 XCTest는 `@MainActor` 격리 환경을 테스트하기 위해 `expectation`과 `wait` 로직을 남발해야 했습니다. Swift Testing 프레임워크는 동시성 모델과 네이티브하게 통합됩니다.

```swift
// Before (XCTest)
func testFetch() {
    let expectation = expectation(description: "fetch")
    Task { @MainActor in
        let cache = DataCache()
        let data = try await cache.fetch(id: testID)
        XCTAssertNotNil(data)
        expectation.fulfill()
    }
    wait(for: [expectation], timeout: 5.0)
}

// After (Swift Testing)
@Test @MainActor
func testActorStateConsistency() async throws {
    let cache = DataCache()
    let data = try await cache.fetch(id: testID)
    #expect(data != nil)
}
```
