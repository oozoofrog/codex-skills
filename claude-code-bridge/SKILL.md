---
name: claude-code-bridge
description: >-
  Bridge Codex with the local Claude Code CLI for real analysis,
  implementation, and review handoffs. Use when Codex should call `claude`
  directly from the shell to analyze a codebase, draft or apply targeted code
  changes, produce a second-opinion review, or compare Codex and Claude outputs
  in trusted local repositories.
---

# Claude Code Bridge

## Overview

Codex가 메인 오케스트레이터로 남으면서, 필요할 때 로컬 `claude` CLI를 직접 호출해 분석, 구현, 리뷰를 보조하게 하기.
이 스킬은 Claude를 대체하지 않고, **Codex가 검증 책임을 유지한 채 Claude Code를 외부 워커처럼 활용**하는 절차를 제공한다.

## Quick Start

1. 먼저 `claude auth status`로 인증 상태를 확인하기.
2. 작업 디렉터리가 신뢰 가능한 로컬 저장소인지 확인하기.
3. iOS/Swift 작업이면 먼저 `../ios-multi-agent-dev/references/master-template.md`의 Task Brief를 채우기.
4. 요청을 `analysis`, `implementation`, `review`, `review-incorporation`, `second-opinion` 중 하나로 분류하기.
5. 명령 템플릿은 `references/cli-recipes.md`를 읽기.
6. 프롬프트 골격은 `references/prompt-templates.md`를 읽기.
7. 상황별 강화 문구는 `references/prompt-boosters.md`를 읽기.
8. 세션 재사용/분리 규칙은 `references/session-strategy.md`를 읽기.
9. 인증/권한/실패 대응은 `references/auth-and-safety.md`를 읽기.
10. Claude 출력은 그대로 완료 처리하지 말고, Codex가 파일/테스트/리스크를 직접 검증하기.

## When to Use Claude Code CLI

다음에 특히 적합하다.
- 큰 코드베이스에서 2차 분석 의견이 필요할 때
- 구현 범위가 명확하고 Claude에게 특정 파일 수정을 맡기고 싶을 때
- Codex 구현 뒤 독립적인 비판적 리뷰가 필요할 때
- Codex와 Claude의 관점을 비교해 더 안전한 수정을 고를 때

다음에는 우선순위가 낮다.
- 매우 단순한 단일 파일 수정
- 현재 로컬 환경에서 `claude` 인증이 안 되어 있을 때
- CLI 호출보다 내가 바로 수정하는 것이 더 빠른 blocking 작업

## Core Principles

- Codex가 최종 판단과 검증을 맡기.
- Claude 출력은 초안 또는 2차 의견으로 취급하기.
- 신뢰 가능한 로컬 디렉터리에서만 `claude -p`를 사용하기.
- 요청 범위, 수정 파일, 검증 기준을 먼저 잠그기.
- 대규모 자유형 위임보다 **짧고 좁은 작업 지시**를 선호하기.
- 한 번의 긴 질문보다 목적이 하나인 짧은 질문 여러 개를 선호하기.
- Codex shell에서 Claude 응답 회수가 불안정하면 TTY/PTy 모드를 우선하기.
- 같은 단계에서 Codex와 Claude에게 동시에 구현 맡기지 말기.
- 구현을 맡긴 Claude 세션에게 자기 구현 리뷰를 맡기지 말기.
- 실패하면 즉시 fallback을 정하고, 성공처럼 보고하지 말기.

## Workflow

### 1) 사전 확인하기

- `claude` 명령 존재 여부 확인하기.
- `claude auth status`로 로그인 상태 확인하기.
- 작업 디렉터리와 허용 범위를 명확히 하기.
- 인증이 안 되어 있으면 Codex 단독 진행 또는 사용자 로그인 유도하기.

### 2) 호출 목적 정하기

- 분석만 필요하면 `analysis`
- 수정 초안이 필요하면 `implementation`
- 깨보기 리뷰가 필요하면 `review`
- 리뷰 반영 전용 수정이면 `review-incorporation`
- Codex 결론 검증이 목적이면 `second-opinion`

### 3) 호출 범위 잠그기

- 작업 디렉터리
- 수정 가능한 파일
- 수정 금지 파일
- 기대 출력 형식
- 검증 명령
- 같은 단계에서 Codex가 직접 할 일과 Claude에게 넘길 일을 분리하기

### 3.5) 역할 잠그기

- `analysis` 단계에서는 구현 금지
- `implementation` 단계에서는 독립 리뷰 금지
- `review` 단계에서는 구현 금지
- `review-incorporation`은 review 결과를 받은 뒤에만 수행하기
- 같은 변경을 Codex와 Claude가 동시에 구현하지 않기

### 4) Claude CLI 호출하기

- 기본적으로 `claude -p` 비대화형 호출을 우선하기.
- 응답 회수가 불안정하면 Codex shell에서 TTY/PTy 모드를 우선하기.
- 긴 프롬프트는 heredoc 또는 임시 파일로 넘기기.
- 분석은 구조 / 의존성 / 리스크 / 다음 단계처럼 질문을 쪼개고, 한 번에 하나만 묻기.
- review는 `findings only`, `3 bullets max`처럼 출력 형식을 강하게 잠그기.
- 필요하면 `--output-format json` 또는 `--json-schema`로 구조화하기.
- 가능한 경우 `--add-dir`로 허용 디렉터리를 명시하기.
- 일정 시간 응답이 없으면 더 짧은 프롬프트, 더 좁은 범위, 더 낮은 출력 길이 제한으로 재시도하기.

### 5) Claude 결과 검증하기

- 실제 수정 파일 열기
- diff 확인하기
- build/test/typecheck 실행하기
- Codex 관점에서 리스크를 다시 평가하기

### 6) 후속 조치하기

- 결과가 좋으면 채택하기
- 부분적으로 좋으면 필요한 부분만 흡수하기
- 불충분하면 Codex가 직접 보완하거나 Claude에 더 좁은 재질문 보내기

### 7) 충돌 시 최종 판단하기

Codex와 Claude 결론이 다르면 다음 순서로 판단하기.
1. correctness
2. minimal diff
3. architecture consistency
4. testability
5. release risk

판단 근거를 짧게 남기고, 필요하면 더 좁은 second-opinion을 다시 요청하기.

## Recommended Pairing

- `ios-multi-agent-dev` + `claude-code-bridge`
  - 멀티에이전트 워크플로 안에서 Claude를 분석/구현/리뷰 워커로 사용하기
- `swift-master` + `claude-code-bridge`
  - Swift 전문 판단과 함께 Claude의 코드베이스 분석/구현력을 보조적으로 사용하기
- `ios-swift-orchestrator` + `claude-code-bridge`
  - 어떤 단계에서 Claude CLI를 호출할지 상위 라우팅에서 결정하기

## iOS/Swift Mapping

원문 협업 템플릿의 Claude 역할을 실제 CLI로 옮길 때 기본 매핑은 다음과 같다.

- 문제 정의: Codex planner / reviewer
- 코드베이스 분석: Claude CLI `analysis`
- 구현: Claude CLI `implementation`
- 독립 리뷰: Codex reviewer 또는 새 Claude 세션 `review`
- 리뷰 반영: 같은 Claude 구현 세션 또는 새 구현 세션 `review-incorporation`

핵심 규칙:
- 같은 단계에서 Codex와 Claude가 동시에 구현하지 않기
- 독립 리뷰는 구현했던 동일 Claude 세션에 맡기지 않기
- iOS 작업이면 Task Brief를 먼저 작성해 Claude에 구조화 입력으로 넘기기

## Output Contract

항상 다음을 포함해 응답하기.
- Claude CLI 사용 여부
- 호출 목적 (`analysis` / `implementation` / `review` / `review-incorporation` / `second-opinion`)
- 실행한 명령 또는 명령 골격
- Claude 결과 요약
- Codex 직접 검증 결과
- 남은 위험 또는 fallback
