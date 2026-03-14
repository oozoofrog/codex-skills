# codex-skills

개인 Codex 스킬 저장소입니다.

## 포함된 스킬

| Skill | Category | Best for | Notes |
|---|---|---|---|
| `claude-code-bridge` | Workflow | Codex와 로컬 Claude CLI를 함께 쓰는 분석/구현/리뷰 handoff | 사용자가 Claude 사용을 명시적으로 원할 때만 활성화 |
| `git-pr-workflow` | Workflow | commit, branch, push, PR 생성, stale branch cleanup, PR review | `commit-commands` + `pr-review-toolkit` 계열 흐름을 Codex-native로 통합 |
| `ralph-loop` | Workflow | bounded iterative Codex loop 설계와 반복 실행 가이드 | 자동 hook 대신 안전한 수동 loop 패턴 사용 |
| `ghostty-setup` | Tooling | Ghostty 테마/프로필/가독성 설정 변경과 검증 | include chain과 rollback 관점까지 포함 |
| `frontend-design` | Design | 개성 있는 웹 UI/UX 설계와 구현 | aesthetic direction을 먼저 고정하는 방식 |
| `ios-multi-agent-dev` | Apple | iOS/Swift 기능 개발을 planner/builder/reviewer로 분리 | 구현과 검증이 큰 작업에 적합 |
| `swift-master` | Apple | SwiftUI, Concurrency, SwiftData, Swift 6, SourceKit-LSP 진단 | Swift 전문 판단과 코드 리뷰/생성 중심 |
| `ios-swift-orchestrator` | Apple | iOS/Swift 작업을 어떤 하위 skill로 진행할지 라우팅 | `ios-multi-agent-dev`, `swift-master`, `claude-code-bridge` 조합 선택 |
| `ios-app-store-release` | Release | TestFlight / App Store 준비, 스크린샷, 메타데이터, 빌드 업로드 | 기존 fastlane / Xcode release flow 재사용 우선 |
| `macos-release` | Release | macOS GUI 앱/CLI 릴리즈, DMG/ZIP, Homebrew, GitHub Actions | Cask/Formula 및 shared tap 운영 reference 포함 |

## 빠른 선택 가이드

- **Codex와 Claude를 함께 쓰고 싶다** → `claude-code-bridge`
- **커밋/PR/리뷰 흐름을 정리하고 싶다** → `git-pr-workflow`
- **반복 실행되는 bounded loop를 설계하고 싶다** → `ralph-loop`
- **개성 있는 웹 UI/UX를 만들고 싶다** → `frontend-design`
- **Swift/iOS 기술 판단이 필요하다** → `swift-master`
- **iOS/Swift 작업을 어떤 skill로 풀지 먼저 결정하고 싶다** → `ios-swift-orchestrator`
- **iOS/watchOS 앱 릴리즈 준비를 하고 싶다** → `ios-app-store-release`
- **macOS 앱/CLI 릴리즈와 Homebrew 반영이 필요하다** → `macos-release`

## 릴리즈 태그

이 저장소는 의미 있는 skill 묶음 변경이 있을 때 annotated tag를 남깁니다.
현재 태그:
- `v0.1.0`
- `v0.1.1`

다음 변경부터도 신규 skill 추가나 큰 구조 변경 시 태그를 갱신합니다.

## 시스템 스킬 미러링

현재 이 저장소는 아래 기본 시스템 스킬도 함께 추적합니다.

- `.system/skill-creator`
- `.system/skill-installer`
- `.system/slides`
- `.system/spreadsheets`

## 사용 예시

### 범용 워크플로 / 도구

```text
$git-pr-workflow 이 변경을 저장소 스타일에 맞게 커밋하고, 필요하면 PR까지 만들어줘.
$git-pr-workflow 이 PR diff를 code/tests/errors/comments/types 관점으로 리뷰해줘.
$ralph-loop 이 작업을 최대 8번 반복하는 bounded Codex loop로 설계해줘.
$claude-code-bridge 이 저장소를 Claude CLI로 분석하게 하고 결과를 내가 다시 검증할 수 있게 정리해줘.
```

### 디자인 / 프론트엔드

```text
$frontend-design 음악 스트리밍 앱용 대시보드를 강한 aesthetic direction으로 구현해줘.
$frontend-design 이 랜딩 페이지를 generic AI 느낌 없이 더 기억에 남게 다시 설계해줘.
```

### Apple 플랫폼 / 릴리즈

```text
$ios-multi-agent-dev 실제 iOS/Swift 작업을 planner, builder, reviewer 역할로 나눠 진행해주세요.
$swift-master 이 SwiftUI 코드의 상태 관리와 동시성 문제를 리뷰해줘.
$swift-master sourcekit-lsp 가 안 잡히는 원인을 진단해줘.
$ios-swift-orchestrator 이 iOS/Swift 작업을 어떤 하위 스킬로 진행할지 결정하고 실행 흐름을 잡아줘.
$ios-app-store-release 이번 버전의 TestFlight 준비를 스크린샷, 메타데이터, 빌드 업로드까지 기준으로 점검해줘.
$macos-release macOS 앱 릴리즈를 dry-run부터 Homebrew 반영까지 정리해줘.
```

## 릴리즈 운영 파일

- [`CHANGELOG.md`](./CHANGELOG.md): 태그 기준 변경 이력
- [`docs/release-notes-template.md`](./docs/release-notes-template.md): GitHub Release 작성용 템플릿
- [`docs/release-checklist.md`](./docs/release-checklist.md): 실제 릴리즈 절차 체크리스트

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
