# Source snapshot

This skill snapshots VoltAgent's awesome-design-md / getdesign.md design-system documents for local Codex use.

- Source repository: https://github.com/voltagent/awesome-design-md
- Source remote: https://github.com/voltagent/awesome-design-md
- Repository HEAD: `6dc4def886e9ad4022d616dc2afc2fcdf0056d07`
- Snapshot downloaded at: 2026-04-30T08:42:31Z → 2026-04-30T08:43:02Z
- Hosted source pattern: `https://getdesign.md/design-md/<slug>/DESIGN.md`
- Snapshot scope: slugs listed in the source repository README collection at the repository HEAD above.
- Snapshot count: 69

## Important caveats

- These are brand-inspired DESIGN.md files, not official brand guidelines.
- The local GitHub repository currently stores per-brand README pointers; the full token documents are served by getdesign.md.
- The original `DESIGN.md` files under `references/design-md/` are the source of truth for this skill.
- Derived extraction, summaries, or script output must not replace the original DESIGN.md text as authority.

## Refreshing

Run from the skill directory:

```bash
python3 scripts/update_snapshot.py
python3 scripts/designmd.py verify
```
