---
name: ooz-macos-release
description: macOS 앱/CLI 릴리스 작업을 자동화하거나 가이드합니다. 버전 범프, Release 빌드, DMG/ZIP, GitHub Release, Homebrew 배포가 필요할 때 사용합니다.
---

# macOS Release

원본 `macos-release`를 Codex repo-local skill로 이식한 버전입니다.

## Use references
- `references/release-checklist.md`
- `references/release-script-guide.md`
- `references/local-install-and-dmg.md`
- `references/github-workflow-guide.md`
- `references/homebrew-publishing.md`
- `references/troubleshooting.md`

## Workflow
1. 프로젝트에서 기존 릴리스 스크립트, Xcode 프로젝트, tap 저장소를 탐지한다.
2. 파괴적 작업 전에는 항상 dry-run 또는 로컬 검증 단계를 먼저 수행한다.
3. 버전 범프 → 빌드 → 패키징 → 로컬 설치 확인 → GitHub Release → Homebrew 순서를 지킨다.
4. 기존 스크립트가 있으면 우선 재사용하고, 없으면 최소 스크립트를 생성한다.
5. 실패 시 어느 단계에서 멈췄는지와 복구 방법을 함께 보고한다.

## Guardrails
- 로컬 설치 검증 전 외부 공개 단계를 진행하지 않는다.
- GitHub/API 인증 상태를 먼저 확인한다.
- Homebrew 갱신은 릴리스 산출물 체크섬이 확정된 뒤에만 수행한다.
