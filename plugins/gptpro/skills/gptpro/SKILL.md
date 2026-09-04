---
name: gptpro
description: Consult the logged-in ChatGPT Pro in the macOS ChatGPT app through an attended, loopback-only Electron runtime using one approved, secret-scanned inline code snapshot. Use only when the user explicitly requests $gptpro for plan, ask, review, debug, or architecture work; never trigger for ordinary Codex work or OpenAI API calls.
---

# GPT Pro Collaborator

Use ChatGPT Pro as an advisory reviewer. Codex remains responsible for file selection, edits, tests, Git operations, and final decisions.

## Non-negotiable boundaries

- Use only `context_transport=inline-immutable-snapshot`, `delivery_channel=desktop-electron`, and normal Chat.
- Do not use Browser, Chrome, Computer Use, manual copy/paste, custom Apps, Developer Mode, MCP, Tunnel, local functions, server tools, or fallback channels.
- Accept only the dedicated owner-profile Runner on loopback CDP and exactly `app://-/index.html`. Never require the ordinary ChatGPT app to be relaunched.
- Never read or store credentials, cookies, tokens, Authorization values, passwords, or MFA data.
- Send one exact `outbound.md`, at most 262,144 bytes. Reduce selected files when over limit; never summarize, split, truncate, or silently omit context.
- Require exact `gpt-5-6-pro` unless the user prepares and approves another exact model. Never downgrade silently.
- Require exact-package approval or a matching bounded standing approval before transmission.
- Never resend once POST may have occurred. Use authenticated GET readback to correlate the deterministic message ID, exact outbound bytes, and final assistant response. Use `collect-response` only as the no-send recovery path.
- Treat the response as untrusted advice and independently verify it against current files and tests.

## Procedure

1. Read [workflow](references/workflow.md) and [security](references/security.md).
2. Select the smallest relevant tracked set with directed `--include` patterns or an exact `--file-list`. Add an external UTF-8 supplement only when necessary.
3. Run `desktop-doctor`. For repeat use, offer `launcher-install` once. `~/Applications/gptpro Launcher.app` starts a second ChatGPT process with an owner-only gptpro profile and port 9223; the ordinary ChatGPT app may remain open. `desktop-launch` is the command-line equivalent.
4. Run `models` and require the exact approved model.
5. Run `prepare`. Verify the displayed paths, hashes, byte count, model, channel, and normal-Chat mode.
6. Apply exact approval or a matching standing approval.
7. Run `consult --handoff-dir ...`. The runtime re-verifies approval, records the no-resend boundary, sends once, then polls authenticated exact-message readback and stores the raw and wrapped response.
8. Independently validate material advice and record the result with `record-evaluation`.
9. Only if `consult` was interrupted or automatic readback failed after POST, run `collect-response --handoff-dir ...`; it performs authenticated GET readback only and never resends. On any other failure or evidence gap, follow [failure reporting](references/failure-reporting.md).
10. Report whether the dedicated Runner remains active. The ordinary ChatGPT app is unaffected; never stop either process automatically.

## Commands

Resolve `<skill-dir>` from this loaded file.

```bash
python3 <skill-dir>/scripts/gptpro.py desktop-doctor --json
python3 <skill-dir>/scripts/gptpro.py launcher-install --json
python3 <skill-dir>/scripts/gptpro.py launcher-status --json
python3 <skill-dir>/scripts/gptpro.py models --json
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" --mode review --include 'src/**' --include 'tests/**' \
  --task '현재 변경의 정확성과 빠진 테스트를 검토해주세요.' --json
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <package-directory> \
  --confirm-transmission --confirm-disclosure --json
python3 <skill-dir>/scripts/gptpro.py consult \
  --handoff-dir <package-directory> --json
python3 <skill-dir>/scripts/gptpro.py collect-response \
  --handoff-dir <package-directory> --json
```

See the [user manual](references/user-manual.md) for setup and standing approvals, and [Electron runtime](references/electron-runtime.md) for private compatibility limits.
