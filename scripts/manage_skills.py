#!/usr/bin/env python3
"""List and atomically install the Desktop gptpro component pair."""

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
import tempfile
import pwd
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IGNORED_TREE_NAMES = {".DS_Store", "__pycache__"}
IGNORED_TREE_SUFFIXES = {".pyc", ".pyo"}
PACKAGE_NAMES = ("gptpro", "gptpro-mcp")
DESCRIPTOR_SCHEMA = "gptpro-install-descriptor-v1"
DESCRIPTOR_NAME = ".gptpro-components.json"
TERMINAL_MCP_STATUSES = {"revoked", "expired"}
SHA256_HEX_LENGTH = 64
DESKTOP_BINDING_CONTRACT = "gptpro-desktop-app-binding-v1"


class ManagerError(Exception):
    """Expected gptpro installation error."""


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_destination() -> Path:
    codex_root = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    return codex_root / "skills"


def desktop_state_root() -> Path:
    try:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, ImportError, TypeError) as exc:
        raise ManagerError("DESKTOP_STATE_HOME_UNAVAILABLE: canonical account home is unavailable") from exc
    if not home.is_absolute() or home == Path(home.anchor):
        raise ManagerError("DESKTOP_STATE_HOME_UNSAFE: canonical account home is invalid")
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "gptpro" / "desktop" / "v2"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(xdg) if xdg else home / ".local" / "state") / "gptpro" / "desktop" / "v2"


def private_directory(path: Path) -> Path:
    runtime_root = repository_root() / "gptpro-mcp"
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    try:
        from runtime.gptpro_desktop.state import DesktopStateError, secure_directory

        return secure_directory(Path(path), create=True)
    except DesktopStateError as exc:
        raise ManagerError(f"{exc.code}: {exc.message}") from exc


def write_private_file(path: Path, data: bytes) -> None:
    runtime_root = repository_root() / "gptpro-mcp"
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    try:
        from runtime.gptpro_desktop.state import DesktopStateError, atomic_write_private

        atomic_write_private(Path(path), data)
    except DesktopStateError as exc:
        raise ManagerError(f"{exc.code}: {exc.message}") from exc


def read_private_app_id(path: Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ManagerError("DESKTOP_APP_ID_FILE_UNSAFE: --app-id-file must be absolute")
    metadata = candidate.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > 4096
    ):
        raise ManagerError("DESKTOP_APP_ID_FILE_UNSAFE: app ID file must be owner-only mode 0600")
    value = candidate.read_text(encoding="utf-8").strip()
    if not value or len(value) > 512 or any(ord(character) < 33 for character in value):
        raise ManagerError("DESKTOP_APP_ID_INVALID: app ID must be one non-empty printable token")
    return value


def discover_skills(root: Path) -> dict[str, Path]:
    return {
        name: root / name
        for name in PACKAGE_NAMES
        if (root / name / "SKILL.md").is_file()
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def descriptor_path(destination: Path) -> Path:
    return destination / DESCRIPTOR_NAME


def load_descriptor(destination: Path) -> dict[str, Any]:
    path = descriptor_path(destination)
    if not path.exists():
        return {"schema": DESCRIPTOR_SCHEMA, "components": {}}
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or metadata.st_size > 64 * 1024
    ):
        raise ManagerError(f"Unsafe install descriptor: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ManagerError(f"Invalid install descriptor: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != DESCRIPTOR_SCHEMA:
        raise ManagerError(f"Unsupported install descriptor: {path}")
    components = value.get("components")
    if not isinstance(components, dict):
        raise ManagerError(f"Invalid install descriptor: {path}")
    return value


def write_descriptor(destination: Path, value: dict[str, Any]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    path = descriptor_path(destination)
    descriptor = dict(value)
    descriptor["schema"] = DESCRIPTOR_SCHEMA
    descriptor["updated_at"] = utc_now()
    payload = (json.dumps(descriptor, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor_fd, temp_name = tempfile.mkstemp(prefix=f".{DESCRIPTOR_NAME}.", dir=destination)
    temp_path = Path(temp_name)
    try:
        os.fchmod(descriptor_fd, 0o600)
        with os.fdopen(descriptor_fd, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def component_capabilities(target: Path) -> dict[str, Any] | None:
    entrypoint = target / "scripts" / "gptpro.py"
    if not entrypoint.is_file():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(entrypoint), "capabilities", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
        value = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def installed_component_binding_verified(
    destination: Path, target: Path, *, name: str
) -> bool:
    """Verify the exact installed tree selected by the owner-only descriptor."""

    path = descriptor_path(destination)
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            return False
        descriptor = load_descriptor(destination)
        components = descriptor.get("components")
        selected = components.get(name) if isinstance(components, dict) else None
        if not isinstance(selected, dict):
            return False
        entrypoint = selected.get("entrypoint")
        expected_tree = selected.get("tree_sha256")
        expected_entrypoint = (target / "scripts" / "gptpro.py").resolve()
        return (
            isinstance(entrypoint, str)
            and Path(entrypoint).is_absolute()
            and Path(entrypoint).resolve() == expected_entrypoint
            and isinstance(expected_tree, str)
            and len(expected_tree) == SHA256_HEX_LENGTH
            and all(character in "0123456789abcdef" for character in expected_tree)
            and tree_hash(target) == expected_tree
        )
    except (ManagerError, OSError):
        return False


def component_runtime_evidence(target: Path) -> dict[str, Any]:
    entrypoint = target / "scripts" / "gptpro.py"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(entrypoint),
                "--error-format",
                "json",
                "diagnostic-status",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
        value = json.loads(result.stdout) if result.returncode == 0 else None
        tunnel = value.get("tunnel") if isinstance(value, dict) else None
        status_value = tunnel.get("recorded_status") if isinstance(tunnel, dict) else None
        stop_proven = tunnel.get("exact_child_stop_proven") if isinstance(tunnel, dict) else None
        session_binding = (
            tunnel.get("migration_session_binding_sha256")
            if isinstance(tunnel, dict)
            else None
        )
        if not (
            isinstance(session_binding, str)
            and len(session_binding) == SHA256_HEX_LENGTH
            and all(character in "0123456789abcdef" for character in session_binding)
        ):
            session_binding = None
        return {
            "status": status_value if isinstance(status_value, str) else "unknown",
            "exact_child_stop_proven": stop_proven is True,
            "migration_session_binding_sha256": session_binding,
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, RecursionError):
        return {
            "status": "unknown",
            "exact_child_stop_proven": False,
            "migration_session_binding_sha256": None,
        }


def _run_transition_command(
    component: Path,
    *,
    operation: str,
    handoff_dir: Path,
    previous_base_entrypoint: Path,
    next_base_entrypoint: Path,
    destination: Path,
    confirm_package_unavailable: bool,
    confirm_residual_ownership: bool = False,
) -> dict[str, Any]:
    entrypoint = component / "scripts" / "gptpro.py"
    command = [
        sys.executable,
        str(entrypoint),
        "--error-format",
        "json",
        "--component-descriptor",
        str(descriptor_path(destination)),
        operation,
        "--handoff-dir",
        str(handoff_dir),
        "--previous-base-entrypoint",
        str(previous_base_entrypoint),
        "--next-base-entrypoint",
        str(next_base_entrypoint),
        "--json",
    ]
    if confirm_package_unavailable:
        command.append("--confirm-package-unavailable")
    if confirm_residual_ownership:
        command.append("--confirm-residual-ownership")
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManagerError(
            "GPTPRO_MCP_TRANSITION_EVIDENCE_UNAVAILABLE: the gptpro-mcp transition "
            "evaluator could not be executed safely"
        ) from exc
    raw = result.stdout if result.returncode == 0 else result.stderr
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ManagerError(
            "GPTPRO_MCP_TRANSITION_EVIDENCE_UNAVAILABLE: the gptpro-mcp transition "
            "evaluator returned invalid JSON"
        ) from exc
    if result.returncode != 0:
        error = value.get("error") if isinstance(value, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        raise ManagerError(
            f"{code or 'GPTPRO_MCP_TRANSITION_EVIDENCE_UNAVAILABLE'}: "
            f"{message or 'the transition evaluator rejected the request'}"
        )
    if not isinstance(value, dict) or value.get("operation") != operation:
        raise ManagerError(
            "GPTPRO_MCP_TRANSITION_EVIDENCE_UNAVAILABLE: the transition evaluator "
            "returned an unsupported contract"
        )
    return value


def _raise_transition_decision(evidence: dict[str, Any]) -> None:
    code = evidence.get("code")
    if not isinstance(code, str):
        code = "GPTPRO_MCP_TRANSITION_BLOCKED"
    explanations = {
        "GPTPRO_LEGACY_PACKAGE_NOT_TERMINAL": (
            "the exact legacy package and authorization must be terminal before the base update"
        ),
        "GPTPRO_MCP_RESIDUAL_RECEIPT_STALE": (
            "the residual ownership receipt no longer matches runtime, package, or component evidence"
        ),
        "GPTPRO_MCP_CONTROLLER_STILL_LIVE": (
            "the exact legacy controller lease is still live"
        ),
        "GPTPRO_MCP_ORPHAN_CLEARANCE_REQUIRED": (
            "exact-child stop is unproven and attended orphan-process clearance is absent"
        ),
    }
    raise ManagerError(f"{code}: {explanations.get(code, 'the legacy MCP transition is not safe')}")


def require_mcp_transition_owner(
    source: Path,
    target: Path,
    destination: Path,
    *,
    legacy_handoff_dir: Path | None,
    adopt_residual_mcp_state: bool,
    confirm_legacy_package_unavailable: bool,
    dry_run: bool,
) -> dict[str, Any] | None:
    old_has_runtime = (target / "runtime" / "gptpro_mcp").is_dir()
    new_has_runtime = (source / "runtime" / "gptpro_mcp").is_dir()
    if not old_has_runtime or new_has_runtime:
        return None
    evidence = component_runtime_evidence(target)
    status_value = evidence["status"]
    if status_value == "absent":
        return None
    if legacy_handoff_dir is None:
        raise ManagerError(
            "GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED: pass --legacy-handoff-dir for the "
            "exact legacy package before replacing the integrated MCP runtime"
        )
    if not legacy_handoff_dir.is_absolute():
        raise ManagerError(
            "GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED: --legacy-handoff-dir must be absolute"
        )
    source_mcp = repository_root() / "gptpro-mcp"
    source_evidence = _run_transition_command(
        source_mcp,
        operation="transition-evidence",
        handoff_dir=legacy_handoff_dir,
        previous_base_entrypoint=target / "scripts" / "gptpro.py",
        next_base_entrypoint=source / "scripts" / "gptpro.py",
        destination=destination,
        confirm_package_unavailable=confirm_legacy_package_unavailable,
    )
    if source_evidence.get("decision") == "safe_exact_terminal":
        return {
            "decision": "safe_exact_terminal",
            "exact_child_stop_proven": True,
            "ownership_transferred": False,
            "residual_receipt_sha256": None,
        }
    if source_evidence.get("decision") == "blocked":
        _raise_transition_decision(source_evidence)
    mcp_target = destination / "gptpro-mcp"
    mcp_capabilities = component_capabilities(mcp_target)
    if (
        not isinstance(mcp_capabilities, dict)
        or mcp_capabilities.get("contract") != "gptpro-component-capabilities-v1"
        or mcp_capabilities.get("component") != "gptpro-mcp"
        or mcp_capabilities.get("mcp_runtime") is not True
        or not isinstance(mcp_capabilities.get("version"), str)
        or not installed_component_binding_verified(
            destination, mcp_target, name="gptpro-mcp"
        )
    ):
        raise ManagerError(
            "GPTPRO_MCP_COMPONENT_REQUIRED: legacy MCP state without verified exact-child "
            "stop evidence must remain owned by a compatible installed gptpro-mcp component "
            "before the base update"
        )
    owner_evidence = _run_transition_command(
        mcp_target,
        operation="transition-evidence",
        handoff_dir=legacy_handoff_dir,
        previous_base_entrypoint=target / "scripts" / "gptpro.py",
        next_base_entrypoint=source / "scripts" / "gptpro.py",
        destination=destination,
        confirm_package_unavailable=confirm_legacy_package_unavailable,
    )
    decision = owner_evidence.get("decision")
    if decision == "safe_exact_terminal":
        return {
            "decision": "safe_exact_terminal",
            "exact_child_stop_proven": True,
            "ownership_transferred": False,
            "residual_receipt_sha256": None,
        }
    if decision == "safe_owned_residual":
        return {
            "decision": "safe_owned_residual",
            "exact_child_stop_proven": owner_evidence.get("exact_child_stop_proven") is True,
            "ownership_transferred": owner_evidence.get("ownership_transferred") is True,
            "residual_receipt_sha256": owner_evidence.get("residual_receipt_sha256"),
        }
    if decision == "adoption_required":
        if not adopt_residual_mcp_state:
            raise ManagerError(
                "GPTPRO_MCP_RESIDUAL_ADOPTION_REQUIRED: exact-child stop is unproven; "
                "review transition-evidence and explicitly pass --adopt-residual-mcp-state"
            )
        if dry_run:
            return {
                "decision": "would_adopt_residual",
                "exact_child_stop_proven": False,
                "ownership_transferred": False,
                "residual_receipt_sha256": None,
            }
        adopted = _run_transition_command(
            mcp_target,
            operation="residual-adopt",
            handoff_dir=legacy_handoff_dir,
            previous_base_entrypoint=target / "scripts" / "gptpro.py",
            next_base_entrypoint=source / "scripts" / "gptpro.py",
            destination=destination,
            confirm_package_unavailable=confirm_legacy_package_unavailable,
            confirm_residual_ownership=True,
        )
        if (
            adopted.get("decision") != "safe_owned_residual"
            or adopted.get("ownership_transferred") is not True
            or not isinstance(adopted.get("residual_receipt_sha256"), str)
        ):
            raise ManagerError(
                "GPTPRO_MCP_RESIDUAL_RECEIPT_STALE: residual ownership did not revalidate"
            )
        return {
            "decision": "safe_owned_residual",
            "exact_child_stop_proven": adopted.get("exact_child_stop_proven") is True,
            "ownership_transferred": True,
            "residual_receipt_sha256": adopted["residual_receipt_sha256"],
        }
    _raise_transition_decision(owner_evidence)
    raise AssertionError("unreachable")


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
        print("The gptpro Skill package was not found.")
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


def record_component_bindings(destination: Path, names: list[str]) -> None:
    descriptor = load_descriptor(destination)
    components = dict(descriptor.get("components", {}))
    for name in names:
        target = destination / name
        if not target.is_dir() or not (target / "SKILL.md").is_file():
            raise ManagerError(f"Installed component is unavailable: {name}")
        components[name] = {
            "entrypoint": str((target / "scripts" / "gptpro.py").resolve()),
            "tree_sha256": tree_hash(target),
        }
    descriptor["components"] = components
    write_descriptor(destination, descriptor)


def command_install(args: argparse.Namespace) -> int:
    root = repository_root()
    packages = discover_skills(root)
    if args.skill not in packages:
        raise ManagerError(f"Unknown skill package: {args.skill}")
    destination = Path(args.dest).expanduser().resolve() if args.dest else default_destination().resolve()
    target = destination / args.skill
    results: list[dict[str, Any]] = []
    if args.skill == "gptpro":
        companion_target = destination / "gptpro-mcp"
        companion_result = install_one(
            packages["gptpro-mcp"],
            companion_target,
            update=args.update,
            dry_run=args.dry_run,
        )
        results.append(
            {
                "name": "gptpro-mcp",
                "result": companion_result,
                "destination": str(companion_target),
                "installed_as": "required-read-only-companion",
            }
        )
        if not args.dry_run:
            record_component_bindings(destination, ["gptpro-mcp"])
    delegated_evidence = None
    if args.skill == "gptpro" and target.exists() and args.update:
        delegated_evidence = require_mcp_transition_owner(
            packages[args.skill],
            target,
            destination,
            legacy_handoff_dir=(
                Path(args.legacy_handoff_dir).expanduser()
                if args.legacy_handoff_dir
                else None
            ),
            adopt_residual_mcp_state=args.adopt_residual_mcp_state,
            confirm_legacy_package_unavailable=args.confirm_legacy_package_unavailable,
            dry_run=args.dry_run,
        )
    result = install_one(packages[args.skill], target, update=args.update, dry_run=args.dry_run)
    if not args.dry_run:
        binding_names = [args.skill]
        if args.skill == "gptpro":
            binding_names.append("gptpro-mcp")
        elif (destination / "gptpro").is_dir():
            binding_names.append("gptpro")
        record_component_bindings(destination, binding_names)
        descriptor = load_descriptor(destination)
        if (
            delegated_evidence is not None
            and delegated_evidence.get("decision") == "safe_owned_residual"
        ):
            descriptor["legacy_mcp_handoff"] = {
                "schema": "gptpro-residual-handoff-summary-v1",
                "owner": "gptpro-mcp",
                "residual_receipt_sha256": delegated_evidence[
                    "residual_receipt_sha256"
                ],
                "recorded_at": utc_now(),
            }
        elif args.skill == "gptpro" and delegated_evidence is not None:
            descriptor.pop("legacy_mcp_handoff", None)
        write_descriptor(destination, descriptor)
    results.append({"name": args.skill, "result": result, "destination": str(target)})
    if delegated_evidence is not None:
        results[-1]["transition"] = delegated_evidence
    print(json.dumps(results, sort_keys=True, indent=2))
    return 0


def command_desktop_bind(args: argparse.Namespace) -> int:
    app_id = read_private_app_id(Path(args.app_id_file))
    app_id_sha256 = hashlib.sha256(app_id.encode("utf-8")).hexdigest()
    state_root = (
        Path(args.state_root).expanduser().resolve()
        if args.state_root
        else desktop_state_root()
    )
    plugin_root = state_root / "companion" / "gptpro-desktop-app"
    binding_path = state_root / "companion" / "app-binding.json"
    result = {
        "ok": True,
        "operation": "desktop-bind",
        "dry_run": bool(args.dry_run),
        "write_performed": False,
        "raw_app_id_exposed": False,
        "app_id_sha256": app_id_sha256,
        "plugin_root": str(plugin_root),
        "binding_path": str(binding_path),
    }
    if args.dry_run:
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    if not args.confirm_bind:
        raise ManagerError(
            "DESKTOP_APP_BIND_CONFIRMATION_REQUIRED: review the dry-run app ID hash and pass --confirm-bind"
        )
    private_directory(plugin_root / ".codex-plugin")
    plugin_manifest = {
        "name": "gptpro-desktop-app",
        "version": "0.1.0",
        "description": "Local apps-only binding for the user's read-only ChatGPT gptpro app.",
        "author": {"name": "local-user"},
        "apps": "./.app.json",
        "interface": {
            "displayName": "GPT Pro Desktop App Binding",
            "shortDescription": "Local ChatGPT app binding for gptpro",
            "longDescription": (
                "Owner-only local binding used by gptpro Desktop consultations. "
                "It contains no Skill, MCP server, shell tool, or repository permission."
            ),
            "developerName": "local-user",
            "category": "Developer Tools",
            "capabilities": ["Interactive"],
            "defaultPrompt": ["Use $gptpro for an explicitly requested Desktop consultation."],
        },
    }
    app_manifest = {
        "apps": {
            "gpt-pro-collaborator": {
                "id": app_id,
                "category": "Developer Tools",
            }
        }
    }
    write_private_file(
        plugin_root / ".codex-plugin" / "plugin.json",
        (json.dumps(plugin_manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    write_private_file(
        plugin_root / ".app.json",
        (json.dumps(app_manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    binding = {
        "schema": DESKTOP_BINDING_CONTRACT,
        "recorded_at": utc_now(),
        "app_key": "gpt-pro-collaborator",
        "app_id_sha256": app_id_sha256,
        "plugin_root": str(plugin_root),
        "plugin_manifest_sha256": hashlib.sha256(
            (json.dumps(plugin_manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
        ).hexdigest(),
        "raw_app_id_stored_only_in_private_app_manifest": True,
    }
    write_private_file(
        binding_path,
        (json.dumps(binding, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    result.update(
        {
            "write_performed": True,
            "binding_contract": DESKTOP_BINDING_CONTRACT,
            "next_action": (
                "Add or install the generated local apps-only plugin once in Codex, then keep the same "
                "binding for every repository. Do not copy the raw app ID into repository files."
            ),
        }
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="List gptpro install status")
    listing.add_argument("--dest", help="Skills directory; defaults to ${CODEX_HOME:-~/.codex}/skills")
    listing.add_argument("--format", choices=("text", "json"), default="text")
    listing.set_defaults(func=command_list)

    install = subparsers.add_parser("install", help="Install or update one GPT Pro Skill")
    install.add_argument("skill", choices=PACKAGE_NAMES, help="Skill package name")
    install.add_argument("--dest", help="Skills directory; defaults to ${CODEX_HOME:-~/.codex}/skills")
    install.add_argument("--update", action="store_true", help="Replace a differing valid installation atomically")
    install.add_argument("--dry-run", action="store_true", help="Report actions without copying files")
    install.add_argument(
        "--legacy-handoff-dir",
        help="Exact absolute legacy MCP package used for split-transition evidence",
    )
    install.add_argument(
        "--adopt-residual-mcp-state",
        action="store_true",
        help="Explicitly transfer unresolved terminal lifecycle responsibility to gptpro-mcp",
    )
    install.add_argument(
        "--confirm-legacy-package-unavailable",
        action="store_true",
        help="Confirm that the exact legacy package is unavailable or damaged after review",
    )
    install.set_defaults(func=command_install)

    desktop_bind = subparsers.add_parser(
        "desktop-bind",
        help="Create an owner-only apps-only companion plugin from one private app ID file",
    )
    desktop_bind.add_argument("--app-id-file", required=True)
    desktop_bind.add_argument("--state-root", help=argparse.SUPPRESS)
    desktop_bind.add_argument("--dry-run", action="store_true")
    desktop_bind.add_argument("--confirm-bind", action="store_true")
    desktop_bind.set_defaults(func=command_desktop_bind)
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
