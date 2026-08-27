# Web MCP repository research

`mcp-research` is the explicit schema-4 transport for a longer ChatGPT Pro repository consultation. It packages one immutable, secret-scanned repository snapshot plus bounded evidence, a workspace index, and a diff from the exact prepared Git SHA. It is experimental, macOS-only in this phase, requires Python 3.11 or newer, and is never selected by `auto`.

This design follows the current ChatGPT Pro custom-MCP boundary: tools exposed to Pro are read/fetch only. It is not ChatGPT Desktop/CDP automation, an OpenAI API client, a model-provider replacement, or a write-capable MCP. ChatGPT remains advisory in visible general Chat; Codex alone may edit the repository, run commands/tests, or make Git changes. See the [official Developer mode documentation](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt).

## Data and authority flow

```text
selected repository files + explicit evidence
  -> secret/exclusion scan and stable Git worktree capture
  -> immutable local ZIP + workspace index + pinned-SHA diff
  -> manifest hashes and package-specific approval
  -> foreground Secure MCP Tunnel session
  -> seven bounded read-only tools
  -> visible ChatGPT response
  -> normal response import
  -> Codex independent verification before implementation
```

Only `prompt.md` is pasted into ChatGPT. The ZIP is not uploaded. The local runtime verifies it without extraction and returns only results allowed by the approved static catalog and budgets.

## Static seven-tool catalog

| Tool | Capability | Important boundary |
|---|---|---|
| `gptpro_package_info` | package, snapshot, path/hash, budget, evidence and note summary | no repository body by default |
| `gptpro_workspace_map` | page through the prepare-time directory/file index | no live filesystem traversal |
| `gptpro_repo_read` | read multiple ordered line ranges from one approved UTF-8 file | exact approved ZIP member only |
| `gptpro_repo_search` | bounded literal multi-query search with `any|all` and safe include/exclude globs | no regex, shell, Git, or arbitrary path |
| `gptpro_repo_diff` | page through the prepare-time pinned-SHA-to-snapshot diff | includes selected deletions; never invokes Git during the session |
| `gptpro_artifact_read` | read an explicitly packaged UTF-8 test/build/diagnostic artifact | approved artifact ID only |
| `gptpro_analysis_status` | read bounded pages of separately approved Codex context notes | no MCP mutation; an audited return is not proof the model consumed it |

All seven tools advertise `readOnlyHint: true`. The catalog contains no write-file, local-ledger write, shell, Git, browser, credential, network, arbitrary-filesystem, or local-function relay. Repository and evidence text are untrusted data, not instructions.

The static catalog is also the execution allowlist. After a session is normally ready, a well-formed tool name not in that catalog is dispatched only to the governance rejection boundary. A successfully synced zero-content rejection consumes one approved physical-call slot, stores a reserved label with a hash binding of the requested name, and returns JSON-RPC `-32602` with stable data code `MCP_INVALID_ARGUMENT`. The raw unadvertised name is not retained, no fallback tool is selected, and the next advertised call continues at the next durable counter. A pre-append audit failure does not consume the in-memory counter. If the exact record may already be present, the runtime reconciles only verifiable cumulative counters, latches the session, and best-effort faults/closes persistent authorization; the operator must stop or recover rather than guess or resend. Malformed or oversized names remain protocol-level denials and do not open the request-scoped compatibility path.

## Prepare and approve

Use the narrowest useful repository selection. Evidence and supplemental documents must be explicit current-owner, single-link, non-group/world-writable UTF-8 regular files and are secret-scanned before packaging. Secure capture requires supported POSIX current-user and descriptor-relative/no-follow file-open capabilities; symlinks, hard links, FIFOs and other non-regular files fail closed. A supplement is an evidence artifact with an additional purpose label; it does not enter repository read/search paths.

```bash
python3 <skill-dir>/scripts/gptpro.py preflight \
  --repo /absolute/path/to/repo \
  --transport mcp-research \
  --json

python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo /absolute/path/to/repo \
  --mode architecture \
  --transport mcp-research \
  --include 'src/**' \
  --include 'tests/**' \
  --evidence-file unit-tests=/absolute/path/to/test-output.txt \
  --supplement requirements=/absolute/path/to/requirements.md \
  --tunnel-profile <selected_profile> \
  --confirm-tunnel-profile-sha256 <selected_profile_sha256> \
  --chatgpt-app-name 'GPT Pro Repository Research' \
  --chatgpt-workspace-label 'Approved Workspace' \
  --task 'Analyze the approved implementation, tests, and prepared diff.'

python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json
```

Preparation fails closed if the Git index/worktree changes during schema-4 snapshot capture. Tracked deletions selected by the disclosure scope are represented explicitly in the prepared diff. HEAD blobs and internal research artifacts are size-checked before expensive reads or package publication. `--supplement` shares safe-label, count, per-file, total-byte, and per-line readability limits with `--evidence-file`; a single UTF-8 line cannot exceed the package's `max_read_content_bytes` (currently 98,304 bytes by default). Option source locators are not persisted in gptpro artifacts, but can remain in shell/process/tool history; they are rejected if reflected into outbound metadata after case-folded Unicode normalization, and captured bytes are never refreshed in place.

Before approval, show the user:

- package ID, Git SHA, dirty summary, selected path/hash set, and maximum disclosure;
- evidence and supplemental artifact IDs/sizes/hashes and workspace-index/diff hashes;
- all seven exact tool names and every call/byte/result/time limit;
- app/workspace labels, expiry, transport `mcp-research`, and delivery `browser`;
- that Pro can only read the approved immutable snapshot and context-note ledger;
- that every later Codex context note needs a new exact-byte publication approval.

Approval requires all three gates:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission \
  --confirm-mcp-disclosure \
  --confirm-analysis-ledger
```

General permission to use `$gptpro`, a previous package approval, or approval of `mcp-read` does not approve this package.

## Activate and consult

Use the secretless `mcp-probe`, profile check, exact binary-hash confirmation, official doctor preflight, foreground `mcp-activate`, visible ChatGPT app authorization, attended prompt send, cooperative stop, and recovery boundaries documented in [workflow.md](workflow.md) and [web-mcp.md](web-mcp.md).

Create an empty new ChatGPT general Chat for this package and confirm zero prior user or assistant turns before selecting the approved app/model and sending once. Do not use an existing conversation, Work, Project, or custom GPT. After the matching turn and canonical `/c/<id>` URL are visible, record them with `mark-submitted --confirm-new-general-chat`; never reuse a conversation URL for another package.

The prepared manifest's schema/profile/tool hash must match exactly. Never expose both schema-3 and schema-4 catalogs under one package, and never silently fall back to another transport after approval. Every durably audited physical call and every committed returned byte consumes budget; the runtime performs no deduplication. For each schema-3/4 committed success, audit schema 2 and `complete_model_visible_result_v1` meter the canonical UTF-8 size of the complete model-visible MCP tool result, including structured metadata, hashes, cursors, disclosure counters, and the fixed text envelope. Tool-specific `content_bytes` or `result_bytes` values remain diagnostic sub-counts rather than the approval boundary. Audit schema 1 is verification-only and is reported as `legacy_tool_body_estimate`, never as current full-result evidence.

Ask Pro to start with `gptpro_package_info`, narrow exploration with `gptpro_workspace_map`, read named supplemental artifacts only through `gptpro_artifact_read`, and cite paths, hashes, ranges, evidence IDs, or diff entries in its visible Chat response. `gptpro_repo_read` and `gptpro_repo_search` cannot see external supplements. Pro cannot persist findings through an MCP write tool. Import the completed visible response through the existing package-marker workflow.

## Codex context-note ledger

The owner-only `mcp-analysis.jsonl` ledger is created at activation. Its header binds the exact package, approval receipt, manifest, session, tool schema, and limits. It contains only user-approved Codex `context_note` events in a canonical sequence-numbered SHA-256 chain. Pro can read them only through `gptpro_analysis_status`.

Inspect or export the verified local ledger:

```bash
python3 <skill-dir>/scripts/gptpro.py analysis-status --handoff-dir <dir> --json
python3 <skill-dir>/scripts/gptpro.py analysis-export \
  --handoff-dir <dir> \
  --format markdown \
  --output /absolute/private/path/analysis.md
```

Stage a note locally:

```bash
chmod 600 /absolute/private/path/note.txt
python3 <skill-dir>/scripts/gptpro.py analysis-note-prepare \
  --handoff-dir <dir> \
  --message-file /absolute/private/path/note.txt
```

The result reports `note_id`, exact UTF-8 byte count, message SHA-256, current ledger-head SHA-256, and stage path. Show the exact note and all reported values to the user. After a fresh note-specific approval, pass those exact reviewed values:

```bash
python3 <skill-dir>/scripts/gptpro.py analysis-note-approve \
  --handoff-dir <dir> \
  --note-id <codex-note-id> \
  --message-sha256 <reviewed-message-sha256> \
  --message-bytes <reviewed-byte-count> \
  --expected-head-sha256 <reviewed-ledger-head> \
  --approved-by user \
  --confirm-publication
```

The approval receipt is committed before the unchanged note bytes are appended. Receipt-before-append crashes are safely replayable. A changed stage, stale head, missing/forged receipt, duplicate note ID, secret-like body, over-budget note, or post-closure append fails closed.

`ledger_published: true` means the local note is available to the read-only MCP tool. It does **not** mean a network transmission occurred. Only a later disclosure-audit record for `gptpro_analysis_status` proves that the runtime returned a page containing the note; it still does not prove ChatGPT consumed or reasoned over it.

## Stop, import, and evaluate

Revocation or expiry closes both the disclosure audit and context-note ledger. The first durably written audit close reason remains authoritative across crash recovery and is bound to the analysis ledger, machine-global state, package state, and receipt. An already `expired` session stays `expired`; a later stop cannot rewrite it as `revoked` and invalidate response evidence.

Ledger closure is not proof that the Tunnel child stopped. Exact-child stop evidence remains separate and is required, along with a normally terminal session, before schema-4 response import. After import, context notes are no longer accepted.

Pro findings are advisory. Codex must reopen current repository files, account for drift from the packaged Git/tree identity, reproduce or test material claims, and record `accepted`, `partially-accepted`, or `rejected` evidence before applying advice.

## Explicit non-goals

- ChatGPT Desktop/CDP or arbitrary browser automation
- automatic ChatGPT login, account switching, CAPTCHA handling, or Send retries
- any MCP mutation, repository write, patch, shell/build/test execution, Git operation, or arbitrary filesystem access
- network fetch, generic MCP proxy, or local tool relay
- automatic model/transport fallback, deduplication, or unattended operation
