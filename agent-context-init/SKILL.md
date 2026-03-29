---
name: agent-context-init
description: 저장소를 분석해 Codex용 instruction 구조를 초기화합니다. 루트 AGENTS.md, 필요 시 하위 AGENTS.md/AGENTS.override.md, 보조 CONTEXT.md를 생성·보강할 때 사용합니다.
---

# Agent Context Init

이 스킬은 원본 `ctx-init`를 Codex용으로 바꾼 버전입니다. 목표는 **짧은 루트 지침 + 가까운 하위 지침 + 선택적 보조 문서**입니다.

## When to use
- 저장소에 Codex용 instruction 구조를 처음 세팅할 때
- 루트/하위 `AGENTS.md`, `AGENTS.override.md`, `CONTEXT.md` 책임을 실제 파일로 만들 때
- 기존 설계안을 작동하는 instruction 레이어로 바꿔야 할 때

## Do not use when
- 구조 진단과 개선안 제시만 필요한 작업 → `agent-context-audit`, `agent-context-guide`
- 현재 instruction 문서의 사실 여부 검증이 주목적인 작업 → `agent-context-verify`
- 단순 README/문서 편집처럼 instruction 계층 자체를 바꾸지 않는 작업

## Quick start
1. 저장소 루트와 주요 디렉토리 구조를 읽는다.
2. 기존 instruction 파일과 fallback 문서를 찾는다.
3. 루트 초안 → 하위 문서 → 보조 문서 순으로 책임을 배치한다.
4. 끝나면 `agent-context-verify`와 `agent-context-audit` 후속 검증을 잡는다.

## Use references
- `../agent-context-guide/references/file-standards.md`
- `../agent-context-guide/references/token-optimization.md`

## Workflow
1. 루트에서 빌드 도구와 주요 디렉토리 구조를 파악한다.
2. 기존 instruction 문서를 찾는다: `AGENTS.md`, `AGENTS.override.md`, fallback 파일, `CONTEXT.md`, `README.md`.
3. 루트 `AGENTS.md` 초안을 작성하거나 기존 파일을 정리한다.
4. 도메인 경계가 분명한 하위 디렉토리에는 `AGENTS.md`를 추가한다.
5. 일시적이거나 더 강한 예외 규칙이 필요하면 `AGENTS.override.md`를 쓴다.
6. 긴 배경 설명은 `CONTEXT.md` 또는 `docs/`로 옮기고, 루트/하위 지침에서는 링크만 남긴다.
7. 생성 후 `agent-context-verify`와 `agent-context-audit`로 검증 계획을 제안한다.

## Guardrails
- 루트 문서에 변동성이 큰 정보나 장문 예시를 넣지 않는다.
- 동일 명령을 여러 instruction 파일에 반복하지 않는다.
- 사용자/팀 고유 규칙은 코드 구조와 가장 가까운 위치에 둔다.

## Review Harness
- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: 저장소 경계, 문서 책임, fallback 파일 사용 여부를 먼저 정리한다
- generator: 루트/하위 `AGENTS.md`, 필요 시 `AGENTS.override.md`, `CONTEXT.md`를 생성·정리한다
- evaluator: `agent-context-verify` 후 `agent-context-audit`로 교차 검증한다
- 평가축: 생성 구조 정확성, 링크 무결성, 중복 감소, 책임 명확성
- artifacts/evidence: 생성 파일 목록, 링크 무결성, 명령 검증, 책임 분리 결과
- pass condition: 깨진 링크가 없고, 중복 규칙이 줄어들며, 루트/하위 지침의 책임이 명확해야 한다
- 자동 다음 행동: `pass`면 완료, `refine`이면 파일/링크 수정, `rescope`면 구조 재배치, `critical`이면 verify/audit 결과를 기준으로 재생성한다

## Output expectation
- 생성/보강한 instruction 파일 목록
- 각 파일의 책임
- 다음 검증 단계 제안
