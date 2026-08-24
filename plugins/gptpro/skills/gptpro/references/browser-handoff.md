# Visible ChatGPT Pro handoff

This stage is attended browser work. Local scripts intentionally stop at verified artifacts and an approval receipt.

## Preferred path

1. If an official Chrome-control Skill is available, read it before browser actions and use its supported visible-session path. Otherwise let the user perform the manual steps.
2. Confirm the handoff phase is `approved` with `gptpro.py status`. Read `transport.resolved` and `outbound_paths`; these are the only approved browser payloads. `local_audit_archive_path` is never a default upload.
3. Open `https://chatgpt.com/` in the user's signed-in Chrome profile.
4. Start a new **general Chat**, not Work, a Project, a custom GPT, or an existing unrelated conversation.
5. Select the exact requested model and Pro/Intelligence setting recorded by `status`. If the controls are unavailable or ambiguous, stop for user direction; do not silently downgrade.
6. Perform exactly one approved transport:
   - `github`: activate the connected GitHub app/plugin, then paste the complete `prompt_path` content. Attach no local file. Confirm the visible prompt names the approved repository, immutable commit, optional PR, and selected paths. Follow [github-transport.md](github-transport.md).
   - `paste`: paste the complete `paste_payload_path` content into the message composer. Do not attach a file.
   - `text-file`: attach the exact `context_path`, then paste the exact `prompt_path` content into the message composer.
   - `mcp-read|mcp-research`: follow [web-mcp.md](web-mcp.md) and, for research, [mcp-research.md](mcp-research.md). Proceed only when package-specific approval is current, the official profile preflight passed, the foreground activation controller is still running, and `mcp-status` proves the exact approved package active after a successful control-plane poll. `doctor`, `/healthz`, or `/readyz` alone is insufficient. Never attach or upload the local ZIP.
7. Verify the requested model/setting, package ID, applicable context markers, and either the complete approved payload, exact Markdown attachment, pinned GitHub identity, or active MCP package are visibly present. Submit once.
8. After visible acceptance, record `mark-submitted`. If submission is ambiguous, do not record it and do not retry automatically.
9. Wait for completion without repeated prompt submission or page refresh. For long reasoning, use bounded waits and infrequent UI inspection. Stop on login loss, CAPTCHA, permission failure, rate limit, selector drift, navigation changes, or lost connection.
10. Capture the complete answer including both package-specific markers into a UTF-8 file and import it locally.

Browser control is not required to complete this stage. When credentials, OAuth/app scope, account choice, permissions, an OS file chooser, model controls, uncertain submission, or response export require a person, follow [human-takeover.md](human-takeover.md). Generate the checklist with `gptpro.py human-handoff` and resume from the user's visible observation. Do not describe a required human checkpoint as a failed consultation.

## Transport failure rule

Do not switch among `github`, `text-file`, `paste`, `mcp-read`, or `mcp-research`, or to ZIP after an app/upload/paste/Tunnel failure. A transport or Web MCP schema change alters the approved outbound artifact set and disclosure. Prepare a new handoff with the desired `--transport`, show its new hashes, and obtain a new approval.

## Approval and permissions

ChatGPT's Chrome integration normally asks before interacting with a new site. Use the narrowest site permission suitable for `chatgpt.com`. The `github` path may separately require the user to connect the GitHub app/plugin and approve repository scope. The `text-file` path may require enabling **Allow access to file URLs** for the Codex Chrome extension; direct `paste` avoids local-file upload permissions. For Web MCP, follow OpenAI's attended [ChatGPT MCP connection flow](https://developers.openai.com/plugins/deploy/connect-chatgpt) without automating Developer Mode or app/workspace authorization.

Never ask the user to choose global all-site access just to complete this handoff. Never enter credentials, solve CAPTCHAs, disable browser security, or read unrelated tabs/history.

## Manual fallback

If browser control is unavailable, run:

```bash
python3 <skill-dir>/scripts/gptpro.py human-handoff \
  --handoff-dir <dir> \
  --reason manual-transport
```

The generated checklist provides the user:

- resolved transport and `outbound_paths`
- `prompt_path` plus pinned GitHub identity, `paste_payload_path`, or `prompt_path` plus `context_path`
- requested model/Pro setting
- exact response markers

For an implemented transport, the user can create the Chat, paste or attach as specified, and report `sent`, `not-sent`, or `unknown`. For Web MCP, the user also confirms the intended Developer Mode app/workspace and the exact schema-specific tool catalog while the activation controller stays in the foreground. Record `mark-submitted` only for a visibly matching sent turn. If response extraction later needs a person, use `--reason response-export`. The same `approve`, `mark-submitted`, and `import-response` receipts still apply.

## Why there are no DOM selectors

ChatGPT UI labels and structure can change. Embedding selectors in a portable Skill would create silent model/setting drift and fragile submission behavior. The supported automation boundary is the official visible Chrome capability plus the machine-readable `status` payload.
