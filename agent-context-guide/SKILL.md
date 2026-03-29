---
name: agent-context-guide
description: Codex용 계층형 컨텍스트 아키텍처를 설계하고 설명합니다. AGENTS.md 루트/하위/override 분리, CONTEXT.md 보조 문서화, 토큰 효율 개선이 필요할 때 사용하고 단순 파일 편집만 할 때는 사용하지 않습니다.
---

# Agent Context Guide

원본 `agent-context` 플러그인을 Codex 기준으로 재해석한 가이드입니다. 핵심은 `CLAUDE.md`가 아니라 **`AGENTS.md` 계층 구조**입니다.

## When to use
- 루트 `AGENTS.md`가 너무 길거나 중복이 많을 때
- 대규모 저장소를 디렉토리별 규칙로 나누고 싶을 때
- 기존 `CLAUDE.md` / `.claude/rules/` 체계를 Codex용으로 옮길 때

## Do not use when
- instruction 파일을 실제로 생성·정리해야 하는 작업 → `agent-context-init`
- 기존 문서의 링크·명령·주장 정합성을 검증하는 작업 → `agent-context-verify`
- 현재 구조의 건강도 진단과 감사가 주목적인 작업 → `agent-context-audit`

## Quick start
1. 루트 `AGENTS.md`와 대표 하위 instruction 파일을 모은다.
2. 루트에 남길 공통 규칙과 하위로 내릴 규칙을 분리한다.
3. 장문 배경은 `CONTEXT.md`/`docs/`로 보내고 링크 구조를 제안한다.

## Read references as needed
- `references/file-standards.md`
- `references/token-optimization.md`
- `references/verification-guide.md`

## Workflow
1. 현재 instruction 문서를 수집한다: `AGENTS.md`, `AGENTS.override.md`, fallback 파일, `CONTEXT.md`, 관련 `docs/`.
2. 루트 `AGENTS.md`에는 저장소 공통 규칙만 남긴다.
3. 특정 서브시스템 전용 규칙은 가장 가까운 하위 `AGENTS.md` 또는 `AGENTS.override.md`로 옮긴다.
4. 장문 배경지식, 표, API 세부 설명은 `CONTEXT.md`나 `docs/`로 분리하고 `AGENTS.md`에서는 링크만 남긴다.
5. 명령, 테스트, 금지사항은 실제 코드/설정에서 검증 가능한 사실만 유지한다.
6. 필요 시 sibling skills를 사용한다:
   - `agent-context-init`
   - `agent-context-verify`
   - `agent-context-audit`

## Review Harness
- mode: optional
- 공통 기준: `../../../docs/review-harness.md`
- generator: AGENTS 계층 구조와 책임 분리 제안
- evaluator: `agent-context-verify`, `agent-context-audit`
- 평가축: 루트/하위 책임 배치, docs 분리 적절성, 검증 가능한 규칙 유지
- artifacts/evidence: 권장 파일 배치, 책임 분리표, docs 분리 계획
- pass condition: 제안안이 링크·명령·중복 규칙 측면에서 verify/audit에 견뎌야 한다
- 자동 다음 행동: `pass`면 설계안 확정, `refine`이면 책임 경계 재조정, `rescope`면 범위를 줄여 다시 설계하고 필요 시 verify/audit로 넘긴다

## Output expectation
- 권장 파일 배치
- 루트/하위 instruction 책임 분리
- 남겨야 할 규칙 vs 외부 문서로 분리할 내용
