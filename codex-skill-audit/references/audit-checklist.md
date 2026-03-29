# Codex skill repo audit checklist

## Structural checks

- [ ] repo root에 `AGENTS.md`가 있다
- [ ] `.agents/skills/` 아래에 스킬이 위치한다
- [ ] 각 스킬 폴더에 `SKILL.md`가 있다
- [ ] 스킬 이름은 kebab-case다
- [ ] 같은 `name`을 가진 스킬이 중복되지 않는다

## Frontmatter checks

- [ ] `name` 존재
- [ ] `description` 존재
- [ ] `description`이 트리거 범위를 설명한다

## Progressive disclosure checks

- [ ] `When to use` 또는 `When it fits`가 있다
- [ ] `Do not use when`이 있다
- [ ] `Quick start`가 있다
- [ ] `Output expectation`이 있다
- [ ] SKILL.md 본문이 핵심 절차 중심이다
- [ ] 긴 예시/세부 규칙은 `references/`로 분리됐다
- [ ] 결정적 반복 작업만 `scripts/`로 분리됐다
- [ ] review loop가 의미 있는 스킬은 `Review Harness` 섹션 또는 동등한 선언을 가진다
- [ ] `mode: none / optional / required`가 실제 위험도와 맞다
- [ ] `평가축`이 단일 모호 문구가 아니라 최소 2개 이상의 평가축을 드러낸다
- [ ] `자동 다음 행동`이 `pass / refine / pivot / rescope / escalate / stop` 또는 evaluator-native status를 backtick token으로 명시한다
- [ ] `mode: none` 스킬은 evaluator-native / review 성격이 설명과 메타데이터에 드러난다
- [ ] `mode: required` 스킬은 구현·릴리스·반복 루프처럼 높은 쓰기/운영 리스크가 설명에 드러난다

## Metadata checks

- [ ] `agents/openai.yaml`가 있으면 SKILL.md와 의미가 맞다
- [ ] `display_name`, `short_description`, `default_prompt`가 과장되지 않는다
- [ ] implicit invocation 정책이 의도와 맞다
- [ ] explicit-only 스킬은 `allow_implicit_invocation: false`다
- [ ] `allow_implicit_invocation: false`인 스킬은 본문에서도 explicit-only 사용 조건을 분명히 선언한다

## Hygiene checks

- [ ] skill dir 안에 불필요한 README.md가 없다
- [ ] references가 너무 깊게 중첩되지 않았다
- [ ] repo-level AGENTS.md와 충돌하는 규칙이 없다
- [ ] 필요 시 plugin packaging으로 넘어갈 준비가 되어 있다
