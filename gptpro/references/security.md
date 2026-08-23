# Security and data handling

## Threat model

The workflow crosses three trust boundaries:

1. local repository -> generated text and local audit archive;
2. approved text artifacts -> `chatgpt.com` after user approval;
3. ChatGPT Pro response -> local Codex judgment.

The experimental Web MCP path adds two boundaries: approved immutable package -> local read-only MCP runtime, and that runtime -> ChatGPT through OpenAI Secure MCP Tunnel. The runtime authorizes one package at a time, reads only its verified archive, and treats the official Tunnel plus the logged-in ChatGPT account/workspace as separate attended boundaries.

Repository text, filenames, webpage content, and Pro output can contain prompt injection. None of them become instructions merely because they are packaged, displayed, or imported.

## Default exclusions

The packager excludes Git internals, prior `.gptpro` artifacts, dependency/build/cache directories, editor state, common environment files, credentials, private keys, certificates, provisioning profiles, oversized files, unreadable files, symlinks, binary files, and text files that are not valid UTF-8.

User `--exclude` patterns take precedence over `--include` and file-list selection. Git-ignored files are not candidates when Git discovery is available.

## Secret scan

Selected text files are scanned for high-confidence credential patterns such as private-key headers, common provider tokens, and credential-like assignments. A matching file is excluded from all generated context artifacts. Findings record only:

- path;
- detector name;
- line number when available;
- action (`excluded`).

The matching value is never printed or copied into the manifest. There is deliberately no flag to force a detected secret into a package. If context genuinely requires a sensitive file, create a redacted derivative outside the source file and select that derivative explicitly.

The scanner is a backstop, not proof that the outbound text is secret-free. The manifest, context, and exact outbound paths still require human review before approval.

Human takeover does not expand the approved disclosure. The person may complete login, OAuth/app scope, browser permission, OS file selection, the exact approved transport, or response export, but must not substitute files, change transports, reveal credentials, inspect unrelated browser data, or treat a click as proof of submission. `human-handoff` is read-only so asking for help cannot silently mutate the audit chain.

## Hashes and tampering

The external manifest records SHA-256 hashes for the prompt, structured context, optional paste payload, local archive, internal manifest, and every included file. The local archive contains its own file manifest. `verify` rejects:

- changed prompt/context/paste/archive bytes;
- duplicate, missing, extra, unsafe, or renamed archive members;
- file hash/size mismatches;
- package/state identity mismatches;
- broken receipt event hashes.

Git HEAD identity and the packaged tree hash are separate. This preserves honest provenance for dirty worktrees.

The outbound structured context omits the local absolute repository root and the absolute source path of `--file-list`. The external local manifest retains them for audit. GitHub transport canonicalizes the repository URL and never stores a credential-bearing remote URL. It verifies that selected bytes equal HEAD and that HEAD is remotely advertised, but the prompt path allowlist is not a technical sandbox: the connected app's repository authorization can be broader. Changing transport changes the outbound artifact set, so the workflow requires a new package and approval instead of automatic fallback after preparation.

For schema-3 `mcp-read`, the ZIP is local-only and no plaintext aggregate context is generated. Approval binds its exact allowed path/size/hash set, static tool schema, budgets, expiry, browser delivery, and connector labels. Preparation accepts the raw Tunnel ID only through a named uppercase environment variable or an absolute owner-only mode-0600 regular file and writes only a package-specific hash into gptpro package/runtime/receipt/audit artifacts. The attended official `init` command necessarily receives the ID in its child argv and stores it in the owner-only user profile; protect that profile and local process visibility accordingly. Tunnel-shaped identifiers found in repository text are excluded as secrets, while any occurrence of the resolved ID in retained paths, task, labels, prompt, or manifest fails preparation.

The Secure MCP Tunnel client is a separate external component and is not vendored by this Skill. Obtain or build it only from the user-reviewed official `openai/tunnel-client` source/distribution path. A no-secret probe reports its path/hash; key-bearing `mcp-profile-init`, separately approved `mcp-profile-refresh`, and `mcp-activate` then require that explicit absolute path and exact hash. This prevents PATH substitution and detects in-session binary drift, but it is not publisher provenance, code-signing, or supply-chain verification.

The client uses outbound connectivity and a local stdio child; credentials remain in a user-controlled environment or transient child memory. The Skill reads and hashes the owner-only profile to validate the exact narrow shape produced by its attended init. It does not expose raw profile contents or delete the profile, and it modifies the profile only through the separately approved, interpreter-path-only `mcp-profile-refresh` exception described below. It does not expose a public inbound repository server, install a persistent service, or automate ChatGPT login/Developer Mode/app authorization. Profile `doctor` validates configuration only. Activation requires the private PID file to agree with the exact foreground `run` child and then requires that PID to pass `health --url-file ... --pid <owned-pid> --require-control-plane-poll --json`; plain `/healthz` or `/readyz` is not sufficient proof of control-plane readiness.

For this phase, key-bearing official-client operations are pinned by CLI override to `https://api.openai.com` with a normalized root URL path, system trust, no proxy/custom CA, and `env:CONTROL_PLANE_API_KEY`; arbitrary endpoint, proxy, certificate, PATH, `SSL_CERT_*`, and `PYTHON*` variables are not inherited. URL userinfo, ports, paths, queries, fragments, or alternate hosts fail closed. The validated profile permits only one `main` stdio command and rejects extra commands/channels, remote MCP URLs, extra headers, proxy/custom-CA/client-certificate settings, Harpoon/Cloudflared expansion, and raw HTTP logging. Activation overrides health/admin serving to one owner-only Unix-domain socket under the private runtime directory, validates the URL file as the exact canonical `http+unix://` encoding of that socket, and opens no TCP health/admin listener.

The MCP command uses canonical absolute paths and is hashed exactly as `/absolute/python -I -S -B -Xpycache_prefix=/dev/null /absolute/skill/scripts/gptpro_mcp.py serve`. Isolated mode and `-S` block user-site, `PYTHONPATH`, and `sitecustomize` injection; the explicit pycache prefix blocks timestamp-valid source-adjacent `.pyc` replacement. The foreground child receives only the finite locale/home/config environment, the transient control-plane key, and the exact two gptpro child-capability variables. Tunnel logs are not persisted to a regular file: `doctor` and `run` override logging to `/dev/null`, and foreground stdout/stderr are discarded because official warning records can contain the raw Tunnel ID. The official in-memory admin/status surface can also include that ID, so gptpro confines it to the owner-only Unix socket and users should stop the foreground session promptly.

An interpreter upgrade does not weaken that pin. The secretless profile check distinguishes an exact command from a change to only its first interpreter-path argument. One canonical owner-only `profile-controller.lock` serializes explicit init, profile inspection/doctor plus the entire foreground activation, and refresh through rollback/cleanup. Repair requires the checked profile hash, the same Tunnel reference, the exact confirmed Tunnel binary, an explicit replacement flag, and either no authorization state or a terminal state whose pre-existing safe controller lease can be exclusively acquired and held for the full refresh. A live, missing, unsafe, or otherwise unresolved terminal lease blocks replacement. The runtime-state lock is held only for the bounded state snapshot, not while the external initializer runs. The official initializer writes an owner-only staged profile, which is validated before an atomic same-filesystem replacement; a synced byte-for-byte private backup is restored on replacement or post-validation failure. Cleanup after a valid commit is reported separately. `TUNNEL_PROFILE_STAGE_CLEANUP_REQUIRED` or `staging_cleanup_complete: false` means a private stage that can contain the raw Tunnel ID may remain: do not print its contents, activate, or retry until an attended user inspects and removes only the `.gptpro-refresh-*` child under the explicitly selected profile directory, then reruns the secretless check. Profile flags, scripts, endpoints, Tunnel identities, symlinks/PATH lookup, and unrelated settings are never auto-migrated; activation fails before resolving the runtime key when refresh is required. This advisory flock coordinates only current gptpro-managed operations; stop any older or unmanaged controller before refresh, and treat same-user manual profile edits as external drift.

User-global authorization state uses `<macOS account home>/Library/Application Support/gptpro/runtime/v1/`. The account home is resolved from the current UID rather than the caller's `HOME` environment. Every lifecycle command uses that canonical per-user slot, and the CLI deliberately exposes no runtime-root override because independent roots would permit concurrent authorizations. Its directory and files are owner-only, no-follow, atomically written, and synced. It stores package/session bindings and the validated profile, Tunnel binary, exact MCP target, and MCP runtime-tree hashes, not the raw per-session capability, API key, cookies, OAuth tokens, or ChatGPT credentials. The capability exists only in the activation-owned child environment. Package state, lifecycle receipts, immutable archive, and disclosure audit stay under the handoff directory.

Each handoff directory retains one package-local mode-`0600` protocol diagnostic plus an owner-only lock. Its header binds the package/session/manifest/approval, archive/file set/tool schema, disclosure-audit header, validated profile/client, exact MCP target, and runtime-tree hashes. The chain retains at most 64 allowlisted events, reserving its final event for an explicit truncation marker. It distinguishes decisions, post-mutation readiness or notification processing, and successful local response flush, while retaining exact protocol versions only from the fixed supported-version allowlist. It never persists JSON-RPC IDs, raw unknown methods or versions, client information/capabilities, arguments, repository paths/queries/content, Tunnel identity, credentials, or environment data.

Legacy `tools/call` compatibility is limited to the exact allowlisted tool name plus optional object-valued `arguments` and `_meta`. Omitted arguments become an empty object. `_meta` is validated only as an object, then ignored: it is not forwarded to repository tools or persisted in diagnostics. Unknown parameter keys, including unsupported task augmentation, remain fail-closed.

Trace path/write/integrity failure stops further protocol dispatch but does not rewrite or substitute the independent disclosure audit. Successful activation binds the header in package and runtime state; a failed activation after header creation binds a separate package/receipt diagnostic to the same consumed session. That failure snapshot precedes exact child termination and therefore claims header binding only, never final artifact or lifecycle binding. Exact-child stop after successful activation records either the verified final prefix/footer summary or a stable invalid-trace code. Safely readable invalid bytes additionally bind raw SHA-256 and length; unsafe/unavailable bytes explicitly remain identity-unbound rather than receiving a false lifecycle-valid claim. Missing footer and corrupt trace therefore do not erase revoke, audit closure, or child-stop evidence. `mcp-protocol-trace` compares valid or fingerprinted bytes with the final receipt, detecting both self-consistent and same-error malformed post-stop rewrites, and its `terminal_evidence` distinguishes protocol footer observation from controller-observed runtime stop. It never creates a synthetic `runtime_stopped` protocol footer. These unkeyed hashes detect accidental drift and post-stop disagreement with the receipt; they do not protect against a malicious same-user process that can rewrite every local trust anchor.

Repository bytes returned through `gptpro_repo_search` or `gptpro_repo_read` come only from verified ZIP members. Their path/range/hash/byte disclosure record is appended and synced before content is returned; audit failure blocks the content. The audit omits full bodies, raw search terms, credentials, and raw environment data. Its hash chain proves local disclosure commitment, not network delivery, ChatGPT use, correctness, or user approval. Identical repeated requests are not collapsed: every physical attempt consumes call budget and every returned copy consumes disclosure bytes, so an unexplained upper-layer duplicate dispatch cannot bypass the approved maximum.

Stopping is fail-closed: revoke content authorization first, then ask the exact foreground controller to terminate its owned child cooperatively. Never scan by process name, use broad `pkill`, kill an unverified PID, or delete the user's Tunnel/profile/key. If the controller cannot be reached, keep authorization revoked and report the process-state uncertainty.

If the package, audit, or receipt evidence cannot be verified during stop, gptpro atomically changes only the exactly bound machine-global authorization to `faulted`, reports package evidence as unavailable, and then asks the exact session-bound controller to stop cooperatively. It does not rewrite any package/audit/receipt bytes or claim terminal audit closure; repairing or replacing that evidence is a separate attended recovery decision. A released controller lease proves only that the controller exited, not that its exact Tunnel child stopped. Without a durable positive child result, `tunnel_runtime_stopped` remains false and manual process review is required.

Receipt and audit event hashes are unkeyed consistency checks. They detect accidental drift and cross-bind the current manifest, artifacts, state, and lifecycle records, but they are not a signature against a malicious process with the same user's file-write authority. A stronger adversary model requires a separate protected trust anchor such as a Keychain-held MAC key or externally retained approval hash; that is outside this runtime.

## Retention

Generated handoffs can contain proprietary source. Keep `.gptpro/` local by default, follow the repository's retention policy, and delete packages only with the user's authorization. The Skill does not upload, delete, or clean handoffs automatically.

First-use initialization is a separate local mutation from transmission approval. Preview it first. The recommended `local` scope appends only a labeled `.gptpro/` rule to the clone's Git `info/exclude`; `repository` scope changes `.gitignore` and therefore requires an explicit user choice. Initialization preserves existing ignore content and only appends its labeled entry when no effective rule already covers the output.
