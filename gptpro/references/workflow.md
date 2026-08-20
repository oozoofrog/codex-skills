# Workflow reference

## Lifecycle

The supported state sequence is:

```text
prepared -> approved -> submitted -> response_imported -> evaluated
```

`verify` is read-only and may run at any phase. Every mutating transition first verifies the existing manifest, archive, prompt, state identity, and receipt hash chain.

## Prepare

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode debug \
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

Preparation records both `git.head_sha` and a hash of the actual packaged file set. A dirty package is not represented as the HEAD commit; dirty paths and the package tree hash remain explicit.

## Verify and inspect

```bash
python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json
```

`status --json` is the machine-readable bridge between local packaging and any visible browser controller. It reports absolute prompt/archive paths, destination, requested model, response markers, current phase, and the next required action. It does not open a browser or submit anything.

## Approve

After showing the manifest summary and receiving a direct user answer:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission
```

Approval binds to current prompt/archive hashes. Any later artifact change makes verification fail and invalidates progression.

## Submit

Follow [browser-handoff.md](browser-handoff.md). After visible UI evidence confirms exactly one successful submission:

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --confirm-sent \
  --observed-model "GPT-5.6 Sol / Intelligence: Pro" \
  --thread-url "https://chatgpt.com/c/<id>"
```

Omit `--thread-url` if the user does not want the URL recorded. Never mark an ambiguous or failed send as submitted.

## Import

Save the visible completed answer to a local UTF-8 file, retaining both package-specific marker lines, then run:

```bash
python3 <skill-dir>/scripts/gptpro.py import-response \
  --handoff-dir <dir> \
  --response-file /path/to/chatgpt-response.md
```

The importer rejects missing, duplicated, reversed, or foreign-package markers. It writes `raw_response.md` and the marker-stripped `response.md`.

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
