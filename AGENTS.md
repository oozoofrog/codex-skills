# AGENTS.md

## Collaboration Rules
- Use the `skill-creator` workflow when creating or materially updating `gptpro`.
- Keep `gptpro/SKILL.md` frontmatter limited to `name` and `description`.
- Keep trigger language aligned across the standalone Skill, Plugin mirror, UI metadata, and `README.md`.
- Prefer `references/` for long guidance and keep top-level instructions lean.
- Keep `gptpro/` and `plugins/gptpro/skills/gptpro/` byte-identical.

## Output Contract
- List changed files or directories.
- List validation commands actually executed.
- State any remaining manual follow-up or risk.

## Review Rules
- When adding a Plugin, update the expected marketplace inventory in `scripts/tests/test_plugin_distribution.py` and run the repository distribution tests.
- Check trigger wording consistency between both `SKILL.md` copies, both UI metadata files, and `README.md`.
- Check every copyable `gptpro.py prepare` example uses directed `--include` or `--file-list` selection unless whole-repository disclosure is explicit and explained.
- Check local links and path references for breakage.
- Check user-visible additions against `CHANGELOG.md`.
- If a rule was missing and caused rework, update the relevant context document instead of fixing code only.
