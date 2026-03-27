---
name: agent-context-audit
description: Codex instruction 구조의 밀도와 건강도를 감사합니다. AGENTS.md 길이, 계층 깊이, 중복 규칙, 커버리지 부족을 찾을 때 사용합니다.
---

# Agent Context Audit

원본 `ctx-audit`의 Codex 버전입니다. 목표는 instruction 체계를 더 짧고, 더 가까이, 더 명확하게 유지하는 것입니다.

## Optional quick check
빠른 점검이 필요하면 `scripts/check_agents_md.sh [target]`를 먼저 실행한다.

## Audit dimensions
- 루트 `AGENTS.md`가 과하게 비대한지
- 하위 `AGENTS.md` 깊이가 불필요하게 깊은지
- 동일 규칙과 명령이 여러 문서에 복제되는지
- 중요한 서브시스템에 가까운 instruction이 빠져 있는지

## Workflow
1. instruction 파일 트리를 수집한다.
2. 루트 문서와 하위 문서의 책임 분리를 평가한다.
3. 중복·장문·휘발성 정보를 찾아 외부 문서 분리 지점을 제안한다.
4. 커버리지 빈 구역이 있으면 하위 `AGENTS.md` 또는 `CONTEXT.md` 추가를 권한다.
5. 결과를 우선순위순 개선안으로 정리한다.

## Output expectation
- 현재 구조의 장점
- 위험 신호 (`critical / warning / info`)
- 우선순위별 분리/정리 제안
