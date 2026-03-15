# AGENTS.md

## Collaboration Rules
- Use the `skill-creator` workflow when creating or materially updating a skill.
- Keep `SKILL.md` frontmatter limited to `name` and `description`.
- Keep trigger language in `SKILL.md` aligned with each skill's UI metadata file.
- Prefer `references/` for long guidance and keep top-level instructions lean.
- Treat `.system/` as mirrored upstream content unless the task explicitly requires a local patch.

## Output Contract
- List changed files or directories.
- List validation commands actually executed.
- State any remaining manual follow-up or risk.

## Review Rules
- Check trigger wording consistency between `SKILL.md`, the UI metadata file, and `README.md`.
- Check local links and path references for breakage.
- Check user-visible additions against `CHANGELOG.md`.
- If a rule was missing and caused rework, update the relevant context document instead of fixing code only.
