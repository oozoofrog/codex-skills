# CLAUDE.md

## Repository Commands
- Validate one skill: `python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-dir>`
- Audit the repository context tree: `python3 hierarchical-context-architecture/scripts/verify_context_tree.py --root .`
- Syntax-check repo shell scripts: `bash -n scripts/*.sh`
- Syntax-check repo Python scripts: `python3 -m py_compile scripts/*.py hierarchical-context-architecture/scripts/verify_context_tree.py`

## Repository Architecture
- Top-level non-hidden directories are usually self-contained skill packages.
- Each skill package should keep user-facing triggers in `SKILL.md`, UI metadata in its `agents/` directory, and long detail in `references/`.
- `docs/` stores release and operator-facing repository documentation.
- `scripts/` stores repository sync automation and launchd helpers.
- `.system/` mirrors upstream system skills; treat edits there as deliberate sync or patch work.

## Working Rules
- Keep `SKILL.md` concise and move bulky detail into `references/`.
- When adding or updating a skill, keep `SKILL.md`, its UI metadata file, `README.md`, and `CHANGELOG.md` in sync.
- Validate every changed skill before reporting success.
- If scripts change, run syntax checks or a safe temp-directory repro.
- Add a local `CONTEXT.md` only when a directory has rules or resource relationships that are no longer obvious from its `SKILL.md` alone.

## Context Tree Entry Points
- Agent collaboration rules: [AGENTS.md](./AGENTS.md)
- Repository docs and release flow: [docs/CONTEXT.md](./docs/CONTEXT.md)
- Repo automation scripts: [scripts/CONTEXT.md](./scripts/CONTEXT.md)
- Mirrored system skills: [.system/CONTEXT.md](./.system/CONTEXT.md)
- Context architecture skill internals: [hierarchical-context-architecture/CONTEXT.md](./hierarchical-context-architecture/CONTEXT.md)

## Validation Expectations
- Do not report success without running at least one relevant validator.
- For context-doc changes, run `verify_context_tree.py`.
- For script changes, prefer syntax checks first and temp-directory tests second.
- If validation fails, report the exact command and failure instead of masking it.
