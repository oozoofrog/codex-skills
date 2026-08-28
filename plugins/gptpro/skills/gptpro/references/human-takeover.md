# Human takeover

Human participation is a supported part of this attended workflow. It is not a failed automation run and does not relax approval, provenance, or duplicate-submission rules.

## When to hand control to the user

Pause browser automation when the next action requires the account owner's judgment or when visible state cannot be proved reliably:

- sign-in, MFA, CAPTCHA, account switching, or workspace selection;
- GitHub or another ChatGPT app authorization and repository-scope choice;
- ChatGPT Developer Mode, Secure MCP Tunnel app, or exact workspace selection;
- Chrome site permission or local-file access permission;
- an operating-system file chooser or exact attachment selection;
- ambiguous model or Pro/reasoning controls;
- an unavailable browser bridge or selector drift;
- an interrupted Send whose outcome cannot be proved;
- response copying or download when automated extraction is incomplete.

Do not ask the user to reveal credentials, codes, cookies, tokens, or unrelated browser content. Do not bypass an OAuth, CAPTCHA, browser, or operating-system boundary with hidden network calls or profile scraping.

## Generate the exact checklist

After package approval, generate a read-only, phase-aware checklist instead of improvising steps:

```bash
python3 <skill-dir>/scripts/gptpro.py human-handoff \
  --handoff-dir <dir> \
  --reason manual-transport \
  --details "Chrome file chooser did not open."
```

Supported pre-submission reasons include `login`, `account-or-workspace`, `app-authorization`, `file-permission`, `file-selection`, `model-selection`, `captcha`, `site-approval`, `manual-transport`, and `submission-uncertain`. For `github`, `app-authorization` names the exact approved repository and commit, while `manual-transport` requires activating the visible GitHub app/plugin, pasting only `prompt.md`, and attaching no local file. Every `manual-transport` checklist creates an empty new general Chat, confirms zero prior user or assistant turns, and excludes existing conversations, Work, Projects, and custom GPTs. For Web MCP, the person also creates/selects the Tunnel/key, enables Developer Mode, confirms the exact ChatGPT account/workspace/app, reviews the schema-specific tool catalog, and visibly submits the approved prompt. The checklist cannot substitute for an exact package approval receipt (manual or valid standing-profile match), an active local authorization, a successful control-plane poll, or schema-4 reply approval. After submission, use `response-export` when a person must save the completed marked response.

The command verifies the package before printing instructions. Its JSON includes the package phase, approved model, transport, exact outbound paths and hashes, human steps, expected return evidence, and retry rule. It does not write state, append a receipt event, authorize transmission, or prove that an action occurred.

## Return contract

Ask the user to report only the observed result needed to resume:

```text
HUMAN_HANDOFF_RESULT
package_id: <id>
reason: <reason>
result: completed | declined | blocked | sent | not-sent | unknown
observed_model: <visible label, when relevant>
new_general_chat_empty_before_send: yes | no | unknown
thread_url: <visible chatgpt.com conversation URL, when sent>
details: <short visible evidence or blocker>
```

Treat this report as an attended observation, not as permission for unrelated actions.

## Resume rules

- For login, permission, app, file-selection, or model-selection help, reacquire the same visible page and re-check the required state before continuing.
- For a completed `manual-transport`, run `mark-submitted --confirm-new-general-chat --thread-url <canonical-url>` only when the person reports `sent`, confirms the Chat was empty immediately before Send, and a matching user turn is visibly present. A `no` or `unknown` new-Chat result cannot become a submitted receipt.
- For `mcp-read|mcp-research`, verify the exact package remains active before Send. Keep the foreground activation controller running through response completion, then revoke/stop it. A user confirmation of Developer Mode or app selection is not proof that the Tunnel or tool calls worked. For research, never publish a Codex context note merely because the package was approved; use the separate exact-byte note gate, and do not call local publication network delivery.
- For `submission-uncertain`, never send again automatically. Record submission only after a matching package-specific user turn is visible. Keep the phase `approved` for `not-sent` or `unknown` and ask before any new attempt.
- For `response-export`, open only the exact conversation URL stored by `mark-submitted` when available and import only the saved UTF-8 file containing both exact response markers. `automatic_collection_retry_allowed` applies only to checking/copying that existing response; `automatic_prompt_resend_allowed` and the legacy generic retry flag remain false.
- For a response that may outlive the current turn, follow [response-monitor.md](response-monitor.md). Its same-task heartbeat is bounded and terminal; a different active task may send one recovery message, but that message is not a recurring watcher or permission to resubmit.
- A declined or blocked human action ends the current browser attempt without changing the approved package. Report the blocker and preserve the handoff for a later explicit decision.

## Why this is safer

Some browser operations are intentionally user-owned, and browser UI evidence can be weaker than local file or receipt evidence. A narrow human checkpoint avoids credential handling, over-broad permission grants, blind retries, transport substitution, and false success claims while preserving the same approved bytes and audit chain.
