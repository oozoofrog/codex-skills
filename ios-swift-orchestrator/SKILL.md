---
name: ios-swift-orchestrator
description: >-
  Route iOS/Swift tasks between multi-agent delivery workflow and deep Swift
  domain expertise. Use when Codex needs a single entry point to decide whether
  to apply `ios-multi-agent-dev`, `swift-master`, or both for iOS bug fixes,
  features, refactors, SwiftUI/SwiftData/concurrency issues, Swift 6
  migrations, release-sensitive changes, or code review.
---

# iOS Swift Orchestrator

## Overview

iOS/Swift 작업의 상위 진입점으로 동작하기.
작업을 먼저 분류한 뒤, 협업 워크플로가 핵심이면 `ios-multi-agent-dev`, Swift 기술 판단이 핵심이면 `swift-master`, 둘 다 필요하면 두 스킬을 함께 적용하기.

## Quick Start

1. `references/routing-guide.md`에서 작업 유형과 위험도를 먼저 분류하기.
2. 협업/검증/릴리즈 리스크가 크면 `../ios-multi-agent-dev/SKILL.md`를 읽기.
3. SwiftUI, SwiftData, Concurrency, DI, Swift 6, Combine 판단이 필요하면 `../swift-master/SKILL.md`를 읽기.
4. 둘 다 필요하면 먼저 오케스트레이션 흐름을 정하고, 그 다음 Swift 세부 판단을 붙이기.
5. `MainActor`, `Sendable`, cancellation, `.task`, SwiftUI lifecycle이 핵심이면 최종 검증 기준을 strict concurrency build/test로 올리기.
6. 항상 선택한 하위 스킬과 선택 이유를 응답에 명시하기.

## Routing Rules

### `ios-multi-agent-dev`를 우선 적용하기

다음 중 하나라도 해당하면 먼저 `../ios-multi-agent-dev/SKILL.md`를 읽기.
- 기능 추가, 버그 수정, 리팩터링처럼 실제 코드 변경이 포함되기
- 여러 단계 handoff, 구현 후 검증, 비판적 리뷰가 중요하기
- 릴리즈 직전, 결제/인증, 데이터 무결성, 회귀 위험 같은 고위험 작업이기
- planner / builder / reviewer 역할 분리가 필요한 작업이기

### `swift-master`를 우선 적용하기

다음 중 하나라도 해당하면 먼저 `../swift-master/SKILL.md`를 읽기.
- SwiftUI 상태 관리, Navigation, 렌더링, SwiftData 모델링 문제이기
- Swift Concurrency, `Sendable`, `@MainActor`, cancellation 검토가 핵심이기
- Swift 6 마이그레이션, `@Observable`, `NavigationStack`, AsyncSequence 전환이 필요하기
- MVVM/TCA, Pure DI, Composition Root 같은 설계 판단이 핵심이기
- repo-wide Swift 리뷰나 코드 생성이 목적이기

### 둘 다 함께 적용하기

다음처럼 “실제 변경 + Swift 전문 판단”이 동시에 필요하면 둘 다 적용하기.
- 릴리즈 민감 iOS 버그 수정 + Concurrency 위험 분석
- SwiftUI 화면 리팩터링 + 멀티에이전트 검증 루프
- Swift 6 마이그레이션을 단계적으로 안전하게 진행하기
- 아키텍처/DI 개편을 여러 단계로 설계하고 구현하기

## Wrapper Workflow

### 1) 작업 분류하기

- 작업을 `협업 중심`, `기술 판단 중심`, `둘 다 필요`로 분류하기.
- 불확실하면 위험이 큰 쪽으로 분류하기.

### 2) 하위 스킬 선택하기

- workflow가 핵심이면 `ios-multi-agent-dev`
- 기술 판단이 핵심이면 `swift-master`
- 둘 다면 오케스트레이션 → 기술 판단 순으로 사용하기

### 3) 결과 통합하기

- `ios-multi-agent-dev`를 쓸 때는 단계, 역할, 검증 상태를 유지하기.
- `swift-master`를 쓸 때는 도메인, 근거, 최소 수정 방향을 유지하기.
- 둘 다 쓸 때는 workflow 출력 형식 안에 Swift 판단 근거를 녹여 넣기.

### 4) 검증 기준 올리기

- SwiftUI lifecycle + concurrency 문제가 섞이면 `typecheck`만으로 끝내지 말기.
- 가능하면 `swift test`, `swift build`, `xcodebuild test`, strict concurrency build를 검증 기준으로 삼기.
- 검증이 실패하면 성공처럼 보고하지 말고, 즉시 수정 루프 또는 구체적인 다음 수정안을 제시하기.

## Companion Skill Contract

- 이 스킬은 세부 구현 규칙을 모두 복제하지 않기.
- 협업 흐름은 `../ios-multi-agent-dev/SKILL.md`에 위임하기.
- Swift 기술 세부사항은 `../swift-master/SKILL.md`와 그 references에 위임하기.
- companion skill이 없으면 현재 SKILL.md의 라우팅 규칙만으로 최소 판단을 수행하고, 부족한 세부 지식은 직접 코드에서 확인하기.

## Output Contract

항상 다음을 포함해 응답하기.
- 선택한 하위 스킬: `ios-multi-agent-dev`, `swift-master`, 또는 둘 다
- 선택 이유
- 현재 단계 또는 작업 모드
- 검증 기준
- 핵심 위험 또는 핵심 기술 판단
- 다음 단계
