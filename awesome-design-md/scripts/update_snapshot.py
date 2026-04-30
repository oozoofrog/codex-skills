#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
REPO_URL = "https://github.com/voltagent/awesome-design-md"
RAW_README = "https://raw.githubusercontent.com/voltagent/awesome-design-md/main/README.md"
DESIGN_BASE = "https://getdesign.md/design-md/{slug}/DESIGN.md"


def fetch(url: str) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "Codex awesome-design-md skill updater"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = resp.read()
        headers = {k.lower(): v for k, v in resp.headers.items()}
    return data, headers


def parse_readme(text: str):
    category = "Uncategorized"
    entries = []
    seen = set()
    for line in text.splitlines():
        if line.startswith("### "):
            category = line[4:].strip()
            continue
        m = re.match(r'- \[\*\*(.+?)\*\*\]\(https://getdesign\.md/([^/]+)/design-md\)\s*-\s*(.+)', line)
        if not m:
            continue
        name, slug, desc = m.groups()
        if slug in seen:
            continue
        seen.add(slug)
        entries.append({"slug": slug, "name": name, "description": desc.strip(), "category": category})
    return entries


def repo_head() -> str:
    try:
        out = subprocess.check_output(["git", "ls-remote", REPO_URL, "refs/heads/main"], text=True, timeout=20)
        return out.split()[0]
    except Exception:
        return "unknown"


def write_catalog(manifest):
    categories = {}
    for m in manifest:
        categories.setdefault(m["category"], []).append(m)
    started = min(m["downloaded_at"] for m in manifest)
    finished = max(m["downloaded_at"] for m in manifest)
    lines = [
        "# Awesome DESIGN.md Catalog",
        "",
        "이 카탈로그는 `references/manifest.json`과 원본 `references/design-md/<slug>/DESIGN.md` 스냅샷의 사람이 읽기 쉬운 색인입니다.",
        "",
        f"- Snapshot count: {len(manifest)}",
        f"- Source: {REPO_URL}",
        f"- Downloaded at: {started} → {finished}",
        "",
    ]
    for category, items in categories.items():
        lines += [f"## {category}", "", "| Slug | Name | Format | Bytes | Description |", "|---|---|---:|---:|---|"]
        for m in items:
            desc = m["description"].replace("|", "\\|")
            lines.append(f"| `{m['slug']}` | {m['name']} | {m['format']} | {m['bytes']} | {desc} |")
        lines.append("")
    (REF / "catalog.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_source(manifest, head: str):
    started = min(m["downloaded_at"] for m in manifest)
    finished = max(m["downloaded_at"] for m in manifest)
    text = f"""# Source snapshot

This skill snapshots VoltAgent's awesome-design-md / getdesign.md design-system documents for local Codex use.

- Source repository: {REPO_URL}
- Source remote: {REPO_URL}
- Repository HEAD: `{head}`
- Snapshot downloaded at: {started} → {finished}
- Hosted source pattern: `https://getdesign.md/design-md/<slug>/DESIGN.md`
- Snapshot scope: slugs listed in the source repository README collection at the repository HEAD above.
- Snapshot count: {len(manifest)}

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
"""
    (REF / "source.md").write_text(text, encoding="utf-8")


def main():
    readme_bytes, _ = fetch(RAW_README)
    entries = parse_readme(readme_bytes.decode("utf-8", "replace"))
    if not entries:
        raise SystemExit("No DESIGN.md entries found in source README")

    manifest = []
    for e in entries:
        slug = e["slug"]
        data, headers = fetch(DESIGN_BASE.format(slug=slug))
        rel = Path("references") / "design-md" / slug / "DESIGN.md"
        out = ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        first = data.decode("utf-8", "replace").splitlines()[0] if data else ""
        manifest.append({
            **e,
            "url": DESIGN_BASE.format(slug=slug),
            "path": str(rel),
            "format": "yaml-frontmatter" if first.strip() == "---" else "markdown",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": headers.get("content-type"),
            "etag": headers.get("etag"),
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        print(f"updated {slug} {len(data)} bytes")

    (REF / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    head = repo_head()
    write_catalog(manifest)
    write_source(manifest, head)
    print(f"OK: updated {len(manifest)} snapshots")


if __name__ == "__main__":
    main()
