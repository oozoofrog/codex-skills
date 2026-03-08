# Prompt Boosters

원문 iOS 협업 템플릿의 “상황별 한 줄 보강 문구”를 Claude CLI용으로 옮긴 것이다.
기본 템플릿 뒤에 필요한 문구만 덧붙이기.

## SwiftUI Booster

```text
In SwiftUI, explain why each state wrapper choice is correct, and check repeated triggers from onAppear, task, refreshable, navigation, sheet, and alert.
```

## UIKit Booster

```text
In UIKit, prioritize viewDidLoad/viewWillAppear/viewDidAppear/deinit effects, delegate or observer duplication, reuse bugs, and layout conflicts.
```

## Networking Booster

```text
For networking work, prioritize retry, timeout, cancellation, auth refresh, error mapping, and idempotency. Distinguish transport errors from domain errors.
```

## Bug Investigation Booster

```text
Prefer root-cause fixes over symptom masking, and include reproduction conditions, disconfirming experiments, and regression coverage.
```

## Swift Concurrency Booster

```text
Prioritize MainActor boundaries, cancellation propagation, shared mutable state access, duplicate task execution, and post-dismiss state updates.
```
