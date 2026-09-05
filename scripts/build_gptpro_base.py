#!/usr/bin/env python3
"""Validate the reviewed gptpro v0.6 isolated Electron Runner boundary."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "gptpro" / "scripts" / "gptpro.py"

REQUIRED = (
    '"component": "gptpro"',
    '"mcp_runtime": False',
    '"delivery_channels": ["desktop-electron"]',
    '"context_transports": [CONTEXT_TRANSPORT]',
    '"local_functions": False',
    '"server_tool_fallback": False',
    '"browser_delivery": False',
    '"secure_mcp_tunnel": False',
    '"electron_private_api": True',
    "runtime.gptpro_runtime",
)
FORBIDDEN = (
    "runtime.gptpro_mcp",
    "runtime.gptpro_browser",
    "command_browser_plan",
    "command_response_monitor_plan",
    "electronBridge",
    "GPTPRO_MCP_COMPONENT_REQUIRED",
    "ToolRuntime",
)


def validate() -> list[str]:
    if not TARGET.is_file():
        return ["Electron base entrypoint is missing"]
    source = TARGET.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        ast.parse(source)
    except SyntaxError as exc:
        errors.append(f"Base entrypoint is not valid Python: {exc}")
        return errors
    for token in REQUIRED:
        if token not in source:
            errors.append(f"Required Desktop boundary is missing: {token}")
    for token in FORBIDDEN:
        if token in source:
            errors.append(f"Forbidden runtime or delivery path remains: {token}")
    node_entrypoint = ROOT / "gptpro" / "scripts" / "chatgpt-desktop.js"
    private_bridge = ROOT / "gptpro" / "runtime" / "chatgpt-desktop" / "private-bridge.js"
    if not node_entrypoint.is_file() or not private_bridge.is_file():
        errors.append("The clean-room private Desktop runtime is incomplete")
    elif "electronBridge" not in private_bridge.read_text(encoding="utf-8"):
        errors.append("The private Electron contract is not isolated in private-bridge.js")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate without writing; retained for the established repository command",
    )
    parser.parse_args(argv)
    errors = validate()
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
