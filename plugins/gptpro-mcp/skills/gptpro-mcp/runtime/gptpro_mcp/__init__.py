"""Read-only MCP runtime contracts for Desktop gptpro."""

from .schema import (
    DEFAULT_LIMITS,
    HARD_LIMITS,
    PROTOCOL_PROFILE,
    SERVER_INSTRUCTIONS,
    TOOL_CATALOG,
    TOOL_NAMES,
    tool_schema_sha256,
    validate_limits,
)

__all__ = [
    "DEFAULT_LIMITS",
    "HARD_LIMITS",
    "PROTOCOL_PROFILE",
    "SERVER_INSTRUCTIONS",
    "TOOL_CATALOG",
    "TOOL_NAMES",
    "tool_schema_sha256",
    "validate_limits",
]
