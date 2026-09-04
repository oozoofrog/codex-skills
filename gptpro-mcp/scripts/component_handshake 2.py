#!/usr/bin/env python3
"""Verify the installer-selected gptpro base component without path discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.component_compat import (  # noqa: E402
    CONTEXT_EXPORT_CONTRACT,
    HandshakeError,
    verify_base_component,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor")
    parser.add_argument("--base-entrypoint", help="Explicit development/test entrypoint")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_base_component(
            skill_root=SKILL_ROOT,
            descriptor_path=Path(args.descriptor) if args.descriptor else None,
            base_entrypoint=Path(args.base_entrypoint) if args.base_entrypoint else None,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "operation": "component-handshake",
                    "selection_source": result["selection_source"],
                    "base_entrypoint": result["base_entrypoint"],
                    "base_version": result["base_version"],
                    "base_tree_sha256": result["base_tree_sha256"],
                    "context_contract": CONTEXT_EXPORT_CONTRACT,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    except HandshakeError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "operation": "component-handshake",
                    "error": {"code": exc.code, "message": exc.message, "sanitized": True},
                },
                sort_keys=True,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
