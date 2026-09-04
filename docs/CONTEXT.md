# CONTEXT.md

## Scope

- `docs/` stores operator-facing repository documentation.
- Follow the repository-wide rules in [../AGENTS.md](../AGENTS.md).

## Key files

- [selective-installation.md](./selective-installation.md): single-package list, dry-run, atomic install, and legacy MCP retirement.
- [gptpro-source-inventory.md](./gptpro-source-inventory.md): Electron reference provenance, license decision, and clean-room boundary.

## Local rules

- Keep commands runnable from the repository root.
- Keep installation behavior aligned with `scripts/manage_skills.py` and the root README.
- The normal gptpro path must use its isolated Runner profile and port. It must not require the ordinary ChatGPT app to be quit, relaunched with debugging flags, or have its profile copied.
