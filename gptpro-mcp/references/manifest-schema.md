# Schema 4 manifest

New preparation supports only:

```text
schema_version = 4
transport = mcp-research
delivery.channel = desktop-ui
connector.type = secure-mcp-tunnel
```

The single outbound artifact is `prompt.md`. The local ZIP holds an immutable repository snapshot and internal manifest; it is not uploaded or attached in ChatGPT. The approved App reads that snapshot through bounded MCP tools.

Manifest integrity binds Git identity, selected paths/sizes/SHA-256 values, archive/tree/file-set hashes, secret findings, tool schema, profile/Tunnel binding hashes, app/workspace/model labels, evidence artifacts, analysis ledger contract, and all TTL/call/match/line/byte limits.

Approval binds both context transport and Desktop delivery. Activation, visible Send, response capture, stop, import, and evaluation remain separate receipt events.

Historical Schema 2/3 and `delivery.channel=browser` receipts remain verifier input only. New preparation, approval, activation, or transmission never selects them.
