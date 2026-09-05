# Read-only repository research contract

New consultations use Schema 4 `mcp-research`. The fixed visible tool catalog is:

- `gptpro_workspace_map`
- `gptpro_package_info`
- `gptpro_repo_read`
- `gptpro_repo_search`
- `gptpro_repo_diff`
- `gptpro_artifact_read`
- `gptpro_analysis_status`

All tools advertise `readOnlyHint: true`. There is no write file, patch, shell, build, test, Git mutation, credential, arbitrary network, arbitrary filesystem, or local-function relay.

Repository tools read the package's verified immutable archive, not the live working tree. Paths must be in the exact approved allowlist and responses consume call, match, line, and byte budgets. Diff is package-bound; artifact reads apply separate evidence allowlists and budgets. `analysis_status` reads a package ledger whose Codex notes require separate local approval and do not grant ChatGPT write authority.

The tool schema SHA-256 is `aa5efa1f52d36a8e6d1300c638b97f6bd76a9ef229d7f74e37ab3e30ebddcf87`. Changing the ChatGPT-visible catalog or input schema is outside this release. A real change requires App tool snapshot refresh and a new review/E2E.

Tool calls are durably audited before successful return. Physical duplicate calls each consume budgets; this release does not deduplicate or auto-retry ambiguous calls.

Before any external owner note is published, `analysis-note-approve --confirm-publication`
must bind its exact bytes. ChatGPT uses the app in one visible Chat inside the
macOS Desktop UI; the Tunnel does not create or select that conversation.
