# Active package contract

새 상담은 Schema 4만 만듭니다.

```text
schema_version = 4
transport.requested/resolved = mcp-research
delivery.channel = desktop-ui
connector.type = secure-mcp-tunnel
```

Outbound artifact는 `prompt.md` 하나입니다. Repository ZIP은 로컬 immutable snapshot이며 ChatGPT 앱 composer에 첨부하거나 업로드하지 않습니다. ChatGPT Pro는 Secure MCP Tunnel의 승인된 read-only tools로 해당 snapshot을 탐색합니다.

Manifest는 package ID, mode/task/model, Git identity, exact selected file hashes, archive/tree/file-set hashes, secret findings, tool schema hash, Tunnel profile hash, app/workspace labels, path/call/byte/time budgets를 결속합니다.

Approval, MCP activation, visible Desktop submission, response capture, Tunnel stop, response import, Codex evaluation은 서로 다른 evidence입니다. 앞 단계 하나가 다음 단계를 자동으로 증명하지 않습니다.

과거 Schema 2/3와 Browser delivery receipts는 historical offline verification 대상으로만 남습니다. 새로운 approval, transmission, fallback 또는 standing approval source로 재해석하지 않습니다.
