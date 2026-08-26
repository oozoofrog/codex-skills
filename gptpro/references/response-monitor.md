# Response completion monitor

Use this procedure after one approved prompt is visibly submitted from an empty new general Chat and `mark-submitted` records the `new-general-chat-empty-v1` contract plus exact canonical `https://chatgpt.com/` conversation URL. The monitor collects the existing response; it never authorizes another submission.

## Boundary

- Use a Codex app heartbeat attached to the same task. Do not create a daemon, cron workaround, separate Codex task, or background Python loop.
- Run every two minutes for at most 30 minutes and 15 executions. Completion, an attended blocker, cancellation, or expiry is terminal.
- Inspect only the recorded conversation URL. Never resend the prompt, create a replacement Chat, switch model/account/workspace/transport, or widen disclosure.
- The heartbeat may write only the normal response/import/evaluation artifacts and response-monitor receipt state. Repository edits remain governed by the original user request and advisory-validation rules.

## Create

1. Generate the read-only plan:

   ```bash
   python3 <skill-dir>/scripts/gptpro.py response-monitor-plan \
     --handoff-dir <dir> \
     --target-thread-id <current-codex-task-id>
   ```

   If the current task ID is not exposed, omit the option; the plan uses `current-thread`, and the Codex heartbeat creation call must omit its target so the app attaches it to the calling task.

2. If `action` is `reuse_existing`, do not create a duplicate. If it is `none`, report the recorded terminal result instead of restarting automatically.
3. For `create_heartbeat`, use the Codex app automation capability with the returned name, prompt, same-task destination, two-minute recurrence, 15-run cap, and 30-minute deadline. The prompt is user-visible. Do not translate it into raw cron or a detached project job.
4. After creation succeeds, record the exact automation ID and the target task ID returned by the app:

   ```bash
   python3 <skill-dir>/scripts/gptpro.py record-response-monitor-started \
     --handoff-dir <dir> \
     --automation-id <id> \
     --target-thread-id <id-or-current-thread> \
     --deadline <deadline-from-plan>
   ```

5. If heartbeat creation fails, record `creation_failed` with the planned target and deadline. If app creation succeeded but local recording fails, delete or pause that exact automation first, then record `creation_failed`; never leave an unbound recurring task running.

## Each heartbeat

Run `status` first. It contains the exact conversation URL, automation ID, package markers, phase, and deadline.

- If the phase is already `response_imported` or `evaluated`, delete or pause the exact heartbeat and record the matching terminal reason.
- If the response is still generating, make no external change and end the run. The next scheduled execution performs the next bounded observation.
- If one complete marked response is visible, save it without editing, import it, independently evaluate it, then delete or pause the automation and record `response_imported` or `evaluated`.
- On login, CAPTCHA, account/workspace ambiguity, missing conversation, truncated response, marker mismatch, or unsafe browser state, delete or pause the automation, record `blocked`, and report the exact attended action needed.
- At the deadline, delete or pause the automation and record `expired`. Never create a replacement automatically.

Record terminal cleanup with:

```bash
python3 <skill-dir>/scripts/gptpro.py record-response-monitor-stopped \
  --handoff-dir <dir> \
  --automation-id <id> \
  --reason response_imported
```

The stable reasons are `response_imported`, `evaluated`, `blocked`, `expired`, `cancelled`, and `creation_failed`. A generic retry flag is deliberately false: only collection of the existing response may repeat, while prompt resubmission is always forbidden.

## Recovery from another active Codex task

If the original task ended before its heartbeat was created, another active Codex task may use `send_message_to_thread` exactly once to wake it. The message must name the existing package, prohibit resubmission, and require inspection of the receipt-recorded conversation URL. This is a one-shot delivery mechanism, not a watcher; the resumed original task creates or reuses its own bounded heartbeat when the response is not yet complete.
