# Workflow reference

## Lifecycle

The supported state sequence is:

```text
prepared -> approved -> submitted -> response_imported -> evaluated
```

`verify` is read-only and may run at any phase. Every mutating transition first verifies the existing manifest, prompt, context, optional paste payload, local archive, state identity, and receipt hash chain.

Schema-1 ZIP-first handoffs are immutable legacy receipts. Do not silently reinterpret their approval as text-transmission approval; prepare and approve a schema-2 handoff instead. Schema 3 is reserved for explicit `mcp-read` maximum-disclosure approval and is never selected by `auto`; see [web-mcp.md](web-mcp.md).

## First-use environment

Preview setup before the first handoff in a repository:

```bash
python3 <skill-dir>/scripts/gptpro.py init --repo "$PWD"
```

Preview is read-only. It reports the output directory, ignore scope and target, effective existing ignore rule, warnings, and planned actions. The default `local` scope uses `.git/info/exclude`, keeping the setting local to the clone and out of tracked files. Show the preview and obtain approval before applying it:

```bash
python3 <skill-dir>/scripts/gptpro.py init --repo "$PWD" --apply
```

Initialization is idempotent. If `ready` is true and `actions` is empty, do not request or perform another mutation. Use `--ignore-scope repository` only after the user explicitly chooses a `.gitignore` edit. `--ignore-scope none` prepares the directory without hiding it from Git. A custom `--output-root` outside the repository needs no ignore entry.

## Prepare

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode debug \
  --transport auto \
  --task "Explain the intermittent timeout and propose discriminating checks." \
  --include "src/**" \
  --include "tests/**" \
  --exclude "tests/fixtures/large/**"
```

Use `--file-list selected-files.txt` for exact workspace-relative paths. Blank lines and `#` comments are ignored. `--include` and `--file-list` may be combined; a file matching either source is selected. Explicit exclusions still win.

Useful safeguards:

- `--require-clean`: fail if the Git worktree is dirty.
- `--max-files`: cap the number of included files.
- `--max-bytes`: cap total uncompressed bytes.
- `--max-file-bytes`: exclude oversized individual files.
- `--dry-run`: scan and summarize without writing a package.
- `--requested-model`: record a user-approved alternative when the default visible ChatGPT Pro selection is not appropriate.
- `--transport auto|github|paste|text-file`: choose the browser handoff. `auto` is the GitHub-first default.
- `--github-remote`: choose the GitHub remote verified by `auto` or `github`; default `origin`.
- `--github-pr-url`: pin an optional GitHub PR whose remote head ref must equal current HEAD. A mismatch fails even under `auto`.
- `--max-paste-bytes`: set the conservative fallback threshold when GitHub-first `auto` is unavailable; the default 128 KiB is Skill policy, not a published ChatGPT limit.

Preparation records both `git.head_sha` and a hash of the actual packaged file set. `auto` first attempts `github`; it succeeds only when every selected byte matches HEAD and that SHA is advertised by the chosen github.com remote. Otherwise it records the reason and resolves to `paste` or `text-file`. Explicit `github` never falls back. A dirty text package is not represented as the HEAD commit; dirty paths and the package tree hash remain explicit. Only valid UTF-8 files enter the text context. The generated ZIP remains local audit evidence and is not a default Pro upload. Read [github-transport.md](github-transport.md) for the remote and response-attestation contract.

When an in-repository output root is not ignored, `prepare` adds a warning pointing to `init`; it does not change Git configuration automatically.

For a deliberate Web MCP package, use `--transport mcp-read` plus `--tunnel-id-ref env:NAME` or an absolute owner-only mode-0600 `file:` reference, the intended app/workspace labels, and the smallest directed file set. It creates schema 3, a prompt-only outbound list, and a local immutable ZIP. It never uploads the ZIP and never makes MCP an `auto` fallback. The raw Tunnel ID/reference is not written to gptpro package/runtime/receipt/audit artifacts; the official attended initializer does store the ID in its owner-only user profile. Approval and activation remain separate actions.

## Verify and inspect

```bash
python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json
```

`status --json` is the machine-readable bridge between local preparation and any visible browser controller. It reports the resolved transport, exact absolute `outbound_paths`, destination, requested model, context/response markers, current phase, and next required action. It labels the ZIP separately as `local_audit_archive_path`. Its `human_takeover` object reports whether a read-only human checklist is available in the current phase and which reasons are valid. It does not open a browser or submit anything.

## Approve

After showing the manifest summary and receiving a direct user answer:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission
```

Approval binds to the manifest, resolved transport, and exact outbound artifact hashes. For `github`, the manifest also binds the repository, immutable commit, optional PR locator, verified remote ref, and selected path set; only `prompt.md` is outbound. Any later artifact change makes verification fail and invalidates progression.

For schema-3 `mcp-read`, first show the exact maximum path/size/hash set, potential bytes, tool schema, limits, expiry, and connector/app/workspace labels, then require both flags:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission \
  --confirm-mcp-disclosure
```

That approval does not authorize a manually fabricated active session. Continue only through the runtime lifecycle below, and do not paste the prompt or record submission until the exact approved session is active.

## Activate an experimental Web MCP session

Read [web-mcp.md](web-mcp.md) first. The official `tunnel-client` profile is user-owned and must point to the exact installed `/absolute/python -I -S -B -Xpycache_prefix=/dev/null /absolute/skill/scripts/gptpro_mcp.py serve` command. Its documented v0.0.12 public flow is:

```text
tunnel-client init --profile <name> ...
tunnel-client doctor --profile <name> --explain
tunnel-client run --profile <name> ...
```

Run the secretless gptpro MCP probe first. On first use, the user explicitly initializes the profile with that exact binary path/hash. Treat `--tunnel-profile` as the exact filename stem, not an alias. A missing profile needs attended init; a profile pinned to another checkout/installation reports `MCP_SKILL_ENTRYPOINT_MISMATCH` and needs a separately named attended profile for the current Skill root, never an interpreter refresh.

Before activation, the user confirms the exact visible ChatGPT app/workspace binding. `mcp-activate` re-verifies the approved package and runs the profile's `doctor` preflight before consuming the package's single activation attempt. It then creates owner-only user-global `activating` state plus a package-local audit header, starts one exact `tunnel-client run` child with an owner-only Unix health/admin socket and no TCP listener, and waits for:

```bash
python3 <skill-dir>/scripts/gptpro.py mcp-probe \
  --tunnel-client /absolute/path/to/tunnel-client \
  --json

python3 <skill-dir>/scripts/gptpro.py mcp-profile-init \
  --tunnel-profile gptpro-web \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --json

python3 <skill-dir>/scripts/gptpro.py mcp-profile-check \
  --tunnel-profile gptpro-web \
  --json

# Only when the check reports MCP_INTERPRETER_PATH_DRIFT, after separate
# approval of the exact current profile hash:
python3 <skill-dir>/scripts/gptpro.py mcp-profile-refresh \
  --tunnel-profile gptpro-web \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --confirm-current-profile-sha256 <tunnel_profile_sha256-from-check> \
  --confirm-profile-replacement \
  --json

python3 <skill-dir>/scripts/gptpro.py mcp-activate \
  --handoff-dir <dir> \
  --tunnel-profile gptpro-web \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --confirm-workspace-binding \
  --json
```

For one explicitly requested duplicate-dispatch investigation, prepare a dedicated approved package and require `mcp-probe` to report `tunnel_client.request_correlation_contract_supported: true` before adding `--diagnose-request-correlation`. This exact-version private-contract path is an operator opt-in, not a default. It raises the official child from `warn` to `info` only for its private in-memory admin ring while keeping the file destination at `/dev/null` and raw HTTP logging disabled. After revoke and before exact-child termination, gptpro verifies the Unix peer PID, enforces one total snapshot deadline, converts allowlisted outer request IDs immediately to session-scoped HMACs, discards the raw snapshot/key, and aligns only a complete forwarded-only result with a closed final protocol trace and disclosure audit. Stable join hashes already retained in the owner-only audit are used internally but are not copied into terminal output. It neither deduplicates nor discounts physical calls or returned bytes. Read [request-correlation.md](request-correlation.md) before use.

The profile check is local and secretless. Refresh is an attended local configuration mutation, not transmission approval: it accepts only interpreter-path-only drift, requires the exact checked profile hash and same Tunnel reference, refuses a live/faulted controller state, stages the official init output under owner-only permissions, and atomically replaces the profile after validation. Activation never performs this repair implicitly.

```bash
tunnel-client health \
  --url-file <activation-health-url-file> \
  --pid <owned-child-pid> \
  --require-control-plane-poll \
  --json
```

Only that successful control-plane poll permits the state to become `active`. `doctor`, `/healthz`, or `/readyz` alone is insufficient. Keep the activation command in the foreground while ChatGPT uses the tools. The controller passes the per-session capability to its stdio child through the environment; the capability and Tunnel/API credentials are not written into package, receipt, audit, prompt, or runtime-state JSON.

Developer Mode, Tunnel/key creation, login, ChatGPT account/workspace/app selection, and visible prompt submission are attended user steps. After the completed response is saved, stop promptly. `mcp-stop` first revokes content authorization and finalizes package evidence, then requests cooperative shutdown from the exact owning controller. It never discovers processes by name or uses a broad kill. If the controller is missing, authorization remains revoked and the failure is reported.

From a second terminal or controller while activation remains in the foreground:

```bash
python3 <skill-dir>/scripts/gptpro.py mcp-status --handoff-dir <dir> --json
python3 <skill-dir>/scripts/gptpro.py mcp-stop --handoff-dir <dir> --json
# Only after separately proving the exact foreground controller is gone:
python3 <skill-dir>/scripts/gptpro.py mcp-recover \
  --handoff-dir <dir> \
  --confirm-controller-lost \
  --json
python3 <skill-dir>/scripts/gptpro.py mcp-verify-audit --handoff-dir <dir> --json
python3 <skill-dir>/scripts/gptpro.py mcp-protocol-trace --handoff-dir <dir> --json
```

Never use `mcp-recover` while the exact controller lease is live. It is a fail-closed authorization recovery path, not process discovery or a substitute for `mcp-stop`.

The protocol trace is package-local, owner-only, and bounded to 64 sanitized events. Successful and failed activation receipts bind its header; an active-session exact-child-stop receipt additionally binds the final trace. A pre-active failure is snapshotted before exact child termination, so it honestly reports header binding but `artifact_identity_bound: false` and `lifecycle_binding_valid: false` until a future failed-stop receipt exists. Its `decision`, notification `processed`, and `response_flushed` stages do not claim remote delivery. A forced stop can legitimately leave `closed: false`; corrupt evidence is retained as `artifact_valid: false` with a stable code so it cannot erase the separate disclosure audit or stop receipt. Safely readable invalid bytes bind SHA-256 plus length; unsafe/unavailable artifacts report `artifact_identity_bound: false` and never claim lifecycle binding. After an active-session stop, either a self-consistent or same-error malformed rewrite fails the final receipt comparison. Read the diagnostic `terminal_evidence` fields together: `protocol_stream_closed` describes only a verified protocol footer, `runtime_stop_observed` describes the controller's exact-child result, and `final_artifact_bound_to_stop_receipt` describes immutable comparison with that stop receipt. `runtime_stopped_protocol_eof_unobserved` is therefore a valid terminal state, not evidence of a live runtime or permission to fabricate a footer.

Advanced `--tunnel-client`, `--profile-dir`, `--ready-timeout`, and `--diagnose-request-correlation` options exist for explicit installation and attended diagnostics. The authorization lifecycle always uses the canonical owner-only per-user runtime slot; there is no CLI runtime-root override because a second namespace would violate the one-active-package invariant. Request-correlation output appears only in the terminal `mcp_stopped` JSON; the Skill does not add it to package state, receipts, the disclosure audit, or the protocol trace. Redirecting terminal output is therefore an operator-controlled retention decision.

Activation and stop append auxiliary receipt events without advancing the consultation phase. A successful activation is not submission evidence, and an audit record is not response-import or evaluation evidence. Do not switch to another transport after activation failure without preparing and approving a new package.

## Human checkpoint

Human involvement is an expected attended path when the browser cannot or should not cross an account, OAuth, permission, operating-system, or ambiguous-state boundary. After approval, generate the exact checklist instead of improvising a workaround:

```bash
python3 <skill-dir>/scripts/gptpro.py human-handoff \
  --handoff-dir <dir> \
  --reason file-selection \
  --details "The browser file chooser did not become observable."
```

The command verifies the package and prints JSON containing the approved model, transport, exact outbound paths and hashes, human steps, expected return evidence, and retry policy. It is read-only: state and receipt bytes remain unchanged. Use `manual-transport` when the person should perform the complete approved send, `submission-uncertain` when Send may already have occurred, and `response-export` after submission when the marked answer must be saved manually.

Read [human-takeover.md](human-takeover.md) for the return contract. A human observation is not a submission receipt. Continue with `mark-submitted` only after a matching user turn is visibly confirmed, and never retry an uncertain submission automatically.

## Submit

Follow [browser-handoff.md](browser-handoff.md). After visible UI evidence confirms exactly one successful submission:

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --confirm-sent \
  --observed-model "ChatGPT Pro / GPT-5.6 Sol / Intelligence: Pro" \
  --observed-transport text-file \
  --thread-url "https://chatgpt.com/c/<id>"
```

For `github`, use `--observed-transport github` and also provide the exact approved `--observed-github-repository owner/repo` and `--observed-github-commit <sha>`. The command rejects identity drift.

Omit `--thread-url` if the user does not want the URL recorded. Never mark an ambiguous or failed send as submitted. If a transport fails, prepare and approve a new handoff instead of silently falling back.

## Import

Save the visible completed answer to a local UTF-8 file, retaining both package-specific marker lines, then run:

```bash
python3 <skill-dir>/scripts/gptpro.py import-response \
  --handoff-dir <dir> \
  --response-file /path/to/chatgpt-response.md
```

The importer rejects missing, duplicated, reversed, or foreign-package markers. A GitHub response must additionally contain the package-requested `GPTPRO_GITHUB_ATTESTATION` with the exact repository/commit and either a non-empty approved `files_read` set or a truthful `blocked` status. It writes `raw_response.md` and the marker-stripped `response.md`.

## Evaluate

After checking claims and running relevant tests:

```bash
python3 <skill-dir>/scripts/gptpro.py record-evaluation \
  --handoff-dir <dir> \
  --verdict partially-accepted \
  --summary "Accepted the lifecycle finding; rejected the caching claim." \
  --evidence "pytest tests/test_lifecycle.py: 18 passed" \
  --evidence "src/cache.py inspection at current HEAD" \
  --applied-git-sha "$(git rev-parse HEAD)"
```

Evidence strings are receipts, not automatically verified command output. Codex must report what was actually executed and avoid claiming stronger evidence than it has.
