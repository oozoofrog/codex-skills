# Component compatibility

The Desktop-only base and read-only companion use `gptpro-component-capabilities-v1` plus an owner-only `.gptpro-components.json` descriptor.

| Base | Companion | Result |
|---|---|---|
| `gptpro` 0.3.x | `gptpro-mcp` 0.2.x | Supported Desktop UI + Schema 4 read-only MCP workflow. |
| `gptpro` 0.3.x | absent or hash-mismatched | Fail closed with `GPTPRO_MCP_COMPONENT_REQUIRED` or `GPTPRO_MCP_COMPONENT_CHANGED`. |
| older integrated install | `gptpro-mcp` 0.2.x | Migration/recovery only until transition evidence is terminal. |
| Browser-first base 0.2.x | any | Historical install only; no new Browser consultation is supported. |

Default `manage_skills.py install gptpro` installs/updates the companion first and records exact absolute entrypoints and tree hashes. New operational commands never search `PATH`, `~/.codex/skills`, or arbitrary checkouts. An explicit base/companion path is accepted only for repository tests.

Every mismatch is **fail-closed**: it stops before MCP activation or Desktop submission.

Legacy `capabilities`, verification, observation-only diagnostics, exact stop/recovery, audit/trace verification and transition evidence remain available for repair.
