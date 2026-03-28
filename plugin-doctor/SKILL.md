---
name: plugin-doctor
description: Codex 플러그인/스킬 저장소를 감사하고 개선합니다. `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.agents/skills`, `.codex/agents`, legacy Claude 산출물을 점검할 때 사용합니다.
---

# Plugin Doctor

원본 `fixer` 스킬을 Codex 기준으로 옮긴 버전입니다.

## Use resources
- `references/official-spec.md`
- `scripts/audit_codex_plugin_repo.py`
- 필요 시 `../codex-skill-audit/scripts/audit_codex_skill_repo.py`

## Workflow
1. 감사 대상 루트를 결정한다. 기본값은 현재 저장소다.
2. `scripts/audit_codex_plugin_repo.py [target]`로 결정적 구조 감사를 먼저 수행한다.
3. legacy Claude 산출물(`CLAUDE.md`, `.claude-plugin/`, hooks 전용 구조`)이 남아 있는지 확인한다.
4. repo-local skills, optional plugin packaging, custom agents의 정합성을 수동 점검한다.
5. `critical / warning / info / strength`로 결과를 보고하고, 안전한 자동 수정 후보를 분리한다.

## What this skill focuses on
- `.agents/skills/**/SKILL.md`
- optional `agents/openai.yaml`
- `.codex/agents/*.toml`
- `.agents/plugins/marketplace.json`와 `plugins/*/.codex-plugin/plugin.json` (존재하는 경우)
- `.mcp.json`, `.app.json` 같은 보조 매니페스트
- Codex로 옮기면서 남은 Claude 전용 흔적

## Review Harness
- mode: none
- 공통 기준: `../../../docs/review-harness.md`
- generator: 상위 변경사항 또는 감사 대상 repo 구조
- evaluator: 이 스킬 자체와 audit script가 evaluator-native plugin audit 역할을 수행한다
- 평가축: marketplace↔package 정합성, manifest 품질, legacy residue, custom agent/skill 연결성
- artifacts/evidence: manifest 구조, audit script output, legacy residue, custom agent 정합성
- pass condition: plugin/skill/custom agent 레이어의 구조 문제를 severity와 근거와 함께 설명할 수 있어야 한다
- 자동 다음 행동: `pass`면 종료, `warning`이면 metadata 정리, `critical`이면 packaging 또는 manifest를 재생성하고 필요 시 `sync_packaged_plugins.py`를 재실행한다
