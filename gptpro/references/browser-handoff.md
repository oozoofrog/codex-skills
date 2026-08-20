# Visible ChatGPT Pro handoff

This stage is attended browser work. Local scripts intentionally stop at verified artifacts and an approval receipt.

## Preferred path

1. If an official Chrome-control Skill is available, read it before browser actions and use its supported visible-session path. Otherwise let the user perform the manual steps.
2. Confirm the handoff phase is `approved` with `gptpro.py status`.
3. Open `https://chatgpt.com/` in the user's signed-in Chrome profile.
4. Start a new **general Chat**, not Work, a Project, a custom GPT, or an existing unrelated conversation.
5. Select the exact requested model and Pro/Intelligence setting recorded by `status`. If the controls are unavailable or ambiguous, stop for user direction; do not silently downgrade.
6. Attach the exact absolute `archive_path` and paste the exact `prompt_path` content.
7. Verify the attachment name, requested model/setting, and prompt are visibly present. Submit once.
8. After visible acceptance, record `mark-submitted`. If submission is ambiguous, do not record it and do not retry automatically.
9. Wait for completion without repeated prompt submission or page refresh. For long reasoning, use bounded waits and infrequent UI inspection. Stop on login loss, CAPTCHA, permission failure, rate limit, selector drift, navigation changes, or lost connection.
10. Capture the complete answer including both package-specific markers into a UTF-8 file and import it locally.

## Approval and permissions

ChatGPT's Chrome integration normally asks before interacting with a new site. Use the narrowest site permission suitable for `chatgpt.com`. File upload may require enabling file-URL access for the Chrome extension and an upload permission in ChatGPT/Codex Computer Use settings.

Never ask the user to choose global all-site access just to complete this handoff. Never enter credentials, solve CAPTCHAs, disable browser security, or read unrelated tabs/history.

## Manual fallback

If browser control is unavailable, provide the user:

- `prompt_path`
- `archive_path`
- requested model/Pro setting
- exact response markers

The user can create the Chat, attach, paste, and return the saved response. The same `approve`, `mark-submitted`, and `import-response` receipts still apply.

## Why there are no DOM selectors

ChatGPT UI labels and structure can change. Embedding selectors in a portable Skill would create silent model/setting drift and fragile submission behavior. The supported automation boundary is the official visible Chrome capability plus the machine-readable `status` payload.
