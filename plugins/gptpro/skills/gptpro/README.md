# gptpro

`gptpro` is an attended Codex Skill for consulting a logged-in ChatGPT Pro general Chat without giving the web model direct authority over the local repository.

It initializes local handoff storage, scans and hashes selected repository files, records the exact Git state, excludes likely secrets and build noise, requires transport-specific user approval, guides the visible Chrome or human handoff, imports only the package-marked response, and records Codex's later evaluation. GitHub-first handoffs pin a remotely verified immutable commit and send only a prompt; text handoffs retain structured Markdown alternatives. A ZIP is retained locally for audit and integrity checks but is not uploaded by default.

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

This release uses manifest schema 2. A schema-1 ZIP-first handoff is not upgraded in place; prepare a new handoff so the new transport and approval hashes are explicit.

## Local CLI

```bash
python3 scripts/gptpro.py prepare --repo /path/to/repo --mode plan --transport auto --task "Plan the change."
python3 scripts/gptpro.py prepare --repo /path/to/repo --mode review --transport github --github-pr-url https://github.com/owner/repo/pull/123 --task "Review the pinned PR."
python3 scripts/gptpro.py verify --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
python3 scripts/gptpro.py status --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
python3 scripts/gptpro.py human-handoff --handoff-dir /path/to/repo/.gptpro/handoffs/<id> --reason manual-transport
```

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

It checks required files, exact `name`/`description` frontmatter, local Markdown links, prompt placeholder contract, Python syntax/executable modes, and optional mirror hashes.

## Security posture

- No OpenAI API key is required.
- No private ChatGPT endpoints or headless session scraping are used.
- Secret values are never printed in findings; matching files are excluded.
- Chrome/browser automation stops for attended human takeover at login, CAPTCHA, OAuth/app scope, permission, file chooser, model-selection, response-export, or ambiguous-submission blockers.
- GitHub transport refuses selected dirty/untracked content and unadvertised commits; it never commits or pushes on the user's behalf.
- The GitHub app's repository scope can be broader than the prompt path allowlist, so repository authorization remains a human decision.
- Imported Pro output is advisory until Codex verifies it against current repository evidence.

Generated handoffs live under `<repo>/.gptpro/handoffs/` by default. Add `.gptpro/` to the target repository's ignore rules if appropriate.
