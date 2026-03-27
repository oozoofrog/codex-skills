---
name: codex-skill-bootstrap
description: Use this skill when the user wants to create, scaffold, or modernize a Codex skill, add a repo-local `.agents/skills/...` structure, split oversized skill instructions into references, or add optional `agents/openai.yaml` metadata in line with Codex official docs.
---

# Codex Skill Bootstrap

Codex 공식 스킬 구조에 맞춰 새 스킬을 만들거나 기존 스킬을 정리합니다.

## When to use

다음 요청에 적합합니다.

- 새 Codex 스킬 만들기
- `.agents/skills/` 구조 추가하기
- 기존 스킬을 Codex 공식 구조로 마이그레이션하기
- `SKILL.md`를 너무 길지 않게 정리하고 `references/`로 분리하기
- `agents/openai.yaml` 추가 또는 갱신하기

## Use these references

작업 전에 필요에 따라 다음 문서를 읽습니다.

- `references/codex-skill-authoring.md` — Codex 공식 스킬 구조, discovery, progressive disclosure 요약
- `references/openai-yaml-guide.md` — `agents/openai.yaml` 작성 가이드

## Workflow

### 1. Scope the skill

먼저 아래를 결정합니다.

- repo-local skill인지
- user/global skill인지
- 나중에 plugin으로 배포할 계획이 있는지
- 스크립트가 필요한지, 아니면 instruction-only skill이면 충분한지

repo-local이면 기본 위치는 다음입니다.

```text
.agents/skills/<skill-name>/
```

### 2. Start with the minimum viable structure

기본 구조만 먼저 만듭니다.

```text
<skill-name>/
├── SKILL.md
└── agents/openai.yaml   # optional but recommended
```

상세 정보가 길어질 때만 다음을 추가합니다.

- `references/` — 자세한 문서, 스키마, 예시
- `scripts/` — 반복적이고 결정적인 작업
- `assets/` — 출력에 쓰일 템플릿/리소스

### 3. Write frontmatter carefully

`name`과 `description`은 Codex가 스킬을 고르고 호출하는 데 직접 사용됩니다.

- `name`: kebab-case
- `description`: 언제 써야 하고 언제 쓰지 말아야 하는지까지 드러나게 작성

설명은 다음 질문을 통과해야 합니다.

- 이 설명만 보고도 Codex가 트리거 시점을 이해할 수 있는가?
- 너무 넓어서 아무 요청에나 발동될 위험은 없는가?
- 너무 좁아서 실제 필요한 상황을 놓치지 않는가?

### 4. Keep SKILL.md lean

SKILL.md 본문에는 아래만 둡니다.

- 언제 쓰는지
- 핵심 절차
- 어떤 참조 파일을 언제 읽는지
- 어떤 스크립트를 언제 실행하는지

자세한 규칙/예시는 `references/`로 이동합니다.

### 5. Add `agents/openai.yaml` if helpful

선택 사항이지만, UI 메타데이터와 invocation policy를 더 명확하게 만들 수 있습니다.

필요하면 `references/openai-yaml-guide.md`를 읽고 아래 항목을 만듭니다.

- `interface.display_name`
- `interface.short_description`
- `interface.default_prompt`
- `policy.allow_implicit_invocation`

### 6. Validate before finishing

완료 전 다음을 확인합니다.

- `.agents/skills/...` 경로가 맞는지
- `SKILL.md` frontmatter가 있는지
- 스킬 이름이 중복되지 않는지
- 너무 긴 본문을 `references/`로 나눴는지
- `agents/openai.yaml`가 SKILL.md와 어긋나지 않는지

가능하면 `$codex-skill-audit`로 마무리 점검합니다.

## Output expectation

작업이 끝나면 최소 다음을 제공합니다.

1. 생성/수정한 파일 목록
2. 스킬의 트리거 설명
3. optional metadata 추가 여부
4. 다음에 넣을 만한 references/scripts 제안
