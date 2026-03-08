# iOS Swift Orchestrator Routing Guide

이 문서는 상위 래퍼 스킬의 빠른 분기표입니다.

## Quick Matrix

| 상황 | 우선 스킬 | 이유 |
|------|-----------|------|
| 단순 SwiftUI/Concurrency 코드 리뷰 | `swift-master` | 기술 판단이 핵심 |
| Swift 6 / `@Observable` / AsyncSequence 마이그레이션 | `swift-master` | 마이그레이션 규칙과 예시가 중요 |
| 릴리즈 직전 iOS 버그 수정 | `ios-multi-agent-dev` | 검증 루프와 리뷰 게이트가 중요 |
| 구현 + 테스트 + 리뷰 + handoff가 필요한 기능 추가 | `ios-multi-agent-dev` | 멀티에이전트 흐름이 핵심 |
| `MainActor` / `Sendable` / cancellation이 얽힌 실제 수정 | 둘 다 | workflow와 strict concurrency 판단이 모두 필요 |
| 큰 코드베이스에서 Claude 2차 분석이 필요한 작업 | `swift-master` + `claude-code-bridge` | 전문 판단과 실제 Claude 분석을 결합 |
| 범위가 잠긴 구현을 Claude CLI에 맡기고 싶은 작업 | `ios-multi-agent-dev` + `claude-code-bridge` | 워크플로 통제와 실제 Claude 구현을 결합 |
| SwiftUI 리팩터링을 여러 단계로 안전하게 진행 | 둘 다 | workflow와 기술 판단이 모두 필요 |
| DI/Architecture 개편 설계 + 구현 | 둘 다 | 설계 판단과 단계적 실행이 모두 필요 |
| SPM → framework 전환, source-of-truth 통합 | 둘 다 | 구조 변경과 모듈 경계 판단이 모두 필요 |
| package product + framework product 중복 링크 제거 | 둘 다 | 빌드 그래프 정리와 모듈/링크 판단이 모두 필요 |
| `xcodegen`/`xcodeproj` 재생성이 포함된 구조 마이그레이션 | 둘 다 | 설정 재생성과 단계별 검증 루프가 필요 |

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

### 4. 실제 Claude CLI 워커가 필요한가?

- 예 → `claude-code-bridge` 추가
- 아니오 → 기존 선택 유지

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
3. concurrency 민감 작업이면 strict concurrency build/test를 검증 기준으로 설정
4. 메인 에이전트가 검증 루프 수행

### 패턴 B: Expertise-first

다음에 적합합니다.
- 코드 리뷰
- 마이그레이션 설계
- SwiftUI/Concurrency/SwiftData 설계 판단
- 아키텍처 비교

순서:
1. `swift-master`로 기술 판단과 reference 선택
2. 실제 구현/검증이 커지면 `ios-multi-agent-dev`로 승격

### 패턴 C: Claude-assisted

다음에 적합합니다.
- 2차 분석 의견 필요
- 특정 파일 구현 초안 필요
- 외부 비판적 리뷰 필요

순서:
1. `ios-multi-agent-dev` 또는 `swift-master`로 단계와 기준 잠금
2. `claude-code-bridge`로 Claude CLI 호출
3. Codex가 build/test와 diff를 직접 검증
4. 검증 실패 시 즉시 수정 루프로 복귀

### 패턴 D: Structure Migration

다음에 적합합니다.
- package → framework 전환
- 모듈 source-of-truth 통합
- duplicate linkage 제거
- `xcodegen` / `xcodeproj` 재생성 포함 작업

순서:
1. 현재 source of truth가 package인지 framework인지 먼저 결정
2. 앱이 package product와 framework product를 동시에 링크하는지 확인
3. generator 설정(`project.yml`, `xcodeproj`)을 한쪽 기준으로 정리
4. `framework build → dependent framework build → app build → app test`
5. 문서와 기본 검증 명령을 새 구조에 맞게 갱신

## Validation Escalation

다음이 보이면 검증 기준을 올리기.
- `@MainActor`
- `Sendable`
- actor/service 경계
- `.task` 또는 SwiftUI lifecycle
- cancellation

이 경우 우선 검토하기.
- `swift test`
- `swift build`
- `xcodebuild test`
- strict concurrency 옵션이 포함된 build/test

검증 실패 시에는 “성공”으로 종료하지 말고 즉시 수정 루프 또는 구체적인 다음 수정안을 제시하기.

구조 마이그레이션이면 추가 확인하기.
- app target이 package product와 framework product를 동시에 링크하는지
- source-of-truth 경로가 하나로 정리됐는지
- dependent framework가 필요한 framework를 명시적으로 링크하는지
- generator(`xcodegen`, `tuist`) 설정과 실제 프로젝트 파일이 일치하는지

## Example Requests

- "이 SwiftUI 코드 상태 관리 문제 리뷰해줘" → `swift-master`
- "릴리즈 전에 이 iOS 버그를 안전하게 고쳐줘" → `ios-multi-agent-dev`
- "Swift 6 마이그레이션을 여러 단계로 안전하게 진행해줘" → 둘 다
- "SwiftData + Concurrency 이슈를 분석하고 수정까지 해줘" → 둘 다
- "이 저장소를 Claude CLI로 한번 더 분석해서 Codex 결론과 비교해줘" → `swift-master` + `claude-code-bridge`
