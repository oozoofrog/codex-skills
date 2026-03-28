---
name: apple-review
description: Apple 플랫폼 관점의 코드·PR 리뷰를 수행합니다. Swift/SwiftUI/UIKit/AppKit 코드의 정확성, API 사용, 빌드 위험, 테스트 누락을 점검할 때 사용합니다.
---

# Apple Review

원본 `apple-review`의 Codex 버전입니다. 일반적인 스타일 리뷰가 아니라 **Apple 생태계 특화 검토**에 초점을 둡니다.

## Use references
- `../apple-craft/references/common-mistakes.md`
- `../apple-craft/references/code-style.md`
- 대상 코드와 관련된 Apple 문서 몇 개

## Workflow
1. 리뷰 범위를 정한다: 현재 변경사항, 특정 파일/디렉토리, PR.
2. 관련 Swift 파일과 빌드 이슈를 수집한다.
3. 공통 reference + 프레임워크별 문서를 로드한다.
4. 정확성, 수명주기, 동시성, 상태 관리, 테스트, 접근성 중심으로 검토한다.
5. 가능하면 빌드/진단 결과로 리뷰를 보강한다.
6. 수정 요청이 있으면 최소 변경으로 후속 수정안을 제시한다.

## Reporting rules
- 한국어로 보고한다.
- `critical / warning / info`로 분류한다.
- 스타일-only 의견보다 실제 버그·회귀 위험을 우선한다.
- 재현 방법이나 근거 파일을 함께 남긴다.

## Review Harness
- mode: none
- 공통 기준: `../../../docs/review-harness.md`
- generator: 상위 구현, PR diff, 또는 대상 Swift 코드
- evaluator: 이 스킬 자체가 evaluator-native Apple review 역할을 수행한다
- 평가축: correctness, lifecycle, concurrency, state management, test/accessibility 누락
- artifacts/evidence: 파일 경로, diagnostics, build 결과, concurrency/lifecycle/accessibility 근거
- pass condition: 모든 finding이 실제 증거와 연결되고 severity가 과장되지 않아야 한다
- 자동 다음 행동: `pass`면 findings 없음으로 종료, `warning`이면 수정 제안, `critical`이면 block finding으로 반환하고 구현 스킬에 수정을 요구한다
