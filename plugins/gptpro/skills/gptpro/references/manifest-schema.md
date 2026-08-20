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
- `transport`: requested/resolved transport, auto threshold, candidate paste size, and the exact outbound artifact list
- `artifacts`: generated prompt, structured context, optional paste payload, local audit archive, state, and receipt filenames
- `hashes`: packaged tree, prompt, context, optional paste payload, local archive, and internal-manifest SHA-256 values

The external manifest is authoritative for local verification. `context-<id>.md` carries package/context markers, sanitized Git and selection metadata, and every selected UTF-8 file. It omits the local absolute repository root and local file-list path.

For `paste`, the only outbound artifact is `paste-<id>.md`, which deterministically combines the prompt and structured context. For `text-file`, the outbound artifacts are `prompt.md` and `context-<id>.md`. The ZIP contains `_gptpro/file-manifest.json` and exact source bytes for local integrity/audit, but is not in the default outbound list.

## `state.json`

Records the current lifecycle phase and phase-specific metadata. Artifact hashes copied into the state bind later approval and response events to the prepared package. Approval and submission events also record the resolved transport and exact outbound artifact metadata.

## `receipt.json`

Contains an ordered event list. Each event includes `sequence`, timestamp, type, data, previous-event hash, and its own SHA-256. `verify` checks the chain and package identity.

## Read-only human handoff output

`status` includes a derived `human_takeover` object with availability and valid reason names for the current phase. `human-handoff` prints a derived checklist containing approved outbound paths and hashes, human steps, expected return evidence, and retry rules. Neither output is an artifact or receipt event, and generating it does not change `state.json`.

## Response artifacts

- `raw_response.md`: exact imported marked response.
- `response.md`: content between the package-specific markers.
- `evaluation.json`: Codex verdict, summary, evidence strings, optional applied Git SHA, and imported-response hash.

All JSON is UTF-8, sorted, indented, and newline-terminated. Hash values are lowercase SHA-256 hex strings.
