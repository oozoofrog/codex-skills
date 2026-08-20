# gptpro

`gptpro` is an attended Codex Skill for consulting a logged-in ChatGPT Pro general Chat without giving the web model direct authority over the local repository.

It converts selected repository files into hash-verified structured Markdown, records the exact Git state, excludes likely secrets and build noise, requires transport-specific user approval, guides the visible Chrome handoff, imports only the package-marked response, and records Codex's later evaluation. A ZIP is retained locally for audit and integrity checks but is not uploaded by default.

## Install

From a clone of `oozoofrog/codex-skills`:

```bash
python3 scripts/manage_skills.py install gptpro
```

Preview the operation or update an existing installation:

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

The default destination is `${CODEX_HOME:-~/.codex}/skills/gptpro`. Restart Codex if the Skill does not appear immediately.

The bundled system installer is also compatible with a fresh installation from GitHub:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo oozoofrog/codex-skills \
  --path gptpro
```

## Use

Invoke `$gptpro` and provide a mode plus task, for example:

```text
$gptpro review 모드로 현재 변경의 정확성과 빠진 테스트를 검토해주세요.
```

The Skill will prepare and verify local artifacts first. Transmission is a separate attended action: it must show the exact manifest summary and receive approval before pasting, attaching, or submitting to `chatgpt.com`.

The default `--transport auto` uses:

- `paste` when the complete structured payload is at most 128 KiB;
- `text-file` for larger payloads, attaching one `context-<id>.md` and pasting `prompt.md`.

The 128 KiB cutoff is a conservative Skill policy, not a published ChatGPT limit. Override it with `--max-paste-bytes`, or choose `--transport paste|text-file` explicitly. A failed transport never falls back automatically because approval binds the exact outbound bytes.

This release uses manifest schema 2. A schema-1 ZIP-first handoff is not upgraded in place; prepare a new handoff so the new transport and approval hashes are explicit.

## Local CLI

```bash
python3 scripts/gptpro.py prepare --repo /path/to/repo --mode plan --transport auto --task "Plan the change."
python3 scripts/gptpro.py verify --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
python3 scripts/gptpro.py status --handoff-dir /path/to/repo/.gptpro/handoffs/<id>
```

The five modes are `plan`, `ask`, `review`, `debug`, and `architecture`. Run `python3 scripts/gptpro.py --help` for the full lifecycle.

## Security posture

- No OpenAI API key is required.
- No private ChatGPT endpoints or headless session scraping are used.
- Secret values are never printed in findings; matching files are excluded.
- Chrome/browser automation stops at login, CAPTCHA, permission, model-selection, or ambiguous-submission blockers.
- Imported Pro output is advisory until Codex verifies it against current repository evidence.

Generated handoffs live under `<repo>/.gptpro/handoffs/` by default. Add `.gptpro/` to the target repository's ignore rules if appropriate.
