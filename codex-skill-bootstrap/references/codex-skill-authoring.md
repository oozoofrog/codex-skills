# Codex skill authoring notes

이 문서는 OpenAI Codex 공식 문서를 바탕으로 정리한 요약입니다.

## 1. Skill directory anatomy

공식 문서 기준으로 Codex 스킬의 최소 단위는 디렉토리 + `SKILL.md`입니다.

```text
skill-name/
├── SKILL.md
├── agents/
│   └── openai.yaml      # optional
├── scripts/             # optional
├── references/          # optional
└── assets/              # optional
```

핵심 원칙:
- `SKILL.md`는 필수
- `name`, `description` frontmatter는 필수
- 본문은 필요할 때만 로드되므로 짧고 핵심적이어야 함

공식 문서:
- https://developers.openai.com/codex/skills

## 2. Discovery locations

Codex는 repo, user, admin, system 위치에서 스킬을 찾습니다.

repo-local 작성의 기본 위치:
- `$REPO_ROOT/.agents/skills`
- 현재 작업 디렉토리에서 repo root까지 올라가며 탐색

실무 권장:
- 팀 공용 스킬은 repo-local
- 개인 범용 스킬은 `~/.agents/skills`

## 3. Explicit vs implicit invocation

Codex는 스킬을 두 가지 방식으로 씁니다.

1. 명시 호출
   - `$skill-name`
   - `/skills` 또는 UI에서 직접 선택
2. 암묵 호출
   - 사용자 요청이 `description`과 잘 맞을 때 자동 선택

따라서 `description`은 짧지만 매우 정확해야 합니다.

## 4. Progressive disclosure

공식 문서와 skill-creator 가이드의 핵심은 다음입니다.

- 항상 context에 들어가는 것은 metadata 수준
- `SKILL.md` 본문은 트리거 후 로드
- 자세한 내용은 `references/`로 분리
- 결정적인 반복 작업은 `scripts/`로 분리

권장 패턴:
- SKILL.md: 핵심 절차 + 라우팅 가이드
- references/: 상세 규칙, 스키마, 예시, 벤더 문서 요약
- scripts/: 반복 감사, 코드 생성, 변환

실무에서는 아래 operator-facing 섹션을 두면 discovery와 실제 사용성이 좋아집니다.

- `When to use` 또는 `When it fits`
- `Do not use when`
- `Quick start`
- `Output expectation`

## 5. Optional `agents/openai.yaml`

공식 문서상 선택 사항이지만, UI와 invocation policy를 더 명확하게 만들 수 있습니다.

대표 필드:
- `interface.display_name`
- `interface.short_description`
- `interface.default_prompt`
- `policy.allow_implicit_invocation`
- `dependencies.tools` (필요 시)

## 6. Best practices

공식 문서에서 가져온 실무 포인트:

- 한 스킬은 한 작업에 집중
- 설명보다 절차와 기준을 우선
- 중복 설명을 피하고 references로 분리
- 필요 없으면 script를 만들지 않음
- repo 전체 규칙은 AGENTS.md에서 관리

## 7. Packaging later as a plugin

스킬을 팀이나 여러 프로젝트에 배포하려면 나중에 plugin으로 패키징할 수 있습니다.

공식 문서 기준 plugin 엔트리 포인트:

```text
.codex-plugin/plugin.json
```

이 프로젝트는 일단 repo-local skills만 다루고, 패키징은 나중 단계로 남겨둡니다.
