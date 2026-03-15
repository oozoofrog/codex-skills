# CONTEXT.md

## Scope
- `hierarchical-context-architecture/`는 대규모 저장소용 컨텍스트 아키텍처를 설계·감사하는 스킬을 담는다.
- 루트 규칙은 [../CLAUDE.md](../CLAUDE.md), 협업 규칙은 [../AGENTS.md](../AGENTS.md)를 함께 따른다.

## Key Files
- [SKILL.md](./SKILL.md): 트리거와 핵심 워크플로
- [agents/openai.yaml](./agents/openai.yaml): UI 표시명과 기본 프롬프트
- [references/architecture-guide.md](./references/architecture-guide.md): 설계 원칙과 운영 지침
- [references/templates.md](./references/templates.md): `CLAUDE.md` / `CONTEXT.md` / `AGENTS.md` 템플릿
- [scripts/verify_context_tree.py](./scripts/verify_context_tree.py): 링크·경로·구조 검증 스크립트

## Local Rules
- 트리거 설명과 UI 메타데이터는 같은 사용 시나리오를 가리키도록 유지하기.
- 절차 요약은 `SKILL.md`에, 긴 설명과 템플릿은 `references/`에 두기.
- 검증 스크립트를 수정하면 실제 임시 저장소 시나리오로 재현 테스트하기.

## Verification Notes
- `python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py hierarchical-context-architecture`
- `python3 hierarchical-context-architecture/scripts/verify_context_tree.py --root .`
