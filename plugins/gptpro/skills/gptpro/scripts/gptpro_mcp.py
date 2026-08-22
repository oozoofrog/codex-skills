#!/usr/bin/env python3
"""Run the dependency-free gptpro read-only MCP stdio server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.server import main as serve  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Serve the gptpro read-only MCP protocol on stdin/stdout. "
            "This Phase-2 entrypoint defaults to deny-all until the governance "
            "layer injects one active approved package."
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


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
