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

Missing response evidence does not prove “not sent.” After `submission_dispatching`, any timeout, cancellation, response error, or protocol uncertainty forbids automatic resend. If the process was interrupted or live readback failed, run `collect-response`; it performs authenticated GET-only correlation and may be retried without a new transmission approval. If exact correlation cannot be proven, stop and inspect normal Chat. Pre-send capability failures may be retried only while the exact approval is still valid and disclosure has not changed.

Readback availability, correlation, and `UNEXPECTED_TOOL_ROUTE` failures fail closed. If `consult` fails after POST, report the submission as ambiguous and use `collect-response`, never `consult`, for that package.

Do not report tokens, cookies, credential values, traceback, raw request/conversation identifiers, unrelated renderer state, or another package path. The optional `last_stage` is one fixed content-free label, not proof that later stages did or did not occur.
