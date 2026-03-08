# iOS Swift Orchestrator Routing Guide

이 문서는 상위 래퍼 스킬의 빠른 분기표입니다.

## Quick Matrix

| 상황 | 우선 스킬 | 이유 |
|------|-----------|------|
| 단순 SwiftUI/Concurrency 코드 리뷰 | `swift-master` | 기술 판단이 핵심 |
| Swift 6 / `@Observable` / AsyncSequence 마이그레이션 | `swift-master` | 마이그레이션 규칙과 예시가 중요 |
| 릴리즈 직전 iOS 버그 수정 | `ios-multi-agent-dev` | 검증 루프와 리뷰 게이트가 중요 |
| 구현 + 테스트 + 리뷰 + handoff가 필요한 기능 추가 | `ios-multi-agent-dev` | 멀티에이전트 흐름이 핵심 |
| SwiftUI 리팩터링을 여러 단계로 안전하게 진행 | 둘 다 | workflow와 기술 판단이 모두 필요 |
| DI/Architecture 개편 설계 + 구현 | 둘 다 | 설계 판단과 단계적 실행이 모두 필요 |

## Decision Tree

### 1. 실제 코드 변경과 handoff가 중심인가?

- 예 → `ios-multi-agent-dev` 우선
- 아니오 → 다음 질문으로 이동

### 2. Swift 기술 전문 판단이 중심인가?

- 예 → `swift-master` 우선
- 아니오 → 다음 질문으로 이동

### 3. 릴리즈 리스크가 높고 Swift 전문 판단도 필요한가?

- 예 → 둘 다 사용
- 아니오 → 더 단순한 쪽 하나만 선택

## Recommended Pairing Pattern

### 패턴 A: Workflow-first

다음에 적합합니다.
- 버그 수정
- 기능 추가
- 릴리즈 민감 변경
- 여러 에이전트 협업이 필요한 작업

순서:
1. `ios-multi-agent-dev`로 Task Brief와 단계 고정
2. 필요한 단계에서 `swift-master`로 기술 판단 보강
3. 메인 에이전트가 검증 루프 수행

### 패턴 B: Expertise-first

다음에 적합합니다.
- 코드 리뷰
- 마이그레이션 설계
- SwiftUI/Concurrency/SwiftData 설계 판단
- 아키텍처 비교

순서:
1. `swift-master`로 기술 판단과 reference 선택
2. 실제 구현/검증이 커지면 `ios-multi-agent-dev`로 승격

## Example Requests

- "이 SwiftUI 코드 상태 관리 문제 리뷰해줘" → `swift-master`
- "릴리즈 전에 이 iOS 버그를 안전하게 고쳐줘" → `ios-multi-agent-dev`
- "Swift 6 마이그레이션을 여러 단계로 안전하게 진행해줘" → 둘 다
- "SwiftData + Concurrency 이슈를 분석하고 수정까지 해줘" → 둘 다
