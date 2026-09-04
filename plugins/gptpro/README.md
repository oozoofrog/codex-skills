# GPT Pro Collaborator Plugin

This directory packages the top-level [`gptpro`](../../gptpro/) v0.6 isolated Electron Runner and inline-snapshot collaboration Skill as a skills-only Codex Plugin.

The canonical standalone Skill remains at `gptpro/` so Codex's bundled `$skill-installer` and existing clone-based installations keep working. `skills/gptpro/` is a byte-and-mode exact distribution mirror. The package has no custom ChatGPT App, Browser, Computer Use, MCP, Secure MCP Tunnel, local-function, or server-tool dependency. Its optional `~/Applications/gptpro Launcher.app` starts a second installed ChatGPT process with a dedicated owner-only profile and port 9223, leaving the ordinary app untouched. Update both copies together; `scripts/tests/test_plugin_distribution.py` rejects drift.

Installation instructions live in [`docs/plugin-installation.md`](../../docs/plugin-installation.md).
