# Workflow reference

## Lifecycle

The supported state sequence is:

```text
prepared -> approved -> submitted -> response_imported -> evaluated
```

`verify` is read-only and may run at any phase. Every mutating transition first verifies the existing manifest, prompt, context, optional paste payload, local archive, state identity, and receipt hash chain.

Schema-1 ZIP-first handoffs are immutable legacy receipts. Do not silently reinterpret their approval as text-transmission approval; prepare and approve a schema-2 handoff instead.

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
- `--transport auto|paste|text-file`: choose the browser handoff. `auto` is the default.
- `--max-paste-bytes`: set the conservative auto-selection threshold; the default 128 KiB is Skill policy, not a published ChatGPT limit.

Preparation records both `git.head_sha` and a hash of the actual packaged file set. A dirty package is not represented as the HEAD commit; dirty paths and the package tree hash remain explicit. Only valid UTF-8 files enter the text context. The generated ZIP remains local audit evidence and is not a default Pro upload.

## Verify and inspect

```bash
python3 <skill-dir>/scripts/gptpro.py verify --handoff-dir <dir>
python3 <skill-dir>/scripts/gptpro.py status --handoff-dir <dir> --json
```

`status --json` is the machine-readable bridge between local preparation and any visible browser controller. It reports the resolved transport, exact absolute `outbound_paths`, destination, requested model, context/response markers, current phase, and next required action. It labels the ZIP separately as `local_audit_archive_path`. It does not open a browser or submit anything.

## Approve

After showing the manifest summary and receiving a direct user answer:

```bash
python3 <skill-dir>/scripts/gptpro.py approve \
  --handoff-dir <dir> \
  --approved-by user \
  --confirm-transmission
```

Approval binds to the manifest, resolved transport, and exact outbound artifact hashes. Any later artifact change makes verification fail and invalidates progression.

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

Omit `--thread-url` if the user does not want the URL recorded. Never mark an ambiguous or failed send as submitted. If a transport fails, prepare and approve a new handoff instead of silently falling back.

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
