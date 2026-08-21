# Workflow reference

## Lifecycle

The supported state sequence is:

```text
prepared -> approved -> submitted -> response_imported -> evaluated
```

`verify` is read-only and may run at any phase. Every mutating transition first verifies the existing manifest, prompt, context, optional paste payload, local archive, state identity, and receipt hash chain.

Schema-1 ZIP-first handoffs are immutable legacy receipts. Schema-2 receipts created before the explicit `delivery` field remain verifiable, but cannot receive a new approval or submission. Do not reinterpret either form; prepare and approve a current schema-2 handoff instead.

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
  --delivery-channel browser \
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
- `--transport auto|github|paste|text-file`: choose how repository context is disclosed. `auto` is the GitHub-first default.
- `--delivery-channel browser|manual|desktop-cdp`: choose how the approved message is sent, independently from context transport. The default is `browser`.
- `--github-remote`: choose the GitHub remote verified by `auto` or `github`; default `origin`.
- `--github-pr-url`: pin an optional GitHub PR whose remote head ref must equal current HEAD. A mismatch fails even under `auto`.
- `--max-paste-bytes`: set the conservative fallback threshold when GitHub-first `auto` is unavailable; the default 128 KiB is Skill policy, not a published ChatGPT limit.

Preparation records both `git.head_sha` and a hash of the actual packaged file set. `auto` first attempts `github`; it succeeds only when every selected byte matches HEAD and that SHA is advertised by the chosen github.com remote. Otherwise it records the reason and resolves to `paste` or `text-file`. Explicit `github` never falls back. A dirty text package is not represented as the HEAD commit; dirty paths and the package tree hash remain explicit. Only valid UTF-8 files enter the text context. The generated ZIP remains local audit evidence and is not a default Pro upload. Read [github-transport.md](github-transport.md) for the remote and response-attestation contract.

Desktop phase 1 supports `paste` and `github`. It rejects `text-file` because the runtime deliberately has no upload operation. `paste` is the direct path because the one approved message includes all selected text. Approval records both the resolved transport and delivery channel.

When an in-repository output root is not ignored, `prepare` adds a warning pointing to `init`; it does not change Git configuration automatically.

## Verify and inspect

```bash
python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json
```

`status --json` is the machine-readable bridge between governance and a selected delivery controller. It reports resolved transport, delivery channel, exact absolute `outbound_paths`, destination, requested model, markers, phase, and next action. It labels the ZIP separately as `local_audit_archive_path`. Its `human_takeover` object reports valid read-only checkpoints. It does not open a browser, connect to Desktop, or submit anything.

## Approve

After showing the manifest summary and receiving a direct user answer:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission
```

Approval binds to the manifest, resolved transport, delivery channel, and exact outbound artifact hashes. For `github`, the manifest also binds the repository, immutable commit, optional PR locator, verified remote ref, and selected path set; only `prompt.md` is outbound. Any later artifact change makes verification fail and invalidates progression.

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

## Submit through browser or manual delivery

Follow [browser-handoff.md](browser-handoff.md). After visible UI evidence confirms exactly one successful submission:

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --confirm-sent \
  --observed-model "ChatGPT Pro / GPT-5.6 Sol / Intelligence: Pro" \
  --observed-transport text-file \
  --observed-channel browser \
  --thread-url "https://chatgpt.com/c/<id>"
```

For `github`, use `--observed-transport github` and also provide the exact approved `--observed-github-repository owner/repo` and `--observed-github-commit <sha>`. The command rejects identity drift.

Omit `--thread-url` if the user does not want the URL recorded. Never mark an ambiguous or failed send as submitted. If a transport fails, prepare and approve a new handoff instead of silently falling back.

## Submit through Desktop CDP

Read [desktop-cdp.md](desktop-cdp.md). After approval, `probe` checks only loopback CDP, the exact renderer, bridge/app-version capability, and DeviceCheck. `models` reads the live account catalog. Resolve the requested human intent to exactly one backend id and supported effort; stop on missing or ambiguous results.

Show the resolved live backend id/effort and obtain explicit user confirmation, then run `approve-desktop-model --approved-by user --model-id <id> [--thinking-effort <effort>] --confirm-live-catalog`. This adds a hash-chained audit event without changing the lifecycle phase. Run `ask` with `--handoff-dir`, the one approved message path/hash, approved manifest hash, package id, that exact backend id/effort, and handoff-local output/result paths. Before connecting, it obtains a read-only `desktop-authorization` from the Python governance CLI and rejects anything but the exact still-approved package/message/channel/model resolution. It creates a fresh conversation, sends `local_function_signatures: []`, and does not retry interruption. After a complete result:

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --observed-transport paste \
  --observed-channel desktop-cdp \
  --observed-model <backend-model-id> \
  --desktop-result <dir>/desktop-result.json \
  --confirm-sent
```

The transition verifies package/manifest/message identity, raw and wrapper hashes, marker ownership, model/conversation evidence, and disabled tool signatures. Failed evidence leaves the phase `approved`. A Desktop failure does not authorize browser/manual fallback.

## Import

For browser/manual, save the visible completed answer to a local UTF-8 file with both markers. Desktop uses the runtime-generated wrapper already bound to its submission receipt. Then run:

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
