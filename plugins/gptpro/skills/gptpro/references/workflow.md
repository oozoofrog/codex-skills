# Workflow

## Consultation

```text
directed file selection
  -> path, tracked-file, UTF-8, and secret checks
  -> prompt.md + system-prompt.md + exact outbound.md
  -> package and outbound hash verification
  -> exact or bounded standing approval
  -> exact live model resolution
  -> durable submission_dispatching receipt
  -> one normal-Chat POST
  -> POST stream_handoff + signed WebSocket subscription
  -> recovered catchups + ordered delta + terminal done
  -> conditional exact current-branch proof when compact branch provenance is ambiguous
  -> raw response + deterministic wrapper
  -> independent Codex evaluation
```

`prepare` never sends. `consult` rechecks the exact package and approval immediately before authorizing the child process to POST. Once `submission_dispatching` exists, that package is never sent again automatically.

Packages are usable only with the exact gptpro runtime version that prepared them. After a version update, old packages are ignored: verification, approval, consultation, and response recovery reject a missing or different `runtime_version` with `PACKAGE_VERSION_UNSUPPORTED`. No migration, conversion, or deletion is performed. Start new consultations with newly prepared packages; never automatically resend a previously dispatched or uncertain request.

After successful POST headers, gptpro requires an SSE response and reads one valid raw `stream_handoff` within the initial 60-second stream boundary. It detects that control frame before decoding ordinary compact deltas, requests the signed WebSocket URL, and subscribes to the exact `conversation-*` topic from offset `0`. The runtime requires an authenticated subscription reply, processes any recovered catchups before live messages, validates conversation/turn identity and the parent stream-item chain, and decodes SSE deltas. Signed `done` proves transport completion only when final assistant text, message identity, and `recipient=all` are also present. The signed topic fails closed after 5 seconds without its first stream item or 30 seconds without later data.

No ChatGPT DOM selector is used. Conversation GET is conditional; the observed canary and larger review both required it, so no frequency claim is made. If a compact stream exposes a tool-role node before branch membership is known, or assistant/delta state begins before the signed handoff and continues inside it, the runtime waits for signed `done`, then polls only the already known conversation ID for at most 30 seconds and requires the deterministic user message, a zero-tool current branch, and the same assistant ID and visible text as the signed result. This authenticated GET is branch proof, not response collection: it cannot provide completion content, cannot change `completion_source=signed-stream-handoff-v1`, and never lists other conversations. Without signed completion, the candidate fails closed. A POST that ends without `stream_handoff` also fails closed instead of accepting direct completion. Protocol, identity, ordering, endpoint, branch-proof, and tool-route violations fail closed. Malformed JSON in any SSE data block rejects the complete batch, including when valid events occur before it.

If live collection ends after POST, recover the same package without sending:

```bash
python3 <skill-dir>/scripts/gptpro.py collect-response \
  --handoff-dir <package-directory> --json
```

This recovery command requires exactly one durable `submission_dispatching` boundary and at most one matching `submission_dispatched` event, then performs GET readback only. This includes the crash window where POST was authorized but the child ended before reporting its request ID. It is needed only when the `consult` process was interrupted or signed-stream collection failed. It may be retried while the response is pending because it cannot create another ChatGPT message.

The package contains no duplicate ZIP. `outbound.md` itself is the immutable disclosure artifact. It contains the task followed by sorted repository-file blocks, one selected Git diff block, and optional sorted supplement blocks. Canonical headers bind path or label, byte size, and SHA-256; UTF-8 bodies are unchanged.

## Approval

Exact approval binds one manifest, outbound, system prompt, model, normal-Chat mode, and Electron channel. A standing approval can cover later packages only within one repository, reviewed include/exclude or exact-path rules, tracked-file policy, supplement labels, modes, exact model, 256 KiB limit, channel, and expiry. Untracked files, new supplement labels, secrets, model changes, or wider paths require new approval.

```bash
python3 <skill-dir>/scripts/gptpro.py standing-approval-create \
  --handoff-dir <reviewed-package> --expires-hours 24 \
  --mode review --mode ask \
  --confirm-transmission --confirm-disclosure --json
```

Supplements use `--supplement LABEL=/absolute/path`. Only a bounded owner-controlled regular UTF-8 file is accepted; its original absolute path is not disclosed.

Follow-up questions use a fresh package. Conversation continuation is deliberately absent until first-turn delivery and capture are proven reliable across current Desktop stream variants.

## Independent validation

Before editing, Codex rereads current files, separates evidence from inference, reproduces material claims where practical, and runs proportional tests. `record-evaluation` records `accepted`, `partially-accepted`, or `rejected`; it does not claim a commit, push, release, or device test.
