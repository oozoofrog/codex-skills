# Supplemental text documents

Use `--supplement LABEL=/ABSOLUTE/PATH` when a consultation needs exact text from a file that is not part of the selected repository snapshot and direct browser upload is undesirable or unavailable. The option is repeatable. It captures a private, immutable preparation-time copy and the runtime never reopens the source path later. The path supplied to this option is not added to package metadata or prompt text; preparation fails if it is repeated in outbound task/model/app/workspace metadata.

This is a text snapshot mechanism, not arbitrary browser file upload. Inputs must be owner-controlled, single-link, non-group/world-writable regular files containing strict UTF-8 with no NUL bytes. Every path component is opened without following symlinks. Labels must be unique lowercase safe IDs, and the same secret scanner used for research evidence rejects credential-like content. Redact a derivative before preparation when the original contains sensitive material.

## Small document: paste

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode review \
  --transport paste \
  --supplement requirements=/absolute/private/requirements.md \
  --task "Review the implementation against the supplemental requirements."
```

Schema 2 embeds the exact document bytes in the structured context and local audit ZIP, records label/size/SHA-256 metadata plus a set hash, and makes only the combined paste payload outbound. `auto` may also be used, but the presence of a supplement prevents GitHub or text-file resolution: it resolves only to paste when the complete payload is within `--max-paste-bytes`, otherwise preparation fails and recommends `mcp-research`. The browser receives no file attachment.

Schema-2 hard limits are 16 documents, 2 MiB per document, and 8 MiB total. The complete combined paste payload must also fit the configured paste threshold, whose default is 128 KiB.

## Larger or exploratory document: Schema 4 research

```bash
python3 <skill-dir>/scripts/gptpro.py prepare \
  --repo "$PWD" \
  --mode architecture \
  --transport mcp-research \
  --supplement specification=/absolute/private/specification.md \
  --tunnel-id-ref env:GPTPRO_TUNNEL_ID \
  --chatgpt-app-name "GPT Pro Repository Research" \
  --chatgpt-workspace-label "Personal" \
  --task "Compare the repository with the approved supplemental specification."
```

Schema 4 maps each supplement into the existing research evidence allowlist. Supplement and `--evidence-file` entries therefore share safe labels and the package's approved `max_evidence_files`, per-file, and total-byte limits. The prompt names the supplement artifact IDs. Pro can discover their sizes and hashes with `gptpro_package_info` and read only those immutable artifacts with `gptpro_artifact_read`; supplements do not become repository paths and cannot be reached with repository read/search tools.

The ordinary schema-4 prompt remains the only browser text artifact. Document bytes flow only through the already approved, audited read-only MCP disclosure budget after Tunnel activation. Package-specific transmission, MCP disclosure, and analysis-ledger approval remain mandatory.

## Unsupported combinations

`--supplement` intentionally rejects `github`, `text-file`, and `mcp-read`:

- GitHub cannot prove or disclose a local external document from the pinned repository commit.
- `text-file` would reintroduce the browser file-upload boundary this option is designed to avoid.
- Schema-3 `mcp-read` has no external-artifact tool or approval contract.

Binary documents, images, archives, PDF bytes, and non-UTF-8 files are not accepted. Extract or export the necessary text into a reviewed UTF-8 derivative, or use a separate attended human upload if the original file format itself is material.

## Snapshot and approval semantics

Preparation copies and hashes the bytes once. Changing or deleting the source afterward does not alter the prepared package; prepare a new package to use a newer version. Verification detects edits to the package manifest, context, ZIP, or supplement metadata/body.

Before approval, show every supplement label, byte count, SHA-256, the resolved transport, and the applicable total limits. Approval binds those exact packaged bytes through the manifest, outbound artifact or MCP approval basis, local archive hash, and receipt. Refer to the document by label in the task and approval text; never copy its local path into outbound text. The packager does not redact path-like strings that are already part of the document body or selected repository content, so review the actual packaged content as well.
