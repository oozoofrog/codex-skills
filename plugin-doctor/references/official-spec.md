# Codex plugin & skill repository notes

> Updated: 2026-03-27
> Sources: OpenAI Codex skills / plugins / AGENTS.md / subagents docs

이 문서는 `plugin-doctor`가 사용하는 **실무용 요약**입니다. 목적은 Codex 저장소에서 중요한 구조 위반과 legacy Claude 잔재를 빨리 찾는 것입니다.

## 1. Repo-local skills

기본 위치:

```text
.agents/skills/<skill-name>/SKILL.md
```

권장 부속 파일:
- `agents/openai.yaml`
- `references/`
- `scripts/`
- `assets/`

핵심 원칙:
- `SKILL.md`는 짧고 절차 중심
- 장문은 `references/`로 분리
- `name`, `description` frontmatter 필수

## 2. Project instructions

Codex는 가까운 instruction 파일을 우선적으로 반영합니다.

우선순위 예시:
- `AGENTS.override.md`
- `AGENTS.md`
- 설정된 fallback filenames

Migration 기준:
- `CLAUDE.md`는 Codex의 공식 instruction 파일이 아님
- Claude용 `.claude/rules/`는 가까운 `AGENTS.md` 또는 `AGENTS.override.md`로 재구성하는 편이 안전함

## 3. Custom agents

프로젝트 범위 custom agent는 보통 다음 위치에 둡니다.

```text
.codex/agents/*.toml
```

자주 쓰는 필드:
- `name`
- `description`
- `model`
- `model_reasoning_effort`
- `sandbox_mode`
- `developer_instructions`

## 4. Plugin packaging

배포형 plugin을 만들 때의 엔트리 포인트:

```text
.codex-plugin/plugin.json
```

이 저장소는 skill-first 구조를 기본으로 하고, plugin packaging은 선택 사항입니다.

## 5. Cross-check priorities

- marketplace entry ↔ packaged plugin directory 1:1 대응
- marketplace `version` / `description` ↔ plugin manifest 정합성
- plugin manifest `skills` / `mcpServers` / asset 경로 실존 여부
- plugin README와 packaged skill 존재 여부

## 6. Audit priorities

### Critical
- `.agents/skills`에 `SKILL.md`가 없거나 frontmatter가 깨짐
- `.codex-plugin/plugin.json` JSON 파싱 실패
- custom agent TOML 파싱 실패
- Claude 전용 구조만 있고 Codex 구조가 전혀 없음

### Warning
- `AGENTS.md` 부재
- `openai.yaml` 누락
- description이 너무 짧아 discovery가 불분명함
- plugin/skill 이름과 디렉토리 책임이 어긋남

### Info
- plugin packaging 미구성
- references나 scripts가 더 분리되면 좋은 경우
- legacy Claude 파일이 보존되어 있으나 참고 자료로만 남아 있는 경우
