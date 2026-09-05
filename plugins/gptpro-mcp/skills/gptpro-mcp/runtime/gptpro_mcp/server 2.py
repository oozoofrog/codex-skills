"""Safe stdio entrypoint for the Phase-2 MCP core.

The standalone entrypoint intentionally has no active authorization.  Phase 3
will inject a provider after validating user-global session state.
"""

from __future__ import annotations

import sys

from .authorization import DenyAllAuthorizationProvider
from .protocol import LegacyMcpServer
from .tools import ToolRuntime


def main() -> int:
    server = LegacyMcpServer(ToolRuntime(DenyAllAuthorizationProvider()))
    return server.serve(sys.stdin, sys.stdout, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
