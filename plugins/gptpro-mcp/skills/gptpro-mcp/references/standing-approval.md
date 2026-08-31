# Machine-global bounded approval

`gptpro-standing-approval-v2` reduces repeated package prompts while retaining per-consultation manifests and receipts. It covers `all-local-git` only when transport, Desktop delivery, Tunnel profile hash, app, workspace, model, mode, path patterns, dirty policy, and budgets match exactly.

Selected untracked files, external evidence, supplements, secret findings, profile/app/workspace/model changes, or larger limits always require exact-package review. Profiles expire within 30 days and may be revoked for future matches.

A profile is created only from an exact Schema 4 package that the user already approved manually. Storing the profile does not activate a Tunnel or send a prompt.

The supported flow is `standing-approval-create --dry-run`, review, then
`standing-approval-create --confirm-standing-approval`. Inspect profiles with
`standing-approval-list`, use one on a prepared package with
`approve --standing-approval NAME`, and stop future matches with
`standing-approval-revoke --confirm-revocation`.

The store is machine-global and owner-only: directories use mode `0700` and
profile files use mode `0600`. The approval can authorize `mcp-research` for at
most 30일. It never covers external evidence or a legacy supplement, and it
never authorizes automatic Send or 자동 재전송.
