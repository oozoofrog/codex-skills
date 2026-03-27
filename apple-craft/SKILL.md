---
name: apple-craft
description: Apple 플랫폼 개발을 돕습니다. Swift, SwiftUI, UIKit, AppKit, Xcode 빌드/프리뷰/디버깅, 최신 Apple API 참조가 필요할 때 사용하고 장기 오케스트레이션은 apple-harness로 넘깁니다.
---

# Apple Craft

원본 `apple-craft` 플러그인의 Codex 버전입니다. Xcode 도구와 번들 reference docs를 함께 사용합니다.

## Knowledge priority
1. `DocumentationSearch` 같은 공식 도구 결과
2. `references/`에 있는 번들 Apple 문서
3. 현재 프로젝트 코드와 빌드 로그
4. 일반 모델 기억

## Use references
- `references/_index.md`
- `references/common-mistakes.md`
- `references/code-style.md`
- 필요한 프레임워크별 문서 한두 개만 추가 로드

## Workflow
1. 작업 유형을 구분한다: `implement`, `explore`, `troubleshoot`.
2. Xcode 프로젝트/패키지 구조와 현재 문제 범위를 먼저 확인한다.
3. 관련 reference doc과 공식 검색 결과를 최소한만 읽는다.
4. 구현·설명·수정 작업을 수행한다.
5. 가능하면 `XcodeRefreshCodeIssuesInFile`, `BuildProject`, `GetBuildLog`, `RenderPreview`로 검증한다.
6. 리뷰 중심 작업은 `apple-review`, 장기 루프는 `apple-harness`를 사용한다.

## Scripts
- `scripts/preflight.sh` — 참조 문서 존재 확인
- `scripts/sync-docs.sh` — Xcode 번들 문서를 로컬 reference로 동기화

## Output expectation
- 읽은 reference 문서
- 적용/수정 내용
- 빌드·프리뷰·진단 결과
