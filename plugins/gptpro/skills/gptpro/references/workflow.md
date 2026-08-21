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

For a deliberate Web MCP foundation package, use `--transport mcp-read` plus `--tunnel-id-ref env:NAME` or an absolute owner-only mode-0600 `file:` reference, the intended app/workspace labels, and the smallest directed file set. It creates schema 3, a prompt-only outbound list, and a local immutable ZIP. It never uploads the ZIP and never makes MCP an `auto` fallback. The raw Tunnel ID/reference is not persisted. This build can verify and approve that contract but cannot activate or submit it.

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

That approval does not authorize a manually fabricated active session. A foundation-only build stops here; do not paste the prompt or record submission.

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
