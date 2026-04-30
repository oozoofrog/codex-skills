#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
MANIFEST = REF / "manifest.json"
DESIGN_ROOT = REF / "design-md"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def by_slug():
    return {m["slug"]: m for m in load_manifest()}


def design_path(slug: str) -> Path:
    items = by_slug()
    if slug not in items:
        known = ", ".join(sorted(items))
        raise SystemExit(f"Unknown slug: {slug}\nKnown slugs: {known}")
    return ROOT / items[slug]["path"]


def cmd_list(args):
    rows = load_manifest()
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    for m in rows:
        print(f"{m['slug']:<14} {m['name']:<18} {m['category']} — {m['description']}")


def cmd_path(args):
    print(design_path(args.slug))


def cmd_show(args):
    text = design_path(args.slug).read_text(encoding="utf-8")
    if args.section:
        pattern = re.compile(args.section, re.IGNORECASE)
        lines = text.splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith("#") and pattern.search(line)]
        if not starts:
            raise SystemExit(f"No heading matched {args.section!r} in {args.slug}")
        start = starts[0]
        end = len(lines)
        level = len(lines[start]) - len(lines[start].lstrip("#"))
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("#"):
                next_level = len(lines[i]) - len(lines[i].lstrip("#"))
                if next_level <= level:
                    end = i
                    break
        print("\n".join(lines[start:end]))
    else:
        print(text, end="" if text.endswith("\n") else "\n")


def cmd_copy(args):
    src = design_path(args.slug)
    out = Path(args.out).expanduser().resolve()
    if out.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing file: {out}\nPass --force to overwrite.")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out)
    print(f"Copied {args.slug} DESIGN.md -> {out}")


def cmd_grep(args):
    flags = re.IGNORECASE if args.ignore_case else 0
    pattern = re.compile(args.pattern, flags)
    rows = [by_slug()[args.slug]] if args.slug else load_manifest()
    for m in rows:
        path = ROOT / m["path"]
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                print(f"{m['slug']}:{lineno}: {line}")


def cmd_verify(_args):
    errors = []
    for m in load_manifest():
        path = ROOT / m["path"]
        if not path.exists():
            errors.append(f"missing file: {path}")
            continue
        data = path.read_bytes()
        digest = __import__("hashlib").sha256(data).hexdigest()
        if digest != m["sha256"]:
            errors.append(f"sha256 mismatch: {m['slug']}")
        if len(data) != m["bytes"]:
            errors.append(f"byte count mismatch: {m['slug']}")
    if errors:
        print("VERIFY FAILED", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: {len(load_manifest())} DESIGN.md snapshots verified")


def main():
    parser = argparse.ArgumentParser(description="Use local awesome-design-md DESIGN.md snapshots")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("path")
    p.add_argument("slug")
    p.set_defaults(func=cmd_path)

    p = sub.add_parser("show")
    p.add_argument("slug")
    p.add_argument("--section", help="Regex matched against markdown headings")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("copy")
    p.add_argument("slug")
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("grep")
    p.add_argument("pattern")
    p.add_argument("--slug")
    p.add_argument("--ignore-case", "-i", action="store_true")
    p.set_defaults(func=cmd_grep)

    p = sub.add_parser("verify")
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
