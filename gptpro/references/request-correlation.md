# Privacy-preserving Tunnel request correlation

This is an opt-in diagnostic for one dedicated, already-approved `mcp-read` activation. Its narrow purpose is to determine whether repeated identical local `tools/call` executions came from one repeated outer Tunnel command ID or from distinct outer command IDs. It is not part of ordinary consultation, does not establish why an upper layer dispatched requests, and must run before any future write-tool design is considered.

## Private compatibility boundary

The implementation target is the exact official build `0.0.12+881c9a8fed7cccbe6607cd419863bbca506b8215 (git sha: 881c9a8fed7cccbe6607cd419863bbca506b8215)`. That build exposes a structured in-memory log ring at `/api/logs` on its admin listener and attaches `request_id`, `rpc_request_id`, and sometimes `cmd_request_id` to terminal dispatcher records. These names, messages, levels, components, attributes, and the admin route are private implementation details, not stable OpenAI APIs.

`mcp-probe` reports `request_correlation_contract_supported` separately from the ordinary public-flow capability result. A different client version may remain usable for normal `mcp-read`, but the diagnostic fails with `REQUEST_CORRELATION_UNSUPPORTED_VERSION`; it never guesses that a later private contract is compatible. The approved package still binds the exact selected binary SHA-256, so the version string is not a replacement for binary identity review.

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
3. `mcp-stop` revokes repository authorization first. While the exact child and its private Unix socket still exist, the foreground controller verifies the connected Unix peer with macOS `LOCAL_PEERPID`, reads at most 2,000 events and 4 MiB from `/api/logs`, and enforces one wall-clock deadline across connect, headers, and body. A slow-drip response cannot postpone exact-child termination indefinitely.
4. In memory, only the pinned message/component/level/attribute shapes are selected. The whole ring sequence must be contiguous from 1. Identifiers are type/size checked and converted with domain-separated HMAC-SHA-256 under a per-session ephemeral key. Unrelated attributes and the raw JSON are discarded.
5. The exact child is then terminated and normal stop/trace evidence is finalized.
6. Only forwarded records may be correlated. Any terminal transport/upstream/downstream error is `REQUEST_CORRELATION_TERMINAL_ERROR_PRESENT`. Only if the complete ring and its forwarded event count/order match a closed, post-stop receipt-bound protocol trace does gptpro align `tools_call` entries with the existing disclosure audit by an internal JSON-RPC request-ID hash. A valid but open prefix is `REQUEST_CORRELATION_TRACE_OPEN`, not successful correlation.

Maximum concurrency remains one, so successful terminal events and local `response_flushed` events have a deterministic order for this compatibility target. A late response after the snapshot changes the final trace count and therefore becomes `inconclusive`; an error event can never balance it. Zero audited tool calls is also `REQUEST_CORRELATION_NO_TOOL_EVENTS`, not proof that no repeated tools existed. Any timeout, peer ambiguity, sequence gap, contract mismatch, truncation, count mismatch, ID mismatch, invalid trace, or unavailable audit remains non-authoritative.

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

Terminal output contains session-scoped outer/JSON-RPC/connector HMACs and a session-local `argument_group_ordinal`. The stable unkeyed JSON-RPC and argument hashes used to join the already-existing local audit are removed before output. In particular, the diagnostic does not add a printed stable digest from which a low-entropy numeric JSON-RPC ID can be recovered by dictionary search.

## Retention and limitations

The diagnostic does not persist the raw admin response, raw IDs, raw payloads, Tunnel/account identifiers, credentials, ephemeral HMAC key, or its sanitized correlation object. The object is printed only in terminal JSON; it is not added to state, receipts, the protocol trace, or the disclosure audit. Separately, the pre-existing owner-only `mcp-audit.jsonl` retains unkeyed JSON-RPC request-ID and argument hashes for integrity and joining. Low-entropy IDs and common argument objects can be guessed from those local hashes, so keep the handoff directory private. Shell redirection or external terminal capture is an operator-controlled retention decision.

The diagnostic is deliberately not receipt evidence: it depends on a private, in-memory compatibility surface and is collected before child termination. It cannot unlock write, patch, shell, Git, or repository-mutation tools. A later write-capability proposal still needs a separate threat model, authorization contract, idempotency design, and review.
