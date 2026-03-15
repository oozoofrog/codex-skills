---
name: hierarchical-context-architecture
description: >-
  Design, bootstrap, and audit hierarchical AI context systems for large
  repositories using root `CLAUDE.md`, local `CONTEXT.md`, and portable
  `AGENTS.md` files. Use when Codex needs to create or refactor repository
  instruction files, split oversized global prompts into directory-local docs,
  define load and override order, reduce context rot, or verify broken and
  stale context references in an existing codebase.
---

# Hierarchical Context Architecture

## Overview

대규모 프로젝트에서 AI 컨텍스트를 전역 규칙, 서브시스템 지식, 현재 작업 상태로 분리해 토큰 예산을 관리하기.
루트 `CLAUDE.md`는 작고 안정적으로 유지하고, 상세 도메인 지식은 가까운 디렉토리의 `CONTEXT.md`로 내려 보내며, 범용 협업 규칙은 `AGENTS.md`에 두기.

## Quick Start

1. 저장소 루트에서 전역 규칙만 추려 `CLAUDE.md` 초안을 잡기.
2. 기능 경계가 분명한 디렉토리마다 `CONTEXT.md`를 두고 해당 영역의 목적, 핵심 파일, 하위 링크를 적기.
3. 여러 도구가 함께 읽어야 하는 협업 규칙은 `AGENTS.md`에 두기.
4. 상위 문서는 짧게 유지하고, 긴 예시·템플릿·세부 설명은 `references/`로 분리하기.
5. 긴 로그나 도구 출력은 XML 스타일 블록으로 격리하거나 별도 참조 파일로 빼기.
6. 변경 후 `scripts/verify_context_tree.py --root <repo-root>`로 링크와 구조를 점검하기.

## Core Rules

### 1) Locality 우선
- 설명은 그것이 적용되는 코드와 최대한 가까운 디렉토리에 두기.
- 전역 문서에 서브시스템 세부사항을 오래 쌓아 두지 말기.
- `CONTEXT.md`는 “무엇을 하는가”보다 “왜 이런 구조인지”를 우선 기록하기.

### 2) Progressive Disclosure 적용
- 처음부터 모든 문서를 한 번에 주입하지 말기.
- 먼저 경로, 파일명, 짧은 요약만 유지하고 실제 상세 내용은 필요할 때 읽기.
- 큰 로그, API 사양, 설계 회의록은 `references/`나 별도 문서로 분리하기.

### 3) Override Rule 명시
- 작업 대상 파일에 더 가까운 지침이 더 우선이라는 점을 항상 유지하기.
- 일반 규칙은 루트에, 예외와 특수 규칙은 하위 `CONTEXT.md`에 적기.
- 상위 규칙을 뒤집는 경우, 하위 문서에 무엇을 왜 덮어쓰는지 명시하기.

### 4) Stable Prefix 유지
- 시스템 프롬프트와 정적 규칙(`CLAUDE.md`, 핵심 `AGENTS.md`)은 항상 프롬프트 앞부분에 오게 설계하기.
- 사용자 입력, 최신 로그, 도구 출력처럼 변동이 큰 내용은 뒤로 밀기.

### 5) Fix the Rules 루프 적용
- AI가 같은 실수를 반복하면 코드만 고치지 말고 해당 규칙 문서도 함께 고치기.
- 규칙 문서는 코드와 동일한 운영 자산으로 취급하기.

## Recommended Workflow

### 1) Context Map 만들기
- 루트 전역 규칙, 주요 서브시스템, 자주 바뀌는 작업 상태를 분리하기.
- 디렉토리 경계가 불분명하면 먼저 코드 구조를 정리하고 나서 문서를 배치하기.

### 2) Root `CLAUDE.md` 축소하기
- 빌드/테스트 명령, 전역 아키텍처 결정, 환경 제약만 남기기.
- 200라인을 넘기지 않기.
- API 세부 문서, 스타일 가이드, 긴 예시는 빼기.

### 3) Subsystem `CONTEXT.md` 작성하기
- 각 문서에 다음만 우선 넣기.
  - 이 디렉토리의 책임
  - 핵심 파일/모듈 관계
  - 주의해야 할 패턴과 금지 패턴
  - 더 내려가야 하는 하위 컨텍스트 링크
- 하위 문서가 있으면 트리처럼 연결하기.

### 4) `AGENTS.md`를 이식성 레이어로 쓰기
- 도구 전용 설정이 아니라 범용 협업 규칙만 적기.
- 어떤 도구가 읽어도 의미가 통하는 표현을 사용하기.

### 5) 동적 데이터 분리하기
- 긴 빌드 로그, 대량 JSON, 생성 결과는 규칙과 섞지 말기.
- `<instructions>`, `<context>`, `<data>`처럼 역할이 분명한 태그나 별도 파일로 분리하기.

### 6) 검증하고 보수하기
- 링크 무결성, 파일 경로 정확성, 문서 길이, 고립된 컨텍스트 후보를 점검하기.
- 검증에서 걸린 항목은 문서 구조 자체를 다시 다듬기.

## File Contracts

### `CLAUDE.md`
- 전역 규칙과 공통 명령만 적기.
- 컴팩션 이후 재주입되는 핵심 앵커로 취급하기.
- 자주 바뀌는 세부 상태는 넣지 말기.

### `CONTEXT.md`
- 서브시스템 전용 의도, 예외 규칙, 하위 링크를 적기.
- 현재 디렉토리와 직접 연결되는 파일 관계를 설명하기.
- 상위 규칙을 덮어쓰면 이유를 분명히 적기.

### `AGENTS.md`
- 협업 규칙, 리뷰 방식, 공통 작업 계약을 적기.
- 특정 IDE나 단일 도구에 종속된 설정은 최소화하기.

## Resources

- 상세 설계 원칙과 운영 지침은 `references/architecture-guide.md`를 읽기.
- 바로 복사해 쓸 수 있는 문서 골격과 XML 분리 예시는 `references/templates.md`를 읽기.
- 저장소 검증은 `scripts/verify_context_tree.py`를 사용하기.
- 검증 결과의 `Content Accuracy Hints` 섹션으로 수동 리뷰가 필요한 문서 후보를 추리기.

## Output Contract

이 스킬을 적용할 때는 항상 다음을 함께 정리하기.
- 제안하는 컨텍스트 트리와 파일 배치
- 각 문서의 책임 범위
- 로드 순서와 override 관계
- 이번 변경에서 새로 만든 규칙 또는 수정한 규칙
- 자동 검증 결과와 남은 수동 확인 항목
