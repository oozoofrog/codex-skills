#!/usr/bin/env python3
"""Desktop-only ChatGPT Pro orchestrator with an exact read-only MCP companion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
DESCRIPTOR_NAME = ".gptpro-components.json"
DESCRIPTOR_SCHEMA = "gptpro-install-descriptor-v1"
CAPABILITIES_CONTRACT = "gptpro-component-capabilities-v1"
CONTEXT_EXPORT_CONTRACT = "gptpro-context-export-v1"
BASE_VERSION = "0.3.0"
MAX_DESCRIPTOR_BYTES = 64 * 1024


@dataclass
class OrchestratorError(Exception):
    code: str
    message: str
    recovery: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_descriptor(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_REQUIRED",
            "The installer-selected gptpro-mcp component is unavailable.",
            "Run scripts/manage_skills.py install gptpro --update, then retry.",
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > MAX_DESCRIPTOR_BYTES
    ):
        raise OrchestratorError(
            "GPTPRO_COMPONENT_DESCRIPTOR_UNSAFE",
            "The component descriptor is not an owner-only regular file.",
            "Reinstall gptpro and gptpro-mcp atomically with the repository installer.",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise OrchestratorError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The component descriptor is invalid.",
            "Reinstall both gptpro components before retrying.",
        ) from exc
    components = value.get("components") if isinstance(value, dict) else None
    if not isinstance(value, dict) or value.get("schema") != DESCRIPTOR_SCHEMA or not isinstance(components, dict):
        raise OrchestratorError(
            "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
            "The component descriptor contract is unsupported.",
            "Update and reinstall gptpro and gptpro-mcp together.",
        )
    return value


def _component_entrypoint(
    *, descriptor_path: Path, explicit_entrypoint: Path | None
) -> tuple[Path, str | None]:
    if explicit_entrypoint is not None:
        entrypoint = explicit_entrypoint
        expected_tree = None
    else:
        descriptor = _load_descriptor(descriptor_path)
        component = descriptor["components"].get("gptpro-mcp")
        if not isinstance(component, dict):
            raise OrchestratorError(
                "GPTPRO_MCP_COMPONENT_REQUIRED",
                "The descriptor does not select a gptpro-mcp component.",
                "Install gptpro with the default companion component.",
            )
        entrypoint_value = component.get("entrypoint")
        expected_tree = component.get("tree_sha256")
        if not isinstance(entrypoint_value, str) or not Path(entrypoint_value).is_absolute():
            raise OrchestratorError(
                "GPTPRO_COMPONENT_DESCRIPTOR_INVALID",
                "The gptpro-mcp entrypoint binding is invalid.",
                "Reinstall both components atomically.",
            )
        entrypoint = Path(entrypoint_value)
    if (
        not entrypoint.is_absolute()
        or entrypoint.name != "gptpro.py"
        or entrypoint.parent.name != "scripts"
    ):
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_INVALID",
            "The selected gptpro-mcp entrypoint is outside the expected Skill layout.",
            "Use the installer-selected component rather than PATH or an arbitrary checkout.",
        )
    try:
        metadata = entrypoint.stat()
    except OSError as exc:
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_REQUIRED",
            "The selected gptpro-mcp entrypoint is unavailable.",
            "Install or repair the gptpro-mcp companion.",
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or not (entrypoint.parent.parent / "SKILL.md").is_file():
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_INVALID",
            "The selected gptpro-mcp component is incomplete.",
            "Reinstall both components atomically.",
        )
    return entrypoint, expected_tree if isinstance(expected_tree, str) else None


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise OrchestratorError(
                "GPTPRO_MCP_COMPONENT_CHANGED",
                "The selected component tree contains a symbolic link.",
                "Reinstall the component before retrying.",
            )
        if path.is_dir() or "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(path.stat().st_mode)).encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _verify_component(entrypoint: Path, expected_tree: str | None) -> None:
    root = entrypoint.parent.parent
    observed = _tree_hash(root)
    if expected_tree is not None and observed != expected_tree:
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_CHANGED",
            "The installed gptpro-mcp tree differs from its descriptor.",
            "Reinstall gptpro and gptpro-mcp before using repository disclosure.",
        )
    result = subprocess.run(
        [sys.executable, str(entrypoint), "capabilities", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
    )
    try:
        value = json.loads(result.stdout) if result.returncode == 0 else None
    except (ValueError, RecursionError):
        value = None
    if (
        not isinstance(value, dict)
        or value.get("contract") != CAPABILITIES_CONTRACT
        or value.get("component") != "gptpro-mcp"
        or value.get("mcp_runtime") is not True
        or "desktop-ui" not in value.get("delivery_channels", [])
    ):
        raise OrchestratorError(
            "GPTPRO_MCP_COMPONENT_INCOMPATIBLE",
            "The selected companion does not provide the Desktop read-only contract.",
            "Update and reinstall the matching gptpro components.",
        )


def _capabilities() -> int:
    print(
        json.dumps(
            {
                "contract": CAPABILITIES_CONTRACT,
                "component": "gptpro",
                "version": BASE_VERSION,
                "features": [
                    "desktop-ui-orchestration-v1",
                    "read-only-mcp-companion",
                    "machine-global-standing-approval-v2",
                    "legacy-receipt-offline-verification",
                ],
                "context_export_contracts": [CONTEXT_EXPORT_CONTRACT],
                "delivery_channels": ["desktop-ui"],
                "mcp_runtime": False,
                "browser_delivery": False,
                "cdp": False,
                "electron_private_api": False,
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def _help() -> int:
    print(
        """usage: gptpro.py [global options] <command> [command options]

Desktop-only ChatGPT Pro collaboration through visible app UI and a read-only MCP companion.

Primary commands:
  desktop-doctor       Inspect macOS, ChatGPT app, Computer Use, and companion readiness
  consult              Prepare one bounded Schema-4 repository consultation
  desktop-plan         Emit the approved visible Desktop handoff contract
  collect              Validate one Desktop submission or response observation
  standing-approval-*  Manage the machine-global bounded approval
  status / verify      Inspect package and receipt evidence

Advanced MCP lifecycle and diagnostics are delegated to the exact installed gptpro-mcp component.
Browser delivery, CDP, remote debugging, and Electron-private APIs are not supported.
"""
    )
    return 0


def _error_format(argv: list[str]) -> str:
    for index, item in enumerate(argv):
        if item == "--error-format" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--error-format="):
            return item.split("=", 1)[1]
    return "text"


def _strip_base_options(argv: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in {"--component-descriptor", "--mcp-entrypoint"}:
            index += 2
            continue
        if item.startswith("--component-descriptor=") or item.startswith("--mcp-entrypoint="):
            index += 1
            continue
        result.append(item)
        index += 1
    return result


def _emit_error(exc: OrchestratorError, *, operation: str, json_mode: bool) -> int:
    if json_mode:
        print(
            json.dumps(
                {
                    "ok": False,
                    "operation": operation,
                    "exit_code": 2,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "automatic_retry_allowed": False,
                        "recovery": exc.recovery,
                        "sanitized": True,
                    },
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    else:
        print(f"Error: {exc}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw == ["--help"] or raw == ["-h"]:
        return _help()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--component-descriptor")
    parser.add_argument("--mcp-entrypoint")
    parser.add_argument("--error-format", choices=("text", "json"), default="text")
    known, remainder = parser.parse_known_args(raw)
    operation = next((item for item in remainder if not item.startswith("-")), "unknown")
    if operation == "capabilities":
        return _capabilities()
    if operation in {"browser-plan", "policy-create", "policy-list", "policy-revoke"}:
        return _emit_error(
            OrchestratorError(
                "GPTPRO_BROWSER_REMOVED",
                "Browser delivery was removed; use the ChatGPT Desktop workflow.",
                "Run desktop-doctor, then consult with the read-only MCP companion.",
            ),
            operation=operation,
            json_mode=_error_format(raw) == "json",
        )
    descriptor = (
        Path(known.component_descriptor).expanduser().resolve()
        if known.component_descriptor
        else SKILL_ROOT.parent / DESCRIPTOR_NAME
    )
    explicit = (
        Path(known.mcp_entrypoint).expanduser().resolve()
        if known.mcp_entrypoint
        else None
    )
    try:
        entrypoint, expected_tree = _component_entrypoint(
            descriptor_path=descriptor, explicit_entrypoint=explicit
        )
        _verify_component(entrypoint, expected_tree)
    except (OrchestratorError, OSError, subprocess.SubprocessError) as exc:
        normalized = (
            exc
            if isinstance(exc, OrchestratorError)
            else OrchestratorError(
                "GPTPRO_MCP_COMPONENT_UNAVAILABLE",
                "The companion could not be verified safely.",
                "Reinstall both gptpro components and retry.",
            )
        )
        return _emit_error(
            normalized,
            operation=operation,
            json_mode=_error_format(raw) == "json",
        )
    command = [
        sys.executable,
        str(entrypoint),
        "--base-entrypoint",
        str(Path(__file__).resolve()),
        *_strip_base_options(raw),
    ]
    try:
        completed = subprocess.run(command, check=False)
    except OSError:
        return _emit_error(
            OrchestratorError(
                "GPTPRO_MCP_COMPONENT_UNAVAILABLE",
                "The verified companion could not be started.",
                "Inspect the local installation and retry without changing disclosure scope.",
            ),
            operation=operation,
            json_mode=_error_format(raw) == "json",
        )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
