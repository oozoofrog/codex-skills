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
  -> authenticated exact-message response polling
  -> raw response + deterministic wrapper
  -> independent Codex evaluation
```

`prepare` never sends. `consult` rechecks the exact package and approval immediately before authorizing the child process to POST. Once `submission_dispatching` exists, that package is never sent again automatically.

After successful POST headers, gptpro polls authenticated conversation GETs while the original reader remains open. The returned conversation must contain the deterministic message ID, the exact approved outbound text, one successful final assistant message, and no tool route. Exact GET correlation supplies both completion and integrity evidence; no ChatGPT DOM selector is used. After completion is proven, gptpro releases the original reader. Protocol, correlation, and tool-route violations fail closed.

If live collection ends after POST, recover the same package without sending:

```bash
python3 <skill-dir>/scripts/gptpro.py collect-response \
  --handoff-dir <package-directory> --json
```

This recovery command requires durable dispatch evidence and performs GET readback only. It is needed only when the `consult` process was interrupted or live readback failed. It may be retried while the response is pending because it cannot create another ChatGPT message.

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
