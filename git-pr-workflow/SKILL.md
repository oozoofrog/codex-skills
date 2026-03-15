---
name: git-pr-workflow
description: >-
  Guide or automate Git commit, branch, push, pull request, stale-branch cleanup,
  and structured PR review workflows. Use when Codex needs to help with commit
  messages, create a branch and PR, clean gone branches, or review a PR across
  code, tests, error handling, comments, types, and simplification.
---

# Git PR Workflow

## Overview

Git commit / push / PR 작성 / stale branch cleanup / PR 리뷰를 하나의 워크플로로 다루는 스킬입니다.
Claude plugin의 `commit-commands`와 `pr-review-toolkit`를 Codex-native 방식으로 합친 형태입니다.

핵심 원칙:
- 요청 범위를 먼저 고정하기: commit-only / commit+push+PR / cleanup / review
- 변경 없는 작업은 만들지 않기
- push/PR 생성은 로컬 상태와 검증 결과를 본 뒤 마지막에 수행하기
- 리뷰는 가능한 한 **구체적인 diff/파일 범위** 기준으로 수행하기

## Quick Start

1. 요청을 아래 중 하나로 분류하기.
   - commit만
   - branch + commit + push + PR
   - `[gone]` 브랜치/워크트리 정리
   - PR 리뷰
2. 먼저 현재 상태를 확인하기.
   - `git status --short`
   - `git branch --show-current`
   - `git diff --stat` 또는 `git diff HEAD`
   - 필요 시 `gh auth status`
3. commit/PR 계열이면 `references/commit-flow.md`를 먼저 읽기.
4. 리뷰 계열이면 `references/pr-review-aspects.md`를 읽고 어떤 aspect가 중요한지 정하기.
5. PR 생성 전에는 `references/gh-pr-checklist.md` 기준으로 제목/요약/테스트 계획을 정리하기.
6. stale branch cleanup은 먼저 preview하고, 적용이 필요할 때만 `scripts/clean_gone.sh --apply` 를 사용하기.

## Workflow

### 1) Commit only
- diff와 최근 commit log를 보고 메시지 스타일을 맞춥니다.
- 사용자가 원하지 않았다면 불필요하게 push/PR을 만들지 않습니다.
- 관련 없는 파일을 같이 stage하지 않습니다.

### 2) Branch + Commit + Push + PR
- 현재 `main`/`master` 같은 기본 브랜치에 있으면 새 브랜치를 만듭니다.
- Codex 환경에서는 보통 `codex/...` prefix를 유지합니다.
- commit 후 push, 그 다음 `gh pr create`를 수행합니다.
- PR 본문에는 최소한 아래를 포함합니다.
  - 변경 요약
  - 테스트/검증
  - 필요 시 위험/주의사항

### 3) Cleanup (`[gone]` branches)
- 먼저 어떤 브랜치가 대상인지 preview합니다.
- 현재 브랜치와 메인 worktree는 절대 삭제하지 않습니다.
- 작업은 deterministic 하므로 `scripts/clean_gone.sh`를 우선 사용합니다.

### 4) PR Review
리뷰 aspect는 다음을 사용합니다.
- `code`: 일반 코드 품질과 버그
- `tests`: 테스트 커버리지/품질
- `errors`: silent failure와 에러 처리
- `comments`: 주석/문서 정확성
- `types`: 타입 설계와 invariant
- `simplify`: 과도한 복잡성 줄이기

기본은 단일 에이전트/단일 응답 흐름으로 수행합니다.
사용자가 명시적으로 병렬/하위 에이전트 리뷰를 요청한 경우에만 더 분리된 흐름을 고려합니다.

리뷰 결과는 **사람이 읽는 Markdown 요약**을 기본으로 작성합니다.
- 먼저 전체 판정과 핵심 이슈 수를 짧게 요약합니다.
- 그 다음 중요도 순으로 finding을 나열합니다.
- 각 finding은 `심각도`, `파일:라인`, `문제`, `영향`, `최소 수정 방향`이 한눈에 보이게 적습니다.
- 이슈가 없으면 `핵심 findings: 없음`이라고 명시합니다.
- `::code-comment` 같은 inline directive는 **보조 수단**입니다. 사용자가 inline 코멘트를 명시적으로 원하거나, 해당 UI가 directive를 잘 렌더링하는 것이 확실할 때만 덧붙입니다.
- directive를 쓰더라도 **raw directive만 단독으로 출력하지 말고**, 항상 사람이 읽는 요약/목록을 먼저 보여줍니다.

## Decision Guardrails

- commit-only 요청에 push/PR을 억지로 붙이지 않기.
- branch/PR 생성 전에는 현재 브랜치와 remote 상태를 확인하기.
- 리뷰 결과는 실제 diff와 파일 근거 중심으로 쓰기.
- inline review가 필요한 환경이면 가능한 한 파일/라인 단위 findings로 표현하되, 기본 응답 본문은 Markdown 요약으로 유지하기.
- raw `::code-comment{...}` 나열만으로 답변을 끝내지 않기.
- cleanup은 preview 없이 바로 destructive 실행하지 않기.

## Output Contract

항상 다음을 포함해 응답하기.
- 현재 분류한 작업 종류
- 확인한 git/gh 상태
- 수행한 단계 또는 앞으로 수행할 단계
- commit/PR 제목 또는 리뷰 범위
- 검증 결과 또는 남은 수동 단계

PR 리뷰 응답일 때는 가능하면 아래 형식을 따르기.
- `검토 범위`: 브랜치/PR/diff/file 범위
- `판정`: blocking 여부와 핵심 이슈 수
- `핵심 findings`: 중요도 순 목록
  - 각 항목은 `[P1/P2/P3] 제목`
  - 하위 bullet으로 `위치`, `이유`, `영향`, `수정 방향`
- `검증/남은 위험`: 확인한 점과 미확인 리스크

inline directive가 꼭 필요할 때만 마지막에 추가하기.
- 요약 섹션의 finding 제목/우선순위와 일치시킬 것
- 한 줄 blob처럼 읽히지 않도록, 사람이 읽는 본문을 먼저 제공할 것
