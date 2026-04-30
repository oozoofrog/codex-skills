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
DESIGN_ROOT = REF / "design-md"
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
    (REF / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"OK: updated {len(manifest)} snapshots")


if __name__ == "__main__":
    main()
