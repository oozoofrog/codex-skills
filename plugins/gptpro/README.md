# GPT Pro Collaborator Plugin

This directory packages the top-level [`gptpro`](../../gptpro/) Skill as a skills-only Codex Plugin.

The canonical standalone Skill remains at `gptpro/` so Codex's bundled `$skill-installer` and existing clone-based installations keep working. `skills/gptpro/` is a distribution mirror. Update both copies together; `scripts/tests/test_plugin_distribution.py` rejects drift.

Installation instructions live in [`docs/plugin-installation.md`](../../docs/plugin-installation.md).
