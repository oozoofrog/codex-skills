# Artifact schema

The verifier dispatches explicit schema versions. Existing GitHub, paste, and text-file packages use schema 2. Explicit `mcp-read` uses schema 3. Explicit `mcp-research` uses schema 4. `auto` never resolves to either Web MCP schema, and approval from one schema is never reinterpreted as another.

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
- `artifacts`: generated prompt, structured context, optional paste payload, local audit archive, state, and receipt filenames
- `hashes`: packaged tree, prompt, context, optional paste payload, local archive, and internal-manifest SHA-256 values

The external manifest is authoritative for local verification. `context-<id>.md` carries package/context markers, sanitized Git and selection metadata, and every selected UTF-8 file. It omits the local absolute repository root and local file-list path.

For `github`, the only outbound artifact is `prompt.md`. `transport.github` records canonical repository/commit URLs, immutable commit SHA, verified remote/ref, optional PR identity, exact allowed paths, selected-tree hash, and preparation-time remote verification. For `paste`, the only outbound artifact is `paste-<id>.md`, which deterministically combines the prompt and structured context. For `text-file`, the outbound artifacts are `prompt.md` and `context-<id>.md`. The ZIP contains `_gptpro/file-manifest.json` and exact source bytes for local integrity/audit, but is not in the default outbound list.

## `state.json`

Records the current lifecycle phase and phase-specific metadata. Artifact hashes copied into the state bind later approval and response events to the prepared package. Approval and submission events also record the resolved transport and exact outbound artifact metadata. GitHub submissions additionally record the approved/observed repository identity; imported GitHub responses store the parsed attestation.

## `receipt.json`

Contains an ordered event list. Each event includes `sequence`, timestamp, type, data, previous-event hash, and its own SHA-256. `verify` checks the chain and package identity.

## Read-only human handoff output

`status` includes a derived `human_takeover` object with availability and valid reason names for the current phase. `human-handoff` prints a derived checklist containing approved outbound paths and hashes, human steps, expected return evidence, and retry rules. Neither output is an artifact or receipt event, and generating it does not change `state.json`.

## Response artifacts

- `raw_response.md`: exact imported marked response.
- `response.md`: content between the package-specific markers.
- `evaluation.json`: Codex verdict, summary, evidence strings, optional applied Git SHA, and imported-response hash.

All JSON is UTF-8, sorted, indented, and newline-terminated. Hash values are lowercase SHA-256 hex strings.

## Schema 3 `mcp-read`

Schema 3 changes approval meaning, so a schema-2 approval is never reinterpreted. Its only outbound text artifact is `prompt.md`; `context-<id>.md` and paste payloads are not created. The ZIP remains local and stores immutable repository members without compression for bounded on-demand reading by the active runtime.

Additional manifest fields bind:

- `delivery.channel = browser` separately from `transport.resolved = mcp-read`;
- `connector.type = secure-mcp-tunnel`, a safe runtime alias, visible app/workspace labels, protocol and tool-schema hashes, and a package-specific hash of the transient Tunnel ID;
- `repository`: public display identity, Git SHA, packaged tree hash, and dirty summary without a local absolute root;
- `mcp_disclosure`: exact path/size/file-hash allowlist, canonical file-set hash, potential file/byte totals, static three-tool list, bounded limits, approval expiry, and audit filename;
- `hashes.approval_basis_sha256`: the canonical maximum-disclosure approval contract;
- `hashes.manifest_basis_sha256`: a self-hash basis that excludes only its own two derived basis hashes.

The raw Tunnel ID, its `env:` or `file:` reference, API keys, credentials, and absolute repository/file-list paths are not persisted in the manifest, package state, receipt, audit, or prompt. Schema-3 approval requires both `--confirm-transmission` and `--confirm-mcp-disclosure` and copies the approval basis into state and receipt.

## Schema 4 `mcp-research`

Schema 4 is additive to schema 3. It retains prompt-only browser delivery, immutable ZIP verification, package-specific Tunnel binding, maximum-disclosure approval, one-active-package runtime state, disclosure audit, protocol trace and existing receipt semantics. It replaces the three-tool catalog with the exact seven-tool, fully read-only research catalog documented in [mcp-research.md](mcp-research.md).

Additional archive members and manifest bindings are:

- `_gptpro/research/workspace-index.json`: canonical prepare-time directory/file metadata derived exactly from approved members;
- `_gptpro/research/diff.json`: canonical prepare-time pinned-HEAD-SHA-to-snapshot entries, including the exact `research.diff.base_sha`, file hashes, and either bounded diff text/hash or a stable content-withheld reason;
- `_gptpro/evidence/<artifact-id>.txt`: explicit strict-UTF-8 evidence members named only by safe IDs;
- `research.workspace_index`, `research.diff`, `research.evidence`, `research.evidence_set_sha256` and matching artifact hashes;
- schema-4 limits for workspace depth, search-query/range counts, evidence members/bytes, diff bytes, analysis events/event bytes/ledger bytes;
- `analysis_collaboration`: `read-only-context-notes-v1`, ledger filename, `mcp_write_tools: false`, visible-Chat Pro response channel, and the exact-byte Codex context-note approval requirement.

The manifest never persists source evidence absolute paths. Approval requires `--confirm-transmission`, `--confirm-mcp-disclosure`, and `--confirm-analysis-ledger`. The research session's default disclosure budget is an explicit fixed approved maximum rather than the selected source byte count because workspace metadata, diff/evidence, ledger pages and repeated physical calls are independently budgeted.

## Schema-3/4 session and audit records

Activation does not change the consultation phase. Instead, `state.mcp_session` binds the package to the active session hash, activation time, expiry, approved Tunnel alias/identity, the exact doctor-observed profile hash, the explicitly selected official `tunnel-client` binary SHA-256, the bundled MCP runtime-tree SHA-256, the exact MCP target hash, audit filename/header hash, and activation receipt event. The matching `mcp_activated` receipt repeats these non-secret hashes, and the user-global record keeps the same bindings immutable for the session. The user-global state may contain the local absolute handoff directory so the stdio server can locate the package; repository-facing artifacts do not expose that path to ChatGPT.

`receipt.json` may append Web MCP auxiliary events such as activation, activation failure, failed-activation exact-child stop, expiry, revocation, normal runtime stop, or explicit recovery. Each auxiliary event must preserve `phase_before == phase_after`, bind the applicable session evidence, and continue the same receipt chain. It never substitutes for `submitted`, `response_imported`, or `evaluated`. `mcp_activation_stopped` is additive: it follows exactly one matching `mcp_activation_failed`, records the observed child return code and forced-termination flag, and binds the final trace artifact hash/length without creating `mcp_stopped` or a disclosure-audit footer. Older completed schema-3 receipts remain verifiable.

`mcp-audit.jsonl` is a separate high-frequency hash chain. Its header binds the package, approved manifest/archive/file set/tool schema, session hash, limits, and approval receipt. Tool records bind the tool, approved relative paths/ranges, file hashes, returned bytes, and cumulative counters without storing full bodies, raw search queries, or credentials. A footer/terminal summary binds final counters and audit head. Content is released only after its disclosure record has been durably committed.

Schema 4 also creates owner-only `mcp-analysis.jsonl`. Its header binds the package/session/manifest/approval/tool schema/limits. The chain contains only separately approved Codex `context_note` events; Pro can read them through `gptpro_analysis_status` but cannot append through MCP. `analysis_note_approved` receipts bind the note ID, exact UTF-8 byte count/hash and expected ledger head before the unchanged note is appended. A receipt-only crash is replayable, while an event without exactly one matching receipt is invalid. Revocation or expiry closes the ledger with the same first durable audit reason, and terminal package/runtime evidence binds `analysis_head_sha256`, final sequence, event count, closed state, and `analysis_close_reason`. Analysis closure is not exact-child stop evidence or proof of network/model consumption.

The user-global authorization record stores one active package at a time and contains only local control bindings and hashes. Activation failure first changes this exact binding to `faulted` and may retain a stable `activation_failure_code` before package evidence is read or written. It may also record a positive exact-child return code/forced-termination observation. When package integrity or the handoff directory itself is unavailable, this machine-global record is the only stop evidence and explicitly says that no package receipt was written. If the same exact package is later restored and verifies, a retry may monotonically change the matching stop's receipt flag from false to true and bind that one receipt hash; it cannot change the child result, reason, forced flag, or replace an existing hash. A terminal record is not archived/replaced while its exact controller lease remains live or while child-stop status is unproven. The only non-receipt clearance is additive `orphan_tunnel_termination_manually_confirmed: true` plus its timestamp, written after an explicit attended process review; it never sets either exact-child field or creates a package receipt. The raw per-session capability is environment-only, while Tunnel/API credentials stay in the official client's user-controlled environment or profile mechanism. See [web-mcp.md](web-mcp.md).
