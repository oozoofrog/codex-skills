# Platform Checklists

필요한 섹션만 읽기.
작업과 무관한 플랫폼 체크리스트까지 모두 끌어오지 말기.

## SwiftUI

우선 점검하기.
- `@State`, `@StateObject`, `@ObservedObject`, `@EnvironmentObject` 선택 근거
- `.task`와 `.task(id:)`의 재실행 조건
- `onAppear`와 `.task`를 중복으로 사용해 동일 작업을 두 번 트리거하지 않는지
- ViewModel 메서드를 `async`로 노출해 화면 생명주기 취소를 자연스럽게 따르는지
- 동일 비동기 작업 중복 실행 방지 로직이 있는지
- 화면 이탈 후 상태 반영 전에 cancellation을 확인하는지
- `CancellationError`를 사용자 노출 에러로 잘못 처리하지 않는지
- `.alert(isPresented:)`에서 `.constant(...)`로 dismiss 불가능한 상태를 만들지 않는지
- 에러 alert는 dismiss 시 상태를 정리하는 `Binding` 또는 `item` 기반 표현을 쓰는지
- View identity 변경에 따른 상태 초기화와 재로딩을 의도적으로 설계했는지
- MainActor 보장 없이 UI 상태를 쓰는 코드가 없는지

## UIKit

우선 점검하기.
- `viewDidLoad`, `viewWillAppear`, `viewDidAppear`, `deinit` 영향
- delegate, datasource, observer 중복 등록
- 셀/뷰 재사용으로 인한 stale UI
- 오토레이아웃 충돌과 화면 회전 영향
- dismissal/presentation 타이밍 이슈
- 생명주기와 비동기 콜백의 경합

## Networking

우선 점검하기.
- retry, timeout, cancellation
- auth refresh와 재시도 루프
- transport error와 domain error 구분
- idempotency와 동일 요청 중복 실행
- 느린 네트워크에서 로딩/실패 UI
- 앱 백그라운드 전환 중 요청 처리

## Swift Concurrency

우선 점검하기.
- MainActor 경계
- cancellation propagation
- 공유 mutable state 접근
- 동일 작업 중복 실행과 재진입
- detached task 또는 unstructured task 남용
- 화면이 사라진 뒤 결과를 반영하는 코드

## Bug Investigation

우선 점검하기.
- 재현 조건 정리
- 반증 실험 설계
- 최근 변경 사항과 최초 발생 시점
- 증상 완화가 아니라 원인 제거인지 여부
- 회귀 테스트 또는 수동 QA 경로
