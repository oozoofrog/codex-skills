"""Installer-selected component compatibility checks without path discovery."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


CAPABILITIES_CONTRACT = "gptpro-component-capabilities-v1"
CONTEXT_EXPORT_CONTRACT = "gptpro-context-export-v1"
DESCRIPTOR_SCHEMA = "gptpro-install-descriptor-v1"
DESCRIPTOR_NAME = ".gptpro-components.json"
MAX_DESCRIPTOR_BYTES = 64 * 1024
IGNORED_TREE_NAMES = frozenset({".DS_Store", "__pycache__"})
IGNORED_TREE_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass
class HandshakeError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.code


def default_descriptor(skill_root: Path | None = None) -> Path:
    root = Path(skill_root) if skill_root is not None else Path(__file__).resolve().parents[2]
    return root.parent / DESCRIPTOR_NAME


def _require_absolute_file(path: Path, *, code: str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise HandshakeError(code, f"The selected {label} must be an absolute path.")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise HandshakeError(code, f"The selected {label} is unavailable.") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise HandshakeError(code, f"The selected {label} is not a regular file.")
    return candidate


def load_descriptor(path: Path) -> dict[str, Any]:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise HandshakeError(
            "GPTPRO_BASE_COMPONENT_REQUIRED",
            "The installer-provided gptpro component descriptor is unavailable.",
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > MAX_DESCRIPTOR_BYTES
    ):
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_UNSAFE",
            "The gptpro component descriptor is not an owner-only regular file.",
        )
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The gptpro component descriptor is invalid.",
        ) from exc
    if not isinstance(value, dict) or value.get("schema") != DESCRIPTOR_SCHEMA:
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The gptpro component descriptor contract is unsupported.",
        )
    if not isinstance(value.get("components"), dict):
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The gptpro component descriptor has no component map.",
        )
    return value


def descriptor_component(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    components = value.get("components")
    component = components.get(name) if isinstance(components, dict) else None
    if not isinstance(component, dict):
        raise HandshakeError(
            "GPTPRO_BASE_COMPONENT_REQUIRED" if name == "gptpro" else "GPTPRO_MCP_COMPONENT_REQUIRED",
            f"The descriptor does not select a {name} component.",
        )
    entrypoint = component.get("entrypoint")
    tree_sha256 = component.get("tree_sha256")
    if (
        not isinstance(entrypoint, str)
        or not Path(entrypoint).is_absolute()
        or not isinstance(tree_sha256, str)
        or len(tree_sha256) != 64
        or any(character not in "0123456789abcdef" for character in tree_sha256)
    ):
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            f"The descriptor binding for {name} is invalid.",
        )
    return dict(component)


def skill_root_for_entrypoint(entrypoint: Path) -> Path:
    candidate = _require_absolute_file(
        entrypoint,
        code="GPTPRO_BASE_COMPONENT_REQUIRED",
        label="component entrypoint",
    )
    if candidate.name != "gptpro.py" or candidate.parent.name != "scripts":
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The selected component entrypoint is outside the expected Skill layout.",
        )
    root = candidate.parent.parent
    if not (root / "SKILL.md").is_file():
        raise HandshakeError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The selected component root is not a Skill package.",
        )
    return root


def tree_hash(root: Path) -> str:
    package = Path(root)
    if not package.is_absolute() or not (package / "SKILL.md").is_file():
        raise HandshakeError(
            "GPTPRO_COMPONENT_TREE_INVALID", "The selected component tree is unavailable."
        )
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*"), key=lambda item: item.relative_to(package).as_posix()):
        relative_path = path.relative_to(package)
        relative = relative_path.as_posix()
        if path.is_symlink():
            raise HandshakeError(
                "GPTPRO_COMPONENT_TREE_INVALID",
                "Component trees may not contain symbolic links.",
            )
        if any(part in IGNORED_TREE_NAMES for part in relative_path.parts):
            continue
        if path.is_dir() or path.suffix in IGNORED_TREE_SUFFIXES:
            continue
        try:
            metadata = path.stat()
            content = path.read_bytes()
        except OSError as exc:
            raise HandshakeError(
                "GPTPRO_COMPONENT_TREE_INVALID",
                "The component tree changed while it was being hashed.",
            ) from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(metadata.st_mode)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def query_base(entrypoint: Path) -> dict[str, Any]:
    candidate = _require_absolute_file(
        entrypoint, code="GPTPRO_BASE_COMPONENT_REQUIRED", label="gptpro base entrypoint"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(candidate), "capabilities", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HandshakeError(
            "GPTPRO_BASE_HANDSHAKE_FAILED",
            "The selected gptpro base did not answer safely.",
        ) from exc
    if result.returncode != 0:
        raise HandshakeError(
            "GPTPRO_BASE_HANDSHAKE_FAILED",
            "The selected gptpro base rejected the handshake.",
        )
    try:
        value = json.loads(result.stdout)
    except (ValueError, RecursionError) as exc:
        raise HandshakeError(
            "GPTPRO_BASE_HANDSHAKE_FAILED",
            "The selected gptpro base returned invalid JSON.",
        ) from exc
    contracts = value.get("context_export_contracts") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("contract") != CAPABILITIES_CONTRACT
        or value.get("component") != "gptpro"
        or not isinstance(contracts, list)
        or CONTEXT_EXPORT_CONTRACT not in contracts
        or value.get("mcp_runtime") is not False
        or not isinstance(value.get("version"), str)
    ):
        raise HandshakeError(
            "GPTPRO_BASE_INCOMPATIBLE",
            "The selected gptpro base does not provide the required context contract.",
        )
    return value


def verify_base_component(
    *,
    skill_root: Path | None = None,
    descriptor_path: Path | None = None,
    base_entrypoint: Path | None = None,
) -> dict[str, Any]:
    """Resolve and verify one exact base; never search PATH, home, or checkouts."""

    descriptor: dict[str, Any] | None = None
    if base_entrypoint is not None:
        entrypoint = Path(base_entrypoint)
        if not entrypoint.is_absolute():
            raise HandshakeError(
                "GPTPRO_BASE_COMPONENT_REQUIRED",
                "An explicitly injected base entrypoint must be absolute.",
            )
        source = "explicit"
        expected_tree = None
    else:
        selected_descriptor = (
            Path(descriptor_path)
            if descriptor_path is not None
            else default_descriptor(skill_root)
        )
        descriptor = load_descriptor(selected_descriptor)
        component = descriptor_component(descriptor, "gptpro")
        entrypoint = Path(component["entrypoint"])
        expected_tree = component["tree_sha256"]
        source = "installer-descriptor"
    base = query_base(entrypoint)
    root = skill_root_for_entrypoint(entrypoint)
    observed_tree = tree_hash(root)
    if expected_tree is not None and observed_tree != expected_tree:
        raise HandshakeError(
            "GPTPRO_BASE_COMPONENT_CHANGED",
            "The selected gptpro base tree differs from the installer descriptor.",
        )
    return {
        "selection_source": source,
        "base_entrypoint": str(entrypoint),
        "base_root": str(root),
        "base_version": base["version"],
        "base_tree_sha256": observed_tree,
        "context_contract": CONTEXT_EXPORT_CONTRACT,
        "descriptor": descriptor,
    }
