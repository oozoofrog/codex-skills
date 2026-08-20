#!/usr/bin/env python3
"""List and selectively install skill packages from this repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


IGNORED_TREE_NAMES = {".DS_Store", "__pycache__"}
IGNORED_TREE_SUFFIXES = {".pyc", ".pyo"}


class ManagerError(Exception):
    """Expected selective-install error."""


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_destination() -> Path:
    codex_root = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    return codex_root / "skills"


def discover_skills(root: Path) -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.name.startswith(".") or not child.is_dir():
            continue
        if (child / "SKILL.md").is_file():
            packages[child.name] = child
    return packages


def tree_hash(root: Path) -> str:
    if not (root / "SKILL.md").is_file():
        raise ManagerError(f"Not a skill package: {root}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ManagerError(f"Symlinks are not supported in skill packages: {rel}")
        if any(part in IGNORED_TREE_NAMES for part in path.relative_to(root).parts):
            continue
        if path.is_dir() or path.suffix in IGNORED_TREE_SUFFIXES:
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        content = path.read_bytes()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(mode).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def package_status(source: Path, target: Path) -> tuple[str, str, str | None]:
    source_hash = tree_hash(source)
    if not target.exists():
        return "not-installed", source_hash, None
    if not target.is_dir() or not (target / "SKILL.md").is_file():
        return "conflict", source_hash, None
    installed_hash = tree_hash(target)
    return ("current" if installed_hash == source_hash else "different", source_hash, installed_hash)


def list_payload(root: Path, destination: Path) -> list[dict[str, Any]]:
    payload = []
    for name, source in discover_skills(root).items():
        status, source_hash, installed_hash = package_status(source, destination / name)
        payload.append(
            {
                "name": name,
                "status": status,
                "source_sha256": source_hash,
                "installed_sha256": installed_hash,
                "destination": str(destination / name),
            }
        )
    return payload


def command_list(args: argparse.Namespace) -> int:
    root = repository_root()
    destination = Path(args.dest).expanduser().resolve() if args.dest else default_destination().resolve()
    payload = list_payload(root, destination)
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 0
    if not payload:
        print("No top-level skill packages found.")
        return 0
    for item in payload:
        print(f"{item['name']}\t{item['status']}\t{item['destination']}")
    return 0


def copy_to_stage(source: Path, destination: Path, name: str) -> tuple[Path, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{name}.install-", dir=destination))
    stage = temp_root / name
    shutil.copytree(
        source,
        stage,
        ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", "*.pyo"),
    )
    return temp_root, stage


def install_one(source: Path, target: Path, *, update: bool, dry_run: bool) -> str:
    status, source_hash, _ = package_status(source, target)
    if status == "current":
        return "unchanged"
    if status == "conflict":
        raise ManagerError(f"Destination is not a valid installed skill: {target}")
    if status == "different" and not update:
        raise ManagerError(f"Destination differs; rerun with --update after review: {target}")
    action = "update" if status == "different" else "install"
    if dry_run:
        return f"would-{action}:{source_hash}"

    temp_root, stage = copy_to_stage(source, target.parent, target.name)
    try:
        if tree_hash(stage) != source_hash:
            raise ManagerError(f"Staged copy hash mismatch for {source.name}")
        if action == "install":
            os.replace(stage, target)
        else:
            backup = target.parent / f".{target.name}.backup-{secrets.token_hex(4)}"
            os.replace(target, backup)
            try:
                os.replace(stage, target)
            except Exception:
                if not target.exists() and backup.exists():
                    os.replace(backup, target)
                raise
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return action


def command_install(args: argparse.Namespace) -> int:
    root = repository_root()
    packages = discover_skills(root)
    unknown = [name for name in args.skills if name not in packages]
    if unknown:
        raise ManagerError(f"Unknown skill package(s): {', '.join(unknown)}")
    destination = Path(args.dest).expanduser().resolve() if args.dest else default_destination().resolve()
    results = []
    for name in args.skills:
        target = destination / name
        result = install_one(packages[name], target, update=args.update, dry_run=args.dry_run)
        results.append({"name": name, "result": result, "destination": str(target)})
    print(json.dumps(results, sort_keys=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="List top-level skill packages and install status")
    listing.add_argument("--dest", help="Skills directory; defaults to ${CODEX_HOME:-~/.codex}/skills")
    listing.add_argument("--format", choices=("text", "json"), default="text")
    listing.set_defaults(func=command_list)

    install = subparsers.add_parser("install", help="Install only the named skill packages")
    install.add_argument("skills", nargs="+", help="Top-level skill package names")
    install.add_argument("--dest", help="Skills directory; defaults to ${CODEX_HOME:-~/.codex}/skills")
    install.add_argument("--update", action="store_true", help="Replace a differing valid installation atomically")
    install.add_argument("--dry-run", action="store_true", help="Report actions without copying files")
    install.set_defaults(func=command_install)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ManagerError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
