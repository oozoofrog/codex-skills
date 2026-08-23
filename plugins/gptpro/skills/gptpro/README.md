# gptpro

`gptpro` is an attended Codex Skill for consulting a logged-in ChatGPT Pro general Chat without giving the web model direct authority over the local repository.

It initializes local handoff storage, scans and hashes selected repository files, records the exact Git state, excludes likely secrets and build noise, requires transport-specific user approval, guides the visible Chrome or human handoff, imports only the package-marked response, and records Codex's later evaluation. GitHub-first handoffs pin a remotely verified immutable commit and send only a prompt; text handoffs retain structured Markdown alternatives. A ZIP is retained locally for audit and integrity checks but is not uploaded by default.

This build also contains an **experimental read-only Web MCP runtime** for an explicit `mcp-read` schema-3 package. It verifies and reads the immutable local ZIP without extraction, exposes exactly three bounded read-only tools, stores one active package authorization in private user-global state, durably audits content before returning it, and supervises the official `tunnel-client` v0.0.12 public foreground flow. It does not automate Developer Mode, ChatGPT app/workspace selection, account authorization, or prompt submission. Local tests and a green Tunnel health check are not evidence of a successful logged-in ChatGPT account E2E; report that separately. See [Web MCP repository consultation](references/web-mcp.md).

## Install

From Codex, request a network installation without running Python directly:

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

Start a new Codex task after installation. Alternatively, register the repository Marketplace once and install `GPT Pro Collaborator` from the Plugins browser:

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
```

The Plugin package is under `plugins/gptpro`; the standalone GitHub path remains available for compatibility. See the [Plugin installation guide](https://github.com/oozoofrog/codex-skills/blob/main/docs/plugin-installation.md) for installation choices and the public-directory release gate.

Maintainers using a reviewed clone can still preview, install, or atomically update the standalone package:

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro
python3 scripts/manage_skills.py install gptpro --update
```

## Use

Invoke `$gptpro` and provide a mode plus task, for example:

```text
$gptpro review 모드로 현재 변경의 정확성과 빠진 테스트를 검토해주세요.
```

The Skill will prepare and verify local artifacts first. Transmission is a separate attended action: it must show the exact manifest summary and receive approval before pasting, attaching, or submitting to `chatgpt.com`.

Human participation is expected at trust and UI boundaries. Login, MFA, CAPTCHA, ChatGPT account/workspace choice, GitHub App authorization and repository scope, Chrome permissions, an OS file chooser, ambiguous model controls, uncertain submission, or response copying may require the user to take over briefly. This is a supported workflow state, not an automation failure. The Skill prints an exact checklist and resumes only from visible evidence.

## First-use setup

Preview the repository-local environment without writing anything:

```bash
python3 scripts/gptpro.py init --repo /path/to/repo
```

The recommended `local` scope plans two idempotent changes: create `<repo>/.gptpro/handoffs/` and add `.gptpro/` to that clone's `.git/info/exclude`. After reviewing and approving the JSON preview:

```bash
python3 scripts/gptpro.py init --repo /path/to/repo --apply
```

Use `--ignore-scope repository` to update the tracked-worktree `.gitignore` instead, or `--ignore-scope none` to create only the directory. The Skill never applies the preview automatically. `prepare` remains usable without initialization but reports a warning when an in-repository output directory is not ignored.

The default `--transport auto` is GitHub-first:

- `github` when every selected file matches HEAD and that SHA is advertised by the configured github.com remote;
- `paste` when GitHub is unavailable and the complete structured payload is at most 128 KiB;
- `text-file` when GitHub is unavailable and the payload is larger, attaching one `context-<id>.md` and pasting `prompt.md`.

Auto records the exact GitHub fallback reason. Supplying `--github-pr-url` makes a verification mismatch fatal instead of falling back. The 128 KiB cutoff is a conservative Skill policy, not a published ChatGPT limit. Override it with `--max-paste-bytes`, require GitHub with `--transport github`, or avoid app access with `--transport paste|text-file`. A transport never changes after approval because approval binds the exact outbound bytes and repository disclosure.

Normal `auto|github|paste|text-file` handoffs continue to use manifest schema 2. Only an explicit `--transport mcp-read` uses schema 3, whose approval binds a maximum dynamic disclosure set and is never inferred from `auto`. A schema-1 ZIP-first handoff is not upgraded in place; prepare a new handoff so the new transport and approval hashes are explicit.

## Local CLI

```bash
python3 scripts/gptpro.py prepare --repo /path/to/repo --mode plan --transport auto --task "Plan the change."
python3 scripts/gptpro.py prepare --repo /path/to/repo --mode review --transport github --github-pr-url https://github.com/owner/repo/pull/123 --task "Review the pinned PR."
python3 scripts/gptpro.py verify --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
python3 scripts/gptpro.py status --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
python3 scripts/gptpro.py human-handoff --handoff-dir /path/to/repo/.gptpro/handoffs/<id> --reason manual-transport
```

Schema-3 preparation requires transient Tunnel identity input plus visible app/workspace labels. The raw Tunnel ID or its reference is not written to package artifacts:

```bash
export GPTPRO_TUNNEL_ID="tunnel_<value>"
python3 scripts/gptpro.py prepare \
  --repo /path/to/repo \
  --mode architecture \
  --transport mcp-read \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --chatgpt-app-name "GPT Pro Repository Reader" \
  --chatgpt-workspace-label "Personal" \
  --include "src/**" \
  --task "Review this approved immutable snapshot."
```

Review `manifest.json`, `status`, and the exact maximum file/hash set before using both approval flags. Approval still does not activate a Tunnel: activation is a separate, attended command and succeeds only after the official client proves a live control-plane poll. Without the activation-generated capability and active package state, `scripts/gptpro_mcp.py serve` denies content calls.

## Experimental Web MCP setup

The phase-3 runtime currently requires macOS and Python 3.11 or newer. This requirement applies to the Web MCP lifecycle, not to ordinary Skill installation or the established browser/manual handoff paths.

The official Secure MCP Tunnel and ChatGPT connection steps are documented by OpenAI in [Secure MCP Tunnels](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server), and [Connect from ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt). Availability and account/workspace controls may change; confirm them in the visible ChatGPT UI.

Install or build the official `tunnel-client` separately, then use the attended `mcp-profile-init` command below to create a user-owned profile for the exact Skill installation. The v0.0.12 public flow is `init`, `doctor`, and foreground `run`; `gptpro` does not depend on undocumented managed-runtime commands. The wrapper pins the exact absolute Python and Skill entrypoint as:

```bash
/absolute/path/to/python3 -I -S -B -Xpycache_prefix=/dev/null \
  "<skill-dir>/scripts/gptpro_mcp.py" serve
```

`--tunnel-profile` is the exact filename stem (`<name>.yaml`), not an auto-discovered alias. A profile is bound to the absolute Skill root used at init: `TUNNEL_PROFILE_NOT_FOUND` requires attended init, while `MCP_SKILL_ENTRYPOINT_MISMATCH` means another checkout/installation needs a separately named attended profile; neither case permits `mcp-profile-refresh`.

Do not hand-edit that command. Isolated mode ignores user-site and `PYTHON*` configuration, `-S` suppresses `sitecustomize`, and the `/dev/null` pycache prefix prevents source-adjacent bytecode from replacing the hashed Skill source. The wrapper validates the narrow official init profile shape, owner-only profile path and bytes, canonical OpenAI endpoint, system-trust/no-proxy policy, single `main` command, and exact command hash before key-bearing `doctor` or `run`.

The user creates/selects the Tunnel and runtime key, enables Developer Mode, and confirms the intended ChatGPT app/workspace. Do not paste keys into prompts, package files, receipts, audit records, or command-line literal arguments. Official profile initialization stores the Tunnel ID in the owner-only user profile; gptpro handoff/runtime/receipt/audit artifacts retain only its package-bound hash. `doctor` is configuration preflight only. During activation, health/admin is confined to an activation-owned owner-only Unix socket with no TCP listener, and readiness additionally requires the exact foreground process to pass:

```bash
tunnel-client health \
  --url-file <activation-health-url-file> \
  --pid <owned-child-pid> \
  --require-control-plane-poll \
  --json
```

Before that command, the wrapper verifies that the activation-owned private PID file contains the same exact `Popen.pid`; official v0.0.12 rejects combining `--pid` and `--pid-file`. A green `/healthz` or `/readyz` response without `--require-control-plane-poll` is not enough. Keep `mcp-activate` in the foreground for the consultation. Stop with `mcp-stop`: authorization is revoked before the exact controller receives a cooperative shutdown request. The Skill never uses a broad process kill, installs a daemon, or silently changes transport.

After package-specific approval, the minimal lifecycle is:

```bash
python3 scripts/gptpro.py mcp-probe \
  --tunnel-client /absolute/path/to/tunnel-client \
  --json

# Copy binary_sha256 from the secretless probe. Profile initialization is
# attended and resolves secret references only after that exact hash matches.
python3 scripts/gptpro.py mcp-profile-init \
  --tunnel-profile gptpro-web \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --json

# Secretless: detects an exact profile or interpreter-path-only drift after a
# Homebrew/Python update. It does not execute tunnel-client or resolve keys.
python3 scripts/gptpro.py mcp-profile-check \
  --tunnel-profile gptpro-web \
  --json

# Run only after reviewing the check output and approving replacement of its
# exact current profile hash. Other profile changes fail closed.
python3 scripts/gptpro.py mcp-profile-refresh \
  --tunnel-profile gptpro-web \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --confirm-current-profile-sha256 <tunnel_profile_sha256-from-check> \
  --confirm-profile-replacement \
  --json

# Foreground: keep this process running during the consultation.
python3 scripts/gptpro.py mcp-activate \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --tunnel-profile gptpro-web \
  --runtime-api-key-ref env:CONTROL_PLANE_API_KEY \
  --tunnel-client /absolute/path/to/tunnel-client \
  --confirm-tunnel-client-sha256 <binary_sha256-from-probe> \
  --confirm-workspace-binding \
  --json

# Run status/stop from another terminal or controller.
python3 scripts/gptpro.py mcp-status \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --json
python3 scripts/gptpro.py mcp-stop \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --json
# Only after separately proving that the exact foreground controller is gone:
python3 scripts/gptpro.py mcp-recover \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --confirm-controller-lost \
  --json
python3 scripts/gptpro.py mcp-verify-audit \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --json
# Verify the package-local sanitized protocol trace, its available lifecycle
# binding scope, and independent disclosure-audit totals.
python3 scripts/gptpro.py mcp-protocol-trace \
  --handoff-dir /path/to/repo/.gptpro/handoffs/<id> \
  --json
```

For a dedicated investigation of repeated connector calls, explicitly add `--diagnose-request-correlation` to `mcp-activate`. The option temporarily admits official `info` records only to the child process's private in-memory admin ring, reads that ring after authorization revoke and before exact-child termination, and emits only session-scoped HMAC equality evidence. It does not persist raw IDs or payloads, enable raw HTTP logging, deduplicate calls, expand disclosure, or unlock write tools. An incomplete ring, trace, or audit is reported as `inconclusive`, and the CLI result is diagnostic output rather than a receipt. Read [Request-correlation diagnostic](references/request-correlation.md) before using it.

PATH discovery is probe-only. Key-bearing `mcp-profile-init`, `mcp-profile-refresh`, and `mcp-activate` require an explicit absolute `--tunnel-client` plus the exact `--confirm-tunnel-client-sha256` copied from the no-secret probe. `--profile-dir` is an explicit installation/test override; never point it at shared or untrusted state. All lifecycle commands use one canonical owner-only per-user runtime slot with no CLI root override, so a second root cannot create a second active authorization. Runtime state and receipts bind the validated profile SHA-256, Tunnel binary SHA-256, exact MCP target SHA-256, bundled MCP runtime-tree SHA-256, and package-local protocol-trace header. The final trace summary is additionally bound after exact child stop for a successfully activated session. A pre-active failure currently binds only the header because its failure callback runs before exact child termination; diagnostics therefore report `header_binding_valid: true` but `lifecycle_binding_valid: false` rather than claiming final-byte integrity. A missing footer or corrupt trace is reported honestly after exact stop and never replaces the independent disclosure audit. Diagnostic `terminal_evidence` therefore reports `runtime_stop_observed`, `protocol_stream_closed`, `protocol_eof_observed`, and `final_artifact_bound_to_stop_receipt` independently. In particular, `runtime_stopped_protocol_eof_unobserved` means the runtime stop and final bytes are receipt-bound even though the stdio child did not append an EOF footer; it does not mean the authorization remains live.

`mcp-profile-refresh` preserves the same Tunnel and bounded profile settings and permits only the first command argument—the absolute Python interpreter path—to change. A machine-global owner-only profile/controller flock serializes attended init, the full foreground activation lifetime, and the full refresh transaction. Refresh additionally requires either no authorization or a terminal session whose pre-existing safe controller lease is exclusively held through cleanup; missing, unsafe, unresolved, or live terminal leases are rejected. It generates a new owner-only profile through the official initializer, validates it, and atomically replaces the stale file. A byte-for-byte private backup restores the old profile if replacement or post-replacement validation fails; after a valid commit, `staging_cleanup_complete` reports cleanup separately. If cleanup is incomplete, do not print the private stage, activate, or retry; inspect and remove only its `.gptpro-refresh-*` child under the selected profile directory, then rerun `mcp-profile-check`. It never runs automatically from `mcp-activate`; a changed flag, entrypoint, Tunnel, endpoint, or unreviewed profile hash is rejected. The flock coordinates only this gptpro version, so stop controllers started by older or unmanaged code before refreshing.

`human-handoff` is read-only: it verifies the package and prints the approved paths, hashes, model, user steps, expected return evidence, and retry rule. It does not change state, authorize transmission, or mark a message as sent. The five modes are `plan`, `ask`, `review`, `debug`, and `architecture`. Run `python3 scripts/gptpro.py --help` for the full lifecycle.

## Validate Skill structure

The included validator uses only the Python standard library; it does not require PyYAML or another package:

```bash
python3 scripts/validate_structure.py --json
```

Repository maintainers can additionally prove that the standalone and Plugin copies are byte-identical:

```bash
python3 gptpro/scripts/validate_structure.py \
  --skill-dir gptpro \
  --mirror plugins/gptpro/skills/gptpro \
  --json
```

It checks required files, exact `name`/`description` frontmatter, local Markdown links, prompt placeholder contract, every packaged Python file's syntax, executable modes, the exact dependency-free read-only MCP schema/runtime, and optional mirror hashes.

## Security posture

- GitHub/paste/text-file handoffs require no OpenAI API key. The experimental Web MCP path requires a user-provisioned Tunnel runtime credential kept in the official client's environment or secure reference, never in gptpro artifacts.
- No private ChatGPT endpoints or headless session scraping are used.
- The Web MCP path exposes only `gptpro_package_info`, `gptpro_repo_search`, and `gptpro_repo_read`; it has no repository write, shell, Git mutation, or generic local tool relay.
- User-global runtime state is owner-only and stores bindings/hashes rather than raw Tunnel/API credentials. Package receipts and the disclosure audit remain in the handoff directory.
- Repository content is returned only after its audit event is durably committed. An audit event proves local disclosure commitment, not network delivery or use by ChatGPT.
- Secret values are never printed in findings; matching files are excluded.
- Chrome/browser automation stops for attended human takeover at login, CAPTCHA, OAuth/app scope, permission, file chooser, model-selection, response-export, or ambiguous-submission blockers.
- GitHub transport refuses selected dirty/untracked content and unadvertised commits; it never commits or pushes on the user's behalf.
- The GitHub app's repository scope can be broader than the prompt path allowlist, so repository authorization remains a human decision.
- Imported Pro output is advisory until Codex verifies it against current repository evidence.

Generated handoffs live under `<repo>/.gptpro/handoffs/` by default. Add `.gptpro/` to the target repository's ignore rules if appropriate.
