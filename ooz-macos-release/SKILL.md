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

## Review Harness
- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: 기존 릴리스 경로, dry-run, 공개 순서를 먼저 정한다
- generator: 버전 범프, 빌드, 패키징, 배포 준비를 수행한다
- evaluator: dry-run, 로컬 설치, 체크섬, release checklist로 결과를 검토한다
- 평가축: release completeness, 로컬 검증 통과, 산출물 무결성, 공개 순서 준수
- artifacts/evidence: build log, 패키지 경로, 체크섬, 설치 확인, 릴리스 노트
- pass condition: 로컬 검증과 산출물 무결성이 확인되기 전에는 외부 공개 단계로 넘어가지 않는다
- 자동 다음 행동: `pass`면 공개 단계 진행, `refine`이면 빌드/패키징 수정, `stop`이면 외부 공개 중단, `critical`이면 checksum 또는 install 문제 해결 전 병합/배포를 금지한다
