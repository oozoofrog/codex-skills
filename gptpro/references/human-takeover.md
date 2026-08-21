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

Supported pre-submission reasons include `login`, `account-or-workspace`, `app-authorization`, `file-permission`, `file-selection`, `model-selection`, `captcha`, `site-approval`, `manual-transport`, and `submission-uncertain`. For `github`, `app-authorization` names the exact approved repository and commit, while `manual-transport` requires activating the visible GitHub app/plugin, pasting only `prompt.md`, and attaching no local file. For `mcp-read`, app/workspace/Tunnel selection is also human-owned, but a checklist cannot replace a missing local runtime or active package authorization. After submission, use `response-export` when a person must save the completed marked response.

The command verifies the package before printing instructions. Its JSON includes the package phase, approved model, transport, exact outbound paths and hashes, human steps, expected return evidence, and retry rule. It does not write state, append a receipt event, authorize transmission, or prove that an action occurred.

## Return contract

Ask the user to report only the observed result needed to resume:

```text
HUMAN_HANDOFF_RESULT
package_id: <id>
reason: <reason>
result: completed | declined | blocked | sent | not-sent | unknown
observed_model: <visible label, when relevant>
thread_url: <visible chatgpt.com conversation URL, when sent>
details: <short visible evidence or blocker>
```

Treat this report as an attended observation, not as permission for unrelated actions.

## Resume rules

- For login, permission, app, file-selection, or model-selection help, reacquire the same visible page and re-check the required state before continuing.
- For a completed `manual-transport`, run `mark-submitted` only when the person reports `sent` and a matching user turn is visibly present.
- For `submission-uncertain`, never send again automatically. Record submission only after a matching package-specific user turn is visible. Keep the phase `approved` for `not-sent` or `unknown` and ask before any new attempt.
- For `response-export`, import only the saved UTF-8 file containing both exact response markers.
- A declined or blocked human action ends the current browser attempt without changing the approved package. Report the blocker and preserve the handoff for a later explicit decision.

## Why this is safer

Some browser operations are intentionally user-owned, and browser UI evidence can be weaker than local file or receipt evidence. A narrow human checkpoint avoids credential handling, over-broad permission grants, blind retries, transport substitution, and false success claims while preserving the same approved bytes and audit chain.
