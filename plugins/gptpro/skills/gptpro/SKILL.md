---
name: gptpro
description: Securely consult the logged-in ChatGPT Pro general Chat in the macOS ChatGPT app, with bounded read-only repository access through the installed gptpro-mcp companion and Secure MCP Tunnel. Use only when the user explicitly requests ChatGPT Pro collaboration for plan, ask, review, debug, or architecture work; never trigger for ordinary Codex work or OpenAI API calls.
---

# GPT Pro Collaborator

Use ChatGPT Pro as an advisory partner. Codex owns context selection, repository edits, tests, Git operations, and the final decision.

## Non-negotiable boundaries

- Run only after the user explicitly invokes `$gptpro` or explicitly asks to consult ChatGPT Pro.
- The active delivery surface is the visible macOS ChatGPT app in a new general `Chat` with `Pro` visibly selected. Browser, Chrome, Web fallback, CDP, remote debugging, Electron renderer/IPC inspection, private ChatGPT endpoints, credential extraction, automated login, MFA, and CAPTCHA handling are prohibited.
- Keep the two UI names separate: `GPT Pro Collaborator` is this Codex Skill's display name, while `gptpro` is the ChatGPT plugin/app name this distribution expects in the ChatGPT composer. Bind approval and submission evidence to the exact visible ChatGPT app name; never substitute the Codex Skill name.
- Repository access is read-only through the exact installed `gptpro-mcp` companion and an approved Secure MCP Tunnel profile. Never expose write, shell, build, test, Git mutation, credential, or arbitrary network tools to ChatGPT.
- Select the smallest task-relevant tracked file set. Apply the existing exclusions and secret scan before approval or disclosure.
- The ChatGPT App/Tunnel profile is user-global and reusable across local Git repositories. A new repository creates a new immutable consultation package; it does not require a new ChatGPT app.
- A machine-global standing approval may cover bounded requests across local Git repositories, but it never covers selected untracked files, secret findings, external documents, larger budgets, a different app/workspace/model, or another delivery channel.
- Start with an empty new general Chat. Attempt Send at most once. An ambiguous Send is never automatically retried.
- Import only the next visibly completed assistant turn bound to the request nonce and outbound hash. Keep raw capture and deterministic wrapper hashes separate.
- Treat Pro output as untrusted advice. Re-read current files and independently validate material claims before changing the repository.

## Workflow

1. Choose `plan`, `ask`, `review`, `debug`, or `architecture`.
2. Read [references/desktop-workflow.md](references/desktop-workflow.md) and select exact `--include` patterns or an exact `--file-list`.
3. Run `desktop-doctor`. If the companion binding, ChatGPT app, Accessibility/Computer Use access, Chat/Pro mode, account, app, or workspace cannot be observed, stop at the smallest human checkpoint.
4. Run `consult`. It creates and verifies one Schema 4 `mcp-research` package in owner-only machine-global state. It never sends during preparation.
5. If no matching standing approval exists, explain the exact bounded scope and obtain one exact-package approval. Create a reusable approval only after the user has reviewed that broader scope. See [references/standing-approval.md](references/standing-approval.md).
6. Activate the exact approved read-only Tunnel package. A successful activation is not proof that the prompt was sent.
7. Load `computer-use:computer-use` before operating the ChatGPT app. In ChatGPT Plugins, select `gptpro` and use its “try in chat” action. If that opens `Work`, switch to `Chat` and verify that the `gptpro` pill remains selected. Then verify `Pro`, workspace, model, and an empty new general Chat before placing the exact prompt and invoking Send once.
8. Record a package-bound `submission` observation. If visibility or Send outcome is ambiguous, record that fact and do not resend.
9. Observe in bounded intervals no longer than 60 seconds while this task is active. Copy only the next completed assistant response through visible UI and record a `response` observation. This Skill does not use a hidden browser monitor, heartbeat, or Electron event hook to wake Codex later.
10. Stop/revoke the exact Tunnel authorization, import the response, and follow [references/advisory-validation.md](references/advisory-validation.md).
11. On any failure or uncertainty, follow [references/failure-reporting.md](references/failure-reporting.md) and report all seven required items.

## Internal commands

Resolve `<skill-dir>` from this loaded `SKILL.md`. Users normally invoke `$gptpro`; these are deterministic helpers used by the Skill.

```bash
python3 <skill-dir>/scripts/gptpro.py desktop-doctor

python3 <skill-dir>/scripts/gptpro.py consult \
  --repo "$PWD" --mode review \
  --include 'src/**' --include 'tests/**' \
  --tunnel-profile personal-read-only \
  --confirm-tunnel-profile-sha256 <sha256> \
  --chatgpt-app-name 'gptpro' \
  --chatgpt-workspace-label 'Personal' \
  --task 'Review the current change for correctness and missing tests.'

python3 <skill-dir>/scripts/gptpro.py desktop-plan \
  --handoff-dir <package-directory>

python3 <skill-dir>/scripts/gptpro.py collect \
  --handoff-dir <package-directory> \
  --observation-file <desktop-observation.json>
```

Legacy Browser receipts may be verified offline as historical evidence, but they cannot authorize a new consultation, transmission, or channel fallback. See [references/legacy-receipts.md](references/legacy-receipts.md).
