---
name: macos-release
description: macOS 앱/CLI 릴리스 작업을 자동화하거나 가이드합니다. 버전 범프, Release 빌드, DMG/ZIP, GitHub Release, Homebrew 배포가 필요할 때 사용합니다.
---

# macOS Release

macOS GUI 앱과 CLI의 릴리스 준비, 패키징, 로컬 설치 검증, GitHub Release, Homebrew 반영을 안전한 순서로 진행합니다.

## When to use
- macOS 앱/CLI의 버전 범프, 빌드, 패키징, GitHub Release, Homebrew 배포가 필요할 때
- 기존 릴리스 스크립트나 GitHub Actions/Homebrew tap 흐름을 점검하거나 보강할 때
- 공개 배포 전에 dry-run, 로컬 설치, checksum 검증을 반복 가능하게 남겨야 할 때

## Do not use when
- 일반 기능 개발, 버그 수정, 코드 리뷰처럼 릴리스 준비가 아닌 작업
- App Store / TestFlight 중심의 iOS/watchOS 릴리스 작업 → `ios-app-store-release`
- 단순 GitHub PR/commit 작업 → `git-pr-workflow`

## Quick start
1. 릴리스 모드를 먼저 고릅니다: 전체 릴리스 / dry-run / 버전만 / 패키징만 / GitHub Release만 / Homebrew만 / workflow 구축.
2. 대상이 GUI 앱(`.app`)인지 CLI인지 확인합니다.
3. 기존 신호를 탐지합니다: `scripts/release.sh`, `fastlane`, `*.xcodeproj`, `.github/workflows`, `Formula/*.rb`, `Casks/*.rb`, `homebrew-*`.
4. 기존 릴리스 구조가 있으면 새 구조를 만들기보다 재사용하고, 가능한 경우 dry-run부터 실행합니다.
5. 기본 순서는 `버전 확인/증가 → 빌드 → 패키징 → 로컬 검증 → tag/release push → Homebrew 반영`입니다.

## Use references
- `references/release-checklist.md`
- `references/release-script-guide.md`
- `references/local-install-and-dmg.md`
- `references/github-actions-release.md`
- `references/homebrew-publishing.md`
- `references/troubleshooting.md`

## Workflow
1. 프로젝트에서 기존 릴리스 자산과 버전 source of truth를 찾습니다.
2. 공개 상태 변경 전에 dry-run 또는 로컬 검증 계획을 먼저 세웁니다.
3. GUI 앱은 DMG/ZIP + Homebrew Cask, CLI는 tarball/source build + Homebrew Formula를 기본 후보로 봅니다.
4. 빌드나 패키징이 실패하면 GitHub Release/Homebrew 단계로 넘어가지 않습니다.
5. Homebrew는 실제 산출물 또는 source tarball에서 checksum을 다시 계산한 뒤 해당 formula/cask만 수정합니다.
6. 실패 시 어느 단계에서 멈췄는지, 필요한 자격 증명, 수동 복구 명령을 명시합니다.

## Guardrails
- 로컬 설치 검증 전 외부 공개 단계를 진행하지 않습니다.
- 기존 release script/workflow/tap이 있으면 병렬 구조를 만들지 않습니다.
- signing, notarization, GitHub Release publish, Homebrew push는 마지막 단계로 미룹니다.
- 공용 tap에서는 요청 대상 파일 외의 dirty 상태가 있으면 중단합니다.

## Review Harness
- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: 기존 릴리스 경로, dry-run, 공개 순서를 먼저 정한다
- generator: 버전 범프, 빌드, 패키징, 배포 준비를 수행한다
- evaluator: dry-run, 로컬 설치, checksum, release checklist로 결과를 검토한다
- 평가축: release completeness, 로컬 검증 통과, 산출물 무결성, 공개 순서 준수
- artifacts/evidence: build log, 패키지 경로, checksum, 설치 확인, 릴리스 노트
- pass condition: 로컬 검증과 산출물 무결성이 확인되기 전에는 외부 공개 단계로 넘어가지 않는다
- 자동 다음 행동: `pass`면 공개 단계 진행, `refine`이면 빌드/패키징 수정, `stop`이면 외부 공개 중단, `critical`이면 checksum 또는 install 문제 해결 전 배포를 금지한다

## Output expectation
- 릴리스 작업 종류와 감지한 기존 릴리스 경로
- 변경 파일과 실행한 핵심 명령
- 생성/업데이트된 버전, 산출물, checksum
- 로컬 설치 또는 smoke 검증 결과
- 다음 공개 액션 또는 중단 사유
