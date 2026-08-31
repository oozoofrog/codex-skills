# Secure MCP Tunnel lifecycle

The official Tunnel carries JSON-RPC between ChatGPT's approved App and the local read-only MCP server over an outbound connection. It is not the prompt/response delivery channel; visible ChatGPT Desktop UI owns that step.

## Setup

Use an owner-only profile containing the Tunnel identity and exact client entrypoint/hash. Profile list/check/preflight are secretless and do not resolve credentials or start the client. Profile creation/refresh is attended and never auto-downloads, upgrades, or downgrades the Tunnel client.

```bash
python3 <skill-dir>/scripts/gptpro.py mcp-profile-list --json
python3 <skill-dir>/scripts/gptpro.py preflight \
  --repo "$PWD" --transport mcp-research --json
```

The profile's raw Tunnel ID/API key is used only where the official client requires it. Package, receipt, audit, terminal success output, and Desktop binding retain non-secret hashes and safe aliases only.

## Activation and stop

Activation requires an approved exact package, matching profile hash, compatible base handshake, workspace confirmation, tool schema hash, and bounded TTL/call/byte limits. Only one package is active in machine-global runtime state.

Stop denies authorization first, then requests exact child termination and closes audit/trace evidence. If the result is ambiguous, do not start a duplicate activation. Use observation-only diagnostics before explicit recovery.

General compatibility uses public capability probing. Private request-correlation remains pinned to its documented supported build and is optional.
