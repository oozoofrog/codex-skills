# GitHub transport

Use `github` when the selected repository context already exists at one immutable commit on `github.com` and the intended ChatGPT account can connect a GitHub app/plugin. ChatGPT plugins can expose connectors to services such as GitHub, and may require the user to connect the external service before tools become available; see OpenAI's [Plugins documentation](https://learn.chatgpt.com/docs/plugins).

GitHub describes context disclosure, not delivery. The same pinned prompt may be delivered through an approved browser/manual channel or optional `desktop-cdp`. Desktop phase 1 does not expose a local repository read/search relay or arbitrary function signatures; the signed-in ChatGPT experience must already be able to satisfy the connected-app request. If exact access is unavailable, return the required blocked attestation rather than changing transport or delivery channel.

## Prepare

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode review \
  --transport github \
  --github-remote origin \
  --github-pr-url "https://github.com/owner/repository/pull/123" \
  --include "src/**" \
  --include "tests/**" \
  --task "Review the pinned pull request for correctness and missing tests."
```

`--github-pr-url` is optional. Without it, current HEAD must be advertised by a branch or tag on the selected remote. With it, `refs/pull/<number>/head` must resolve to current HEAD. The remote URL must identify `github.com/<owner>/<repository>`; credential-bearing remote text is never copied into the package.

Preparation fails unless every selected file is tracked at HEAD and its current bytes exactly match that commit. It also fails when HEAD is not advertised by the selected GitHub remote or PR head. Commit and push relevant local changes first, or prepare a new `paste`/`text-file` handoff. The Skill never commits or pushes local content as part of preparation.

`auto` is GitHub-first. It resolves to `github` when the selected bytes match HEAD and that SHA is advertised by the configured GitHub remote; otherwise it records the exact preparation-time reason and falls back to `paste` or `text-file`. If `--github-pr-url` is supplied, verification failure is fatal instead of falling back. App availability and authorization remain attended browser checkpoints after approval. Choose `--transport paste|text-file` explicitly when GitHub access is not desired.

## Pinned context contract

The manifest records:

- canonical `owner/repository` and repository URL;
- immutable commit SHA and commit URL;
- verified remote name and branch/tag/PR head ref;
- optional canonical PR number and URL;
- exact allowed path list and selected-tree SHA-256;
- `remote_verified: true` from preparation-time `git ls-remote` evidence.

The local Markdown context and ZIP remain integrity/audit artifacts. Neither is outbound for `github`; only `prompt.md` is approved for transmission. Approval binds the manifest hash, prompt hash, repository, commit, PR locator, and selected path set.

A moving branch or PR URL is never the sole identity. The commit SHA is authoritative. Remote deletion or later permission changes can still make the app unable to retrieve it; the Pro response must report `blocked` rather than silently substitute another snapshot.

## Visible handoff

After package-specific approval:

1. Open a new ChatGPT general Chat in the intended account/workspace and select the approved model/Pro setting.
2. If GitHub is not connected, run `human-handoff --reason app-authorization`. The user reviews the app, account, organization, requested permissions, and repository scope.
3. Activate the visible GitHub app/plugin for the Chat.
4. Paste the exact approved `prompt.md`; attach no local context or ZIP.
5. Confirm the prompt visibly names the approved repository, commit, optional PR, and selected paths. Submit once.
6. Record submission only with matching observed repository and commit arguments.

```bash
python3 <skill-dir>/scripts/gptpro.py mark-submitted \
  --handoff-dir <dir> \
  --confirm-sent \
  --observed-model "ChatGPT Pro / GPT-5.6 Sol / Intelligence: Pro" \
  --observed-transport github \
  --observed-channel browser \
  --observed-github-repository owner/repository \
  --observed-github-commit <40-or-64-hex-sha> \
  --thread-url "https://chatgpt.com/c/<id>"
```

The app's repository authorization may be broader than the prompt's allowed path list. Treat the list as an analysis/disclosure instruction, not a technical repository sandbox. Prefer the narrowest repository scope the user accepts, and never authorize another repository on their behalf.

## Response attestation

Pro must include exactly one attestation line in the advisory response body. Browser/manual delivery places it inside the package markers; Desktop delivery captures the raw body and then adds those markers deterministically:

```text
GPTPRO_GITHUB_ATTESTATION: {"commit_sha":"<sha>","files_read":["src/file.py"],"repository":"owner/repository","status":"accessed"}
```

For successful access, `files_read` must be non-empty and contain only approved paths. If exact access failed, status is `blocked` and `files_read` is empty. `import-response` rejects a missing, malformed, foreign-repository, wrong-commit, duplicate-path, or out-of-selection attestation.

The attestation is still advisory self-report. Codex reopens cited files, compares current local state with the pinned commit/package identity, reproduces material claims, and records an evidence-backed evaluation before applying anything.

## Unsupported shortcuts

- Do not upload the local ZIP or context Markdown in addition to the approved GitHub prompt.
- Do not switch to a default branch, current PR head, web search, or copied snippets when the pinned commit is unavailable.
- Do not commit or push dirty/untracked content merely to make the transport pass without separate user authorization.
- Do not ask ChatGPT Pro to write, merge, or mutate the repository. This transport is an advisory read workflow.
- Do not fall back to another transport after approval. Prepare and approve a new package.
