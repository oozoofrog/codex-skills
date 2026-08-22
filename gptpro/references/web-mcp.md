# ChatGPT Web MCP repository consultation

The phase-3 runtime currently supports macOS with Python 3.11 or newer. Other platforms and older Python versions remain outside this runtime's tested contract; the existing attended browser/manual transports are separate.

This path lets a logged-in ChatGPT Web conversation inspect one explicitly approved immutable repository package through OpenAI Secure MCP Tunnel. It is experimental and attended. Codex still owns repository edits, commands, tests, Git operations, and the final decision.

## Evidence levels

Keep these claims separate:

- **Package/governance:** schema 3 can prepare, verify, approve, receipt, import, and evaluate an `mcp-read` handoff.
- **Local runtime:** the dependency-free stdio server can verify the immutable ZIP, authorize one active package, durably audit disclosure, and expose the exact read-only tools under deterministic tests.
- **Official client compatibility:** the installed `tunnel-client` can pass the documented profile preflight and foreground lifecycle checks.
- **Logged-in account E2E:** ChatGPT Developer Mode discovers the tools, performs bounded calls, returns the marked answer, and that answer is imported and evaluated.

Passing a lower level does not prove a higher one. In particular, `doctor`, `/healthz`, `/readyz`, protocol transcripts, and mock tests are not a logged-in account E2E. The official client, private account availability, and ChatGPT workspace controls can change.

## Three independent axes

| Axis | Phase-1 value | Meaning |
|---|---|---|
| Context transport | `mcp-read` | Repository bytes are disclosed on demand from the approved package. |
| Delivery channel | `browser` | A person visibly sends the prompt and receives the answer in ChatGPT Web. |
| Connector | `secure-mcp-tunnel` | The official Tunnel connects ChatGPT to the local stdio server. |

Changing any axis after approval requires revoking/stopping the current session, preparing a new package, and obtaining a new package-specific approval. Never silently fall back to GitHub, paste, text-file, manual, ZIP upload, or Desktop CDP.

## Approved immutable source

`mcp-read` uses manifest schema 3. Its approval covers:

- the exact prompt bytes and hash;
- every maximum-disclosure path, size, and SHA-256;
- archive, internal-manifest, file-set, tool-schema, limits, and approval-basis hashes;
- repository and Git snapshot identity;
- call, byte, line, result, and TTL bounds;
- `delivery.channel = browser` and `connector.type = secure-mcp-tunnel`;
- the Tunnel binding hash and visible ChatGPT app/workspace labels.

The ZIP is a local immutable source and audit artifact. It is not uploaded. The server reads approved `repo/<path>` members without extraction and never reads the live working tree, repository parent, home directory, arbitrary environment, or files absent from the manifest. Archive, member, type, path, UTF-8, size, hash, and package bindings fail closed.

Before approval, show the exact maximum file/hash set and potential bytes, exclusions and secret findings, prompt/archive hashes, tool schema, connector/app/workspace labels, limits, and expiry. The scanner is a backstop, not proof that the package contains no sensitive material.

## Exact read-only tools

Phase 1 exposes only:

- `gptpro_package_info`: approved package/snapshot metadata, allowlisted paths, limits, and expiry;
- `gptpro_repo_search`: bounded literal UTF-8 search within approved files;
- `gptpro_repo_read`: bounded UTF-8 line-range reads from one approved file.

There is no write, patch, shell, command execution, Git mutation, network fetch, arbitrary file read, or local tool relay. Every content call must name the active package and revalidate authorization, manifest/archive hashes, tool-schema binding, expiry, counters, and budgets. Cursor state is authenticated and package-bound.

## Runtime and audit boundary

The active authorization is user-global so two repositories cannot silently become active at once. All lifecycle commands share the canonical slot, resolve the account home from the current UID rather than `HOME`, and expose no CLI runtime-root override. On macOS its root is:

```text
~/Library/Application Support/gptpro/runtime/v1/
```

The directory is owner-only (`0700`), state/control files are owner-only (`0600`), symlinks and unsafe ownership/link/mode are rejected, writes are atomic and synced, and the global state stores hashes/bindings rather than the raw session capability or Tunnel/API credentials. The exact capability is generated per activation and passed only to the owned stdio child environment.

The long-lived package artifacts remain repository-local:

```text
<repo>/.gptpro/handoffs/<package-id>/
├── manifest.json
├── state.json
├── receipt.json
├── context-<package-id>.zip
└── mcp-audit.jsonl
```

`mcp-audit.jsonl` is an append-only hash chain. It records approved relative path/range/hash/returned-byte metadata and lifecycle summaries; it does not record full response bodies, raw search queries, credentials, or raw environment data. A content result is released only after its audit event is appended and synced. Audit failure therefore denies content. An audit record proves that local disclosure was committed for return, not that the network delivered it or ChatGPT used it.

## Official `tunnel-client` v0.0.12 flow

Use only the documented public profile lifecycle:

```text
tunnel-client init --profile <name> ...
tunnel-client doctor --profile <name> --explain
tunnel-client run --profile <name> ...
```

The profile is user-owned. `gptpro` creates it only during the explicit attended init, then reads/hashes it for policy and drift checks but does not edit, delete, print, or silently replace it. Official v0.0.12 stores the raw Tunnel ID in that owner-only profile, and `init` necessarily receives the ID in its child argv; gptpro package/runtime/receipt/audit artifacts retain only the package-bound hash. Keep the runtime API key in the supported `env:` or owner-only `file:` reference supplied to `gptpro`; the adapter resolves it only for the child process and normalizes the official profile reference to `env:CONTROL_PLANE_API_KEY`. Never put the key value in a package, prompt, receipt, audit, log, state file, or command-line literal.

Phase 1 accepts only the canonical `https://api.openai.com` control-plane origin with no userinfo, port, query, fragment, or non-root URL prefix. The adapter passes explicit canonical base/root-path and system-trust overrides to official `init`, `doctor`, and foreground `run`; proxy/custom-CA variables and PATH are not inherited. A profile with proxy, custom CA/client certificate, extra headers, remote MCP URLs, another command/channel, Harpoon/Cloudflared expansion, or raw HTTP logging fails before key-bearing `doctor` or `run`. The standalone `health` command reads only activation-owned URL/PID files whose URL must identify the exact owner-only Unix socket; it does not consume a remote control-plane endpoint.

The profile's MCP command must be the exact installed Skill entrypoint:

```bash
/absolute/path/to/python3 -I -S -B -Xpycache_prefix=/dev/null \
  "<skill-dir>/scripts/gptpro_mcp.py" serve
```

Keep the script path quoted because an installation path can contain spaces. The wrapper constructs canonical absolute paths; do not hand-edit the command. `-I -S` rejects user-site/environment startup injection, and the explicit `/dev/null` pycache prefix prevents a source-adjacent `.pyc` from replacing hashed source. The official client parses the command into arguments and executes it directly; do not add shell pipelines, redirects, or command substitutions.

`doctor` is a configuration preflight, not a server handshake or proof of authentication/control-plane reachability. Activation starts one exact `tunnel-client run` child in the foreground with an activation-owned owner-only Unix-domain health/admin socket, URL/PID files, and one MCP request at a time; it does not bind a TCP health/admin port. The URL file must be the exact canonical `http+unix://<base64url(absolute-socket-path)>` value for that socket. It forces official file logging to `/dev/null` and discards child stdout/stderr because even warning output can contain the raw Tunnel ID. The official in-memory status/log surface can also contain that ID, but it is confined to the private socket and disappears when the foreground child stops. It becomes active only after this check succeeds for that exact PID:

```bash
tunnel-client health \
  --url-file <activation-health-url-file> \
  --pid <owned-child-pid> \
  --require-control-plane-poll \
  --json
```

The adapter first requires the activation-owned private PID file to equal that exact `Popen.pid`; official v0.0.12 rejects combining `--pid` and `--pid-file`. A green `/healthz` or `/readyz` response alone is insufficient because it can exist before a successful control-plane poll. Do not rely on undocumented managed-runtime commands as the stable contract.

The adapter feature-probes the installed binary and records a safe version/hash summary. PATH discovery is probe-only; key-bearing profile init and activation require an explicit absolute client path plus the exact probe hash, and receipts/state bind the validated profile SHA-256, Tunnel binary SHA-256, exact MCP target SHA-256, and MCP runtime-tree SHA-256. That detects PATH substitution and in-session drift but does not prove publisher provenance or replace code-signature/supply-chain review. Missing `init`/`doctor`/foreground `run`/Unix-health/control-plane-health capabilities fail closed; readiness also passes the exact owned `Popen.pid` through `health --pid` and requires it to agree with the private PID file. The Skill does not silently substitute another client or lifecycle. v0.0.12 is the compatibility target tested for this phase, not a promise that future official releases or account availability will remain unchanged.

## Attended lifecycle

1. The user first creates/selects the intended Tunnel and keeps its raw ID in an owner-only `env:` or mode-`0600` `file:` reference. This identifies the disclosure destination but does not connect the repository or send content.
2. Prepare `--transport mcp-read` explicitly with that Tunnel ID reference and the smallest useful directed file selection. `auto` remains GitHub-first and never selects MCP.
3. Verify the package and inspect the complete schema-3 maximum-disclosure contract, including the bound Tunnel ID hash.
4. Obtain the two package-specific approval confirmations. A general request to use `$gptpro` is not this approval. Selecting a different Tunnel requires preparing and approving a new package.
5. The user creates the runtime key, configures the official profile for the same bound Tunnel, enables ChatGPT Developer Mode, selects the intended account/workspace/app, and reviews the three discovered tools. Login, MFA, CAPTCHA, OAuth/key creation, and account/workspace permissions are human steps.
6. Run the secretless probe and official `doctor` preflight. Neither intentionally sends a prompt or repository content from the gptpro wrapper. The first probe may create the canonical owner-only runtime directory (`0700`) and lock file (`0600`) while inspecting the empty authorization slot, and it executes the selected or PATH-discovered `tunnel-client` in bounded version/help subprocesses. Therefore, review and trust that external binary before probing it; an arbitrary executable is outside the wrapper's no-disclosure claim. The probe does not create a ChatGPT conversation or resolve credentials.
7. Start `mcp-activate` in the foreground. It re-verifies the approved package, writes private `activating` state and the audit header, starts exactly one official client child, requires a successful control-plane poll, records activation evidence, and only then changes authorization to `active`.
8. Keep that foreground controller alive. In visible ChatGPT Web, confirm the intended app/workspace/model and paste the approved prompt once. Never automate a login or silently resend after an ambiguous submission.
9. ChatGPT may call the three read-only tools within the approved budget. Import only the completed package-marked answer and independently evaluate it.
10. Stop promptly. `mcp-stop` revokes authorization first, finalizes audit/receipt evidence, then sends a cooperative request to the exact owning controller. It never scans process names, uses broad `pkill`, kills unrelated processes, or deletes the Tunnel/profile/package. If the controller is missing or refuses to stop, authorization remains revoked and the failure is reported.

   If package/audit/receipt verification is unavailable at stop time, the emergency path instead atomically marks only the exact global handoff/session binding `faulted`, leaves every package/audit/receipt byte untouched, reports `PACKAGE_EVIDENCE_UNAVAILABLE`, and requests cooperative stop through that session's exact controller socket. This denies further content access but is not proof that the audit or receipt was finalized. Controller lease release alone is not exact-child termination evidence; the runtime reports the Tunnel process as unconfirmed and requires attended process review unless a durable positive stop result exists.

The consultation lifecycle (`prepared -> approved -> submitted -> response_imported -> evaluated`) remains separate from MCP activation events. Activation does not submit the prompt, and stopping a session does not imply response import or evaluation.

## Failure rules

- Integrity, ownership, mode, approval, expiry, audit, budget, runtime-state, profile, workspace, or protocol ambiguity denies content.
- An activation failure must not leave content authorization active. Stop only the exact child that this controller started.
- A controller crash or lost control socket leaves authorization denied/revoked; recovery never guesses a PID or uses a broad kill.
- If Developer Mode, app/workspace binding, account entitlement, or the Tunnel path is unavailable, stop/revoke the session and prepare a new package for any other transport. The prior MCP approval does not authorize a fallback.
- Never expose a public inbound repository server or replace the activation-owned Unix health/admin socket with a TCP listener.
- Never automate credentials, MFA, CAPTCHA, Developer Mode, Tunnel/key creation, app/workspace selection, prompt submission, or response export.

## E2E reporting

The first real validation must use a harmless sandbox with a unique nonce. Record `not-run`, `blocked`, `failed`, or `passed` plus the exact Skill commit/tree, `tunnel-client` version, protocol/tool-schema hash, activation and final audit heads, visible account/app/workspace evidence, response import/evaluation, and confirmation that source files were unchanged. Do not call the Web MCP path verified until the logged-in account performs the tool calls and the marked response completes this lifecycle.

## Official references

- [OpenAI Secure MCP Tunnels](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Connect an MCP server from ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt)
