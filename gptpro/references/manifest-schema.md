# Artifact schema

The current `schema_version` is `2`.

## `manifest.json`

Important fields:

- `package_id`, `created_at`, `mode`, `task`, `destination`, `requested_model`
- `git`: repository root, HEAD SHA, branch, clean flag, and dirty paths
- `selection`: whole or directed mode plus include/exclude/file-list criteria
- `files`: included workspace-relative path, size, SHA-256, and local-audit archive path
- `excluded`: path and non-secret reason
- `security_findings`: path, detector, optional line, and exclusion action; never a secret value
- `totals`: candidate, included, excluded, omitted, and byte counts
- `response_markers`: package-specific begin/end lines
- `transport`: requested/resolved transport, auto threshold, candidate paste size, exact outbound artifact list, and optional GitHub identity
- `delivery`: approved execution channel (`browser`, `manual`, or `desktop-cdp`) and channel-specific security policy
- `artifacts`: generated prompt, structured context, optional paste payload, local audit archive, state, and receipt filenames
- `hashes`: packaged tree, prompt, context, optional paste payload, local archive, and internal-manifest SHA-256 values

The external manifest is authoritative for local verification. `context-<id>.md` carries package/context markers, sanitized Git and selection metadata, and every selected UTF-8 file. It omits the local absolute repository root and local file-list path.

For `github`, the only outbound artifact is `prompt.md`. `transport.github` records canonical repository/commit URLs, immutable commit SHA, verified remote/ref, optional PR identity, exact allowed paths, selected-tree hash, and preparation-time remote verification. For `paste`, the only outbound artifact is `paste-<id>.md`, which deterministically combines the prompt and structured context. For `text-file`, the outbound artifacts are `prompt.md` and `context-<id>.md`. The ZIP contains `_gptpro/file-manifest.json` and exact source bytes for local integrity/audit, but is not in the default outbound list.

Transport answers how repository context is disclosed. Delivery answers which local/user channel sends it. These fields are independent approval inputs and are never silently reinterpreted. Desktop phase 1 rejects `text-file` because it has no attachment operation. A schema-2 record created before the `delivery` field remains verifiable as a legacy receipt, but it cannot receive a new approval or submission transition; prepare a new package instead.

## `state.json`

Records the current lifecycle phase and phase-specific metadata. Artifact hashes copied into the state bind later approval and response events to the prepared package. Approval and submission events record the resolved transport, delivery channel, and exact outbound artifact metadata. GitHub submissions additionally record the approved/observed repository identity; imported GitHub responses store the parsed attestation.

A Desktop submission additionally records the live backend model, requested/observed effort, conversation/message identifiers when available, `local_function_signatures_count: 0`, trusted transport completion, the completion signal, observed assistant-message evidence/status, and the result/raw/wrapper artifact hashes. These values are admitted only after `gptpro.py` validates the completion evidence and recomputes the approved manifest and outbound-message hashes plus the deterministic wrapper bytes.

## `receipt.json`

Contains an ordered event list. Each event includes `sequence`, timestamp, type, data, previous-event hash, and its own SHA-256. `verify` checks the chain and package identity.

Lifecycle event types remain `prepared`, `approved`, `submitted`, `response_imported`, and `evaluated`. Desktop delivery may add an auxiliary `desktop-model-resolved` event while phase remains `approved`; it binds the manifest hash, human-facing requested intent, dynamic catalog source, exact backend model id, optional effort, confirmer, and timestamp. `verify` requires state to match the latest such event and the latest lifecycle event to match `state.phase`.

## Read-only human handoff output

`status` includes a derived `human_takeover` object with availability and valid reason names for the current phase. `human-handoff` prints a derived checklist containing approved outbound paths and hashes, human steps, expected return evidence, and retry rules. Neither output is an artifact or receipt event, and generating it does not change `state.json`.

## Response artifacts

- `raw_response.md`: exact imported marked response.
- `response.md`: content between the package-specific markers.
- `evaluation.json`: Codex verdict, summary, evidence strings, optional applied Git SHA, and imported-response hash.

Desktop delivery first writes `desktop-response.raw.md` (exact captured assistant body), `desktop-response.md` (runtime-marked wrapper), and `desktop-result.json` (capture receipt). Import then preserves the wrapper as `raw_response.md` and the marker-stripped body as `response.md`. The two raw names describe different integrity stages and are intentionally both retained.

All JSON is UTF-8, sorted, indented, and newline-terminated. Hash values are lowercase SHA-256 hex strings.
