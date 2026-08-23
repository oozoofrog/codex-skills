# Privacy-preserving Tunnel request correlation

This is an opt-in diagnostic for one dedicated, already-approved `mcp-read` activation. Its narrow purpose is to determine whether repeated identical local `tools/call` executions came from one repeated outer Tunnel command ID or from distinct outer command IDs. It is not part of ordinary consultation, does not establish why an upper layer dispatched requests, and must run before any future write-tool design is considered.

## Private compatibility boundary

The implementation target is official `openai/tunnel-client` v0.0.12. That build exposes a structured in-memory log ring at `/api/logs` on its admin listener and attaches `request_id`, `rpc_request_id`, and sometimes `cmd_request_id` to terminal dispatcher records. These names, messages, and the admin route are private implementation details, not stable OpenAI APIs. A later client change must produce `unavailable` or `inconclusive`, never a guessed mapping.

The Skill reimplements the bounded reader with Python's standard library; it does not vendor or copy Tunnel source. Reference behavior can be inspected in the official [protocol description](https://github.com/openai/tunnel-client/blob/v0.0.12/docs/protocol.md), [structured logger](https://github.com/openai/tunnel-client/blob/v0.0.12/pkg/log/logger.go), [admin log buffer](https://github.com/openai/tunnel-client/blob/v0.0.12/pkg/adminui/log_buffer.go), and [admin JSON handler](https://github.com/openai/tunnel-client/blob/v0.0.12/pkg/adminui/ui.go).

## Explicit run

Use a new package because one schema-3 package has one activation attempt. Review and approve its normal prompt and maximum disclosure contract first, then add the diagnostic flag before activation starts:

```bash
python3 <skill-dir>/scripts/gptpro.py mcp-activate \
  --handoff-dir .gptpro/handoffs/<package-id> \
  --tunnel-profile gptpro-web \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --confirm-workspace-binding \
  --diagnose-request-correlation \
  --json
```

This flag does not replace package-specific transmission/MCP-disclosure approval. It does not send a prompt, click ChatGPT controls, expand the approved file set, or authorize another delivery channel.

## Data flow

1. Normal activation safety checks and exact-child ownership still apply.
2. The selected child uses `info` for the official private in-memory ring. File logging stays `/dev/null`, stdout/stderr stay discarded, raw HTTP logging stays disabled, and no TCP admin listener is opened.
3. `mcp-stop` revokes repository authorization first. While the exact child and its private Unix socket still exist, the foreground controller reads at most 2,000 events and 4 MiB from `/api/logs`.
4. In memory, only allowlisted terminal dispatcher events are selected. Identifiers are type/size checked and converted with domain-separated HMAC-SHA-256 under a per-session ephemeral key. Unrelated attributes and the raw JSON are discarded.
5. The exact child is then terminated and normal stop/trace evidence is finalized.
6. Only if the admin ring begins at sequence 1 and its terminal event count/order matches the complete receipt-bound protocol trace does gptpro align `tools_call` entries with the existing disclosure audit by JSON-RPC request-ID hash.

Maximum concurrency remains one, so successful terminal events and local `response_flushed` events have a deterministic order for this compatibility target. Any error, truncation, count mismatch, ID mismatch, invalid trace, or unavailable audit makes the result non-authoritative.

## Output semantics

The foreground command emits the sanitized result under `mcp_stopped.request_correlation_diagnostic`:

- `correlated`: the complete windows and existing hashes aligned;
- `inconclusive`: sanitized input existed but completeness or alignment was not proven;
- `unavailable`: the private endpoint, format, or capture failed safely.

Repeated tool-and-argument groups are classified as:

- `same_outer_request_repeated`: every physical copy has the same session-scoped outer-ID HMAC;
- `distinct_outer_requests`: every copy has a different outer-ID HMAC;
- `mixed_outer_requests`: both patterns occur.

These are equality classifications, not an attribution of intent to ChatGPT Pro, its planner, the connector, or Tunnel service. No deduplication occurs. Every physical call still consumes call budget, and every committed returned copy still consumes disclosure bytes.

## Retention and limitations

The Skill does not persist the raw admin response, raw IDs, raw payloads, Tunnel/account identifiers, credentials, or the ephemeral HMAC key. The sanitized correlation object is printed only in terminal JSON; it is not added to state, receipts, the protocol trace, or the disclosure audit. Shell redirection or external terminal capture is an operator-controlled retention decision.

The diagnostic is deliberately not receipt evidence: it depends on a private, in-memory compatibility surface and is collected before child termination. It cannot unlock write, patch, shell, Git, or repository-mutation tools. A later write-capability proposal still needs a separate threat model, authorization contract, idempotency design, and review.
