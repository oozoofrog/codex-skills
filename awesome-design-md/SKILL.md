---
name: awesome-design-md
description: Use when a user wants to apply, copy, inspect, compare, or generate UI from getdesign.md or VoltAgent awesome-design-md DESIGN.md files, brand-inspired design tokens, color palettes, typography, spacing, component styling, responsive behavior, or DESIGN.md snapshots.
---

# Awesome DESIGN.md

## Overview

This skill provides a local snapshot of VoltAgent's `awesome-design-md` / getdesign.md DESIGN.md collection. The authoritative tokens are the original files in `references/design-md/<slug>/DESIGN.md`; do not paraphrase them when exact colors, typography, spacing, or component rules are needed.

## When to use

Use this skill when the user asks for:

- `awesome-design-md`, `getdesign.md`, `DESIGN.md`, or `npx getdesign` help.
- A page/component that follows a specific listed brand-inspired visual system.
- Exact design tokens: color hex values, typography, spacing, radii, shadows, components, responsive behavior.
- Copying a ready-to-use `DESIGN.md` into a project.
- Reviewing whether an implementation follows one of the included design systems.

## Do not use when

- The user needs an official brand guideline, trademark approval, or licensed brand asset pack.
- The user needs strict machine-token formats such as Style Dictionary JSON as the source of truth.
- The task is generic UI design with no requested DESIGN.md or brand-inspired source.

## Quick start

1. Pick the slug from `references/catalog.md` or run `python3 scripts/designmd.py list`.
2. Read the exact source file: `references/design-md/<slug>/DESIGN.md`.
3. For project use, copy it: `python3 scripts/designmd.py copy <slug> --out ./DESIGN.md`.
4. When implementing or reviewing UI, cite the exact token/rule from that source file and avoid inventing missing tokens.

## Workflow

### Copy a design system into a project

```bash
python3 /Users/oozoofrog/.codex/skills/awesome-design-md/scripts/designmd.py copy stripe --out ./DESIGN.md
```

Use `--force` only when overwriting is intended.

### Inspect available systems

```bash
python3 /Users/oozoofrog/.codex/skills/awesome-design-md/scripts/designmd.py list
python3 /Users/oozoofrog/.codex/skills/awesome-design-md/scripts/designmd.py show apple
python3 /Users/oozoofrog/.codex/skills/awesome-design-md/scripts/designmd.py grep "#533afd" --slug stripe
```

### Implement UI from a DESIGN.md

- Treat `DESIGN.md` as the source of truth.
- Use named tokens and semantic roles before raw hex values when both are present.
- Preserve documented constraints such as “do not introduce a second accent color.”
- If a token is absent, say it is absent and choose the nearest documented rule only with an explicit inference note.

### Review UI against a DESIGN.md

Check in this order:

1. Colors and semantic roles.
2. Typography family, weight, size, line-height, letter-spacing.
3. Radius, spacing, borders, shadows, elevation.
4. Component states and guardrails.
5. Responsive behavior and touch targets.

## Source and license

- Source repo: `https://github.com/voltagent/awesome-design-md`
- Snapshot source: `https://getdesign.md/design-md/<slug>/DESIGN.md`
- Repo HEAD at snapshot: `6dc4def886e9ad4022d616dc2afc2fcdf0056d07`
- License copy: `references/LICENSE.voltagent.md`
- Source details: `references/source.md`

The included files are brand-inspired references from VoltAgent's MIT-licensed collection. They are not official brand design systems.

## Review Harness

- mode: optional
- generator: creates or edits UI using one selected `DESIGN.md`
- evaluator: compares output against the same `DESIGN.md`, prioritizing exact token usage and documented guardrails
- evaluation axes: token fidelity, component fidelity, responsive behavior, unsupported-token honesty, minimal unrelated UI changes
- artifacts/evidence: selected slug, source file path, copied `DESIGN.md` path if any, implementation diff or screenshots when available
- pass condition: no invented core tokens and no obvious violation of the selected document's Do/Don't rules

## Output expectation

When using this skill, include:

1. Selected slug and source file path.
2. Whether a `DESIGN.md` was copied or only referenced.
3. Exact token/rule highlights used for implementation or review.
4. Any gaps where the source document does not define a token/state.
