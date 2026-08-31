# Companion workflow

```text
capability handshake
  -> profile check/preflight
  -> Schema 4 prepare/verify
  -> exact or standing approval
  -> mcp-activate
  -> visible Desktop Send handled by $gptpro
  -> audited read-only calls
  -> mcp-stop and audit verification
  -> Desktop response import/evaluation handled by $gptpro
```

`mcp-activate` never sends the prompt. `mcp-stop` never imports the visible answer. Each boundary has separate evidence.

New commands accept only `mcp-research` plus `desktop-ui`. Browser/Chrome/Web fallback, GitHub transport, paste, file upload, CDP and Electron internals are not selectable.

If activation is ambiguous, use `diagnostic-status` before any explicit recovery. Do not auto-start another Tunnel child. If visible Send is ambiguous, do not resend.
