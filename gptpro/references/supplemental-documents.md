# Supplemental text documents

Use `--supplement LABEL=/ABSOLUTE/PATH` when a consultation needs exact text from a file that is not part of the selected repository snapshot and direct browser upload is undesirable or unavailable. The option is repeatable. It captures a private, immutable preparation-time copy and the runtime never reopens the source path later. The path supplied to this option is local invocation metadata: it can appear in shell history, process listings, terminal capture, or an orchestrating tool's logs, but is not added to gptpro package metadata or prompt text. Preparation fails cleanly when a `~user` locator cannot be resolved and rejects a source locator reflected into outbound task/model/app/workspace metadata, including case or Unicode-normalization variants.

This is a text snapshot mechanism, not arbitrary browser file upload. Inputs require a supported POSIX host with current-user identity and descriptor-relative/no-follow file-open capabilities. The source must be a current-user-owned, single-link, non-group/world-writable regular file containing strict UTF-8 with no NUL bytes. Every path component is opened without following symlinks; symlinks, hard links, FIFOs, sockets, devices, ownership/mode ambiguity, and unsupported platform capabilities fail closed. Labels must be unique lowercase safe IDs, and the same secret scanner used for research evidence rejects credential-like content. Redact a derivative before preparation when the original contains sensitive material.

## Small complete package: paste

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode review \
  --transport paste \
  --include "src/**" \
  --include "tests/**" \
  --supplement requirements=/absolute/private/requirements.md \
  --task "Review the implementation against the supplemental requirements."
```

Schema 2 embeds the exact document bytes in the structured context and local audit ZIP, records label/size/SHA-256 metadata plus a set hash, and makes only the combined paste payload outbound. The verifier requires the exact supplement entry keys and declared totals/limits, reconstructs the structured context from the archive member bytes, and checks the deterministic paste bytes against that context. `auto` may also be used, but the presence of a supplement prevents GitHub or text-file resolution: it resolves only to paste when the complete prompt-plus-context payload is within `--max-paste-bytes`, otherwise preparation fails and recommends `mcp-research`. The browser receives no file attachment.

Schema-2 hard limits are 16 documents, 2 MiB per document, and 8 MiB total. The complete combined paste payload, including the selected repository files and prompt, must also fit the configured paste threshold, whose default is 128 KiB. A small supplement does not imply a small payload, so always use directed `--include` entries or an exact `--file-list`.

ChatGPT may render a large direct paste as a visible **pasted text** item instead of inline composer text. That display does not change the approved `paste` transport into a file upload. Verify that the complete approved payload and package markers are present, then submit once; do not attach the source document or switch transport without a new package and approval.

## Larger or exploratory document: Schema 4 research

```bash
python3 <skill-dir>/scripts/gptpro.py preflight \
  --repo "$PWD" \
  --transport mcp-research \
  --json

python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode architecture \
  --transport mcp-research \
  --include "src/**" \
  --include "tests/**" \
  --supplement specification=/absolute/private/specification.md \
  --tunnel-profile <selected_profile> \
  --confirm-tunnel-profile-sha256 <selected_profile_sha256> \
  --chatgpt-app-name "GPT Pro Repository Research" \
  --chatgpt-workspace-label "Personal" \
  --task "Compare the repository with the approved supplemental specification."
```

Schema 4 maps each supplement into the existing research evidence allowlist. Supplement and `--evidence-file` entries therefore share safe labels and the package's approved `max_evidence_files`, per-file, and total-byte limits. The manifest's supplemental counts/bytes are cross-checked against the supplement-ID subset of that evidence allowlist. A readable artifact also cannot contain a single UTF-8 line longer than the package's `max_read_content_bytes` limit (currently 98,304 bytes by default); reflow or export machine-generated one-line JSON/log content before preparation. The prompt names the supplement artifact IDs. Pro can discover their sizes and hashes with `gptpro_package_info` and read only those immutable artifacts with `gptpro_artifact_read`; supplements do not become repository paths and cannot be reached with repository read/search tools.

The ordinary schema-4 prompt remains the only browser text artifact. Document bytes flow only through the already approved, audited read-only MCP disclosure budget after Tunnel activation. Package-specific transmission, MCP disclosure, and analysis-ledger approval remain mandatory.

## Unsupported combinations

`--supplement` intentionally rejects `github`, `text-file`, and `mcp-read`:

- GitHub cannot prove or disclose a local external document from the pinned repository commit.
- `text-file` would reintroduce the browser file-upload boundary this option is designed to avoid.
- Schema-3 `mcp-read` has no external-artifact tool or approval contract.

Binary documents, images, archives, PDF bytes, and non-UTF-8 files are not accepted. Extract or export the necessary text into a reviewed UTF-8 derivative, or use a separate attended human upload if the original file format itself is material.

## Snapshot and approval semantics

Preparation copies and hashes the bytes once. Changing or deleting the source afterward does not alter the prepared package; prepare a new package to use a newer version. For Schema 2, verification binds the archive body byte-for-byte to the supplement metadata, reconstructed context, deterministic paste payload, manifest totals/limits, approval state, and receipt. For Schema 4, it binds the evidence member, evidence allowlist/set hash, supplement-ID subset counts/bytes, maximum-disclosure approval, archive, and receipt. Edits or unexplained fields in these contracts fail verification.

Before approval, show every supplement label, byte count, SHA-256, the resolved transport, and the applicable total limits. Approval binds those exact packaged bytes through the manifest, outbound artifact or MCP approval basis, local archive hash, and receipt. Refer to the document by label in the task and approval text; never copy its local path into outbound text. The packager does not redact path-like strings that are already part of the document body or selected repository content, so review the actual packaged content as well.
