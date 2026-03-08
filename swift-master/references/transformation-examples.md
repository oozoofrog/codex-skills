# Swift Transformation Examples

실제 코드 변환 예시 모음입니다.

---

## Quick Index

- ObservableObject → `@Observable`
- `NavigationView` → `NavigationStack`
- Singleton Cache → Actor
- Core Data Background → SwiftData `@ModelActor`
- Combine Publisher → `AsyncSequence`
- Delegate Pattern → async/await
- Quick Transformation Cheat Sheet

## 1. ObservableObject → @Observable 전체 예시

### Before

```swift
import SwiftUI
import Combine

class UserViewModel: ObservableObject {
    @Published var user: User?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private var cancellables = Set<AnyCancellable>()

    func loadUser(id: String) {
        isLoading = true
        errorMessage = nil

        NetworkService.shared.fetchUser(id: id)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] completion in
                self?.isLoading = false
                if case .failure(let error) = completion {
                    self?.errorMessage = error.localizedDescription
                }
            } receiveValue: { [weak self] user in
                self?.user = user
            }
            .store(in: &cancellables)
    }
}

struct UserProfileView: View {
    @StateObject private var viewModel = UserViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView()
            } else if let user = viewModel.user {
                VStack {
                    Text(user.name)
                    Text(user.email)
                }
            } else if let error = viewModel.errorMessage {
                Text(error).foregroundColor(.red)
            }
        }
        .onAppear {
            viewModel.loadUser(id: "123")
        }
    }
}
```

### After

```swift
import SwiftUI

@Observable
@MainActor
final class UserViewModel {
    var user: User?
    var isLoading = false
    var errorMessage: String?

    func loadUser(id: String) async {
        isLoading = true
        errorMessage = nil

        do {
            user = try await NetworkService.shared.fetchUser(id: id)
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

struct UserProfileView: View {
    @State private var viewModel = UserViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView()
            } else if let user = viewModel.user {
                VStack {
                    Text(user.name)
                    Text(user.email)
                }
            } else if let error = viewModel.errorMessage {
                Text(error).foregroundColor(.red)
            }
        }
        .task {
            await viewModel.loadUser(id: "123")
        }
    }
}
```

---

## 2. NavigationView → NavigationStack 전체 예시

### Before

```swift
struct ContentView: View {
    @State private var selectedItem: Item?

    var body: some View {
        NavigationView {
            List(items) { item in
                NavigationLink(destination: DetailView(item: item)) {
                    ItemRow(item: item)
                }
            }
            .navigationTitle("Items")
        }
        .navigationViewStyle(.stack)
    }
}

struct DetailView: View {
    let item: Item

    var body: some View {
        VStack {
            Text(item.title)
            NavigationLink("Edit", destination: EditView(item: item))
        }
    }
}
```

### After

```swift
enum Route: Hashable {
    case detail(Item)
    case edit(Item)
    case settings
}

struct ContentView: View {
    @State private var path: [Route] = []

    var body: some View {
        NavigationStack(path: $path) {
            List(items) { item in
                Button {
                    path.append(.detail(item))
                } label: {
                    ItemRow(item: item)
                }
            }
            .navigationTitle("Items")
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .detail(let item):
                    DetailView(item: item, path: $path)
                case .edit(let item):
                    EditView(item: item)
                case .settings:
                    SettingsView()
                }
            }
        }
    }
}

struct DetailView: View {
    let item: Item
    @Binding var path: [Route]

    var body: some View {
        VStack {
            Text(item.title)
            Button("Edit") {
                path.append(.edit(item))
            }
        }
    }
}
```

---

## 3. Singleton Cache → Actor

### Before

```swift
class ImageCache {
    static let shared = ImageCache()

    private var cache = NSCache<NSString, UIImage>()
    private let lock = NSLock()

    private init() {}

    func image(for key: String) -> UIImage? {
        lock.lock()
        defer { lock.unlock() }
        return cache.object(forKey: key as NSString)
    }

    func setImage(_ image: UIImage, for key: String) {
        lock.lock()
        defer { lock.unlock() }
        cache.setObject(image, forKey: key as NSString)
    }

    func downloadImage(from url: URL, completion: @escaping (UIImage?) -> Void) {
        if let cached = image(for: url.absoluteString) {
            completion(cached)
            return
        }

        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let data = data, let image = UIImage(data: data) else {
                completion(nil)
                return
            }
            self?.setImage(image, for: url.absoluteString)
            DispatchQueue.main.async {
                completion(image)
            }
        }.resume()
    }
}
```

### After

```swift
actor ImageCache {
    static let shared = ImageCache()

    private var cache: [String: UIImage] = [:]
    private var inProgress: [String: Task<UIImage?, Never>] = [:]

    func image(for key: String) -> UIImage? {
        cache[key]
    }

    func setImage(_ image: UIImage, for key: String) {
        cache[key] = image
    }

    func downloadImage(from url: URL) async -> UIImage? {
        let key = url.absoluteString

        // 캐시 확인
        if let cached = cache[key] {
            return cached
        }

        // 진행 중인 다운로드 확인 (중복 요청 방지)
        if let existing = inProgress[key] {
            return await existing.value
        }

        // 새 다운로드 시작
        let task = Task<UIImage?, Never> {
            guard let (data, _) = try? await URLSession.shared.data(from: url),
                  let image = UIImage(data: data) else {
                return nil
            }
            cache[key] = image
            return image
        }

        inProgress[key] = task
        let result = await task.value
        inProgress.removeValue(forKey: key)

        return result
    }
}

// 사용
Task {
    let image = await ImageCache.shared.downloadImage(from: url)
    await MainActor.run {
        imageView.image = image
    }
}
```

---

## 4. Core Data Background → SwiftData @ModelActor

### Before (Core Data)

```swift
class DataManager {
    let container: NSPersistentContainer

    func fetchUsers(completion: @escaping ([User]) -> Void) {
        container.performBackgroundTask { context in
            let request = NSFetchRequest<UserEntity>(entityName: "UserEntity")
            let entities = try? context.fetch(request)

            let users = entities?.map { entity in
                User(id: entity.id!, name: entity.name!, email: entity.email!)
            } ?? []

            DispatchQueue.main.async {
                completion(users)
            }
        }
    }

    func createUser(name: String, email: String, completion: @escaping (Bool) -> Void) {
        container.performBackgroundTask { context in
            let entity = UserEntity(context: context)
            entity.id = UUID()
            entity.name = name
            entity.email = email

            do {
                try context.save()
                DispatchQueue.main.async { completion(true) }
            } catch {
                DispatchQueue.main.async { completion(false) }
            }
        }
    }
}
```

### After (SwiftData)

```swift
@Model
final class User {
    @Attribute(.unique)
    var id: UUID
    var name: String
    var email: String

    init(name: String, email: String) {
        self.id = UUID()
        self.name = name
        self.email = email
    }
}

// Sendable DTO for cross-actor communication
struct UserDTO: Sendable {
    let id: PersistentIdentifier
    let name: String
    let email: String
}

@ModelActor
actor DatabaseManager {
    func fetchUsers() -> [UserDTO] {
        let descriptor = FetchDescriptor<User>(
            sortBy: [SortDescriptor(\.name)]
        )

        guard let users = try? modelContext.fetch(descriptor) else {
            return []
        }

        return users.map { user in
            UserDTO(id: user.persistentModelID, name: user.name, email: user.email)
        }
    }

    func createUser(name: String, email: String) -> UserDTO? {
        let user = User(name: name, email: email)
        modelContext.insert(user)

        do {
            try modelContext.save()
            return UserDTO(id: user.persistentModelID, name: user.name, email: user.email)
        } catch {
            return nil
        }
    }

    func deleteUser(id: PersistentIdentifier) -> Bool {
        guard let user = modelContext.model(for: id) as? User else {
            return false
        }

        modelContext.delete(user)

        do {
            try modelContext.save()
            return true
        } catch {
            return false
        }
    }
}

// Usage in View
struct UserListView: View {
    @Environment(\.modelContainer) private var container
    @State private var users: [UserDTO] = []

    var body: some View {
        List(users, id: \.id) { user in
            Text(user.name)
        }
        .task {
            let manager = DatabaseManager(modelContainer: container)
            users = await manager.fetchUsers()
        }
    }
}
```

---

## 5. Combine Publisher → AsyncSequence

### Before

```swift
class SearchViewModel: ObservableObject {
    @Published var searchText = ""
    @Published var results: [SearchResult] = []

    private var cancellables = Set<AnyCancellable>()

    init() {
        $searchText
            .debounce(for: .milliseconds(300), scheduler: RunLoop.main)
            .removeDuplicates()
            .filter { !$0.isEmpty }
            .flatMap { query in
                SearchService.shared.search(query: query)
                    .catch { _ in Just([]) }
            }
            .receive(on: DispatchQueue.main)
            .assign(to: &$results)
    }
}
```

### After

```swift
@Observable
@MainActor
final class SearchViewModel {
    var searchText = ""
    var results: [SearchResult] = []

    private var searchTask: Task<Void, Never>?

    func searchTextChanged(_ newValue: String) {
        searchTask?.cancel()

        guard !newValue.isEmpty else {
            results = []
            return
        }

        searchTask = Task {
            // Debounce
            try? await Task.sleep(for: .milliseconds(300))

            guard !Task.isCancelled else { return }

            do {
                let searchResults = try await SearchService.shared.search(query: newValue)

                guard !Task.isCancelled else { return }

                results = searchResults
            } catch {
                if !Task.isCancelled {
                    results = []
                }
            }
        }
    }
}

// View
struct SearchView: View {
    @State private var viewModel = SearchViewModel()

    var body: some View {
        List(viewModel.results) { result in
            Text(result.title)
        }
        .searchable(text: $viewModel.searchText)
        .onChange(of: viewModel.searchText) { _, newValue in
            viewModel.searchTextChanged(newValue)
        }
    }
}
```

---

## 6. Delegate Pattern → async/await

### Before

```swift
protocol LocationManagerDelegate: AnyObject {
    func didUpdateLocation(_ location: CLLocation)
    func didFailWithError(_ error: Error)
}

class LocationManager: NSObject, CLLocationManagerDelegate {
    weak var delegate: LocationManagerDelegate?
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
    }

    func requestLocation() {
        manager.requestLocation()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        if let location = locations.first {
            delegate?.didUpdateLocation(location)
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        delegate?.didFailWithError(error)
    }
}
```

### After

```swift
actor LocationManager {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocation, Error>?

    func requestLocation() async throws -> CLLocation {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation

            Task { @MainActor in
                manager.requestLocation()
            }
        }
    }

    func handleLocation(_ location: CLLocation) {
        continuation?.resume(returning: location)
        continuation = nil
    }

    func handleError(_ error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}

// CLLocationManagerDelegate 구현 (Bridge)
class LocationManagerBridge: NSObject, CLLocationManagerDelegate {
    let actor: LocationManager

    init(actor: LocationManager) {
        self.actor = actor
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        if let location = locations.first {
            Task { await actor.handleLocation(location) }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { await actor.handleError(error) }
    }
}

// Usage
Task {
    do {
        let location = try await locationManager.requestLocation()
        print("Location: \(location)")
    } catch {
        print("Error: \(error)")
    }
}
```

---

## Quick Transformation Cheat Sheet

| Before | After |
|--------|-------|
| `DispatchQueue.main.async { }` | `await MainActor.run { }` |
| `DispatchQueue.global().async { }` | `Task { }` |
| `DispatchGroup` | `withTaskGroup` |
| `DispatchSemaphore` | `Actor` |
| `@escaping completion` | `async throws ->` |
| `ObservableObject` | `@Observable` |
| `@Published` | (제거) |
| `@StateObject` | `@State` |
| `@ObservedObject` | `@Bindable` or plain property |
| `.onAppear { }` (async work) | `.task { }` |
| `Timer.scheduledTimer` | `AsyncTimerSequence` |
| `NotificationCenter.addObserver` | `NotificationCenter.notifications(named:)` |
| `URLSession.dataTask` | `URLSession.data(from:)` |
