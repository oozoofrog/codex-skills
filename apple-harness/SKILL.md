---
name: apple-harness
description: Swift/SwiftUI 기능이나 Apple 앱을 처음부터 끝까지 구현해야 할 때 사용하는 장기 오케스트레이션 스킬입니다. PLAN→DESIGN→BUILD→EVALUATE 루프가 필요할 때만 사용합니다.
---

# Apple Harness

원본 `apple-harness`의 의도를 Codex 오케스트레이션으로 옮긴 스킬입니다.

## When to use
- 새 기능을 처음부터 끝까지 구현해야 할 때
- 대규모 UI 리팩터링이나 복합 프레임워크 통합이 필요할 때
- 단일 파일 수정이 아니라 단계별 검증 루프가 필요할 때

## Shared artifacts
작업 산출물은 기본적으로 `.codex/harness/` 아래에 둔다.

- `harness-spec.md` — 제품/기능 스펙
- `features.json` — 기능 목록과 상태
- `design-spec.md` — 디자인 토큰·화면 구조
- `evaluation-round-N.md` — 검증 피드백

## Use references
- `references/harness-design-principles.md`
- `references/apple-hig-map.md`
- `references/walkthrough-liquid-glass-settings.md`

## Orchestration flow
1. **PLAN** — 요구사항을 구조화하고 `harness-spec.md`, `features.json`을 만든다.
2. **DESIGN** — Pencil이 가능하면 화면 구조와 디자인 토큰을 `design-spec.md`에 남긴다.
3. **BUILD** — 우선순위가 가장 높은 기능부터 작은 단위로 구현한다.
4. **EVALUATE** — 빌드, 프리뷰, 런타임, 접근성, 설계 일치 여부를 점검한다.
5. 실패한 항목이 있으면 최대 3라운드까지 반복한다.

## Agent mapping
- Codex app/CLI에서는 `.codex/agents/harness-*.toml` custom agents를 우선 사용한다.
- 현재 환경에 custom agent 호출이 없으면 built-in subagent 또는 로컬 작업으로 역할을 분리한다.
- 평가 단계는 가능하면 read-only 역할로 유지하고, 구현 단계와 쓰기 범위를 분리한다.

## Guardrails
- `features.json`의 기능 항목은 삭제하지 말고 상태만 변경한다.
- 한 번에 한 기능 또는 명확히 분리된 write scope만 다룬다.
- 빌드 성공 전 파괴적 후속 작업을 밀어붙이지 않는다.

## Output expectation
- 라운드별 결과
- 완료/실패 기능 목록
- 남은 리스크와 다음 액션
