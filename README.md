# codex-skills

개인 Codex 사용자 스킬 저장소입니다. 스킬은 전역 설치 위치인 `~/.codex/skills/<skill-name>/SKILL.md` 기준으로 관리합니다.

## 현재 활성 사용자 스킬

### Codex skill / plugin 관리

| Skill | Best for |
|---|---|
| `codex-skill-audit` | Codex skill 구조, frontmatter, discovery, harness 감사 |
| `codex-skill-bootstrap` | 새 Codex skill 생성 또는 기존 skill 현대화 |
| `plugin-doctor` | Codex plugin/skill 저장소 구조 감사와 legacy 산출물 점검 |

### Agent context / instruction 구조

| Skill | Best for |
|---|---|
| `agent-context-audit` | `AGENTS.md` 밀도, 중복, 커버리지 감사 |
| `agent-context-guide` | Codex용 `AGENTS.md`/`CONTEXT.md` 계층 설계 |
| `agent-context-init` | 저장소에 Codex instruction 구조 초기화 |
| `agent-context-verify` | Codex context 링크, 코드 참조, 주장 정확성 검증 |
| `hierarchical-context-architecture` | 대규모 repo instruction/context architecture 설계 |
| `ctx-audit` | legacy `CLAUDE.md` 중심 context 효율 감사 |
| `ctx-guide` | legacy `CLAUDE.md`/`CONTEXT.md` 구조 가이드 |
| `ctx-init` | legacy context file scaffold |
| `ctx-verify` | legacy context file 검증 |

### 연구 / 위임 / 반복 실행

| Skill | Best for |
|---|---|
| `goal-research-loop` | 새 목표 지향 반복 연구 루프 설계·운영 |
| `codex-research` | 기존 `.codex-research/` runner 상태 재개·점검 |
| `hey-codex` | 명시 요청 시 별도 Codex CLI 인스턴스 실행 |
| `gpt-research` | 외부 GPT/deep research에 넘길 구조화 프롬프트 작성 |
| `ralph-loop` | 완료 조건까지 bounded 반복 실행 설계 |
| `claude-code-bridge` | 명시 요청 시 로컬 Claude Code CLI와 Codex handoff |
| `chronicle` | 최근 화면 맥락으로 사용자 요청 disambiguation |

### Apple / Swift / 앱 자동화

| Skill | Best for |
|---|---|
| `app-automation` | baepsae 기반 iOS Simulator/macOS 앱 UI 자동화 |
| `apple-craft` | Swift/SwiftUI/UIKit/AppKit/Xcode 작업 지원 |
| `apple-harness` | Apple 앱 기능의 PLAN→DESIGN→BUILD→EVALUATE 장기 루프 |
| `apple-review` | Apple 플랫폼 코드·PR 리뷰 |
| `swift-master` | SwiftUI, Swift Concurrency, SwiftData, Swift 6 전문 판단 |
| `ios-multi-agent-dev` | iOS/Swift 작업의 planner/builder/reviewer 역할 분리 |
| `ios-swift-orchestrator` | iOS/Swift 작업에서 하위 skill 라우팅 |
| `ios-app-store-release` | TestFlight/App Store 릴리스 준비 |
| `os-log` | iOS/watchOS/macOS `os_log` stream/show 조사 |
| `tuist-management` | talkmediakitui Tuist module/target lifecycle 관리 |

### Workflow / release / tooling / design

| Skill | Best for |
|---|---|
| `git-pr-workflow` | commit, branch, PR 생성, PR 리뷰 흐름 |
| `macos-release` | macOS GUI 앱/CLI 릴리스, DMG/ZIP, GitHub Release, Homebrew |
| `frontend-design` | 개성 있고 production-grade인 웹 UI/UX 설계·구현 |
| `ghostty-setup` | Ghostty terminal config/theme/profile 설정 |
| `karpathy-wiki` | raw source와 LLM-maintained wiki 분리형 지식 베이스 설계 |
| `api-learn` | 프로젝트 API/library reference 수집·내재화 |
| `api-scan` | 프로젝트 dependency scan과 reference 누락 식별 |

## 정리 기준

- 중복 discovery를 만들지 않습니다.
- `SKILL.md` frontmatter는 `name`과 `description`만 유지합니다.
- UI metadata는 각 skill의 `agents/openai.yaml`에 둡니다.
- 긴 절차와 reference는 `references/`, 반복 명령은 `scripts/`에 둡니다.
- 새 연구 루프는 `goal-research-loop`를 우선 사용하고, `codex-research`는 기존 `.codex-research/` 호환이 필요할 때만 사용합니다.
- macOS 릴리스는 `macos-release` 하나로 통합했습니다.
- plugin 감사는 `plugin-doctor`로 통합했습니다.

## 사용 예시

```text
$codex-skill-audit ~/.codex/skills를 감사해주세요.
$agent-context-init 이 저장소에 Codex용 AGENTS.md 구조를 만들어주세요.
$goal-research-loop 이 성능 개선 목표를 5라운드 반복 연구 루프로 설계해주세요.
$swift-master 이 SwiftUI 상태 관리와 동시성 위험을 리뷰해주세요.
$ios-swift-orchestrator 이 iOS 작업을 어떤 하위 스킬로 진행할지 결정해주세요.
$app-automation 실행 중인 macOS 앱 UI를 분석하고 스크린샷 증거를 남겨주세요.
$macos-release 이번 macOS CLI 릴리스를 dry-run부터 Homebrew 반영까지 점검해주세요.
```

## 릴리즈 운영 파일

- [`CHANGELOG.md`](./CHANGELOG.md): 태그 기준 변경 이력
- [`docs/release-notes-template.md`](./docs/release-notes-template.md): GitHub Release 작성용 템플릿
- [`docs/release-checklist.md`](./docs/release-checklist.md): 실제 릴리즈 절차 체크리스트

## 저장소 동기화 자동화

수동 동기화:

```bash
./scripts/sync_repo.sh
```

자동 동기화 설치:

```bash
./scripts/install_auto_sync_launchd.sh
```

로그 확인:

```bash
tail -f ~/Library/Logs/com.oozoofrog.codex-skills-autosync.out.log
tail -f ~/Library/Logs/com.oozoofrog.codex-skills-autosync.err.log
launchctl print gui/$(id -u)/com.oozoofrog.codex-skills-autosync
```
