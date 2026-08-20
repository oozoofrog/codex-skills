# Security and data handling

## Threat model

The workflow crosses three trust boundaries:

1. local repository -> generated text and local audit archive;
2. approved text artifacts -> `chatgpt.com` after user approval;
3. ChatGPT Pro response -> local Codex judgment.

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

## Retention

Generated handoffs can contain proprietary source. Keep `.gptpro/` local by default, follow the repository's retention policy, and delete packages only with the user's authorization. The Skill does not upload, delete, or clean handoffs automatically.

First-use initialization is a separate local mutation from transmission approval. Preview it first. The recommended `local` scope appends only a labeled `.gptpro/` rule to the clone's Git `info/exclude`; `repository` scope changes `.gitignore` and therefore requires an explicit user choice. Initialization preserves existing ignore content and only appends its labeled entry when no effective rule already covers the output.
