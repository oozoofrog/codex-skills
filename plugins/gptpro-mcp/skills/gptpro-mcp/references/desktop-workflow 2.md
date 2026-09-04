# Desktop orchestration boundary

`gptpro-mcp` does not automate ChatGPT UI. It provides the package, read-only tools, authorization, audit, and Tunnel lifecycle used by the base `$gptpro` Skill.

```text
$gptpro base
  ├─ visible macOS ChatGPT app UI through Computer Use
  └─ exact installed gptpro-mcp
       ├─ Schema 4 package and immutable archive
       ├─ read-only MCP tools
       ├─ Secure MCP Tunnel child
       └─ audit, expiry, stop, recovery
```

New package delivery is always `desktop-ui`. The companion never opens a Browser, Chrome, or ChatGPT Web page; never uses CDP or Electron internals; and never extracts credentials or sessions.

App/Tunnel setup is account-level and reusable. Package scope is consultation-level. Starting a second repository therefore reuses the same verified profile but creates a new exact file/hash/budget authorization.

The Tunnel supervisor owns only the exact child process and authorization lifecycle. It does not observe assistant text, create a heartbeat, or wake a Codex task after the task has ended.
