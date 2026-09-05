# Failure reporting

Every failure or evidence gap reports:

1. failed stage and operation;
2. expected result and actual observation;
3. sanitized stable error code and explanation;
4. proven transmission, approval, repository, package-artifact, and Git-metadata effects;
5. current package and Electron state;
6. whether automatic retry is allowed;
7. one exact next action and whether new approval is required.

Use the observation-only command:

```bash
python3 <skill-dir>/scripts/gptpro.py --error-format json \
  diagnostic-status --handoff-dir <package-directory> --json
```

Missing response evidence does not prove “not sent.” After `submission_dispatching`, any timeout, cancellation, handoff error, WebSocket close, malformed stream, or protocol uncertainty forbids automatic resend. If the child ended before emitting `submitted`, the durable dispatch boundary still permits only `collect-response`, never another `consult`. `collect-response` performs authenticated GET-only correlation and may be retried without a new transmission approval. If exact correlation cannot be proven, stop and inspect normal Chat. Pre-send capability failures may be retried only while the exact approval is still valid and disclosure has not changed.

Handoff identity, SSE content type, initial POST body/frame, subscription recovery, signed-topic initial/idle deadline, stream ordering, current-branch proof, readback correlation, and `UNEXPECTED_TOOL_ROUTE` failures fail closed. A proof-required state without signed `done`, a current-branch tool node, a 30-second proof timeout, or a signed-vs-GET assistant ID/text mismatch is ambiguous. After dispatch authorization, child retry metadata is not authoritative: the parent records ambiguous state with GET-only recovery guidance. If `consult` fails after POST, use `collect-response`, never `consult`, for that package.

Do not report tokens, cookies, credential values, traceback, raw request/conversation identifiers, unrelated renderer state, or another package path. The optional `last_stage` is one fixed content-free label, not proof that later stages did or did not occur.

Recovery is bounded, not guaranteed for arbitrary historical conversations. When no conversation ID survived in memory, the current collector considers the 20 most recently updated conversations and filters by the dispatch time window. A matching conversation outside that page cannot be found by repeatedly retrying the same scan. Report this limitation on repeated collection timeouts; do not claim the response is absent, resend, or silently widen account-history access. Stop and inspect the exact conversation in normal Chat. Pagination or explicit conversation selection requires a separately reviewed recovery change.
