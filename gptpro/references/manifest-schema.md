# Artifact schema

The current `schema_version` is `1`.

## `manifest.json`

Important fields:

- `package_id`, `created_at`, `mode`, `task`, `destination`, `requested_model`
- `git`: repository root, HEAD SHA, branch, clean flag, and dirty paths
- `selection`: whole or directed mode plus include/exclude/file-list criteria
- `files`: included workspace-relative path, size, SHA-256, and archive path
- `excluded`: path and non-secret reason
- `security_findings`: path, detector, optional line, and exclusion action; never a secret value
- `totals`: candidate, included, excluded, omitted, and byte counts
- `response_markers`: package-specific begin/end lines
- `artifacts`: generated filenames
- `hashes`: packaged tree, prompt, archive, and internal-manifest SHA-256 values

The external manifest is authoritative for local verification. The archive contains `_gptpro/file-manifest.json`, which covers Git/selection identity and every `repo/...` member but intentionally omits the archive's self-hash.

## `state.json`

Records the current lifecycle phase and phase-specific metadata. Artifact hashes copied into the state bind later approval and response events to the prepared package.

## `receipt.json`

Contains an ordered event list. Each event includes `sequence`, timestamp, type, data, previous-event hash, and its own SHA-256. `verify` checks the chain and package identity.

## Response artifacts

- `raw_response.md`: exact imported marked response.
- `response.md`: content between the package-specific markers.
- `evaluation.json`: Codex verdict, summary, evidence strings, optional applied Git SHA, and imported-response hash.

All JSON is UTF-8, sorted, indented, and newline-terminated. Hash values are lowercase SHA-256 hex strings.
