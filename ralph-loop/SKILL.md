---
name: ralph-loop
description: >-
  Guide iterative self-referential Codex loops for well-scoped tasks that can
  be retried until a clear completion condition is met. Use when the user asks
  for Ralph Loop, repeated Codex execution, overnight iteration, or a bounded
  loop that keeps working until tests pass or a completion promise is reached.
---

# Ralph Loop

## Overview

Ralph Loop 기법을 Codex에서 안전하게 재해석한 스킬입니다.
Claude plugin의 Stop hook 기반 자동 세션 재주입은 Codex에 그대로 옮기지 않고,
**명시적 opt-in + bounded loop + 명확한 종료 조건** 기반 운영 가이드로 제공합니다.

핵심 원칙:
- 사용자가 분명히 원할 때만 사용하기
- 항상 **완료 조건**과 **최대 반복 수**를 같이 두기
- 테스트/검증 가능한 작업에만 쓰기
- 사람 판단이 중요한 작업에는 기본값으로 쓰지 않기

## Quick Start

1. 먼저 작업이 Ralph Loop에 적합한지 판단하기.
   - 테스트가 통과할 때까지 반복
   - 잘 정의된 refactor/cleanup 반복
   - 명확한 completion phrase 또는 검증 조건 존재
2. 완료 조건을 고정하기.
   - 예: 모든 테스트 통과
   - 예: 특정 문자열 출력
3. 최대 반복 수를 고정하기.
4. `references/manual-loop.md`의 bounded loop 예시를 사용하기.
5. 위험하거나 파괴적인 작업이면 `references/safety-rails.md`를 먼저 읽기.

## When It Fits

좋은 경우:
- 요구사항이 명확한 구현 작업
- 테스트/린트/빌드로 자동 검증 가능한 작업
- 반복적인 self-correction이 유효한 작업
- 장시간 unattended run이 사용자 의도와 맞는 작업

좋지 않은 경우:
- 사람 판단이 필요한 설계 결정
- 모호한 성공 조건
- 프로덕션 장애 대응
- destructive operation 위주 작업

## Workflow

### 1) 작업을 loop-friendly 하게 바꾸기
- 한 번에 너무 큰 목표를 주지 않기
- 성공 조건을 measurable 하게 만들기
- “잘 되면 끝” 대신 테스트/문구/파일 조건으로 바꾸기

### 2) bounded loop 사용하기
- 무한 루프를 기본값으로 쓰지 않기
- `max-iterations` 또는 shell loop count를 반드시 두기
- 반복 로그와 마지막 응답을 남기기

### 3) prompt 품질 관리
- 작업 목표
- 검증 명령
- 완료 신호
- stuck일 때 보고 방식
을 명시하기

자세한 템플릿은 `references/prompt-templates.md`를 읽기.

## Decision Guardrails

- Codex에서 Claude의 Stop hook을 재현하려고 하지 않기.
- 자동 루프는 항상 사용자가 명시적으로 요청했을 때만 제안하기.
- 실패해도 계속 돈다면 중간 산출물과 blocking issue를 남기도록 설계하기.
- destructive command, credential 사용, production 배포를 loop 기본 경로로 넣지 않기.

## Output Contract

항상 다음을 포함해 응답하기.
- loop 사용 적합성 판단
- 완료 조건
- 최대 반복 수
- 사용한 실행 방식 (`codex exec`, shell loop 등)
- 중단/복구 방법
