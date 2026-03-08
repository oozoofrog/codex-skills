# codex-skills

개인 Codex 스킬 저장소입니다.

## 포함된 스킬

- `ios-multi-agent-dev`
  - iOS/Swift 작업을 여러 에이전트에 역할 분리해 진행하는 협업 개발 스킬
  - 정의 → 분석 → 구현 → 메인 검증 → 비판적 리뷰 → 반영 흐름 제공

- `swift-master`
  - Swift 6, SwiftUI, Swift Concurrency, SwiftData, Architecture, Pure DI, Combine 마이그레이션을 다루는 통합 Swift/iOS 스킬
  - 리뷰, 최적화, 마이그레이션, 가이드, 코드 생성 워크플로 제공

- `ios-swift-orchestrator`
  - iOS/Swift 작업의 상위 진입점으로, 협업 워크플로와 Swift 전문성을 라우팅하는 래퍼 스킬
  - `ios-multi-agent-dev`, `swift-master`, `claude-code-bridge` 중 필요한 조합을 선택해 오케스트레이션

- `claude-code-bridge`
  - Codex를 메인 오케스트레이터로 유지하면서 로컬 Claude Code CLI를 실제 분석/구현/리뷰 워커로 연결하는 브리지 스킬
  - `analysis → implementation → review → review-incorporation` 단계 분리, 세션 전략, 역할 잠금, Task Brief 기반 구조화 입력 규칙 제공

- `ghostty-setup`
  - Ghostty 터미널 설정을 안전하게 조정·검증하는 스킬
  - 테마, 프로필, 가독성, include 체인 변경 작업에 사용

- `ios-app-store-release`
  - iOS/watchOS 앱의 TestFlight 및 App Store 출시 준비를 지원하는 스킬
  - 스크린샷, 메타데이터, 버전/빌드, fastlane 기반 릴리스 검증 흐름 제공

## 시스템 스킬 미러링

현재 이 저장소는 아래 기본 시스템 스킬도 함께 추적합니다.

- `.system/skill-creator`
- `.system/skill-installer`
- `.system/slides`
- `.system/spreadsheets`

## 사용 예시

```text
$ios-multi-agent-dev 실제 iOS/Swift 작업을 planner, builder, reviewer 역할로 나눠 진행해주세요.
$swift-master 이 SwiftUI 코드의 상태 관리와 동시성 문제를 리뷰해줘.
$ios-swift-orchestrator 이 iOS/Swift 작업을 어떤 하위 스킬로 진행할지 결정하고 실행 흐름을 잡아줘.
$claude-code-bridge 이 저장소를 Claude CLI로 분석하게 하고 결과를 내가 다시 검증할 수 있게 정리해줘.
```

## 검증 원칙

iOS/Swift 작업 중 다음이 핵심이면 `typecheck`만으로 완료 처리하지 않습니다.

- `@MainActor`
- `Sendable`
- actor/service 경계
- SwiftUI `.task`와 lifecycle
- cancellation
- SwiftData threading

우선 검토할 검증:

- `swift test`
- `swift build`
- `xcodebuild test`
- strict concurrency 옵션이 포함된 build/test

검증이 실패하면:

- 성공처럼 보고하지 않기
- 실패한 명령과 핵심 오류를 그대로 남기기
- 바로 수정 루프를 시작하거나 다음 수정안을 제시하기

## 저장소 동기화 자동화

이 저장소에는 로컬 스킬 변경을 원격 저장소에 반영하기 위한 수동/자동 동기화 스크립트가 포함됩니다.

### 1) 수동 동기화

```bash
./scripts/sync_repo.sh
```

유용한 옵션:

```bash
./scripts/sync_repo.sh --dry-run
./scripts/sync_repo.sh --message "Add new skill"
./scripts/sync_repo.sh --no-push
```

기본 동작:
- `git fetch`
- `git pull --rebase --autostash`
- `git add -A`
- 변경이 있으면 자동 commit
- 원격보다 앞서 있으면 자동 push

### 2) 자동 커밋/푸시 워크플로

macOS에서는 launchd 에이전트로 자동 동기화를 켤 수 있습니다.  
백그라운드 daemon이 `git status --porcelain`을 주기적으로 확인하고, 변경이 일정 시간 안정화되면 `sync_repo.sh`를 호출합니다.

설치:

```bash
./scripts/install_auto_sync_launchd.sh
```

옵션 예시:

```bash
./scripts/install_auto_sync_launchd.sh --interval 15 --debounce 20 --retry-cooldown 120
```

제거:

```bash
./scripts/uninstall_auto_sync_launchd.sh
```

기본값:
- poll interval: 15초
- debounce: 20초
- failed retry cooldown: 120초

로그 확인:

```bash
tail -f ~/Library/Logs/com.oozoofrog.codex-skills-autosync.out.log
tail -f ~/Library/Logs/com.oozoofrog.codex-skills-autosync.err.log
launchctl print gui/$(id -u)/com.oozoofrog.codex-skills-autosync
```
