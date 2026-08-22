#!/usr/bin/env python3
"""Run the dependency-free gptpro read-only MCP stdio server."""

from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

_INHERITED_SECRET_ENV = (
    "CONTROL_PLANE_API_KEY",
    "OPENAI_API_KEY",
    "CLOUDFLARED_TUNNEL_TOKEN",
    "CONTROL_PLANE_CLIENT_KEY",
    "CONTROL_PLANE_EXTRA_HEADERS",
    "MCP_CLIENT_KEY",
    "MCP_EXTRA_HEADERS",
    "MCP_DISCOVERY_EXTRA_HEADERS",
)
_SESSION_CAPABILITY_ENV = "GPTPRO_MCP_SESSION_CAPABILITY"
_RUNTIME_DIRECTORY_ENV = "GPTPRO_MCP_RUNTIME_DIR"


class RuntimeBootstrapError(Exception):
    """Sanitized bootstrap failure for the stdio entrypoint."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Serve the gptpro read-only MCP protocol on stdin/stdout. "
            "It defaults to deny-all unless the foreground governance controller "
            "injects one exact active package capability."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve",),
        default="serve",
        help="serve newline-delimited JSON-RPC on stdio (default)",
    )
    return parser


def _runtime_from_environment() -> tuple[Any, Any | None, type[Any]]:
    # Consume the only permitted capability values and remove inherited Tunnel
    # credentials before importing any bundled runtime module. This keeps
    # import-time code outside the control-plane secret boundary.
    capability_text = os.environ.pop(_SESSION_CAPABILITY_ENV, "")
    runtime_text = os.environ.pop(_RUNTIME_DIRECTORY_ENV, "")
    for name in _INHERITED_SECRET_ENV:
        os.environ.pop(name, None)
    try:
        from runtime.gptpro_mcp.authorization import DenyAllAuthorizationProvider
        from runtime.gptpro_mcp.live import (
            RUNTIME_DIRECTORY_ENV,
            SESSION_CAPABILITY_ENV,
            ActiveRuntimeContext,
            RuntimeServerLease,
            decode_session_capability,
        )
        from runtime.gptpro_mcp.protocol import LegacyMcpServer
        from runtime.gptpro_mcp.runtime_state import RuntimeStateError, RuntimeStateStore
        from runtime.gptpro_mcp.tools import ToolRuntime
    except ImportError as exc:
        raise RuntimeBootstrapError("The bundled runtime could not be imported.") from exc

    try:
        if (
            SESSION_CAPABILITY_ENV != _SESSION_CAPABILITY_ENV
            or RUNTIME_DIRECTORY_ENV != _RUNTIME_DIRECTORY_ENV
        ):
            raise RuntimeBootstrapError("The bundled capability contract is inconsistent.")
        if not capability_text and not runtime_text:
            return ToolRuntime(DenyAllAuthorizationProvider()), None, LegacyMcpServer
        if not capability_text or not runtime_text:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The foreground MCP capability environment is incomplete."
            )
        capability = decode_session_capability(capability_text)
        runtime_root = Path(runtime_text).expanduser()
        if not runtime_root.is_absolute():
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The foreground MCP runtime directory is invalid."
            )
        store = RuntimeStateStore(root=runtime_root)
        state = store.read()
        import gptpro as governance

        session_hash = governance.sha256_bytes(capability)
        if (
            state is None
            or state.get("status") not in {"activating", "active"}
            or state.get("session_id_sha256") != session_hash
        ):
            raise RuntimeStateError(
                "SESSION_CONFLICT", "The foreground MCP capability does not match the live session."
            )

        def validate_binding(
            verified: dict[str, object], runtime_state: dict[str, object], expected_session: str
        ) -> None:
            governance.assert_mcp_runtime_binding(
                verified,
                runtime_state,
                session_id_sha256=expected_session,
                expected_statuses={"active"},
                require_unexpired=True,
            )

        context = ActiveRuntimeContext(
            runtime_store=store,
            session_capability=capability,
            package_loader=functools.partial(
                governance.verify_package, recover_lifecycle=False
            ),
            binding_validator=validate_binding,
            audit_factory=lambda verified, expected_session: governance.audit_log_for(
                verified,
                expected_session,
                runtime_store=store,
            ),
        )
        lease = RuntimeServerLease(store, session_hash).acquire()
        return ToolRuntime(context, committer=context), lease, LegacyMcpServer
    except RuntimeBootstrapError:
        raise
    except (ImportError, RuntimeStateError, ValueError) as exc:
        raise RuntimeBootstrapError("The active authorization could not be bootstrapped.") from exc


def serve() -> int:
    try:
        runtime, lease, server_class = _runtime_from_environment()
    except RuntimeBootstrapError:
        print("RUNTIME_BOOTSTRAP_FAILED: active authorization is unavailable", file=sys.stderr)
        return 2
    try:
        return server_class(runtime).serve(sys.stdin, sys.stdout, sys.stderr)
    finally:
        if lease is not None:
            lease.close()


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
