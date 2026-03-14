---
name: frontend-design
description: >-
  Create distinctive, production-grade frontend interfaces for web components,
  pages, dashboards, and applications. Use when Codex needs to build or refine
  UI/UX with strong aesthetic direction, polished interactions, and better-than-
  generic visual quality instead of default AI-looking frontend output.
---

# Frontend Design

## Overview

웹 프론트엔드 UI를 만들 때 쓰는 스킬입니다.
목표는 “작동하는 코드”를 넘어서 **기억에 남는 미감과 일관된 시각적 방향**을 가진 결과를 만드는 것입니다.

핵심 원칙:
- 먼저 **목적 / 사용자 / 제약**을 이해하기
- 바로 코드로 들어가기 전에 **명확한 aesthetic direction**을 고정하기
- 흔한 AI 스타일(무난한 폰트, 밋밋한 카드, 안전한 보라 그라디언트)로 수렴하지 않기
- 미감이 강할수록 코드도 그 미감을 뒷받침하도록 구체적으로 구현하기

## Quick Start

1. 요청을 먼저 분류하기.
   - 컴포넌트
   - 페이지
   - 대시보드
   - 전체 웹앱/랜딩
2. 아래 4가지를 짧게 고정하기.
   - 목적
   - 타깃 사용자
   - 기술 제약(React, HTML/CSS/JS, Vue 등)
   - 톤/무드
3. 하나의 **분명한 시각 방향**을 먼저 선언하기.
   - 예: editorial, brutalist, luxury, retro-futuristic, soft/pastel, industrial, playful
4. `references/aesthetics-guide.md`를 읽고 typography, color, motion, spatial composition을 그 방향에 맞게 선택하기.
5. 구현 시에는 미감과 기능을 함께 챙기기.
   - 반응형
   - 접근성
   - 상태 표현
   - hover/focus/empty/loading states
6. 결과를 설명할 때는 aesthetic direction, 핵심 시각 포인트, 구현 포인트를 함께 보고하기.

## Workflow

### 1) 방향 먼저 고정
다음 질문에 스스로 답한 뒤 구현을 시작합니다.
- 이 UI는 무엇을 해결하는가?
- 누가 쓰는가?
- 무엇이 가장 먼저 기억에 남아야 하는가?
- 어떤 분위기가 제품/브랜드와 맞는가?

방향이 불분명하면 “무난한 UI”가 되기 쉽습니다.

### 2) 구현 난이도와 미감 강도를 맞추기
- 강한 미감(실험적/화려함) → layout, animation, texture, interaction도 더 적극적으로 구현
- 절제된 미감(미니멀/럭셔리) → spacing, typography, hierarchy, subtle motion을 정밀하게 다듬기

### 3) generic AI aesthetics 피하기
다음을 기본값으로 두지 않기.
- 무난한 시스템 폰트 조합
- 안전한 보라/파랑 gradient hero
- 뻔한 marketing card grid
- 모두 비슷한 radius/shadow/button 처리

### 4) production-grade 기준 유지
시각적 완성도만이 아니라 아래를 같이 확인하기.
- semantic markup
- keyboard/focus states
- responsive behavior
- loading/empty/error states
- design token 또는 CSS variable 일관성

## Decision Guardrails

- 디자인 방향 없이 곧바로 컴포넌트만 복제하지 않기.
- 브랜드/제품 맥락이 있으면 그 맥락에 맞는 미감을 우선하기.
- “예쁘게”보다 “기억에 남고 맥락에 맞게”를 목표로 하기.
- 과한 장식이 기능을 해치면 줄이되, 그렇다고 평범한 UI로 후퇴하지는 않기.

## Output Contract

항상 다음을 포함해 응답하기.
- 선택한 aesthetic direction
- 핵심 시각 요소(typography, color, layout, motion)
- 구현 방식(어떤 기술/구조로 만들었는지)
- 반응형/접근성/상태 표현 처리 여부
