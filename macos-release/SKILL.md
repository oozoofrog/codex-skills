---
name: macos-release
description: Automate or guide macOS app release work across Xcode version bumps, release builds, DMG or ZIP packaging, local install verification, GitHub Releases, Homebrew Cask or Formula updates, and release-oriented GitHub Actions. Use when Codex needs to ship or set up release automation for a macOS app or CLI, especially for requests mentioning release, deploy, version bump, DMG, Homebrew, cask, formula, or release workflow.
---

# macOS Release

## Overview

macOS 프로젝트의 릴리스 준비, 배포, 자동화 구성을 다룰 때 사용하는 스킬입니다.
기존 저장소의 릴리스 스크립트, Xcode 설정, GitHub Release 흐름, Homebrew tap 구조를 우선 재사용하고, 불필요한 새 파이프라인은 만들지 않습니다.

## Quick Start

1. 릴리스 대상이 GUI 앱인지 CLI인지 먼저 구분하기.
2. 기존 릴리스 신호를 찾기: `scripts/release.sh`, `fastlane`, `*.xcodeproj`, `*.xcworkspace`, `.github/workflows`, Homebrew tap.
3. 요청 범위를 고정하기: 전체 릴리스, dry-run, Homebrew만, GitHub Actions만, 릴리스 스크립트 생성.
4. 파괴적 단계(`git push`, Release publish, Homebrew push)는 검증 후 마지막에만 실행하기.
5. 결과 보고 시 변경 파일, 실행한 명령, 남은 수동 단계, 복구 포인트를 함께 정리하기.

상세 체크리스트는 `references/release-checklist.md` 를 읽기.
Homebrew 배포 판단 기준과 공용 tap 운영 규칙은 `references/homebrew-publishing.md` 를 읽기.
GitHub Actions 릴리스 자동화 패턴은 `references/github-actions-release.md` 를 읽기.

## Workflow

### 1) 릴리스 모드 분류

먼저 요청을 아래 중 하나로 분류합니다.

- 전체 릴리스
- dry-run / 사전 점검
- 버전만 업데이트
- DMG/ZIP 패키징만
- GitHub Release만
- Homebrew 업데이트만
- 릴리스 자동화(workflow/script) 구축

범위가 좁으면 전체 릴리스 파이프라인을 억지로 실행하지 않습니다.
예를 들어 Homebrew만 바꾸는 요청이면 release build 없이 tarball/DMG/sha256 갱신만 수행합니다.

### 2) 기존 릴리스 자산 탐지

다음 신호를 우선 탐색합니다.

- `scripts/release.sh` 또는 유사 릴리스 스크립트
- `fastlane/Fastfile`, `Fastlane`, `Snapfile`
- `*.xcodeproj`, `*.xcworkspace`, scheme 설정
- `.github/workflows/release*.yml`, `update-homebrew*.yml`
- `homebrew-tap`, `homebrew-*`, `Formula/*.rb`, `Casks/*.rb`
- 버전 소스: `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, plist, release notes 파일

원칙:
- 기존 스크립트가 있으면 먼저 dry-run 경로를 찾습니다.
- 기존 tap/workflow가 있으면 그 구조를 유지합니다.
- 릴리스 구조가 이미 있는데 병렬로 새 구조를 추가하지 않습니다.

### 3) 앱 유형별 배포 선택

- GUI macOS 앱 (`.app`, 메뉴바 앱, 일반 앱): 보통 **DMG/ZIP + Homebrew Cask**
- CLI 도구: 보통 **tarball/소스 + Homebrew Formula**

판단이 애매하면 최종 산출물이 `.app` 인지, 사용자가 `brew install --cask` 를 기대하는지, 혹은 `brew install` CLI 형태인지로 구분합니다.

### 4) 릴리스 실행 원칙

기본 순서는 아래를 따릅니다.

`버전 확인/증가 → 빌드 → 패키징 → 로컬 검증 → git/release push → Homebrew 반영`

세부 규칙:
- 먼저 버전 소스를 찾고, 저장소가 쓰는 정식 위치만 수정합니다.
- 빌드나 패키징이 실패하면 그 이후 외부 publish 단계는 중단합니다.
- 로컬 설치 검증 또는 최소 smoke test 없이 GitHub Release/Homebrew push를 서두르지 않습니다.
- Release notes는 사용자 가치 중심으로 요약하고 내부 refactor만 나열하지 않습니다.

### 5) Homebrew 작업

Homebrew는 저장소 구조를 먼저 따릅니다.

- 기존 공용 tap이 있으면 그 tap을 재사용합니다.
- 공용 tap에서는 **해당 formula/cask 한 파일만** 수정합니다.
- 다른 formula/cask를 건드리지 않습니다.
- SHA256은 실제 배포 산출물 또는 source tarball에서 다시 계산합니다.
- tap push 전에 rebase가 필요할 수 있으므로 충돌 가능성을 항상 고려합니다.

공용 tap 안전 규칙과 formula/cask 선택 기준은 `references/homebrew-publishing.md` 를 읽기.

### 6) GitHub Actions 자동화

릴리스 자동화 요청이면 아래를 구분합니다.

- 릴리즈 생성 workflow
- Release publish 이후 Homebrew를 갱신하는 workflow
- 수동 복구용 로컬 스크립트

권장 패턴:
- 로컬 또는 주 workflow가 GitHub Release를 생성
- `release.published` 이벤트로 Homebrew update workflow 트리거
- tap push용 token은 최소 권한으로 분리

자세한 패턴과 secret 요구사항은 `references/github-actions-release.md` 를 읽기.

## Decision Guardrails

- 기존 릴리스 구조를 재사용하는 쪽을 기본값으로 둡니다.
- dry-run이나 검증 경로가 있으면 먼저 사용합니다.
- 서명, notarization, Homebrew, Release publish 같은 외부 상태 변경은 마지막 단계로 미룹니다.
- Homebrew 공용 tap에서는 해당 프로젝트 파일 하나만 수정하고, 관련 없는 dirty 상태가 있으면 중단합니다.
- 문제가 생기면 실패 지점, 필요한 자격 증명, 수동 복구 명령을 명시적으로 보고합니다.

## Output Contract

항상 다음을 포함해 보고합니다.

- 릴리스 작업 종류(전체 릴리스 / Homebrew만 / 자동화 구축 등)
- 확인한 기존 릴리스 신호와 재사용한 도구
- 변경 파일 목록
- 실행한 핵심 명령
- 생성/업데이트된 버전 및 산출물
- 남은 수동 단계 또는 복구 방법

## References

- `references/release-checklist.md`: 전체 릴리스 체크리스트와 dry-run 우선 원칙
- `references/homebrew-publishing.md`: Homebrew Cask/Formula 선택, 공용 tap 운영 규칙, push/rebase 패턴
- `references/github-actions-release.md`: release.published 기반 자동화, secret, 실패 시 수동 복구 패턴
