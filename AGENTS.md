# AGENTS.md

## Collaboration Rules
- Use the `skill-creator` workflow when creating or materially updating skills.
- Keep `gptplease/SKILL.md` frontmatter limited to `name` and `description`.
- Keep trigger language aligned across the standalone Skill, Plugin mirror, UI metadata, and `README.md`.
- Prefer `references/` for long guidance and keep top-level instructions lean.
- Keep `gptplease/` and `plugins/gptplease/skills/gptplease/` byte-identical.

## Output Contract
- List changed files or directories.
- List validation commands actually executed.
- State any remaining manual follow-up or risk.

## Review Rules
- Apply checks to the changed skill/package and affected distribution surfaces. Run relevant checks once; repeat only after related changes, failures, or new evidence.
- When adding, renaming, or removing a Plugin, update the expected marketplace inventory in `scripts/tests/test_plugin_distribution.py` and run the repository distribution tests. Preserve unrelated in-progress entries and files.
- Keep gptplease Plugin `interface.defaultPrompt` to 1–3 entries, each at most 128 characters and containing `$gptplease`, as enforced by `scripts/tests/test_plugin_distribution.py`.
- Check trigger wording consistency between both `SKILL.md` copies, both UI metadata files, and `README.md`.
- Check local links and path references for breakage, and user-visible additions against `CHANGELOG.md`.
- If a rule was missing and caused rework, update the relevant context document instead of fixing code only.
- For Chat/Work changes, verify the selected surface and actual UI model/reasoning before Send. Chat Pro, a Pro plan badge, and Work Max/Ultra are distinct. Keep automatic model/effort policy in `gptplease/references/model-selection.md`; explicit settings override it, and live availability is surface-specific.
- For file-delivery validation, distinguish actual attachment from path/text delivery; correlate the final assistant turn and compare original/retrieved files when a supported read provides them.
- Keep live UI evidence, server-internal model claims, installed/enabled state, and fresh-session skill exposure separate. Do not claim the removed runtime's scan, approval, signed-stream, or receipt guarantees.
- Retired consultation packages and login profiles are user data. Do not migrate, resend, or delete them when renaming or removing a skill.
