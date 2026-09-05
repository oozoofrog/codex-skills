#!/usr/bin/env python3
"""List and atomically install the standalone gptpro Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_NAMES = ("gptpro",)
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
TERMINAL_STATUSES = {"revoked", "expired"}
TERMINAL_PACKAGE_PHASES = {"evaluated"}
LEGACY_DESCRIPTOR = ".gptpro-components.json"


class ManagerError(Exception):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_destination() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "skills"


def discover_skills(root: Path) -> dict[str, Path]:
    return {name: root / name for name in PACKAGE_NAMES if (root / name / "SKILL.md").is_file()}


def ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return (
        any(part in IGNORED_NAMES or " 2." in part for part in relative.parts)
        or path.suffix in IGNORED_SUFFIXES
    )


def package_files(root: Path) -> list[Path]:
    if not (root / "SKILL.md").is_file():
        raise ManagerError(f"Not a skill package: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ManagerError(f"Symlinks are not supported in skill packages: {path.relative_to(root)}")
        if path.is_file() and not ignored(path, root):
            result.append(path)
    return result


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in package_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(path.stat().st_mode)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def package_status(source: Path, target: Path) -> tuple[str, str, str | None]:
    source_hash = tree_hash(source)
    if not target.exists():
        return "not-installed", source_hash, None
    if not target.is_dir() or not (target / "SKILL.md").is_file():
        return "conflict", source_hash, None
    try:
        installed_hash = tree_hash(target)
    except ManagerError:
        return "conflict", source_hash, None
    return ("current" if installed_hash == source_hash else "update-available", source_hash, installed_hash)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_runtime_evidence(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except (ValueError, RecursionError) as exc:
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_INVALID: diagnostic-status returned invalid JSON") from exc
    tunnel = value.get("tunnel") if isinstance(value, dict) else None
    package = value.get("package") if isinstance(value, dict) else None
    if not isinstance(tunnel, dict):
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_INVALID: diagnostic-status omitted Tunnel evidence")
    if not isinstance(package, dict):
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_INVALID: diagnostic-status omitted package evidence")
    return {
        "recorded_status": tunnel.get("recorded_status"),
        "controller_lease": tunnel.get("controller_lease"),
        "exact_child_stop_proven": tunnel.get("exact_child_stop_proven") is True,
        "package_binding": tunnel.get("package_binding"),
        "package_availability": package.get("availability"),
        "package_phase": package.get("phase"),
    }


def legacy_mcp_evidence(destination: Path, *, handoff_dir: Path | None = None) -> dict[str, Any]:
    component = destination / "gptpro-mcp"
    if not component.exists():
        return {"applicable": False, "safe_to_remove": True}
    if handoff_dir is None:
        raise ManagerError(
            "GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED: --legacy-handoff-dir must identify the exact terminal package"
        )
    entrypoint = component / "scripts" / "gptpro.py"
    if not entrypoint.is_file():
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_INVALID: installed gptpro-mcp is incomplete")
    command = [sys.executable, str(entrypoint), "--error-format", "json", "diagnostic-status"]
    if not handoff_dir.is_absolute():
        raise ManagerError("GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED: --legacy-handoff-dir must be absolute")
    command += ["--handoff-dir", str(handoff_dir)]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_UNAVAILABLE: installed diagnostic-status could not run") from exc
    if result.returncode != 0:
        raise ManagerError("GPTPRO_LEGACY_MCP_EVIDENCE_UNAVAILABLE: installed diagnostic-status failed")
    evidence = _parse_runtime_evidence(result.stdout)
    safe = (
        evidence["recorded_status"] in TERMINAL_STATUSES
        and evidence["controller_lease"] in {"not_live", "absent"}
        and evidence["exact_child_stop_proven"]
        and evidence["package_binding"] == "same_package"
        and evidence["package_availability"] == "verified"
        and evidence["package_phase"] in TERMINAL_PACKAGE_PHASES
    )
    return {"applicable": True, "safe_to_remove": safe, **evidence}


def require_legacy_terminal(destination: Path, *, handoff_dir: Path | None = None) -> dict[str, Any]:
    evidence = legacy_mcp_evidence(destination, handoff_dir=handoff_dir)
    if not evidence["safe_to_remove"]:
        raise ManagerError(
            "GPTPRO_LEGACY_MCP_ACTIVE: the installed MCP/Tunnel runtime lacks terminal authorization and exact-child stop evidence"
        )
    return evidence


def _copy_package(source: Path, target: Path) -> None:
    target.mkdir(mode=0o700, parents=True)
    directories = {path.parent.relative_to(source) for path in package_files(source)}
    for relative in sorted(directories, key=lambda item: (len(item.parts), item.as_posix())):
        (target / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    for source_file in package_files(source):
        relative = source_file.relative_to(source)
        destination = target / relative
        destination.write_bytes(source_file.read_bytes())
        os.chmod(destination, stat.S_IMODE(source_file.stat().st_mode))


def _trash_root() -> Path:
    path = Path.home() / ".Trash"
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def move_to_trash(path: Path, *, label: str) -> Path | None:
    if not path.exists() and not path.is_symlink():
        return None
    trash = _trash_root()
    trash.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = trash / f"{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    os.replace(path, destination)
    return destination


def atomic_install(source: Path, target: Path) -> None:
    destination = target.parent
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = destination / f".{target.name}.stage-{secrets.token_hex(6)}"
    backup = destination / f".{target.name}.backup-{secrets.token_hex(6)}"
    try:
        _copy_package(source, stage)
        if tree_hash(stage) != tree_hash(source):
            raise ManagerError("GPTPRO_INSTALL_HASH_MISMATCH: staged package differs from source")
        if target.exists():
            os.replace(target, backup)
        os.replace(stage, target)
        if tree_hash(target) != tree_hash(source):
            raise ManagerError("GPTPRO_INSTALL_HASH_MISMATCH: installed package differs from source")
    except BaseException:
        if backup.exists():
            if target.exists():
                shutil.rmtree(target)
            os.replace(backup, target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    # Delete the old install only after publication and verification succeeded.
    # If rollback itself fails, its backup must remain available for recovery.
    if backup.exists():
        shutil.rmtree(backup)


def install(
    name: str,
    *,
    destination: Path,
    update: bool,
    dry_run: bool,
    legacy_handoff_dir: Path | None,
) -> dict[str, Any]:
    if name not in PACKAGE_NAMES:
        raise ManagerError(f"Unknown package: {name}")
    source = repository_root() / name
    target = destination / name
    status_value, source_hash, installed_hash = package_status(source, target)
    if status_value == "conflict":
        raise ManagerError(f"Install target is not a valid gptpro Skill: {target}")
    if status_value == "update-available" and not update:
        raise ManagerError("An installed gptpro differs; pass --update to replace it atomically")
    transition = require_legacy_terminal(destination, handoff_dir=legacy_handoff_dir)
    action = "none" if status_value == "current" else "install" if status_value == "not-installed" else "update"
    result: dict[str, Any] = {
        "ok": True,
        "operation": "install",
        "name": name,
        "action": action,
        "dry_run": dry_run,
        "source_sha256": source_hash,
        "installed_sha256_before": installed_hash,
        "legacy_mcp": transition,
        "legacy_removed": False,
        "trash": [],
    }
    if dry_run:
        result["installed_sha256_after"] = source_hash if action != "none" else installed_hash
        return result
    if action != "none":
        atomic_install(source, target)
    if transition["applicable"]:
        moved = move_to_trash(destination / "gptpro-mcp", label="gptpro-mcp-retired")
        if moved:
            result["trash"].append(str(moved))
        descriptor = move_to_trash(destination / LEGACY_DESCRIPTOR, label="gptpro-components-retired")
        if descriptor:
            result["trash"].append(str(descriptor))
        result["legacy_removed"] = True
    elif (destination / LEGACY_DESCRIPTOR).exists():
        descriptor = move_to_trash(destination / LEGACY_DESCRIPTOR, label="gptpro-components-retired")
        if descriptor:
            result["trash"].append(str(descriptor))
            result["legacy_removed"] = True
    result["installed_sha256_after"] = tree_hash(target)
    if result["installed_sha256_after"] != source_hash:
        raise ManagerError("GPTPRO_INSTALL_HASH_MISMATCH: installed tree differs after update")
    return result


def list_packages(destination: Path) -> list[dict[str, Any]]:
    rows = []
    for name, source in discover_skills(repository_root()).items():
        status_value, source_hash, installed_hash = package_status(source, destination / name)
        rows.append(
            {
                "name": name,
                "status": status_value,
                "source_sha256": source_hash,
                "installed_sha256": installed_hash,
                "source": str(source),
                "destination": str(destination / name),
            }
        )
    return rows


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--dest", default=str(default_destination()))
    listing.add_argument("--format", choices=("table", "json"), default="table")
    installer = commands.add_parser("install")
    installer.add_argument("name", choices=PACKAGE_NAMES)
    installer.add_argument("--dest", default=str(default_destination()))
    installer.add_argument("--update", action="store_true")
    installer.add_argument("--dry-run", action="store_true")
    installer.add_argument("--legacy-handoff-dir")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        destination = Path(args.dest).expanduser().resolve()
        if args.command == "list":
            rows = list_packages(destination)
            if args.format == "json":
                print(json.dumps(rows, sort_keys=True, indent=2))
            else:
                for row in rows:
                    print(f"{row['name']}: {row['status']} ({row['destination']})")
            return 0
        result = install(
            args.name,
            destination=destination,
            update=args.update,
            dry_run=args.dry_run,
            legacy_handoff_dir=Path(args.legacy_handoff_dir).expanduser().resolve() if args.legacy_handoff_dir else None,
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ManagerError, OSError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
