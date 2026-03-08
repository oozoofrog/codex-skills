---
name: ghostty-setup
description: >-
  Configure and troubleshoot Ghostty terminal settings with a safe, repeatable
  workflow for themes, profiles, accessibility/readability, and include chains.
  Use when Codex needs to create, update, or debug Ghostty config files (for
  example `config`, `themes/*.conf`, `profiles/*.conf`), adjust
  contrast/font/cursor/padding behavior, or switch and verify theme/profile
  setups.
---

# Ghostty Setup

## Overview

Ghostty 설정을 안전하게 변경하고 검증하는 표준 절차를 제공하기.
테마/프로필/가독성 옵션을 수정할 때 변경 범위를 최소화하고 회귀를 방지하기.

## Quick Start

1. 수정 대상 파일과 include 체인을 먼저 식별하기.
2. 사용자 요구를 옵션 단위로 분해해 변경안을 확정하기.
3. 필요한 옵션만 수정하고 관련 파일만 검증하기.
4. 결과와 롤백 방법을 함께 보고하기.

상세 절차는 `references/workflow.md`를 읽기.
옵션별 의미와 주의점은 `references/options-map.md`를 읽기.

## Workflow

### 1) 현재 상태 파악하기

- Ghostty 설정 루트를 확인하기 (`~/.config/ghostty` 또는 작업 디렉터리).
- 엔트리 파일(`config`)과 `config-file` include 체인을 추적하기.
- 변경 대상 파일의 현재 값을 확인하기.

### 2) 변경 계획 확정하기

- 요청을 기능 단위로 분해하기:
  - 가독성: `font-size`, `minimum-contrast`, 선택 영역 대비
  - 시각 스타일: `background`, `foreground`, ANSI `palette`
  - 조작감: `cursor-style`, `cursor-style-blink`, padding
  - 구성 구조: profile/theme 분리, include 순서
- 기존 설정을 유지할 값과 덮어쓸 값을 구분하기.
- 한 번에 하나의 목표(예: 대비 개선)만 우선 적용하기.

### 3) 파일 수정하기

- 공통값은 base profile에 두고, 환경별 값은 active profile/theme로 분리하기.
- 중복 선언을 줄이고 선언 우선순위가 드러나게 정리하기.
- 의미 없는 대규모 재정렬을 피하고, 필요한 라인만 수정하기.

### 4) 검증하기

- include 경로 오탈자, 파일 존재 여부, 순환 참조 위험을 점검하기.
- 동일 옵션의 중복 선언 시 최종 적용 위치를 확인하기.
- 사용자가 즉시 확인할 수 있는 검증 절차(재로드, 시각 확인 항목)를 제공하기.

### 5) 결과 보고하기

- 변경 파일 목록과 핵심 diff 의도를 요약하기.
- 확인해야 할 동작(예: 커서 깜빡임, 선택 영역 대비)을 체크리스트로 제시하기.
- 문제 발생 시 되돌릴 파일/라인 단서를 제공하기.

## Task Patterns

### 가독성/접근성 조정

- 배경/전경 대비와 `minimum-contrast`를 함께 다루기.
- 글자 크기, 커서 형태, 선택 영역 색상을 묶어서 조정하기.
- 저자극 모드(짙은 배경)와 고대비 라이트 모드를 분리 제공하기.

### 테마 전환

- theme 파일을 독립적으로 유지하고 profile에서 선택만 바꾸기.
- palette 전체 톤을 함께 조정해 ANSI 색만 튀지 않게 관리하기.

### profile 구조 정리

- `config` -> `profiles/*.conf` -> `themes/*.conf` 형태로 계층화하기.
- 공통값과 변동값을 분리해 재사용성과 롤백 용이성을 확보하기.

### 문제 해결

- "변경이 안 먹는다" 요청 시 include 순서와 동일 키 중복을 먼저 점검하기.
- "눈이 피로하다" 요청 시 contrast/size/cursor/selection을 우선 조정하기.

## Output Contract

- 항상 다음을 포함해 응답하기:
  - 변경/점검한 파일 경로
  - 적용한 핵심 옵션과 이유
  - 사용자가 바로 실행할 검증 단계
- 값을 확신할 수 없으면 임의 추정 대신 확인 질문을 최소 단위로 요청하기.
