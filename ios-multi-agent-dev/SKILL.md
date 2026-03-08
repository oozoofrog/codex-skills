---
name: ios-multi-agent-dev
description: >-
  Coordinate multi-agent iOS/Swift development by splitting work across task
  framing, codebase analysis, implementation, critical review, and review
  incorporation. Use when Codex should orchestrate separate planner/reviewer and
  builder agents for SwiftUI/UIKit, networking, concurrency, feature work, bug
  fixes, refactors, or release-sensitive changes instead of letting one agent
  both analyze and implement.
---

# iOS Multi-Agent Dev

## Overview

iOS/Swift 작업을 여러 에이전트에 역할 분리해 안전하게 진행하기.
정의 → 분석 → 구현 → 메인 에이전트 검증 → 비판적 리뷰 → 반영 순서를 유지하고, 최소 변경으로 목표를 달성하기.

## Quick Start

1. `references/master-template.md`의 Task Brief를 채우기.
2. 변경 크기와 위험도를 보고 경로를 고르기.
   - 작거나 단순한 수정: 분석 → 구현 → 메인 검증 → 리뷰
   - 릴리즈 민감/동시성/네트워킹/상태 버그: 전체 흐름
3. 메인 에이전트는 오케스트레이션, 검증, 최종 통합을 직접 맡기.
4. 분석/리뷰는 read-only explorer 또는 default 에이전트에 맡기.
5. 구현은 worker 에이전트에 맡기고 수정 파일 소유권을 명시하기.
6. 구현 handoff를 받으면 `references/validation-loop.md`의 검증 루프를 먼저 수행하기.
7. `MainActor`, `Sendable`, cancellation, `.task`, SwiftUI lifecycle, SwiftData threading이 걸린 작업은 `typecheck`만으로 끝내지 말고 strict concurrency 기준의 build/test를 우선하기.
8. 리뷰 결과가 형식 불일치거나 피상적 요약이면 즉시 무효 처리하고 재프롬프트하기.
9. 한 번에 둘 이상의 에이전트에게 같은 파일을 수정하게 하지 말기.
10. 실제 Claude CLI를 쓰면 `../claude-code-bridge/SKILL.md`의 역할 잠금 규칙을 따르기.
11. SPM → framework 전환, 모듈 이동, `xcodegen`/`xcodeproj` 재생성이 걸리면 구조 마이그레이션 검증 루프를 추가 적용하기.

상세 프롬프트는 `references/master-template.md`를 읽기.
작업 유형별 순서는 `references/task-patterns.md`를 읽기.
플랫폼 체크리스트는 `references/platform-checklists.md`를 읽기.
리뷰 기준은 `references/review-checklist.md`를 읽기.
검증 루프는 `references/validation-loop.md`를 읽기.

## Core Principles

- 구현과 리뷰 역할을 분리하기.
- 동일 단계에서 두 에이전트에게 같은 구현을 경쟁시키지 말기.
- 실제 Claude CLI를 쓸 때도 같은 단계에서 Codex와 Claude가 동시에 구현하지 말기.
- 가능한 최소 변경으로 해결하기.
- 기존 구조와 공개 API를 존중하기.
- 요구사항과 무관한 리팩터링과 포맷 정리를 피하기.
- 메인 에이전트가 항상 최종 판단과 통합을 맡기.
- 메인 에이전트가 서브에이전트의 주장만 믿고 완료 처리하지 말기.
- 바로 다음 행동이 막히는 작업은 서브에이전트에 넘기지 말고 직접 처리하기.
- 구현 전에는 반드시 분석 산출물을 확보하기.
- 리뷰는 칭찬보다 결함 탐지에 집중하기.
- 형식이 맞지 않는 리뷰와 근거 없는 리뷰는 결과로 인정하지 말기.

## Workflow

### 1) Task Brief 만들기

- Project Context, Task Type, Task, User Perspective, Related Code, Constraints, Risk Notes를 채우기.
- 빠진 정보가 있어도 추정 가능한 범위와 확인이 필요한 범위를 분리하기.
- 성공 기준, 실패 기준, 수정 금지 범위를 먼저 명시하기.

### 2) Planner/Reviewer 에이전트로 문제 정의하기

- 목표 재정의, 추천 접근, 대안, 영향 파일 추정, 상태/이벤트 흐름, 테스트 전략, 회귀 위험을 정리하게 하기.
- 결과는 Builder 에이전트에게 전달할 구현 브리프 형태로 정리하게 하기.
- 과도한 구조 개편 제안은 제외하게 하기.

### 3) Builder 에이전트로 코드베이스 분석만 하기

- 아직 수정하지 말고 현재 구조, 관련 파일, 변경 포인트, 최소 수정 전략, 숨은 위험, 테스트 위치를 정리하게 하기.
- 분석 단계에서는 코드 패치나 파일 쓰기를 금지하기.
- 메인 에이전트는 분석 결과를 읽고 실제 구현 범위를 잠그기.

### 4) Builder 에이전트로 구현하기

- worker 에이전트에 파일 소유권을 명확히 넘기기.
- 구현 결과로 변경 요약, 파일별 수정 내용, 코드 패치, 테스트, 잔여 위험을 요구하기.
- SwiftUI에서는 `.task`, `.task(id:)`, `.alert`, cancellation, MainActor 관련 결정을 설명하게 하기.
- 실제 Claude CLI를 구현 워커로 쓰면 review 전용 세션과 분리하기.
- 리뷰가 끝나기 전까지 추가 기능을 끼워 넣지 말기.

### 5) 메인 에이전트가 구현 handoff 검증하기

- 실제 수정된 파일을 직접 열어 worker 요약과 일치하는지 확인하기.
- 약속한 테스트/검증 명령이 실제로 실행됐는지 직접 재검증하기.
- 변경이 Task Brief의 범위를 넘지 않았는지 확인하기.
- 가능한 경우 typecheck, build, test, lint 중 최소 하나를 직접 실행하기.
- Concurrency 민감 작업에서는 `swift test`, `swift build`, `xcodebuild test`, strict concurrency build를 `typecheck`보다 우선하기.
- 검증 불가 항목은 이유와 잔여 위험을 명시하기.
- 검증이 실패하면 완료로 보고하지 말고, 바로 수정 루프를 시작하거나 구체적인 다음 수정안을 제시하기.
- 이 단계가 끝나기 전에는 리뷰 단계로 넘기지 말기.

### 6) Planner/Reviewer 에이전트로 비판적 리뷰하기

- 치명적 문제, 높은 확률의 버그, 회귀 가능성, 테스트 누락, 성능/메모리/동시성 문제, 수동 QA 항목을 우선 찾게 하기.
- 문제 숨기기인지 원인 제거인지 구분하게 하기.
- 각 지적마다 파일/함수, 근거, 영향, 최소 수정 방향을 포함하게 하기.
- 섹션별 이슈가 없으면 `없음`을 명시하게 하기.
- 형식이 맞지 않거나 결함 없이 요약만 하면 무효로 보고 재프롬프트하기.

### 7) Builder 에이전트로 리뷰 반영하기

- 리뷰 항목별 수용/비수용 판단과 근거를 작성하게 하기.
- 원래 요구 범위를 넘는 변경은 분리 표기하게 하기.
- 동일한 유형의 회귀가 다시 생기지 않도록 테스트와 방어 로직을 보강하게 하기.
- 반영 후 메인 에이전트가 다시 검증 루프를 수행하게 하기.

## Review Quality Gate

다음 중 하나라도 해당하면 리뷰 결과를 무효로 처리하기.

- 요청한 헤딩 형식을 따르지 않기
- 구현 요약이나 칭찬 위주로 채우기
- 문제 지적에 파일/함수/근거가 없기
- 수정 요청이 추상적이고 바로 실행 불가능하기
- 섹션을 비워 두고 넘어가기

무효 리뷰를 받으면 다음처럼 재지시하기.
- 각 항목마다 `어디서`, `왜`, `무슨 영향`, `최소 수정 방향`을 쓰기
- 이슈가 없으면 `없음`을 명시하기
- 장점 요약은 한 문장 이하로 제한하기

## Agent Assignment Rules

### 메인 에이전트가 맡을 일

- 사용자 요구 해석하기
- Task Brief 확정하기
- 어떤 단계가 즉시 blocking인지 판단하기
- 서브에이전트 결과 비교와 통합하기
- 수정 파일 직접 확인하기
- 검증 명령 직접 실행하기
- 형식 불량 handoff와 리뷰를 거절하기
- 최종 수정, 테스트, 보고하기

### explorer/default 에이전트에 맡길 일

- 읽기 전용 구조 분석
- 설계 대안 비교
- 비판적 코드 리뷰
- 테스트 관점 점검
- 위험 식별

### worker 에이전트에 맡길 일

- 범위가 고정된 코드 수정
- 테스트 추가
- 지정한 파일군 내부 리팩터링
- 리뷰 피드백 반영

### 피하기

- 같은 파일을 여러 worker에게 동시에 맡기기
- 분석이 끝나기 전에 구현 맡기기
- 리뷰 에이전트에게 구현까지 맡기기
- 로컬에서 바로 확인 가능한 blocking 작업을 기다리며 정지하기
- 수정된 파일을 열어보지 않고 서브에이전트 요약만 믿고 완료 처리하기

## Default Output Contract

- 항상 다음을 포함해 응답하기.
  - 현재 단계
  - 변경 또는 분석 대상 파일
  - 핵심 판단 근거
  - 테스트/검증 상태
  - 남은 위험
  - 다음 단계 또는 handoff 대상
- 리뷰 단계에서는 요청한 헤딩을 그대로 사용하기.
- 검증 단계에서는 직접 실행한 명령과 결과를 분리해 적기.
- 검증 실패 시에는 실패한 명령, 핵심 오류 요약, 바로 이어질 수정 계획을 함께 적기.

## iOS Risk Baseline

모든 단계에서 기본 점검 항목으로 삼기.

- MainActor 및 UI thread 안전성
- async/await 취소와 중복 실행
- retain cycle
- observer/delegate 등록·해제 균형
- source of truth 일관성
- view lifecycle 재호출
- cell/view 재사용 오염
- 네트워크 실패, 재시도, timeout, auth refresh
- 앱 생명주기 전환
- 상태 복원과 idempotency
- 테스트 가능성과 회귀 범위

## Escalation Guidance

- 버그 수정은 증상 가리기보다 원인 제거를 우선하기.
- 릴리즈 임박, 결제/인증, 데이터 무결성, 동시성 문제는 전체 흐름을 강제하기.
- 구조 마이그레이션은 source-of-truth 결정, generator 재생성, 단계별 build/test, 문서 동기화를 한 세트로 다루기.
- 단순 UI 문구나 레이아웃 수정처럼 위험이 낮으면 분석과 구현 단계를 압축하되, 메인 검증과 리뷰는 생략하지 않기.
