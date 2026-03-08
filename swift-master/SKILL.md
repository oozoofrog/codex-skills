---
name: swift-master
description: >-
  Review, optimize, migrate, guide, and generate Swift/iOS code across Swift 6,
  SwiftUI, Swift Concurrency, SwiftData, MVVM/TCA architecture, Pure DI, and
  Combine-to-AsyncSequence conversion. Use when Codex needs domain-specific
  Swift expertise for `.swift` files, iOS app codebases, SwiftUI state
  management, concurrency correctness, Swift 6 migration, architecture choices,
  dependency injection, or repo-wide code review.
---

# Swift Master

## Overview

Swift/iOS 코드베이스를 리뷰, 최적화, 마이그레이션, 가이드, 생성할 때 사용하는 통합 스킬.
항상 작업 모드와 도메인을 먼저 고르고, 관련 reference만 읽고, 파일/라인 근거가 있는 결과를 내기.

## Quick Start

1. 먼저 `references/quick-reference.md`에서 작업 유형별 진입점을 고르기.
2. 요청을 모드와 도메인으로 분류하기.
3. 필요한 reference만 선택해서 읽기.
4. 리뷰나 마이그레이션은 최소 변경과 버전 제약을 먼저 확인하기.
5. `MainActor`, `Sendable`, actor 경계, cancellation이 얽히면 strict concurrency 검증을 기본 검증 기준으로 올리기.
6. 결과에는 근거, 영향, 수정 방향, 검증 방법을 포함하기.

자주 쓰는 reference:
- 빠른 진입: `references/quick-reference.md`
- SwiftUI: `references/swiftui-reference.md`
- SwiftData: `references/swiftdata-reference.md`
- Concurrency: `references/concurrency-reference.md`
- Swift 6: `references/swift6-reference.md`
- Architecture: `references/architecture-reference.md`
- Pure DI: `references/pure-di-reference.md`
- Combine 변환: `references/combine-migration.md`
- 짧은 팀 규칙: `references/swift-conventions-reference.md`
- 예시 중심 실전 패턴: `references/swift-practices-reference.md`
- 전체 변환 예시: `references/transformation-examples.md`

## Mode Selection

### REVIEW

- 안티패턴, 버그 위험, 설계 문제, 마이그레이션 포인트를 찾기.
- 전체 repo 리뷰라면 관련 도메인 reference를 1~2개만 먼저 열고 검색 범위를 좁히기.

### OPTIMIZE

- 성능, 메모리, 재렌더링, 불필요한 추상화, 취소 누락, 상태 오염을 점검하기.
- 코드 변경이 필요 없으면 관찰 결과와 우선순위만 제시하기.

### MIGRATE

- Swift 6, `@Observable`, `NavigationStack`, Swift Concurrency, AsyncSequence 등 최신 패턴으로 전환하기.
- 배포 타깃과 프레임워크 제약이 확인되지 않으면 가정과 대안을 함께 적기.

### GUIDE

- 패턴 선택, 설계 비교, 베스트 프랙티스, 팀 규칙 정리에 집중하기.
- MVVM/TCA, Pure DI, SwiftData 도입 판단 같은 질문에 적합하기.

### GENERATE

- 새 타입, ViewModel, Actor, AsyncSequence 브리지, DI wiring 같은 코드를 생성하기.
- 생성 시 선택한 패턴의 이유와 테스트 포인트를 함께 제시하기.

## Domain Routing

### SwiftUI

다음을 우선 점검하기.
- `ObservableObject` vs `@Observable`
- `@State`, `@StateObject`, `@Bindable`, `@Environment` 선택
- `NavigationView` → `NavigationStack`
- View 재렌더링, state source of truth, MainActor 경계

필요 시 `references/swiftui-reference.md`를 읽기.

### SwiftData

다음을 우선 점검하기.
- `@Model` 설계, 관계 모델링, delete rule
- `ModelContext` 생성 위치
- 스레딩 규칙과 `PersistentIdentifier` 전달
- Preview/Test용 in-memory container

필요 시 `references/swiftdata-reference.md`를 읽기.

### Concurrency

다음을 우선 점검하기.
- `DispatchQueue`, `DispatchGroup`, `DispatchSemaphore` 대체
- `Task`, `TaskGroup`, `Actor`, `AsyncStream`, cancellation
- `Sendable`, actor 재진입, `@MainActor`, continuation 안전성
- actor-isolated 타입이 non-Sendable 서비스나 protocol existential을 보관한 채 async 호출하는지
- `async func`가 실제 작업 완료 전에 return하는 의미 불일치 패턴인지
- 취소된 이전 Task가 최신 요청의 `isLoading` / `error` / `result` 상태를 덮어쓰는지

필요 시 `references/concurrency-reference.md`와 `references/swift6-reference.md`를 읽기.

### Architecture / DI

다음을 우선 점검하기.
- MVVM vs TCA 선택 기준
- Composition Root, Factory, Protocol Witness, Environment 패턴
- Service Locator 또는 전역 상태 남용 여부

필요 시 `references/architecture-reference.md`와 `references/pure-di-reference.md`를 읽기.

### Combine / Migration

다음을 우선 점검하기.
- `Publisher` → `AsyncSequence`
- `sink` → `for await`
- `AnyCancellable` → `Task`
- 레거시 callback/delegate → continuation 또는 `AsyncStream`

필요 시 `references/combine-migration.md`와 `references/transformation-examples.md`를 읽기.

## Workflow

### 1) 범위와 버전 가정 확정하기

- 리뷰 대상 파일, 프레임워크, 최소 iOS 버전, Swift 버전을 먼저 확인하기.
- 버전이 불명확하면 최신 패턴을 강제하지 말고 가정으로 명시하기.

### 2) 필요한 reference만 고르기

- SwiftUI 문제면 `swiftui-reference.md`부터 읽기.
- 동시성 경고나 데드락 위험이면 `concurrency-reference.md`와 `swift6-reference.md`를 읽기.
- 설계 질문이면 `architecture-reference.md` 또는 `pure-di-reference.md`를 읽기.
- 모든 reference를 한 번에 읽지 말기.

### 3) 코드와 로그를 검색하기

- repo-wide 리뷰에서는 먼저 검색으로 후보를 좁히기.
- 예: `Task.detached`, `DispatchQueue.main.sync`, `@unchecked Sendable`, `NavigationLink(destination:)`, `@State private var ... = ViewModel()`, `modelContext.insert`
- 예: `Task { ... }`를 spawn만 하고 기다리지 않는 `async` 함수, `generate()`처럼 보이지만 실제로는 `startGenerate()` 의미인 API, `requestID`/token 없이 최신 상태를 덮어쓰는 코드
- 검색 결과와 실제 코드 읽기를 결합해 판단하기.

### 4) 결과를 구조화하기

- 리뷰는 심각도별로 묶기.
- 각 항목에 파일/라인, 문제 이유, 영향, 최소 수정 방향을 포함하기.
- 참고한 reference를 같이 적기.
- strict concurrency 위험을 찾으면 진단으로 끝내지 말고, 바로 적용 가능한 수정 방향 1개 이상을 반드시 포함하기.

### 5) 변경이나 생성이 필요하면 최소 diff로 진행하기

- 무관한 스타일 정리나 대규모 구조 개편을 피하기.
- 마이그레이션은 한 번에 한 축씩 진행하기.
- 가능하면 테스트나 검증 명령도 함께 제시하기.
- Concurrency 작업은 가능하면 `swift test`, `swift build`, `xcodebuild test`, strict concurrency build를 우선 검증 명령으로 제시하기.

## Migration Defaults

- iOS 17+가 확실하면 `ObservableObject` 대신 `@Observable`을 우선 검토하기.
- iOS 16+면 `NavigationView`보다 `NavigationStack`을 우선 검토하기.
- GCD와 callback은 `async/await`, `TaskGroup`, `Actor`, continuation으로 단계적 전환을 우선하기.
- DI는 container보다 Pure DI와 Composition Root를 우선 검토하기.
- Combine은 새 코드에서 AsyncSequence 기반 설계를 우선 검토하기.
- 다만 배포 타깃, 팀 규칙, 외부 라이브러리 의존성 때문에 유지가 필요하면 근거를 남기기.

## Output Contract

- 항상 다음을 포함해 응답하기.
  - 작업 모드와 도메인
  - 검토/수정한 파일 범위
  - 핵심 이슈 또는 선택한 패턴
  - 근거와 영향
  - 최소 수정 방향 또는 생성 결과
  - 검증 또는 다음 단계
- strict concurrency 위험을 찾으면 예상 실패 명령 또는 실제 실패 명령, 그리고 즉시 적용 가능한 다음 수정안을 포함하기.

- 리뷰 결과에는 가능하면 다음 형식을 따르기.
  - CRITICAL: 반드시 수정해야 하는 문제
  - WARNING: 높은 확률의 버그 또는 유지보수 위험
  - INFO: 개선 권장 사항

- 가이드 요청에는 다음을 포함하기.
  - 추천안
  - 대안 1개 이상
  - 선택 기준
  - 적용 시 주의점
