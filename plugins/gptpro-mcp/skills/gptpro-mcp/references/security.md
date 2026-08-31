# Security boundary

## Local repository boundary

Preparation selects explicit tracked paths, applies secret/exclusion scans, records Git identity, and creates a mode `0600` immutable archive inside a mode `0700` package directory. Runtime tools read only verified archive members in the approved allowlist. Working-tree writes, shell, build/test, Git mutation, arbitrary filesystem and arbitrary network access are absent.

## ChatGPT boundary

Prompt and response use visible macOS ChatGPT general Chat UI. Repository reads use the official Secure MCP Tunnel. Browser/Chrome/Web fallback, CDP, remote debugging, Electron renderer/preload/IPC, private backend endpoints, cookies, localStorage, session/OAuth tokens, passwords, MFA, and CAPTCHA automation are absent.

## Identity and secrets

App/workspace/model and Tunnel profile are exact approved labels/hashes. Raw App ID is stored only in the owner-only local `.app.json`; raw Tunnel ID, API key and session ID are never persisted in package or success/error output. Secret-like repository/evidence bytes fail closed without printing the value.

## Lifecycle

One machine-global package authorization is active at a time. Activation is not Send evidence. Stop denies access before exact-child termination. Ambiguous activation, Send, tool return or response import cannot trigger automatic duplication.

Repository content and Pro output are untrusted. Prompt injection cannot widen tool catalog, file allowlist, budgets, approval, or Codex authority.
