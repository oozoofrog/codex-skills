# Split-install transition evidence

This contract is used only when an older integrated or Browser-first `gptpro` installation is replaced by the Desktop-only base while legacy machine-global MCP evidence still exists. It does not authorize a Tunnel, resume a session, disclose repository data, or prove that an unobserved process stopped.

## Read-only decision

```bash
python3 <gptpro-mcp-dir>/scripts/gptpro.py transition-evidence \
  --handoff-dir /absolute/path/to/the/exact/legacy-package \
  --json
```

The command reads only the exact package-bound active state or its exact session-hash archive. It does not recover, expire, stop, create a lock, write a receipt, or search other packages. The principal decisions are:

- `safe_exact_terminal`: the package terminal receipt and machine-global exact-child stop evidence both verify.
- `adoption_required`: authorization and package evidence are terminal, the controller is not live, attended orphan-process clearance exists, but exact-child stop is not proven and no residual ownership receipt exists.
- `safe_owned_residual`: the same terminal evidence is bound to a verified `gptpro-mcp-residual-ownership-v1` receipt owned by the exact installed optional component.
- `blocked`: non-terminal, live, unavailable, mismatched, unsafe, or stale evidence prevents the base replacement.

`ownership_transferred=true` never changes `exact_child_stop_proven=false` into a stop claim. It means only that the optional component retains `status` and recovery responsibility for unresolved terminal evidence.

## Explicit residual adoption

The installer invokes this internal operation only after installing and hashing `gptpro-mcp`:

```bash
python3 <gptpro-mcp-dir>/scripts/gptpro.py residual-adopt \
  --handoff-dir /absolute/path/to/the/exact/legacy-package \
  --next-base-entrypoint /absolute/path/to/gptpro/scripts/gptpro.py \
  --confirm-residual-ownership \
  --json
```

The installed component descriptor supplies the exact previous base and owner component. The next base must answer the public component capability handshake. A development test may inject an exact absolute previous entrypoint; production installation does not search `PATH`, `~/.codex/skills`, or arbitrary checkouts.

The receipt is atomically created as mode `0600` under the owner-only machine runtime directory. It binds the domain-separated session identity, terminal authorization status, canonical runtime state hash/revision, verified package terminal receipt hash or an explicit unavailable-package evidence kind, and previous/next/owner component versions and tree hashes. It stores no raw session ID, Tunnel ID, API key, or package path.

If the exact terminal state later moves from `active.json` to its immutable session archive, the same state hash and revision keep the receipt valid. A runtime revision, package receipt, owner tree, previous base tree, or next base tree change makes it stale. Stale receipts are never silently rewritten.

## Installer behavior and crash recovery

`manage_skills.py install gptpro --update` uses the same decision path in dry-run and actual mode:

```bash
python3 scripts/manage_skills.py install gptpro --update --dry-run \
  --legacy-handoff-dir /absolute/path/to/the/exact/legacy-package \
  --adopt-residual-mcp-state
```

`--dry-run` never records ownership or changes the install descriptor. Actual residual adoption follows this order: verify installed `gptpro-mcp`, create and re-read the receipt, atomically replace the base, then update the descriptor. A failure after receipt creation preserves the old base and the receipt; retrying the identical inputs is idempotent. A descriptor write failure after base replacement is repaired by re-verifying the installed trees and receipt, then rewriting only the descriptor.

The descriptor's `legacy_mcp_handoff` field is an audit summary containing the real machine-global receipt SHA-256. It is not authorization evidence. Every decision revalidates the original owner-only receipt.

For a damaged or missing package, `--confirm-legacy-package-unavailable` is accepted only after attended review and only when the exact active runtime path still binds the requested location. This fallback cannot create terminal package-receipt evidence and therefore cannot produce `safe_exact_terminal`.

## Public MCP compatibility

This transition does not change the ChatGPT-visible MCP tool catalog, tool input schema, or JSON-RPC wire contract. The fixed catalog hashes are:

```text
mcp-read:     38575a038b9d90eda9d2e467a1107e2059832d14e44067311e2b43c92d6a2823
mcp-research: aa5efa1f52d36a8e6d1300c638b97f6bd76a9ef229d7f74e37ab3e30ebddcf87
```

General Tunnel compatibility remains capability-based. Only the optional private request-correlation diagnostic retains its exact supported Tunnel version contract; lack of that private diagnostic does not invalidate an otherwise successful read-only Tunnel run.
