---
name: codex-skill-audit
description: Use this skill when the user wants to audit a Codex skill or skill repository for official structure compliance, discovery readiness, frontmatter quality, oversized SKILL bodies, stale `agents/openai.yaml`, duplicate skill names, or missing repo-level AGENTS guidance.
---

# Codex Skill Audit

Codex 스킬 저장소를 공식 구조와 운영 관점에서 감사하고 개선점을 제안합니다.

## When to use

다음 요청에 적합합니다.

- `.agents/skills` 구조 점검
- Codex 스킬 저장소 품질 감사
- discovery 문제 진단
- 스킬 이름 중복/설명 부정확/본문 비대화 점검
- `agents/openai.yaml`와 SKILL.md 정합성 확인

## Use these resources

- `references/audit-checklist.md` — 사람이 직접 볼 감사 기준
- `scripts/audit_codex_skill_repo.py` — 반복 가능한 구조 점검 스크립트

## Audit workflow

### 1. Find the target root

명시 경로가 없으면 현재 repo를 기준으로 감사합니다.

### 2. Run the deterministic audit

가능하면 먼저 아래 스크립트를 실행합니다.

```bash
python3 .agents/skills/codex-skill-audit/scripts/audit_codex_skill_repo.py [target]
```

이 스크립트는 최소 다음을 확인합니다.

- repo root에 `AGENTS.md` 존재 여부
- `.agents/skills/**/SKILL.md` 탐색
- frontmatter의 `name`, `description`
- kebab-case 이름 규칙
- 중복 스킬 이름
- 과도하게 긴 `SKILL.md`
- skill dir 안의 불필요한 `README.md`
- `agents/openai.yaml` 존재 여부와 기본 정합성

### 3. Inspect qualitative issues

스크립트 결과 이후 수동으로 아래를 점검합니다.

- `description`이 너무 넓거나 너무 좁지 않은가
- `SKILL.md` 본문이 핵심 절차 중심인가
- 상세 설명이 `references/`로 충분히 분리되었는가
- script가 꼭 필요한 곳에만 들어가 있는가
- repo-level AGENTS.md 규칙과 충돌하지 않는가

### 4. Report by severity

결과는 다음 4단계로 정리합니다.

- `critical` — 발견/실행 자체가 깨짐
- `warning` — 구조는 되지만 품질 저하 위험
- `info` — 선택적 개선
- `strength` — 잘한 점

### 5. End with concrete fixes

항상 아래 형태로 마무리합니다.

1. 바로 고쳐야 할 파일
2. 권장 수정안
3. 필요하면 신규 파일 제안
4. plugin packaging 전환 전 준비사항

## Output expectation

최종 결과는 다음 형식을 권장합니다.

```markdown
# Codex Skill Audit Report

## Summary
...

## Findings
- [critical] ...
- [warning] ...
- [info] ...

## Recommended fixes
1. ...
2. ...
```
