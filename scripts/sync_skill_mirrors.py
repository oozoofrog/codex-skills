#!/usr/bin/env python3
"""Check or atomically regenerate standalone Skill Plugin mirrors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Any

PACKAGES = ("gptpro", "gptpro-mcp")
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


class SyncError(Exception):
    """Expected mirror synchronization failure."""


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def package_files(root: Path) -> dict[str, tuple[int, str]]:
    if not (root / "SKILL.md").is_file():
        raise SyncError(f"Not a Skill package: {root}")
    files: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise SyncError(f"Symlink is not allowed in Skill package: {relative.as_posix()}")
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_dir() or path.suffix in IGNORED_SUFFIXES:
            continue
        files[relative.as_posix()] = (
            path.stat().st_mode & 0o777,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return files


def mirror_paths(root: Path, name: str) -> tuple[Path, Path] | None:
    source = root / name
    if not (source / "SKILL.md").is_file():
        return None
    mirror = root / "plugins" / name / "skills" / name
    return source, mirror


def sync_one(source: Path, mirror: Path, *, write: bool) -> dict[str, Any]:
    source_files = package_files(source)
    mirror_files = package_files(mirror) if (mirror / "SKILL.md").is_file() else {}
    current = source_files == mirror_files
    result: dict[str, Any] = {
        "name": source.name,
        "source": str(source),
        "mirror": str(mirror),
        "current": current,
        "write_performed": False,
    }
    if current or not write:
        return result
    mirror.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{source.name}.mirror-", dir=mirror.parent))
    staged = temporary / source.name
    backup = mirror.parent / f".{source.name}.mirror-backup-{secrets.token_hex(4)}"
    try:
        shutil.copytree(
            source,
            staged,
            copy_function=shutil.copy2,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", "*.pyo"),
        )
        if package_files(staged) != source_files:
            raise SyncError(f"Staged mirror differs from source: {source.name}")
        if mirror.exists():
            os.replace(mirror, backup)
        try:
            os.replace(staged, mirror)
        except Exception:
            if backup.exists() and not mirror.exists():
                os.replace(backup, mirror)
            raise
        if package_files(mirror) != source_files:
            raise SyncError(f"Installed mirror differs from source: {source.name}")
        if backup.exists():
            shutil.rmtree(backup)
        result.update({"current": True, "write_performed": True})
        return result
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Atomically replace differing mirrors")
    parser.add_argument("--package", choices=PACKAGES, action="append", default=[])
    args = parser.parse_args(argv)
    root = repository_root()
    selected = tuple(args.package) if args.package else PACKAGES
    try:
        results = []
        for name in selected:
            paths = mirror_paths(root, name)
            if paths is None:
                if args.package:
                    raise SyncError(f"Skill package is absent: {name}")
                continue
            results.append(sync_one(*paths, write=args.write))
        print(json.dumps({"ok": all(item["current"] for item in results), "results": results}, indent=2))
        return 0 if all(item["current"] for item in results) else 1
    except (OSError, SyncError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
